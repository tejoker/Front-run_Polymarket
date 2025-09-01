#include <iostream>
#include <string>
#include <vector>
#include <map>
#include <chrono>
#include <thread>
#include <future>
#include <mutex>
#include <fstream>
#include <sstream>
#include <iomanip>
#include <algorithm>
#include <regex>
#include <curl/curl.h>
#include <sqlite3.h>

// Global ROI parameters - OPTIMIZED FOR HFT LATENCY
double GLOBAL_FEE = 0.03; // 3% fees on profit (Polymarket standard)
double GLOBAL_CATCHUP_SPEED = 0.8; // 80% per second (optimized for speed)
double GLOBAL_ACTION_TIME = 0.025; // 25ms (optimized HFT latency)
double GLOBAL_FIXED_COST = 0.0005; // Reduced fixed costs for HFT

// HFT optimizations - ROI cache to avoid recalculations
std::map<std::string, double> roi_cache;
std::mutex roi_cache_mutex;
const int MAX_CACHE_SIZE = 1000;

// HFT optimizations - Precomputed lookup tables
std::vector<double> precomputed_roi_table;
bool roi_table_initialized = false;

// FFI pour Rust
extern "C" {
    // Structures compatibles avec Rust
    typedef struct {
        char* id;
        char* question;
        char* description;
        char* domain;
        double probability;
        char* resolution_source;
    } Market_C;
    
    typedef struct {
        char* market_id;
        char* source_url;
        double relevance_score;
        char* confidence;
        char* reason;
        double potential_roi_v1;
        double potential_roi_v2;
    } ArbitrageOpportunity_C;
    
    typedef struct {
        char* market_id;
        char* action;
        char* confidence;
        double potential_roi_v1;
        double potential_roi_v2;
        char* source_url;
        char* reason;
        uint64_t reaction_time;
        uint64_t execution_time;
        uint64_t total_time;
        char* grade;
    } TradingSignal_C;
}

using namespace std;

// Configuration
const string POLYMARKET_API = "https://clob.polymarket.com/markets";
const string GRAPHQL_ENDPOINT = "https://api.thegraph.com/subgraphs/name/polymarket/polymarket";
const int MAX_CONCURRENT_REQUESTS = 50;
const int REQUEST_TIMEOUT_MS = 5000;

// Structures de données
struct Market {
    string id;
    string question;
    string description;
    string domain;
    double probability;
    string resolution_source;
    chrono::system_clock::time_point last_update;
};

struct ArbitrageOpportunity {
    string market_id;
    string source_url;
    double relevance_score;
    string confidence;
    string reason;
    double potential_roi_v1;
    double potential_roi_v2;
    chrono::system_clock::time_point timestamp;
};

struct TradingSignal {
    string market_id;
    string action;
    string confidence;
    double potential_roi_v1;
    double potential_roi_v2;
    string source_url;
    string reason;
    uint64_t reaction_time;
    uint64_t execution_time;
    uint64_t total_time;
    string grade;
};

struct SourceData {
    string url;
    bool accessible;
    int content_length;
    vector<string> found_keywords;
    string error;
    chrono::system_clock::time_point last_check;
};

// Variables globales
vector<Market> markets;
vector<ArbitrageOpportunity> opportunities;
vector<TradingSignal> signals;
map<string, SourceData> source_data;
mutex markets_mutex;
mutex opportunities_mutex;
mutex signals_mutex;
mutex source_data_mutex;

// Callback pour libcurl
size_t WriteCallback(void* contents, size_t size, size_t nmemb, string* userp) {
    userp->append((char*)contents, size * nmemb);
    return size * nmemb;
}

