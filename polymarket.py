import re
import requests
import os
import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ——— Configurable Endpoints ———
GAMMA_API = os.getenv("GAMMA_API", "https://gamma-api.polymarket.com/markets")
GRAPHQL_URL = os.getenv("GRAPHQL_URL", "https://gateway.thegraph.com/api/subgraphs/id/81Dm16JjuFSrqz813HysXoUPvzTwE7fsfPk2RTf66nyC")
GRAPH_API_KEY = os.getenv("GRAPH_API_KEY", "")

# ——— Helper Functions ———

def fetch_open_markets() -> List[Dict]:
    """Retrieve all open (unfinished) markets from the Polymarket Gamma API."""
    resp = requests.get(GAMMA_API, params={"closed": "false"})
    resp.raise_for_status()
    data = resp.json()
    # Some deployments wrap results in {"data": [...]}; handle both cases
    return data.get("data", data) if isinstance(data, dict) else data

def extract_resolution_source(description: str) -> Optional[str]:
    """
    Extract the sentence containing 'Resolution Source:' from a market description.
    Returns the snippet or None if not found.
    """
    idx = description.lower().find("resolution source")
    if idx == -1:
        return None
    snippet = description[idx:]
    # Grab through the first period (end of sentence)
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
        """Export all data to JSON file."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM markets")
            columns = [description[0] for description in cursor.description]
            markets = []
            for row in cursor.fetchall():
                markets.append(dict(zip(columns, row)))
            
            stats = self.get_domain_statistics()
            
            data = {
                "export_date": datetime.now().isoformat(),
                "statistics": stats,
                "markets": markets
            }
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            print(f"Data exported to {filename}")
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

if __name__ == "__main__":
    main() 