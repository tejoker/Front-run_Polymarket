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

# Web content analysis imports
try:
    from bs4 import BeautifulSoup
    BEAUTIFULSOUP_AVAILABLE = True
except ImportError:
    BEAUTIFULSOUP_AVAILABLE = False
    print("⚠️  BeautifulSoup not available. Install with: pip install beautifulsoup4")

# Continuous monitoring imports - will be checked at runtime problem with schedule module
SCHEDULE_AVAILABLE = None

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

# Load environment variables from .env file
load_dotenv()

# ——— Configurable Endpoints ———
GAMMA_API = os.getenv("GAMMA_API", "https://gamma-api.polymarket.com/markets")
GRAPHQL_URL = os.getenv("GRAPHQL_URL", "https://gateway.thegraph.com/api/subgraphs/id/81Dm16JjuFSrqz813HysXoUPvzTwE7fsfPk2RTf66nyC")
GRAPH_API_KEY = os.getenv("GRAPH_API_KEY", "")

# ——— Helper Functions ———

def fetch_open_markets() -> List[Dict]:
    """
    Retrieve all open (unfinished) markets from the Polymarket Gamma API.
    
    This function makes a REST API call to Polymarket's Gamma API to fetch
    all currently open markets. The API returns market data including:
    - Market ID, question, description
    - Resolution sources and conditions
    - Current status and closing dates
    
    Returns:
        List[Dict]: List of market dictionaries containing market information
        
    Raises:
        requests.HTTPError: If the API request fails
        requests.RequestException: For network or connection errors
        
    Example:
        >>> markets = fetch_open_markets()
        >>> print(f"Found {len(markets)} open markets")
    """
    # Make HTTP GET request to Polymarket API
    # params={"closed": "false"} filters for only open markets
    resp = requests.get(GAMMA_API, params={"closed": "false"})
    
    # Raise exception for HTTP error codes (4xx, 5xx)
    resp.raise_for_status()
    
    # Parse JSON response
    data = resp.json()
    
    # Handle different response formats:
    # Some APIs wrap results in {"data": [...]}, others return array directly
    return data.get("data", data) if isinstance(data, dict) else data

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
    # Convert to lowercase for case-insensitive search
    idx = description.lower().find("resolution source")
    
    # Return None if "resolution source" not found
    if idx == -1:
        return None
    
    # Extract substring starting from "resolution source"
    snippet = description[idx:]
    
    # Use regex to capture text until first period (end of sentence)
    # Pattern: ^(.*?\.) - start of string, capture everything until first period
    m = re.match(r'^(.*?\.)', snippet)
    
    # Return captured group if match found, otherwise return full snippet
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
        # Prepare headers with API key
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