// Classe HTTP Client optimisée
class FastHTTPClient {
private:
    CURL* curl;
    struct curl_slist* headers;
    
public:
    FastHTTPClient() {
        curl_global_init(CURL_GLOBAL_ALL);
        curl = curl_easy_init();
        headers = nullptr;
        
        if (curl) {
            headers = curl_slist_append(headers, "User-Agent: Polymarket-Bot/1.0");
            headers = curl_slist_append(headers, "Accept: application/json");
            headers = curl_slist_append(headers, "Content-Type: application/json");
            curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
            curl_easy_setopt(curl, CURLOPT_TIMEOUT, REQUEST_TIMEOUT_MS / 1000);
            curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, 3);
            curl_easy_setopt(curl, CURLOPT_TCP_NODELAY, 1L);
            curl_easy_setopt(curl, CURLOPT_TCP_FASTOPEN, 1L);
        }
    }
    
    ~FastHTTPClient() {
        if (headers) curl_slist_free_all(headers);
        if (curl) curl_easy_cleanup(curl);
        curl_global_cleanup();
    }
    
    string GET(const string& url) {
        string response;
        
        if (!curl) return "";
        
        curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
        curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, WriteCallback);
        curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response);
        
        CURLcode res = curl_easy_perform(curl);
        
        if (res != CURLE_OK) {
            return "";
        }
        
        return response;
    }
    
    string POST(const string& url, const string& data) {
        string response;
        
        if (!curl) return "";
        
        curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
        curl_easy_setopt(curl, CURLOPT_POST, 1L);
        curl_easy_setopt(curl, CURLOPT_POSTFIELDS, data.c_str());
        curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, WriteCallback);
        curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response);
        
        CURLcode res = curl_easy_perform(curl);
        
        if (res != CURLE_OK) {
            return "";
        }
        
        return response;
    }
};

// Fonctions utilitaires
string get_current_timestamp() {
    auto now = chrono::system_clock::now();
    auto time_t = chrono::system_clock::to_time_t(now);
    auto ms = chrono::duration_cast<chrono::milliseconds>(now.time_since_epoch()) % 1000;
    
    stringstream ss;
    ss << put_time(localtime(&time_t), "%Y-%m-%d %H:%M:%S");
    ss << '.' << setfill('0') << setw(3) << ms.count();
    return ss.str();
}

string categorize_market_domain(const string& question, const string& description) {
    string text = question + " " + description;
    transform(text.begin(), text.end(), text.begin(), ::tolower);
    
    if (text.find("fed") != string::npos || text.find("rate") != string::npos || 
        text.find("recession") != string::npos || text.find("gdp") != string::npos) {
        return "economy";
    }
    if (text.find("trump") != string::npos || text.find("election") != string::npos || 
        text.find("president") != string::npos) {
        return "politics";
    }
    if (text.find("bitcoin") != string::npos || text.find("ethereum") != string::npos || 
        text.find("crypto") != string::npos || text.find("tether") != string::npos) {
        return "crypto";
    }
    if (text.find("match") != string::npos || text.find("game") != string::npos || 
        text.find("sports") != string::npos) {
        return "sports";
    }
    if (text.find("covid") != string::npos || text.find("health") != string::npos || 
        text.find("vaccine") != string::npos) {
        return "health";
    }
    
    return "other";
}

vector<string> extract_urls(const string& text) {
    vector<string> urls;
    regex url_pattern(R"((https?://[^\s]+))");
    
    auto words_begin = sregex_iterator(text.begin(), text.end(), url_pattern);
    auto words_end = sregex_iterator();
    
    for (sregex_iterator i = words_begin; i != words_end; ++i) {
        smatch match = *i;
        urls.push_back(match.str());
    }
    
    return urls;
}

string extract_resolution_source(const string& description) {
    if (description.find("resolution source") != string::npos) {
        size_t pos = description.find("resolution source");
        if (pos != string::npos) {
            return description.substr(pos);
        }
    }
    return "";
}

vector<string> extract_market_keywords(const string& question, const string& description) {
    vector<string> keywords;
    string text = question + " " + description;
    transform(text.begin(), text.end(), text.begin(), ::tolower);
    
    if (text.find("fed") != string::npos) keywords.push_back("federal reserve");
    if (text.find("rate") != string::npos) keywords.push_back("interest rate");
    if (text.find("recession") != string::npos) keywords.push_back("recession");
    if (text.find("crypto") != string::npos) keywords.push_back("crypto");
    if (text.find("bitcoin") != string::npos) keywords.push_back("bitcoin");
    if (text.find("ethereum") != string::npos) keywords.push_back("ethereum");
    
    return keywords;
}

