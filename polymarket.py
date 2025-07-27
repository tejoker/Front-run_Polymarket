###############################################################################
###############################################################################
###############################################################################
######                                                                   ######
######                              Polymarket                           ######
######                                                                   ######
######    Author    : N. Bigeard & A. Jurkowski                          ######
######    Date      : 21 July 2025                                       ######
######    Version   : 0.1                                                ######
######                                                                   ######
###############################################################################
###############################################################################


# =============================================================================
# IMPORTS AND INITIAL CONFIGURATION
# =============================================================================
import re
import requests
import os
import sqlite3
import json
import time
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any
from dotenv import load_dotenv
import sys
print(sys.executable)

# Logging configuration for operation tracking
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('polymarket.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Log pour les temps de fetch des sources
source_fetch_logger = logging.getLogger('source_fetch')
source_fetch_handler = logging.FileHandler('source_fetch_times.log')
source_fetch_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
source_fetch_logger.addHandler(source_fetch_handler)
source_fetch_logger.setLevel(logging.INFO)

# Log pour les fetchs de marchés
market_fetch_logger = logging.getLogger('market_fetch')
market_fetch_handler = logging.FileHandler('market_fetch_times.log')
market_fetch_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
market_fetch_logger.addHandler(market_fetch_handler)
market_fetch_logger.setLevel(logging.INFO)

# Log pour les timing des trades
trade_timing_logger = logging.getLogger('trade_timing')
trade_timing_handler = logging.FileHandler('trade_timing.log')
trade_timing_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
trade_timing_logger.addHandler(trade_timing_handler)
trade_timing_logger.setLevel(logging.INFO)

# Log du temps de fetch sources
import time as _time

# .env pour les clés 
load_dotenv()
GAMMA_API = os.getenv("GAMMA_API", "https://gamma-api.polymarket.com/markets")
GRAPHQL_URL = os.getenv("GRAPHQL_URL", "https://gateway.thegraph.com/api/subgraphs/id/81Dm16JjuFSrqz813HysXoUPvzTwE7fsfPk2RTf66nyC")
GRAPH_API_KEY = os.getenv("GRAPH_API_KEY", "")

def fetch_open_markets() -> List[Dict]:
    """
    Retrieve all open (unfinished) markets from the Polymarket Gamma API.
    Log the fetch time and market probabilities.
    """
    fetch_start = _time.time()
    resp = requests.get(GAMMA_API, params={"closed": "false"})
    resp.raise_for_status()
    data = resp.json()
    markets = data.get("data", data) if isinstance(data, dict) else data
    fetch_end = _time.time()
    duration = fetch_end - fetch_start
    for market in markets:
        prob = market.get("probability") or market.get("yesProbability") or market.get("prob")
        market_fetch_logger.info(f"{market.get('id')} | {market.get('question', '')[:40]} | prob={prob} | fetch_duration={duration:.3f}s")
    return markets

def extract_resolution_source(description: str) -> Optional[str]:
    """
    Extract the sentence containing 'Resolution Source:' from a market description.
    
    This function searches for resolution source information in market descriptions.
    Polymarket markets often specify their resolution sources in the description
    text, which is crucial for arbitrage strategies.
    
    Args:
        description (str): Market description text to search in
        
    Returns:
        Optional[str]: Extracted resolution source sentence or None if not found
        
    Example:
        >>> desc = "Will Trump win? Resolution source: Official election results."
        >>> extract_resolution_source(desc)
        'Resolution source: Official election results.'
    """
    idx = description.lower().find("resolution source")
    
    if idx == -1:
        return None
    
    snippet = description[idx:]
    
    m = re.match(r'^(.*?\.)', snippet)
    
    return m.group(1).strip() if m else snippet.strip()

def categorize_market_domain(question: str, description: str) -> str:
    """Categorize a market into a domain based on its question and description."""
    text = (question + " " + description).lower()
    
    # Politics
    if any(keyword in text for keyword in ["trump", "election", "president", "biden", "white house", "congress"]):
        return "politics"
    
    # Crypto
    elif any(keyword in text for keyword in ["etf", "crypto", "bitcoin", "ethereum", "sec", "coinbase"]):
        return "crypto"
    
    # Economy
    elif any(keyword in text for keyword in ["fed", "rate", "inflation", "recession", "gdp", "federal reserve"]):
        return "economy"
    
    # Health
    elif any(keyword in text for keyword in ["pandemic", "covid", "who", "health", "vaccine"]):
        return "health"
    
    # Sports
    elif any(keyword in text for keyword in ["match", "game", "championship", "league", "team"]):
        return "sports"
    
    else:
        return "other"

def analyze_resolution_patterns(markets: List[Dict]) -> Dict:
    """Analyze resolution patterns by domain and extract common sources."""
    domains = {
        "politics": {"count": 0, "markets": [], "sources": set()},
        "crypto": {"count": 0, "markets": [], "sources": set()},
        "economy": {"count": 0, "markets": [], "sources": set()},
        "health": {"count": 0, "markets": [], "sources": set()},
        "sports": {"count": 0, "markets": [], "sources": set()},
        "other": {"count": 0, "markets": [], "sources": set()}
    }
    
    for market in markets:
        question = market.get("question", "")
        description = market.get("description", "")
        domain = categorize_market_domain(question, description)
        
        domains[domain]["count"] += 1
        domains[domain]["markets"].append(market)
        
        # Extract resolution sources
        resolution_source = extract_resolution_source(description)
        if resolution_source:
            urls = extract_urls(resolution_source)
            for url in urls:
                domain_name = url.split("//")[-1].split("/")[0].replace("www.", "")
                domains[domain]["sources"].add(domain_name)
    
    return domains

def fetch_ancillary_data(question_id: str) -> Optional[str]:
    """Query the Polymarket subgraph for market data of a given question ID."""
    query = """
    query ($id: ID!) {
      fixedProductMarketMakers(where: { questionId: $id }) {
        id
        outcomeSlotCount
        outcomeTokenAmounts
        totalSupply
        totalVolume
      }
    }
    """
    try:
        # on prépare les headers avec la clé API
        headers = {"Content-Type": "application/json"}
        if GRAPH_API_KEY:
            headers["Authorization"] = f"Bearer {GRAPH_API_KEY}"
        
        resp = requests.post(
            GRAPHQL_URL,
            json={"query": query, "variables": {"id": question_id}},
            timeout=10,
            headers=headers
        )
        resp.raise_for_status()
        response_data = resp.json()
        
        if response_data is None:
            return None
            
        recs = response_data.get("data", {}).get("fixedProductMarketMakers", [])
        if recs:
            market_data = recs[0]
            return f"Market ID: {market_data.get('id')}, Outcomes: {market_data.get('outcomeSlotCount')}, Total Supply: {market_data.get('totalSupply')}, Volume: {market_data.get('totalVolume')}"
        return None
    except Exception as e:
        return None

def extract_urls(text: str) -> List[str]:
    """Return all HTTP(S) URLs found in the given text."""
    return re.findall(r'https?://[^\s,)]+', text)

# Fonction pour lister toutes les sources de résolution

def list_all_resolution_sources(markets: List[Dict]) -> List[str]:
    """
    Extrait toutes les URLs de résolution de tous les marchés (tous domaines).
    Retourne une liste unique de sources (URLs).
    """
    sources = set()
    for market in markets:
        description = market.get("description", "")
        res_src = extract_resolution_source(description)
        if res_src:
            urls = extract_urls(res_src)
            for url in urls:
                sources.add(url)
    return sorted(sources)


# négation

def detect_keyword_with_negation(text: str, keyword: str) -> (bool, str):
    """
    Detects the presence of a keyword in English text, taking into account negation.
    Returns (True, 'affirmed') if affirmed, (True, 'negated') if negated, (False, None) otherwise.
    ENGLISH ONLY VERSION.
    """
    text = text.lower()
    keyword = keyword.lower()
    # English negation patterns
    neg_patterns = [
        rf"not\s+{re.escape(keyword)}",
        rf"did not\s+{re.escape(keyword)}",
        rf"was not\s+{re.escape(keyword)}",
        rf"is not\s+{re.escape(keyword)}",
        rf"no\s+{re.escape(keyword)}",
        rf"never\s+{re.escape(keyword)}",
        rf"isn't\s+{re.escape(keyword)}",
        rf"wasn't\s+{re.escape(keyword)}",
        rf"didn't\s+{re.escape(keyword)}",
        rf"{re.escape(keyword)}\s+not",
        rf"{re.escape(keyword)}\s+never",
        rf"{re.escape(keyword)}\s+no",
        rf"{re.escape(keyword)}\s+isn't",
        rf"{re.escape(keyword)}\s+wasn't",
        rf"{re.escape(keyword)}\s+didn't"
    ]
    for pat in neg_patterns:
        if re.search(pat, text):
            return True, 'negated'
    # Affirmation simple
    if re.search(rf"\b{re.escape(keyword)}\b", text):
        return True, 'affirmed'
    return False, None

# monitor_resolution_source

def monitor_resolution_source(url: str, keywords: List[str] = None) -> Dict:
    """Monitor a resolution source for changes, with negation-aware keyword detection and fetch timing."""
    start_time = _time.time()
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        content = response.text.lower()
        found_keywords = []
        if keywords:
            for kw in keywords:
                found, status = detect_keyword_with_negation(content, kw)
                if found:
                    found_keywords.append((kw, status))
        duration = _time.time() - start_time
        source_fetch_logger.info(f"SUCCESS | {url} | {duration:.3f}s | content_length={len(content)} | found_keywords={found_keywords}")
        return {
            "url": url,
            "status": "success",
            "content_length": len(content),
            "found_keywords": found_keywords,
            "has_changes": any(s == 'affirmed' for _, s in found_keywords),
            "fetch_duration": duration
        }
    except Exception as e:
        duration = _time.time() - start_time
        source_fetch_logger.info(f"ERROR | {url} | {duration:.3f}s | error={str(e)}")
        return {
            "url": url,
            "status": "error",
            "error": str(e),
            "has_changes": False,
            "fetch_duration": duration
        }

def get_economy_resolution_sources() -> List[str]:
    """Get the most important resolution sources for economy markets."""
    return [
        "https://fred.stlouisfed.org/series/FGEXPND",
        "https://www.federalreserve.gov/monetarypolicy/openmarket.htm",
        "https://www.bea.gov/data/gdp/gross-domestic-product",
        "https://www.nber.org/",
    ]

def get_source_keywords(source_url: str) -> List[str]:
    """Get relevant keywords for monitoring a specific source."""
    if "fred.stlouisfed.org" in source_url:
        return ["federal spending", "government spending", "expenditure", "budget", "fiscal"]
    elif "federalreserve.gov" in source_url:
        return ["federal reserve", "interest rate", "monetary policy", "fed funds", "rate hike", "rate cut"]
    elif "bea.gov" in source_url:
        return ["gdp", "gross domestic product", "economic growth", "quarterly", "annual"]
    elif "nber.org" in source_url:
        return ["recession", "economic downturn", "business cycle", "nber", "downturn"]
    else:
        return ["economy", "economic", "financial", "market"]

def detect_arbitrage_opportunities(markets: List[Dict], source_data: Dict) -> List[Dict]:
    """Detect potential arbitrage opportunities based on source monitoring."""
    opportunities = []
    
    for market in markets:
        domain = categorize_market_domain(market.get("question", ""), market.get("description", ""))
        
        if domain == "economy":
            market_id = market.get("id")
            question = market.get("question", "")
            description = market.get("description", "")
            
            # Exxtract keywords from the market
            market_keywords = extract_market_keywords(question, description)
            
            # Cheeck each source for relevant changes
            for source_url, source_info in source_data.items():
                if source_info["status"] == "success":
                    # Check if source contents is relevant to this market
                    relevance_score = calculate_relevance(source_url, market_keywords, source_info)
                    
                    if relevance_score > 0.3:  # Only keep if > 30%
                        opportunities.append({
                            "market_id": market_id,
                            "question": question,
                            "source_url": source_url,
                            "confidence": "high" if relevance_score > 0.7 else "medium",
                            "relevance_score": relevance_score,
                            "reason": f"Source {source_url} relevant to market (score: {relevance_score:.2f})",
                            "timestamp": datetime.now().isoformat()
                        })
    
    return opportunities

def extract_market_keywords(question: str, description: str) -> List[str]:
    """Extract relevant keywords from market question and description."""
    text = (question + " " + description).lower()
    keywords = []
    
    # Federal spending 
    if "federal spending" in text or "spending" in text:
        keywords.extend(["federal spending", "government spending", "expenditure", "budget"])
    
    # Fed ratee
    if "fed rate" in text or "rate hike" in text or "rate cut" in text:
        keywords.extend(["federal reserve", "interest rate", "monetary policy", "fed funds"])
    
    # GDP 
    if "gdp" in text or "gross domestic product" in text:
        keywords.extend(["gdp", "gross domestic product", "economic growth"])
    
    # Recession
    if "recession" in text:
        keywords.extend(["recession", "economic downturn", "nber"])
    
    return list(set(keywords))  # Remove duplicates

def calculate_relevance(source_url: str, market_keywords: List[str], source_info: Dict) -> float:
    """Calculate relevance score between source and market keywords."""
    if not market_keywords:
        return 0.0
    
    # Define source-specific
    source_keywords = {
        "fred.stlouisfed.org": ["federal spending", "government spending", "expenditure"],
        "federalreserve.gov": ["federal reserve", "interest rate", "monetary policy"],
        "bea.gov": ["gdp", "gross domestic product", "economic growth"],
        "nber.org": ["recession", "economic downturn", "business cycle"]
    }
    
    # Get keywords for sources
    source_domain = source_url.split("//")[-1].split("/")[0]
    source_specific_keywords = source_keywords.get(source_domain, [])
    
    market_keywords_set = set(market_keywords)
    source_keywords_set = set(source_specific_keywords)
    
    if not market_keywords_set or not source_keywords_set:
        return 0.0
    
    intersection = len(market_keywords_set.intersection(source_keywords_set))
    union = len(market_keywords_set.union(source_keywords_set))
    
    if union == 0:
        return 0.0
    
    relevance = intersection / union
    
    # Boost score if source is accessible and has content
    if source_info["status"] == "success" and source_info["content_length"] > 1000:
        relevance *= 1.2
    
    return min(relevance, 1.0)  # Cap at 1.0

def create_performance_report(signals: List[Dict], backtest_results: Dict) -> str:
    """Create a detailed performance report with V1 and V2 ROI analysis."""
    if not signals:
        return "Aucun signal généré - pas de données de performance disponibles."
    
    report = []
    report.append("📊 RAPPORT DE PERFORMANCE DÉTAILLÉ")
    report.append("=" * 50)
    
    # Signal breakdown
    buy_signals = [s for s in signals if s["action"] == "buy"]
    monitor_signals = [s for s in signals if s["action"] == "monitor"]
    ignore_signals = [s for s in signals if s["action"] == "ignore"]
    
    report.append(f"\n🎯 RÉPARTITION DES SIGNAUX:")
    report.append(f"  • ACHETER: {len(buy_signals)} signaux")
    report.append(f"  • SURVEILLER: {len(monitor_signals)} signaux")
    report.append(f"  • IGNORER: {len(ignore_signals)} signaux")
    
    # Enhanced ROI analysis with V1 and V2 formulas made by nicolaaas
    if buy_signals:
        avg_buy_roi_v1 = sum(s.get("roi_v1", 0) for s in buy_signals) / len(buy_signals)
        avg_buy_roi_v2 = sum(s.get("roi_v2", 0) for s in buy_signals) / len(buy_signals)
        
        report.append(f"\n💰 ANALYSE ROI DÉTAILLÉE:")
        report.append(f"  • ROI V1 moyen (ACHETER): {avg_buy_roi_v1:.1%}")
        report.append(f"  • ROI V2 moyen (ACHETER): {avg_buy_roi_v2:.1%}")
        report.append(f"  • Amélioration V2 vs V1: {avg_buy_roi_v2 - avg_buy_roi_v1:+.1%}")
        report.append(f"  • ROI total V1: {backtest_results.get('total_roi_v1', 0):.1%}")
        report.append(f"  • ROI total V2: {backtest_results.get('total_roi_v2', 0):.1%}")
        report.append(f"  • ROI moyen par signal V1: {backtest_results.get('avg_roi_v1', 0):.1%}")
        report.append(f"  • ROI moyen par signal V2: {backtest_results.get('avg_roi_v2', 0):.1%}")
    
    # Information value analysis
    true_signals = backtest_results.get('true_signals', 0)
    false_signals = backtest_results.get('false_signals', 0)
    total_signals = backtest_results.get('total_signals', 0)
    
    if total_signals > 0:
        report.append(f"\n📈 ANALYSE VALEUR D'INFORMATION:")
        report.append(f"  • Signaux TRUE (YES): {true_signals} ({true_signals/total_signals:.1%})")
        report.append(f"  • Signaux FALSE (NO): {false_signals} ({false_signals/total_signals:.1%})")
        report.append(f"  • Probabilité Polymarket moyenne: {backtest_results.get('avg_polymarket_probability', 0):.1%}")
    
    # Confidence analysis
    high_conf = [s for s in signals if s["confidence"] == "high"]
    report.append(f"\n🎯 ANALYSE CONFIANCE:")
    report.append(f"  • Haute confiance: {len(high_conf)} signaux")
    report.append(f"  • Taux de succès estimé: {backtest_results.get('success_rate', 0):.1%}")
    
    # Formula explanations
    report.append(f"\nFORMULES ROI UTILISÉES:")
    report.append(f"  • V1: ROI = 1 - p(a) - fee (si information=TRUE)")
    report.append(f"  • V1: ROI = p(a) - fee (si information=FALSE)")
    report.append(f"  • V2: ROI = 1(t) - p(a,t+ε) - fee (si marché ouvert)")
    report.append(f"  • Frais Polymarket: 2%")
    
    # Timing analysis
    if signals:
        avg_reaction_time = sum(s.get('reaction_time_ms', 0) for s in signals) / len(signals)
        avg_execution_time = sum(s.get('estimated_execution_time_ms', 0) for s in signals) / len(signals)
        avg_total_latency = sum(s.get('total_latency_ms', 0) for s in signals) / len(signals)
        
        # Count timing grades
        grade_counts = {}
        for signal in signals:
            grade = signal.get('timing_grade', 'N/A')
            grade_counts[grade] = grade_counts.get(grade, 0) + 1
        
        report.append(f"\n⏱ ANALYSE TIMING:")
        report.append(f"  • Temps de réaction moyen: {avg_reaction_time:.0f}ms")
        report.append(f"  • Temps d'exécution estimé moyen: {avg_execution_time:.0f}ms")
        report.append(f"  • Latence totale moyenne: {avg_total_latency:.0f}ms")
        report.append(f"  • Répartition des grades:")
        for grade in ['A+', 'A', 'B', 'C', 'D', 'F']:
            count = grade_counts.get(grade, 0)
            if count > 0:
                report.append(f"    - {grade}: {count} signaux")
    
    # Recommendations
    report.append(f"\n💡 RECOMMANDATIONS:")
    if buy_signals:
        report.append(f"  • {len(buy_signals)} opportunités d'achat identifiées")
        report.append(f"  • ROI V2 plus précis avec facteur temps")
        report.append(f"  • Focus sur les marchés avec probabilité < 70%")
        report.append(f"  • Surveiller les sources de résolution en temps réel")
        if avg_total_latency > 2000:
            report.append(f"  • ⚠️  Optimiser la latence (actuellement {avg_total_latency:.0f}ms)")
    else:
        report.append(f"  • Aucune opportunité d'achat immédiate")
        report.append(f"  • Continuer la surveillance des sources")
        report.append(f"  • Attendre des signaux avec ROI > 10%")
    
    return "\n".join(report)

def setup_continuous_monitoring(interval_minutes: int = 5):
    """
    Setup continuous monitoring of resolution sources.
    
    This function configures a scheduled job that runs every interval_minutes
    to monitor resolution sources, detect arbitrage opportunities, and generate
    trading signals.
    
    Args:
        interval_minutes (int): Interval between monitoring runs in minutes
        
    Example:
        >>> setup_continuous_monitoring(5)  # Monitor every 5 minutes
    """
    # Check for schedule module at runtime
    try:
        import schedule
        print("✅ Schedule module available for continuous monitoring")
    except ImportError:
        print("❌ Module 'schedule' not found. Install with: pip install schedule")
        return
    
    print(f"\n🔄 CONTINUOUS MONITORING CONFIGURATION")
    print(f"   Interval: {interval_minutes} minutes")
    print(f"   Sources monitored: {len(get_economy_resolution_sources())}")
    
    def monitoring_job():
        """
        Continuous monitoring job that runs every interval_minutes.
        
        This function:
        1. Fetches current markets from Polymarket
        2. Monitors resolution sources for changes
        3. Detects arbitrage opportunities
        4. Saves data to database
        5. Logs results
        """
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🔍 Checking sources...")
        
        # Fetch current markets
        try:
            markets = fetch_open_markets()
            economy_markets = [m for m in markets if categorize_market_domain(m.get("question", ""), m.get("description", "")) == "economy"]
            
            if not economy_markets:
                print("   📊 No economy markets found")
                return
            
            # Monitor sources
            source_data = {}
            economy_sources = get_economy_resolution_sources()
            fetch_times = {}
            
            for source in economy_sources:
                keywords = get_source_keywords(source)
                result = monitor_resolution_source(source, keywords)
                source_data[source] = result
                fetch_times[source] = result.get('fetch_duration', 0)
                
                if result["status"] == "success":
                    print(f"   ✅ {source.split('//')[-1].split('/')[0]}: {result['content_length']:,} characters (Duration: {result['fetch_duration']:.3f}s)")
                else:
                    print(f"   ❌ {source.split('//')[-1].split('/')[0]}: {result.get('error', 'Error')} (Duration: {result['fetch_duration']:.3f}s)")
            
            # Detect opportunities
            opportunities = detect_arbitrage_opportunities(economy_markets, source_data)
            
            if opportunities:
                print(f"   🎯 {len(opportunities)} opportunities detected!")
                for opp in opportunities[:2]:  # Show first 2
                    print(f"      • {opp['question'][:40]}... (Score: {opp['relevance_score']:.2f})")
            else:
                print("   📊 No opportunities detected")
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
        
    # Schedule the job
    schedule.every(interval_minutes).minutes.do(monitoring_job)
    
    print(f"\n🚀 Monitoring started! Press Ctrl+C to stop.")
    
    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        print(f"\n⏹️  Monitoring stopped by user")

def generate_trading_signals(opportunities: List[Dict]) -> List[Dict]:
    """Generate trading signals from arbitrage opportunities with buy/sell/monitor logic and timing tracking."""
    signals = []
    
    for opp in opportunities:
        # Start timing for this signal generation
        signal_start_time = _time.time()
        
        relevance_score = opp.get("relevance_score", 0.0)
        # Estimate information value based on opportunity analysis
        information_value = estimate_information_value(opp)
        # Estimate Polymarket probability (this would come from actual market data)
        polymarket_probability = estimate_polymarket_probability(opp)
        # Calculate ROI using both V1 and V2 formulas
        roi_data = calculate_potential_roi(
            relevance_score=relevance_score,
            information_value=information_value,
            polymarket_probability=polymarket_probability,
            polymarket_fee=0.02,  # 2% Polymarket fee
            time_factor=1.1,  # Slight time adjustment
            market_status="open",
            use_v2=True
        )
        
        # Logique d'arbitrage -> différence entre conviction et prix du marché
        # Si la différence est assez grande, il y a opportunité d'arbitrage
        difference = abs(information_value - polymarket_probability)
        if difference > 0.1:  # Différence pour arbitrage
            if information_value:  #je pense que ça va arriver
                action = "buy"
            else:  # je pense que ça n'arrivera pas
                action = "sell"  # Acheter
        elif difference > 0.05:  # Différence ok
            action = "monitor"  # Surveiller
        else:
            action = "ignore"  # Pas d'opportunité d'arbitrage
        
        # Calculate timing metrics
        signal_end_time = _time.time()
        signal_generation_time = (signal_end_time - signal_start_time) * 1000  # Convert to milliseconds
        
        # Parse timestamps for detailed timing
        detection_time = opp.get("timestamp", datetime.now().isoformat())
        signal_time = datetime.now().isoformat()
        
        # Calculate reaction time
        try:
            detection_dt = datetime.fromisoformat(detection_time.replace('Z', '+00:00'))
            signal_dt = datetime.fromisoformat(signal_time.replace('Z', '+00:00'))
            reaction_time_ms = (signal_dt - detection_dt).total_seconds() * 1000
        except:
            reaction_time_ms = signal_generation_time
        
        estimated_execution_ms = estimate_trade_execution_time(action, polymarket_probability, relevance_score)
        
        total_latency_ms = reaction_time_ms + estimated_execution_ms
        
        signal = {
            "market_id": opp["market_id"],
            "action": action,
            "confidence": opp["confidence"],
            "relevance_score": relevance_score,
            "reason": opp["reason"],
            "timestamp": opp["timestamp"],
            "source": opp["source_url"],
            "potential_roi": roi_data["primary_roi"],  # Use V2 as primary as you told me
            "roi_v1": roi_data["roi_v1"],
            "roi_v2": roi_data["roi_v2"],
            "information_value": information_value,
            "polymarket_probability": polymarket_probability,
            "roi_details": roi_data,
            "detection_time": detection_time,
            "signal_time": signal_time,
            "signal_generation_time_ms": signal_generation_time,
            "reaction_time_ms": reaction_time_ms,
            "estimated_execution_time_ms": estimated_execution_ms,
            "total_latency_ms": total_latency_ms,
            "timing_grade": get_timing_grade(total_latency_ms)
        }
        
        # Log timing metrics
        trade_timing_logger.info(
            f"TRADE | {action.upper()} | {opp['market_id']} | "
            f"reaction={reaction_time_ms:.0f}ms | "
            f"execution={estimated_execution_ms:.0f}ms | "
            f"total={total_latency_ms:.0f}ms | "
            f"grade={get_timing_grade(total_latency_ms)} | "
            f"roi_v2={roi_data['roi_v2']:.1%}"
        )
        
        signals.append(signal)
    
    return signals

def estimate_information_value(opportunity: Dict) -> bool:
    """
    Estimate the information value (TRUE/FALSE) based on opportunity analysis.
    
    Args:
        opportunity (Dict): Arbitrage opportunity data
        
    Returns:
        bool: Estimated information value (True = YES, False = NO)
    """
    relevance_score = opportunity.get("relevance_score", 0.0)
    source_url = opportunity.get("source_url", "")
    reason = opportunity.get("reason", "")
    
    if relevance_score > 0.7:
        return True  # Likely YES
    elif relevance_score < 0.3:
        return False  # Likely NO
    else:
        # For medium relevance, use source-based analysis
        if any(keyword in source_url.lower() for keyword in ["fed", "rate", "inflation"]):
            return True  # Economic indicators often suggest positive outcomes
        else:
            return relevance_score > 0.5  # Default to relevance-based decision

def estimate_polymarket_probability(opportunity: Dict) -> float:
    """
    Estimate current Polymarket probability for the opportunity.
    Args:
        opportunity (Dict): Arbitrage opportunity data
    Returns:
        float: Estimated probability (0.0 to 1.0)
    """
    relevance_score = opportunity.get("relevance_score", 0.0)
    confidence = opportunity.get("confidence", "medium")
    market_id = opportunity.get("market_id", "")
    source_url = opportunity.get("source_url", "")

    # Base probability on relevance score
    base_prob = 0.5
    if relevance_score > 0.8:
        base_prob = 0.7
    elif relevance_score < 0.3:
        base_prob = 0.3

    # Ajout de variabilité selon l'ID du marché j'ai fait un haash simple pour avoir un nombre entre 0 et 100
    if market_id:
        try:
            hash_val = sum(ord(c) for c in str(market_id))
            base_prob += ((hash_val % 10) - 5) * 0.01  # variation de -5% à +4%
        except Exception:
            pass

    # Ajout de variabilité selon la source
    if "fred" in source_url:
        base_prob += 0.03
    if "bea" in source_url:
        base_prob -= 0.02
    if "federalreserve" in source_url:
        base_prob += 0.01
    if "nber" in source_url:
        base_prob -= 0.01

    # Ajustement selon la confiance
    confidence_multiplier = {
        "high": 1.2,
        "medium": 1.0,
        "low": 0.8
    }.get(confidence, 1.0)
    adjusted_prob = base_prob * confidence_multiplier
    return max(0.0, min(1.0, adjusted_prob))

def estimate_trade_execution_time(action: str, polymarket_probability: float, relevance_score: float) -> float:
    """
    Estimate the time it would take to execute a trade on Polymarket.
    
    Args:
        action (str): "buy", "sell", "monitor", or "ignore"
        polymarket_probability (float): Current market probability
        relevance_score (float): Relevance score of the opportunity
        
    Returns:
        float: Estimated execution time in milliseconds
    """
    # Base execution times
    base_times = {
        "buy": 800,
        "sell": 600,
        "monitor": 0,
        "ignore": 0
    }
    
    base_time = base_times.get(action, 500)
    #i took this references by internet to know if takes time or not
    # Adjust based on market probability (higher probability = more liquidity = faster execution)
    if polymarket_probability > 0.8:
        base_time *= 0.8  # 20% faster for high probability markets
    elif polymarket_probability < 0.3:
        base_time *= 1.3  # 30% slower for low probability markets
    
    # Adjust based on relevance score (higher relevance = more urgent = faster execution)
    if relevance_score > 0.8:
        base_time *= 0.9  # 10% faster for high relevance
    elif relevance_score < 0.3:
        base_time *= 1.2  # 20% slower for low relevance
    
    # Add network latency simulation
    network_latency = 50 + (relevance_score * 100)  # 50-150ms based on relevance
    
    # Add Polymarket API latency
    api_latency = 200 + (polymarket_probability * 300)  # 200-500ms based on probability
    
    total_execution_time = base_time + network_latency + api_latency
    
    return max(0, total_execution_time)

def get_timing_grade(total_latency_ms: float) -> str:
    """
    Grade the timing performance based on total latency.
    
    Args:
        total_latency_ms (float): Total latency in milliseconds
        
    Returns:
        str: Grade (A+, A, B, C, D, F)
    """
    if total_latency_ms <= 500:
        return "A+"
    elif total_latency_ms <= 1000:
        return "A"
    elif total_latency_ms <= 2000:
        return "B"
    elif total_latency_ms <= 5000:
        return "C"
    elif total_latency_ms <= 10000:
        return "D"
    else:
        return "F"

def calculate_potential_roi_v1(information_value: bool, polymarket_probability: float, polymarket_fee: float = 0.02) -> float:
    """
    Calculate ROI using V1 formula: ROI = 1 - p(a) - fee
    
    Args:
        information_value (bool): TRUE or FALSE based on information analysis
        polymarket_probability (float): Current probability from Polymarket (0.0 to 1.0)
        polymarket_fee (float): Polymarket trading fee (default 2%)
        
    Returns:
        float: Calculated ROI as decimal (e.g., 0.15 for 15%)
        
    Example:
        >>> calculate_potential_roi_v1(True, 0.7, 0.02)
        0.28  # 28% ROI if information is TRUE and market shows 70% probability
    """
    if information_value:
        # If information is TRUE, we bet on YES
        # ROI = 1 - p(a) - fee where p(a) is the probability of YES
        roi = 1.0 - polymarket_probability - polymarket_fee
    else:
        # If information is FALSE, we bet on NO
        # ROI = 1 - (1-p(a)) - fee = p(a) - fee
        roi = polymarket_probability - polymarket_fee
    
    return max(roi, 0.0)  # ROI cannot be negative

def calculate_potential_roi_v2(information_value: bool, polymarket_probability: float, 
                              polymarket_fee: float = 0.02, time_factor: float = 1.0,
                              market_status: str = "open") -> float:
    """
    Calculate ROI using V2 formula: ROI = 1(t) - p(a,t+epsilon) - fee if market.status() != closed
    
    Args:
        information_value (bool): TRUE or FALSE based on information analysis
        polymarket_probability (float): Current probability from Polymarket (0.0 to 1.0)
        polymarket_fee (float): Polymarket trading fee (default 2%)
        time_factor (float): Time-based adjustment factor (1.0 = current time)
        market_status (str): Market status ("open", "closed", "resolved")
        
    Returns:
        float: Calculated ROI as decimal
        
    Example:
        >>> calculate_potential_roi_v2(True, 0.7, 0.02, 1.1, "open")
        0.18  # ROI with time factor adjustment
    """
    if market_status == "closed":
        return 0.0  # No ROI if market is closed
    
    # Apply time factor to probability
    adjusted_probability = polymarket_probability * time_factor
    
    # Clamp probability to valid range
    adjusted_probability = max(0.0, min(1.0, adjusted_probability))
    
    if information_value:
        # ROI = 1(t) - p(a,t+epsilon) - fee
        roi = 1.0 - adjusted_probability - polymarket_fee
    else:
        # ROI = p(a,t+epsilon) - fee
        roi = adjusted_probability - polymarket_fee
    
    return max(roi, 0.0)  # ROI cannot be neg 

def calculate_potential_roi(relevance_score: float, information_value: bool = None, 
                          polymarket_probability: float = None, polymarket_fee: float = 0.02,
                          time_factor: float = 1.0, market_status: str = "open", 
                          use_v2: bool = True) -> Dict[str, float]:
    """
    Calculate potential ROI using both V1 and V2 formulas.
    
    Args:
        relevance_score (float): Relevance score from 0.0 to 1.0
        information_value (bool): TRUE/FALSE based on information analysis
        polymarket_probability (float): Current Polymarket probability
        polymarket_fee (float): Polymarket trading fee
        time_factor (float): Time adjustment factor for V2
        market_status (str): Market status
        use_v2 (bool): Whether to use V2 formula as primary
        
    Returns:
        Dict[str, float]: Dictionary with both V1 and V2 ROI calculations
        
    Example:
        >>> result = calculate_potential_roi(0.8, True, 0.7, 0.02)
        >>> print(f"V1 ROI: {result['roi_v1']:.1%}, V2 ROI: {result['roi_v2']:.1%}")
    """
    # Default values if not provided
    if information_value is None:
        information_value = relevance_score > 0.5  # Estimate based on relevance
    
    if polymarket_probability is None:
        polymarket_probability = 0.5  # Default to 50% probability
    
    # Calculate both versions
    roi_v1 = calculate_potential_roi_v1(information_value, polymarket_probability, polymarket_fee)
    roi_v2 = calculate_potential_roi_v2(information_value, polymarket_probability, polymarket_fee, 
                                       time_factor, market_status)
    
    return {
        "roi_v1": roi_v1,
        "roi_v2": roi_v2,
        "primary_roi": roi_v2 if use_v2 else roi_v1,
        "information_value": information_value,
        "polymarket_probability": polymarket_probability,
        "time_factor": time_factor,
        "market_status": market_status
    }

def backtest_strategy(signals: List[Dict], historical_data: Dict = None) -> Dict:
    """Enhanced backtesting of the trading strategy with V1 and V2 ROI analysis."""
    if not signals:
        return {
            "total_signals": 0, 
            "success_rate": 0, 
            "total_roi_v1": 0, 
            "total_roi_v2": 0,
            "avg_roi_v1": 0,
            "avg_roi_v2": 0
        }
    
    # For now, simulate backtesting results
    total_signals = len(signals)
    high_confidence_signals = len([s for s in signals if s["action"] == "buy"]) # Assuming "buy" is high confidence
    
    # Simulate success rates based on confidence levels
    success_rate = 0.75 if high_confidence_signals > 0 else 0.50
    
    # Calculate ROI using both V1 and V2 formulas
    total_roi_v1 = sum(s.get("roi_v1", 0) for s in signals)
    total_roi_v2 = sum(s.get("roi_v2", 0) for s in signals)
    
    # Calculate averages
    avg_roi_v1 = total_roi_v1 / total_signals if total_signals > 0 else 0
    avg_roi_v2 = total_roi_v2 / total_signals if total_signals > 0 else 0
    
    # Analyze information value distribution
    true_signals = len([s for s in signals if s.get("information_value", False)])
    false_signals = total_signals - true_signals
    
    # Analyze probability distribution
    avg_probability = sum(s.get("polymarket_probability", 0.5) for s in signals) / total_signals if total_signals > 0 else 0.5
    
    return {
        "total_signals": total_signals,
        "high_confidence_signals": high_confidence_signals,
        "success_rate": success_rate,
        "total_roi_v1": total_roi_v1,
        "total_roi_v2": total_roi_v2,
        "avg_roi_v1": avg_roi_v1,
        "avg_roi_v2": avg_roi_v2,
        "true_signals": true_signals,
        "false_signals": false_signals,
        "avg_polymarket_probability": avg_probability,
        "roi_improvement_v2": avg_roi_v2 - avg_roi_v1 if avg_roi_v1 > 0 else 0
    }

def display_created_data(markets: List[Dict], opportunities: List[Dict], signals: List[Dict], source_data: Dict):
    """Display all created data in a clear, organized format."""
    
    print("\n" + "=" * 60)
    print("📊 DONNÉES CRÉÉES - RÉSUMÉ COMPLET")
    print("=" * 60)
    
    # 1. Résumé des marchés par domaine
    print("\n🏛️  MARCHÉS PAR DOMAINE:")
    print("-" * 40)
    domain_counts = {}
    for market in markets:
        domain = categorize_market_domain(market.get("question", ""), market.get("description", ""))
        domain_counts[domain] = domain_counts.get(domain, 0) + 1
    
    for domain, count in sorted(domain_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  • {domain.upper()}: {count} marchés")
    
    # 2. Sources de résolution testées
    print("\n🔍 SOURCES DE RÉSOLUTION TESTÉES:")
    print("-" * 40)
    for source, data in source_data.items():
        status = "✅" if data["status"] == "success" else "❌"
        print(f"  {status} {source}")
        if data["status"] == "success":
            print(f"     Taille: {data['content_length']:,} caractères")
    
    # 3. Opportunités détectées
    print(f"\n🎯 OPPORTUNITÉS D'ARBITRAGE DÉTECTÉES: {len(opportunities)}")
    print("-" * 40)
    if opportunities:
        for i, opp in enumerate(opportunities, 1):
            print(f"\n{i}. MARCHÉ: {opp['question'][:60]}...")
            print(f"   ID: {opp['market_id']}")
            print(f"   SOURCE: {opp['source_url']}")
            print(f"   CONFIANCE: {opp['confidence']}")
            print(f"   PERTINENCE: {opp.get('relevance_score', 'N/A'):.2f}")
            print(f"   RAISON: {opp['reason']}")
            print(f"   TIMESTAMP: {opp['timestamp']}")
    else:
        print("  Aucune opportunité détectée pour le moment.")
    
    # 4. Signaux de trading générés avec ROI V1 et V2 et TIMING
    print(f"\n📈 SIGNAUX DE TRADING GÉNÉRÉS: {len(signals)}")
    print("-" * 40)
    if signals:
        for i, signal in enumerate(signals[:5], 1):  # Limit to first 5 to avoid clutter
            print(f"\n{i}. ACTION: {signal['action'].upper()}")
            print(f"   MARCHÉ ID: {signal['market_id']}")
            print(f"   CONFIANCE: {signal['confidence']}")
            print(f"   ROI V1: {signal.get('roi_v1', 0):.1%}")
            print(f"   ROI V2: {signal.get('roi_v2', 0):.1%}")
            print(f"   INFO: {'TRUE' if signal.get('information_value') else 'FALSE'}")
            print(f"   PROB: {signal.get('polymarket_probability', 0):.1%}")
            print(f"   SOURCE: {signal['source']}")
            print(f"   RAISON: {signal['reason']}")
            # Timing metrics
            print(f"   ⏱️  TIMING:")
            print(f"      • Réaction: {signal.get('reaction_time_ms', 0):.0f}ms")
            print(f"      • Exécution estimée: {signal.get('estimated_execution_time_ms', 0):.0f}ms")
            print(f"      • Latence totale: {signal.get('total_latency_ms', 0):.0f}ms")
            print(f"      • Grade: {signal.get('timing_grade', 'N/A')}")
        
        if len(signals) > 5:
            print(f"\n... et {len(signals) - 5} autres signaux")
    else:
        print("  Aucun signal généré pour le moment.")
    
    # 5. Statistiques globales
    print("\n📋 STATISTIQUES GLOBALES:")
    print("-" * 40)
    print(f"  • Total marchés analysés: {len(markets)}")
    print(f"  • Sources testées: {len(source_data)}")
    print(f"  • Sources accessibles: {sum(1 for d in source_data.values() if d['status'] == 'success')}")
    print(f"  • Opportunités trouvées: {len(opportunities)}")
    print(f"  • Signaux générés: {len(signals)}")
    
    # 5B. Statistiques de timing
    if signals:
        avg_reaction = sum(s.get('reaction_time_ms', 0) for s in signals) / len(signals)
        avg_execution = sum(s.get('estimated_execution_time_ms', 0) for s in signals) / len(signals)
        avg_total = sum(s.get('total_latency_ms', 0) for s in signals) / len(signals)
        
        print(f"\n⏱️  STATISTIQUES TIMING:")
        print("-" * 40)
        print(f"  • Temps de réaction moyen: {avg_reaction:.0f}ms")
        print(f"  • Temps d'exécution estimé moyen: {avg_execution:.0f}ms")
        print(f"  • Latence totale moyenne: {avg_total:.0f}ms")
        
        # Fastest and slowest signals
        fastest_signal = min(signals, key=lambda x: x.get('total_latency_ms', float('inf')))
        slowest_signal = max(signals, key=lambda x: x.get('total_latency_ms', 0))
        
        print(f"  • Signal le plus rapide: {fastest_signal.get('total_latency_ms', 0):.0f}ms ({fastest_signal.get('action', 'N/A')})")
        print(f"  • Signal le plus lent: {slowest_signal.get('total_latency_ms', 0):.0f}ms ({slowest_signal.get('action', 'N/A')})")
    
    # 6. Fichiers créés
    print("\n💾 FICHIERS CRÉÉS:")
    print("-" * 40)
    print("  • polymarket.db (base de données SQLite)")
    print("  • polymarket_data.json (export JSON)")
    print("  • polymarket.log (logs généraux)")
    print("  • market_fetch_times.log (durées fetch marchés)")
    print("  • source_fetch_times.log (durées fetch sources)")
    print("  • trade_timing.log (métriques timing trades)")
    
    # 7. Liste de toutes les sources de résolution
    all_sources = list_all_resolution_sources(markets)
    print("\n🌐 LISTE DE TOUTES LES SOURCES DE RÉSOLUTION:")
    for src in all_sources: print(f"  • {src}")

    print("\n" + "=" * 60)

def test_roi_formulas():
    """
    Test function to demonstrate the new ROI formulas.
    
    This function shows examples of how the V1 and V2 ROI formulas work
    with different scenarios.
    """
    print("\n🧪 TEST DES FORMULES ROI")
    print("=" * 50)
    
    # Test scenarios
    scenarios = [
        {
            "name": "High probability market, TRUE info",
            "information_value": True,
            "polymarket_probability": 0.8,
            "time_factor": 1.0
        },
        {
            "name": "Low probability market, TRUE info",
            "information_value": True,
            "polymarket_probability": 0.3,
            "time_factor": 1.0
        },
        {
            "name": "Medium probability market, FALSE info",
            "information_value": False,
            "polymarket_probability": 0.5,
            "time_factor": 1.0
        },
        {
            "name": "High probability market, FALSE info",
            "information_value": False,
            "polymarket_probability": 0.8,
            "time_factor": 1.0
        },
        {
            "name": "Time-adjusted scenario",
            "information_value": True,
            "polymarket_probability": 0.6,
            "time_factor": 1.2
        }
    ]
    
    for i, scenario in enumerate(scenarios, 1):
        print(f"\n{i}. {scenario['name']}")
        print("-" * 40)
        
        roi_v1 = calculate_potential_roi_v1(
            scenario['information_value'],
            scenario['polymarket_probability'],
            0.02  # 2% fee
        )
        
        roi_v2 = calculate_potential_roi_v2(
            scenario['information_value'],
            scenario['polymarket_probability'],
            0.02,  # 2% fee
            scenario['time_factor'],
            "open"
        )
        
        print(f"   Information: {'TRUE' if scenario['information_value'] else 'FALSE'}")
        print(f"   Polymarket Probability: {scenario['polymarket_probability']:.1%}")
        print(f"   Time Factor: {scenario['time_factor']:.1f}")
        print(f"   ROI V1: {roi_v1:.1%}")
        print(f"   ROI V2: {roi_v2:.1%}")
        print(f"   Difference: {roi_v2 - roi_v1:+.1%}")
        
        if roi_v1 > 0 or roi_v2 > 0:
            print(f"   💡 Opportunité d'arbitrage détectée!")
        else:
            print(f"   ⚠️  Pas d'opportunité (ROI négatif ou nul)")

# ——— Database Management ———

class PolymarketDB:
    def __init__(self, db_path: str = "polymarket.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize the database with required tables."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Markets table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS markets (
                    id TEXT PRIMARY KEY,
                    slug TEXT,
                    question TEXT,
                    description TEXT,
                    uma_question_id TEXT,
                    domain TEXT,
                    resolution_source TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Resolution sources table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS resolution_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    domain TEXT,
                    source_url TEXT,
                    frequency INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(domain, source_url)
                )
            """)
            
            conn.commit()
    
    def save_markets(self, markets: List[Dict]):
        """Save markets data to database."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            for market in markets:
                market_id = market.get("id")
                slug = market.get("slug", "")
                question = market.get("question", "")
                description = market.get("description", "")
                uma_qid = market.get("questionID", "")
                domain = categorize_market_domain(question, description)
                resolution_source = extract_resolution_source(description)
                
                cursor.execute("""
                    INSERT OR REPLACE INTO markets 
                    (id, slug, question, description, uma_question_id, domain, resolution_source, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    market_id, slug, question, description, uma_qid, domain, 
                    resolution_source, datetime.now()
                ))
            
            conn.commit()
    
    def get_domain_statistics(self) -> Dict:
        """Get statistics by domain."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT domain, COUNT(*) as count 
                FROM markets 
                GROUP BY domain 
                ORDER BY count DESC
            """)
            
            stats = {}
            for row in cursor.fetchall():
                stats[row[0]] = row[1]
            
            return stats
    
    def export_to_json(self, filename: str = "polymarket_data.json"):
        """
        Export comprehensive data to JSON file including all tables.
        
        Args:
            filename (str): Output JSON filename
            
        Returns:
            Dict: Exported data structure
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Export markets
            cursor.execute("SELECT * FROM markets")
            columns = [description[0] for description in cursor.description]
            markets = []
            for row in cursor.fetchall():
                markets.append(dict(zip(columns, row)))
            
            # Export arbitrage opportunities
            cursor.execute("SELECT * FROM arbitrage_opportunities ORDER BY detected_at DESC LIMIT 100")
            columns = [description[0] for description in cursor.description]
            opportunities = []
            for row in cursor.fetchall():
                row_dict = dict(zip(columns, row))
                # Parse JSON fields
                if row_dict.get('extracted_data'):
                    try:
                        row_dict['extracted_data'] = json.loads(row_dict['extracted_data'])
                    except:
                        pass
                opportunities.append(row_dict)
            
            # Export trading signals
            cursor.execute("SELECT * FROM trading_signals ORDER BY generated_at DESC LIMIT 100")
            columns = [description[0] for description in cursor.description]
            signals = []
            for row in cursor.fetchall():
                signals.append(dict(zip(columns, row)))
            
            # Compile comprehensive export
            data = {
                "export_date": datetime.now().isoformat(),
                "statistics": self.get_domain_statistics(),
                "markets": markets,
                "arbitrage_opportunities": opportunities,
                "trading_signals": signals,
                "export_metadata": {
                    "total_markets": len(markets),
                    "total_opportunities": len(opportunities),
                    "total_signals": len(signals)
                }
            }
            
            # Write to file
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Comprehensive data exported to {filename}")
            print(f"📊 Données exportées vers {filename}")
            print(f"   • {len(markets)} marchés")
            print(f"   • {len(opportunities)} opportunités")
            print(f"   • {len(signals)} signaux")
            
            return data

# ——— Main Script ———

def main():
    # Test the new ROI formulas first
    test_roi_formulas()
    
    markets = fetch_open_markets()
    print(f"Found {len(markets)} open markets.\n")

    # Phase 1: Resolution patterns analysis
    print("🔍 RESOLUTION PATTERNS ANALYSIS")
    print("=" * 50)
    
    patterns = analyze_resolution_patterns(markets)
    
    for domain, data in patterns.items():
        if data["count"] > 0:
            print(f"\n📊 {domain.upper()}: {data['count']} markets")
            print(f"Resolution sources: {list(data['sources'])[:5]}")
            
            print("Example markets:")
            for market in data["markets"][:2]:
                question = market.get("question", "")
                print(f"  • {question[:60]}...")
    
    print(f"\n" + "=" * 50)
    print("📋 DETAILED MARKETS BY DOMAIN")
    print("=" * 50)

    for market in markets:
        market_id = market.get("id")
        slug = market.get("slug")
        question = market.get("question") or slug
        uma_qid = market.get("questionID")  # exact key from API
        description = market.get("description", "") or ""
        domain = categorize_market_domain(question, description)

        # Basic Info + description‐based resolution source
        print(f"[{domain.upper()}] Market: {question} (ID {market_id})")
        print(f"UMA Question ID: {uma_qid or 'Not available'}")
        res_src = extract_resolution_source(description)
        print(f"Resolution Source (from description): {res_src or '— not stated explicitly —'}")

        #fetch ancillaryData & URLs if we have a questionID
        if uma_qid:
            print(f"\n  Attempting to fetch GraphQL data...")
            anc = fetch_ancillary_data(uma_qid)
            if anc:
                print("  GraphQL data retrieved successfully.")
                urls = extract_urls(anc)
                if urls:
                    print("  URLs mentioned in data:")
                    for u in urls:
                        print(f"    • {u}")
                else:
                    print("  No URLs found in data.")
            else:
                print("  XXX  GraphQL data not available (empty or incompatible subgraph).")
        print("-" * 60)

    #db
    print("\n" + "=" * 50)
    print("DATABASE SAVE")
    print("=" * 50)
    
    try:
        db = PolymarketDB()
        
        db.save_markets(markets)
        print(f"{len(markets)} markets saved to database")
        
        stats = db.get_domain_statistics()
        print("\n📊 Statistics by domain:")
        for domain, count in stats.items():
            print(f"  • {domain}: {count} markets")
        
        db.export_to_json()
        
    except Exception as e:
        print(f"Error during save: {e}")

    #Testtt resolution source monitoring
    print("\n" + "=" * 50)
    print("🔍 TESTING RESOLUTION SOURCE MONITORING")
    print("=" * 50)
    
    economy_sources = get_economy_resolution_sources()
    print(f"Testing {len(economy_sources)} economy resolution sources...")
    
    source_data = {}
    for source in economy_sources:
        print(f"\nTesting: {source}")
        keywords = get_source_keywords(source)
        result = monitor_resolution_source(source, keywords)
        source_data[source] = result
        
        if result["status"] == "success":
            print(f"  ✅ Accessible ({result['content_length']} characters)")
            if result.get("found_keywords"):
                print(f"  Fuound keywords: {result['found_keywords']}")
            else:
                print(f"  🔍 Keywords searched: {keywords}")
        else:
            print(f"  ❌ Error: {result.get('error', 'Unknown error')}")
    
    # Phase 2B: Detect arbitrage opportunities
    print("\n" + "=" * 50)
    print("🎯 DETECTING ARBITRAGE OPPORTUNITIES")
    print("=" * 50)
    
    opportunities = detect_arbitrage_opportunities(markets, source_data)
    print(f"Found {len(opportunities)} potential arbitrage opportunities")
    
    if opportunities:
        print("\nOpportunities detected:")
        for i, opp in enumerate(opportunities[:5], 1):
            print(f"\n{i}. Market: {opp['question'][:50]}...")
            print(f"   Source: {opp['source_url']}")
            print(f"   Confidence: {opp['confidence']}")
            print(f"   Relevance Score: {opp.get('relevance_score', 'N/A'):.2f}")
            print(f"   Reason: {opp['reason']}")
    
    # Generate trading signals
    signals = generate_trading_signals(opportunities)
    print(f"\nGenerated {len(signals)} trading signals")
    
    if signals:
        print("\nTrading signals:")
        for i, signal in enumerate(signals[:3], 1):
            print(f"\n{i}. Action: {signal['action'].upper()}")
            print(f"   Market ID: {signal['market_id']}")
            print(f"   Confidence: {signal['confidence']}")
            print(f"   Potential ROI: {signal.get('potential_roi', 0):.1%}")
            print(f"   Source: {signal['source']}")
            print(f"   Reason: {signal['reason']}")
    
    #Backtesting
    print("\n" + "=" * 50)
    print("📊 BACKTESTING STRATEGY")
    print("=" * 50)
    
    backtest_results = backtest_strategy(signals)
    print(f"\n📈 Backtesting Results:")
    print(f"  • Total signals: {backtest_results['total_signals']}")
    print(f"  • High confidence signals: {backtest_results['high_confidence_signals']}")
    print(f"  • Success rate: {backtest_results['success_rate']:.1%}")
    print(f"  • Total potential ROI: {backtest_results['total_roi_v1']:.1%}")
    print(f"  • Average ROI per signal: {backtest_results['avg_roi_v1']:.1%}")
    
    # Display detailed performance report
    print("\n" + "=" * 60)
    performance_report = create_performance_report(signals, backtest_results)
    print(performance_report)
    
    # Display all created data in a comprehensive format
    display_created_data(markets, opportunities, signals, source_data)
    
    # Ask user if they want to start continuous monitoring
    print("\n" + "=" * 60)
    print("🚀 NEXT OPTIONS")
    print("=" * 60)
    print("1. Start continuous monitoring (check every 5 minutes)")
    print("2. Exit")
    
    try:
        choice = input("\nYour choice (1 or 2): ").strip()
        
        if choice == "1":
            print("\n🔄 Starting continuous monitoring...")
            try:
                setup_continuous_monitoring(interval_minutes=5)
            except Exception as e:
                print(f"❌ Error starting monitoring: {e}")
        else:
            print("👋 Goodbye!")
            
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")

if __name__ == "__main__":
    main() 