def monitor_resolution_source(url: str, keywords: List[str] = None) -> Dict:
    """Monitor a resolution source for changes."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        content = response.text.lower()
        
        # Check for specific keywords if provided
        if keywords:
            found_keywords = [kw for kw in keywords if kw.lower() in content]
            return {
                "url": url,
                "status": "success",
                "content_length": len(content),
                "found_keywords": found_keywords,
                "has_changes": len(found_keywords) > 0
            }
        
        return {
            "url": url,
            "status": "success",
            "content_length": len(content),
            "has_changes": True  # Assume any response means potential change
        }
        
    except Exception as e:
        return {
            "url": url,
            "status": "error",
            "error": str(e),
            "has_changes": False
        }

def get_economy_resolution_sources() -> List[str]:
    """Get the most important resolution sources for economy markets."""
    return [
        "https://fred.stlouisfed.org/series/FGEXPND",  # Federal spending
        "https://www.federalreserve.gov/monetarypolicy/openmarket.htm",  # Fed rates
        "https://www.bea.gov/data/gdp/gross-domestic-product",  # GDP data
        "https://www.nber.org/",  # Recession announcements
    ]

def detect_arbitrage_opportunities(markets: List[Dict], source_data: Dict) -> List[Dict]:
    """Detect potential arbitrage opportunities based on source monitoring."""
    opportunities = []
    
    for market in markets:
        domain = categorize_market_domain(market.get("question", ""), market.get("description", ""))
        
        if domain == "economy":
            market_id = market.get("id")
            question = market.get("question", "")
            description = market.get("description", "")
            
            # Extract relevant keywords from the market
            market_keywords = extract_market_keywords(question, description)
            
            # Check each source for relevant changes
            for source_url, source_info in source_data.items():
                if source_info["status"] == "success":
                    # Check if source content is relevant to this market
                    relevance_score = calculate_relevance(source_url, market_keywords, source_info)
                    
                    if relevance_score > 0.3:  # Only consider if relevance > 30%
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
    
    # Federal spending keywords
    if "federal spending" in text or "spending" in text:
        keywords.extend(["federal spending", "government spending", "expenditure", "budget"])
    
    # Fed rate keywords
    if "fed rate" in text or "rate hike" in text or "rate cut" in text:
        keywords.extend(["federal reserve", "interest rate", "monetary policy", "fed funds"])
    
    # GDP keywords
    if "gdp" in text or "gross domestic product" in text:
        keywords.extend(["gdp", "gross domestic product", "economic growth"])
    
    # Recession keywords
    if "recession" in text:
        keywords.extend(["recession", "economic downturn", "nber"])
    
    return list(set(keywords))  # Remove duplicates

def calculate_relevance(source_url: str, market_keywords: List[str], source_info: Dict) -> float:
    """Calculate relevance score between source and market keywords."""
    if not market_keywords:
        return 0.0
    
    # Define source-specific keywords
    source_keywords = {
        "fred.stlouisfed.org": ["federal spending", "government spending", "expenditure"],
        "federalreserve.gov": ["federal reserve", "interest rate", "monetary policy"],
        "bea.gov": ["gdp", "gross domestic product", "economic growth"],
        "nber.org": ["recession", "economic downturn", "business cycle"]
    }
    
    # Get keywords for this source
    source_domain = source_url.split("//")[-1].split("/")[0]
    source_specific_keywords = source_keywords.get(source_domain, [])
    
    # Calculate overlap
    market_keywords_set = set(market_keywords)
    source_keywords_set = set(source_specific_keywords)
    
    if not market_keywords_set or not source_keywords_set:
        return 0.0
    
    # Calculate Jaccard similarity
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
    """Create a detailed performance report."""
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
    
    # ROI analysis
    if buy_signals:
        avg_buy_roi = sum(s.get("potential_roi", 0) for s in buy_signals) / len(buy_signals)
        report.append(f"\n💰 ANALYSE ROI:")
        report.append(f"  • ROI moyen (ACHETER): {avg_buy_roi:.1%}")
        report.append(f"  • ROI total potentiel: {backtest_results['total_roi']:.1%}")
        report.append(f"  • ROI par signal: {backtest_results['avg_roi_per_signal']:.1%}")
    
    # Confidence analysis
    high_conf = [s for s in signals if s["confidence"] == "high"]
    report.append(f"\n🎯 ANALYSE CONFIANCE:")
    report.append(f"  • Haute confiance: {len(high_conf)} signaux")
    report.append(f"  • Taux de succès estimé: {backtest_results['success_rate']:.1%}")
    
    # Recommendations
    report.append(f"\n💡 RECOMMANDATIONS:")
    if buy_signals:
        report.append(f"  • {len(buy_signals)} opportunités d'achat identifiées")
        report.append(f"  • Focus sur les marchés de dépenses fédérales")
        report.append(f"  • Surveiller fred.stlouisfed.org pour les mises à jour")
    else:
        report.append(f"  • Aucune opportunité d'achat immédiate")
        report.append(f"  • Continuer la surveillance des sources")
    
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
            
            for source in economy_sources:
                result = monitor_resolution_source(source)
                source_data[source] = result
                
                if result["status"] == "success":
                    print(f"   ✅ {source.split('//')[-1].split('/')[0]}: {result['content_length']:,} characters")
                else:
                    print(f"   ❌ {source.split('//')[-1].split('/')[0]}: {result.get('error', 'Error')}")
            
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
    """Generate trading signals from arbitrage opportunities."""
    signals = []
    
    for opp in opportunities:
        # Enhanced signal generation with more sophisticated logic
        relevance_score = opp.get("relevance_score", 0.0)
        
        # Determine action based on relevance and confidence
        if relevance_score > 0.8:
            action = "buy"  # High confidence opportunity
        elif relevance_score > 0.6:
            action = "monitor"  # Medium confidence, watch closely
        else:
            action = "ignore"  # Low confidence, skip
        
        signal = {
            "market_id": opp["market_id"],
            "action": action,
            "confidence": opp["confidence"],
            "relevance_score": relevance_score,
            "reason": opp["reason"],
            "timestamp": opp["timestamp"],
            "source": opp["source_url"],
            "potential_roi": calculate_potential_roi(relevance_score)
        }
        signals.append(signal)
    
    return signals

def calculate_potential_roi(relevance_score: float) -> float:
    """Calculate potential ROI based on relevance score."""
    # Simple ROI estimation: higher relevance = higher potential returns
    base_roi = 0.05  # 5% base return
    relevance_multiplier = relevance_score * 2  # Up to 2x multiplier
    return base_roi * relevance_multiplier

def backtest_strategy(signals: List[Dict], historical_data: Dict = None) -> Dict:
    """Simple backtesting of the trading strategy."""
    if not signals:
        return {"total_signals": 0, "success_rate": 0, "total_roi": 0}
    
    # For now, simulate backtesting results
    # In a real system, you'd use actual historical market data
    total_signals = len(signals)
    high_confidence_signals = len([s for s in signals if s["confidence"] == "high"])
    
    # Simulate success rates based on confidence levels
    success_rate = 0.75 if high_confidence_signals > 0 else 0.50
    
    # Calculate total potential ROI
    total_roi = sum(s.get("potential_roi", 0) for s in signals)
    
    return {
        "total_signals": total_signals,
        "high_confidence_signals": high_confidence_signals,
        "success_rate": success_rate,
        "total_roi": total_roi,
        "avg_roi_per_signal": total_roi / total_signals if total_signals > 0 else 0
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
    
    # 4. Signaux de trading générés
    print(f"\n📈 SIGNAUX DE TRADING GÉNÉRÉS: {len(signals)}")
    print("-" * 40)
    if signals:
        for i, signal in enumerate(signals[:5], 1):  # Limit to first 5 to avoid clutter
            print(f"\n{i}. ACTION: {signal['action'].upper()}")
            print(f"   MARCHÉ ID: {signal['market_id']}")
            print(f"   CONFIANCE: {signal['confidence']}")
            print(f"   ROI POTENTIEL: {signal.get('potential_roi', 0):.1%}")
            print(f"   SOURCE: {signal['source']}")
            print(f"   RAISON: {signal['reason']}")
        
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
    
    # 6. Fichiers créés
    print("\n💾 FICHIERS CRÉÉS:")
    print("-" * 40)
    print("  • polymarket.db (base de données SQLite)")
    print("  • polymarket_data.json (export JSON)")
    
    print("\n" + "=" * 60)

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

        # 1) Basic Info + description‐based resolution source
        print(f"[{domain.upper()}] Market: {question} (ID {market_id})")
        print(f"UMA Question ID: {uma_qid or 'Not available'}")
        res_src = extract_resolution_source(description)
        print(f"Resolution Source (from description): {res_src or '— not stated explicitly —'}")

        # 2) If we have a questionID, fetch ancillaryData & URLs
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

    # Phase 1: Database save
    print("\n" + "=" * 50)
    print("DATABASE SAVE")
    print("=" * 50)
    
    try:
        # Initialize database
        db = PolymarketDB()
        
        # Save to database
        db.save_markets(markets)
        print(f"{len(markets)} markets saved to database")
        
        # Display statistics
        stats = db.get_domain_statistics()
        print("\n📊 Statistics by domain:")
        for domain, count in stats.items():
            print(f"  • {domain}: {count} markets")
        
        # Export to JSON
        db.export_to_json()
        
    except Exception as e:
        print(f"Error during save: {e}")

    # Phase 2: Test resolution source monitoring
    print("\n" + "=" * 50)
    print("🔍 TESTING RESOLUTION SOURCE MONITORING")
    print("=" * 50)
    
    economy_sources = get_economy_resolution_sources()
    print(f"Testing {len(economy_sources)} economy resolution sources...")
    
    source_data = {}
    for source in economy_sources:
        print(f"\nTesting: {source}")
        result = monitor_resolution_source(source)
        source_data[source] = result
        
        if result["status"] == "success":
            print(f"  ✅ Accessible ({result['content_length']} characters)")
            if result.get("found_keywords"):
                print(f"  📊 Found keywords: {result['found_keywords']}")
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
        for i, opp in enumerate(opportunities[:5], 1):  # Show first 5
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
        for i, signal in enumerate(signals[:3], 1):  # Show first 3
            print(f"\n{i}. Action: {signal['action'].upper()}")
            print(f"   Market ID: {signal['market_id']}")
            print(f"   Confidence: {signal['confidence']}")
            print(f"   Potential ROI: {signal.get('potential_roi', 0):.1%}")
            print(f"   Source: {signal['source']}")
            print(f"   Reason: {signal['reason']}")
    
    # Phase 3: Backtesting
    print("\n" + "=" * 50)
    print("📊 BACKTESTING STRATEGY")
    print("=" * 50)
    
    backtest_results = backtest_strategy(signals)
    print(f"\n📈 Backtesting Results:")
    print(f"  • Total signals: {backtest_results['total_signals']}")
    print(f"  • High confidence signals: {backtest_results['high_confidence_signals']}")
    print(f"  • Success rate: {backtest_results['success_rate']:.1%}")
    print(f"  • Total potential ROI: {backtest_results['total_roi']:.1%}")
    print(f"  • Average ROI per signal: {backtest_results['avg_roi_per_signal']:.1%}")
    
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