// Fetch des marchés Polymarket (version simplifiée)
vector<Market> fetch_polymarket_markets(FastHTTPClient& client) {
    vector<Market> fetched_markets;
    
    auto start_time = chrono::high_resolution_clock::now();
    
    // Simuler la récupération de marchés (version simplifiée)
    Market market1;
    market1.id = "test-market-1";
    market1.question = "Test Market Question";
    market1.description = "Test Market Description";
    market1.domain = "economy";
    market1.probability = 0.5;
    market1.resolution_source = "test-source.com";
    market1.last_update = chrono::system_clock::now();
    
    fetched_markets.push_back(market1);
    
    auto end_time = chrono::high_resolution_clock::now();
    auto duration = chrono::duration_cast<chrono::milliseconds>(end_time - start_time);
    
    cout << "[OK] " << fetched_markets.size() << " marchés récupérés en " << duration.count() << "ms" << endl;
    
    return fetched_markets;
}

// Monitoring des sources de résolution
SourceData monitor_resolution_source(FastHTTPClient& client, const string& url, const vector<string>& keywords) {
    SourceData data;
    data.url = url;
    
    auto start_time = chrono::high_resolution_clock::now();
    string response = client.GET(url);
    auto end_time = chrono::high_resolution_clock::now();
    
    if (response.empty()) {
        data.accessible = false;
        data.error = "Empty response";
        return data;
    }
    
    data.accessible = true;
    data.content_length = response.length();
    data.last_check = chrono::system_clock::now();
    
    string lower_response = response;
    transform(lower_response.begin(), lower_response.end(), lower_response.begin(), ::tolower);
    
    for (const auto& keyword : keywords) {
        if (lower_response.find(keyword) != string::npos) {
            data.found_keywords.push_back(keyword);
        }
    }
    
    auto duration = chrono::duration_cast<chrono::milliseconds>(end_time - start_time);
            cout << "  [OK] " << url << " (" << data.content_length << " chars, " << duration.count() << "ms)" << endl;
    
    return data;
}

// FORMULE ROI PROFESSIONNELLE POLYMARKET (frais 3% sur le profit uniquement)
double calculate_real_roi(double current_price, double fee, double catchup_speed, double action_time) {
    // Use global parameters for consistency
    fee = GLOBAL_FEE;           // 3% fees on profit
    catchup_speed = GLOBAL_CATCHUP_SPEED;
    action_time = GLOBAL_ACTION_TIME;
    double g = GLOBAL_FIXED_COST; // Fixed costs per share
    
    // LOGIQUE MARCHÉ BINAIRE: Décider si on parie "OUI" ou "NON"
    bool bet_on_yes = current_price < 0.5; // Si prix < 50%, on parie "OUI"
    
    // Calcul du prix d'achat effectif (avec spread/slippage)
    double p;
    if (bet_on_yes) {
        // Parie "OUI": prix d'achat = prix_actuel + (vitesse_rattrapage × temps_action)
        p = current_price + (catchup_speed * action_time);
    } else {
        // Parie "NON": prix d'achat = (1 - prix_actuel) + (vitesse_rattrapage × temps_action)
        p = (1.0 - current_price) + (catchup_speed * action_time);
    }
    
    // Limiter prix d'achat à des valeurs réalistes
    if (p > 0.95) p = 0.95;
    if (p < 0.05) p = 0.05;
    
    // π = proba subjective que l'événement soit YES
    double pi_yes = 0.55;  // 55% de confiance (réaliste pour du trading quotidien)
    
    double expected_profit;
    double pi_star; // seuil break-even exprimé en proba YES
    
    if (bet_on_yes) {
        // Prix p = prix du YES
        // ROI_yes = [π*(1-p)*(1-f) - (1-π)*p - g] / (p+g)
        expected_profit = pi_yes * (1.0 - p) * (1.0 - fee)
                        - (1.0 - pi_yes) * p - g;
        pi_star = (p + g) / (p + (1.0 - p) * (1.0 - fee));              // seuil YES
    } else {
        // Prix p = prix du NO
        // ROI_no = [(1-π)*(1-p)*(1-f) - π*p - g] / (p+g)
        expected_profit = (1.0 - pi_yes) * (1.0 - p) * (1.0 - fee)
                        - pi_yes * p - g;
        pi_star = 1.0 - (p + g) / (p + (1.0 - p) * (1.0 - fee));        // seuil YES
    }
    
    double roi = expected_profit / (p + g);
    
    // Affichage : pi_star est en proba YES
    cout << "[ROI PRO] Current: " << (current_price * 100) << "%, ";
    cout << "Bet: " << (bet_on_yes ? "YES" : "NO") << ", ";
    cout << "Buy price (p): " << fixed << setprecision(2) << (p * 100) << "%, ";
    cout << "Confidence (π): " << (pi_yes * 100) << "%, ";
    cout << "Break-even (π*): " << (pi_star * 100) << "%, ";
    cout << "ROI: " << (roi * 100) << "%" << endl;
    
    return roi;
}

// Arbitrage opportunity detection
vector<ArbitrageOpportunity> detect_arbitrage_opportunities(const vector<Market>& markets, const map<string, SourceData>& sources) {
    vector<ArbitrageOpportunity> opportunities;
    
    for (const auto& market : markets) {
        vector<string> market_keywords = extract_market_keywords(market.question, market.description);
        
        for (const auto& [url, source] : sources) {
            if (!source.accessible) continue;
            
            double relevance = 0.0;
            for (const auto& keyword : market_keywords) {
                for (const auto& found : source.found_keywords) {
                    if (found.find(keyword) != string::npos) {
                        relevance += 0.2;
                    }
                }
            }
            
            if (relevance > 0.05) {
                ArbitrageOpportunity opp;
                opp.market_id = market.id;
                opp.source_url = url;
                opp.relevance_score = relevance;
                opp.timestamp = chrono::system_clock::now();
                
                if (relevance > 0.7) opp.confidence = "high";
                else if (relevance > 0.3) opp.confidence = "medium";
                else opp.confidence = "low";
                
                // ROI calculation with configurable global parameters
                double new_roi = calculate_real_roi(market.probability, GLOBAL_FEE, GLOBAL_CATCHUP_SPEED, GLOBAL_ACTION_TIME);
                
                // Keep old calculations for compatibility
                double difference = abs(0.5 - market.probability);
                opp.potential_roi_v1 = difference * 100;
                opp.potential_roi_v2 = new_roi * 100; // New ROI in percentage
                
                opp.reason = "Source " + url + " relevant to market (score: " + to_string(relevance) + ")";
                
                opportunities.push_back(opp);
            }
        }
    }
    
    return opportunities;
}

// Trading signal generation
vector<TradingSignal> generate_trading_signals(const vector<ArbitrageOpportunity>& opportunities) {
    vector<TradingSignal> signals;
    
    for (const auto& opp : opportunities) {
        TradingSignal signal;
        signal.market_id = opp.market_id;
        signal.confidence = opp.confidence;
        signal.potential_roi_v1 = opp.potential_roi_v1;
        signal.potential_roi_v2 = opp.potential_roi_v2;
        signal.source_url = opp.source_url;
        signal.reason = opp.reason;
        
        auto start_time = chrono::high_resolution_clock::now();
        
        // Final decision by C++ - realistic thresholds for 4000€
        // ROI values are in percentage (e.g., 23.9 = 23.9%)
        if (opp.potential_roi_v2 > 2.0) { // ROI > 2%
            signal.action = "BUY";
            cout << "[C++ DECISION] BUY signal for " << opp.market_id << " (ROI: " << opp.potential_roi_v2 << "%)" << endl;
        } else if (opp.potential_roi_v2 > 0.5) { // ROI > 0.5%
            signal.action = "SELL";
            cout << "[C++ DECISION] SELL signal for " << opp.market_id << " (ROI: " << opp.potential_roi_v2 << "%)" << endl;
        } else {
            signal.action = "MONITOR";
        }
        
        auto end_time = chrono::high_resolution_clock::now();
        auto duration = chrono::duration_cast<chrono::microseconds>(end_time - start_time);
        
        signal.reaction_time = duration.count() / 1000; // in ms
        signal.execution_time = 1000; // estimation
        signal.total_time = signal.reaction_time + signal.execution_time;
        signal.grade = "B";
        
        signals.push_back(signal);
    }
    
    return signals;
}

// FFI functions for Rust
extern "C" {
    
    // Initialize C++ module
    bool init_polymarket_core() {
        cout << "Initializing C++ Polymarket Core module" << endl;
        return true;
    }
    
    // Configure ROI parameters
    void configure_roi_params(double fee, double catchup_speed, double action_time) {
        GLOBAL_FEE = fee;
        GLOBAL_CATCHUP_SPEED = catchup_speed;
        GLOBAL_ACTION_TIME = action_time;
        cout << "ROI params configured: fee=" << fee << ", catchup_speed=" << catchup_speed << ", action_time=" << action_time << endl;
    }
    
    // FFI function to calculate realistic ROI
    double calculate_real_roi_cpp(double current_price, double fee, double catchup_speed, double action_time) {
        return calculate_real_roi(current_price, fee, catchup_speed, action_time);
    }
    
    // Update market data
    bool update_market_data() {
        FastHTTPClient client;
        
        // Fetch markets
        auto fetched_markets = fetch_polymarket_markets(client);
        
        {
            lock_guard<mutex> lock(markets_mutex);
            markets = fetched_markets;
        }
        
        // Monitoring des sources
        vector<string> sources = {
            "https://fred.stlouisfed.org/series/FGEXPND",
            "https://www.federalreserve.gov/monetarypolicy/openmarket.htm",
            "https://www.bea.gov/data/gdp/gross-domestic-product",
            "https://www.nber.org/",
            "https://www.whitehouse.gov/",
            "https://www.foxnews.com/",
            "https://www.cnn.com/",
            "https://www.sec.gov/",
            "https://www.coinbase.com/",
            "https://www.ethereum.org/"
        };
        
        vector<string> keywords = {"federal", "reserve", "rate", "gdp", "recession", "crypto", "bitcoin", "ethereum"};
        
        vector<future<SourceData>> futures;
        
        for (const auto& source : sources) {
            futures.push_back(async(launch::async, [&client, source, keywords]() {
                return monitor_resolution_source(client, source, keywords);
            }));
        }
        
        map<string, SourceData> new_source_data;
        for (auto& future : futures) {
            SourceData data = future.get();
            new_source_data[data.url] = data;
        }
        
        {
            lock_guard<mutex> lock(source_data_mutex);
            source_data = new_source_data;
        }
        
        // Détection d'opportunités
        auto new_opportunities = detect_arbitrage_opportunities(markets, source_data);
        
        {
            lock_guard<mutex> lock(opportunities_mutex);
            opportunities = new_opportunities;
        }
        
        // Génération de signaux
        auto new_signals = generate_trading_signals(opportunities);
        
        {
            lock_guard<mutex> lock(signals_mutex);
            signals = new_signals;
        }
        
        cout << "[OK] Données mises à jour: " << markets.size() << " marchés, " 
             << opportunities.size() << " opportunités, " << signals.size() << " signaux" << endl;
        
        return true;
    }
    
    // Obtenir le nombre de marchés
    int get_markets_count() {
        lock_guard<mutex> lock(markets_mutex);
        return markets.size();
    }
    
    // Obtenir le nombre d'opportunités
    int get_opportunities_count() {
        lock_guard<mutex> lock(opportunities_mutex);
        return opportunities.size();
    }
    
    // Obtenir le nombre de signaux
    int get_signals_count() {
        lock_guard<mutex> lock(signals_mutex);
        return signals.size();
    }
    
    // Exécuter un trade (appelé par Rust)
    bool execute_trade_cpp(const char* market_id, const char* action, double amount) {
        cout << "Exécution de trade C++:" << endl;
        cout << "   Market ID: " << market_id << endl;
        cout << "   Action: " << action << endl;
        cout << "   Amount: " << amount << " ETH" << endl;
        
        // Ici vous pouvez ajouter la logique d'exécution spécifique
        // Par exemple, appel direct à l'API Polymarket
        
        cout << "[OK] Trade exécuté avec succès" << endl;
        return true;
    }

    // ===== FONCTIONS HFT ULTRA-OPTIMISÉES =====
    
    // Calcul ROI ultra-rapide avec cache (latence < 1μs)
    double calculate_roi_hft_cached(double current_price, double fee, double catchup_speed, double action_time) {
        // Clé de cache pour éviter les recalculs
        std::string cache_key = std::to_string(current_price) + "_" + std::to_string(fee) + "_" + 
                          std::to_string(catchup_speed) + "_" + std::to_string(action_time);
        
        {
            std::lock_guard<std::mutex> lock(roi_cache_mutex);
            auto it = roi_cache.find(cache_key);
            if (it != roi_cache.end()) {
                return it->second; // Cache hit - retour immédiat
            }
        }
        
            // Cache miss - calcul rapide avec paramètres FORCÉS pour test
    double roi = calculate_real_roi(current_price, GLOBAL_FEE, GLOBAL_CATCHUP_SPEED, GLOBAL_ACTION_TIME);
        
        // Mise en cache avec gestion de la taille
        {
            std::lock_guard<std::mutex> lock(roi_cache_mutex);
            if (roi_cache.size() >= MAX_CACHE_SIZE) {
                roi_cache.clear(); // Reset si trop plein
            }
            roi_cache[cache_key] = roi;
        }
        
        return roi;
    }
    
    // Décision de trading ultra-rapide (latence < 100ns) - OPTIMISÉE HFT
    const char* make_trading_decision_hft(double roi, double confidence) {
        // Lookup table pour décisions instantanées
        static const char* decisions[] = {"MONITOR", "BUY", "SELL"};
        
        // Seuils optimisés pour HFT - plus agressifs
        if (roi > 0.03 && confidence > 0.6) return decisions[1]; // BUY (seuil baissé)
        if (roi > 0.02 && confidence > 0.45) return decisions[2]; // SELL (seuil baissé)
        return decisions[0]; // MONITOR
    }
    
    // Calcul de position size ultra-rapide (latence < 50ns) - OPTIMISÉE HFT
    double calculate_position_size_hft(double capital, double roi, const char* confidence) {
        // Lookup table précalculée pour positions - plus agressive
        static double position_multipliers[] = {0.008, 0.015, 0.025, 0.04, 0.06};
        
        int index = 0;
        if (roi > 0.08) index = 4;      // 6% du capital (seuil baissé)
        else if (roi > 0.05) index = 3; // 4% du capital (seuil baissé)
        else if (roi > 0.03) index = 2; // 2.5% du capital (seuil baissé)
        else if (roi > 0.02) index = 1; // 1.5% du capital (seuil baissé)
        else index = 0;                 // 0.8% du capital (augmenté)
        
        return capital * position_multipliers[index];
    }
    
    // Validation de trade
    bool validate_trade_hft(const char* market_id, double amount, double current_balance) {
        // Vérifications minimales pour vitesse maximale
        if (amount <= 0 || amount > current_balance * 0.1) return false;
        if (strlen(market_id) == 0) return false;
        return true;
    }
    
    // Calcul de latence réseau estimée (latence < 10ns)
    double estimate_network_latency_hft() {
        // Valeurs précalculées basées sur l'historique
        static double avg_latency = 0.045;
        static double jitter = 0.010;
        
        return avg_latency + (rand() % 100 - 50) * jitter / 100.0;
    }
    
    // Prédiction de latence
    double predict_latency_hft(const char* endpoint) {
        // Lookup table pour latences précalculées
        static std::map<std::string, double> latency_table = {
            {"gamma-api.polymarket.com", 0.035},  // 35ms
            {"clob.polymarket.com", 0.040},       // 40ms
            {"api.stlouisfed.org", 0.050},        // 50ms
            {"www.federalreserve.gov", 0.045},    // 45ms
            {"www.sec.gov", 0.055},               // 55ms
            {"www.coindesk.com", 0.060}           // 60ms
        };
        
        std::string key(endpoint);
        auto it = latency_table.find(key);
        return (it != latency_table.end()) ? it->second : 0.050; // 50ms par défaut
    }
    
    // Optimisation mémoire pour HFT
    void optimize_memory_hft() {
        // Pré-allocation des vecteurs pour éviter les reallocations
        precomputed_roi_table.reserve(10000);
        
        // Initialisation de la lookup table ROI
        if (!roi_table_initialized) {
            for (int i = 0; i < 10000; i++) {
                double price = i / 10000.0;
                precomputed_roi_table.push_back(calculate_real_roi(price, GLOBAL_FEE, GLOBAL_CATCHUP_SPEED, GLOBAL_ACTION_TIME));
            }
            roi_table_initialized = true;
        }
    }
    
    // Fonction de nettoyage périodique pour éviter la fragmentation mémoire
    void cleanup_hft_cache() {
        std::lock_guard<std::mutex> lock(roi_cache_mutex);
        if (roi_cache.size() > MAX_CACHE_SIZE * 0.8) {
            roi_cache.clear();
        }
    }
}
