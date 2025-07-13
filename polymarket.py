import re
import requests
from typing import List, Dict, Optional

# ——— Configurable Endpoints ———
GAMMA_API = "https://gamma-api.polymarket.com/markets"

# Any keyless or your API‐key endpoint for the Resolution Subgraph
# e.g. Goldsky public endpoint (no API key needed):
GRAPHQL_URL = (
    "https://api.goldsky.com/api/public/"
    "project_cl6mb8i9h0003e201j6li0diw"
    "/subgraphs/resolutions-subgraph/0.0.1/gn"
)

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

def fetch_ancillary_data(question_id: str) -> Optional[str]:
    """Query the Resolution Subgraph for ancillaryData of a given question ID."""
    query = """
    query ($id: ID!) {
      marketResolutions(where: { id: $id }) {
        ancillaryData
      }
    }
    """
    try:
        resp = requests.post(
            GRAPHQL_URL,
            json={"query": query, "variables": {"id": question_id}},
            timeout=5
        )
        resp.raise_for_status()
        recs = resp.json().get("data", {}).get("marketResolutions", [])
        return recs[0].get("ancillaryData") if recs else None
    except Exception:
        return None

def extract_urls(text: str) -> List[str]:
    """Return all HTTP(S) URLs found in the given text."""
    return re.findall(r'https?://[^\s,)]+', text)

# ——— Main Script ———

def main():
    markets = fetch_open_markets()
    print(f"Found {len(markets)} open markets.\n")

    for market in markets:
        market_id = market.get("id")
        slug = market.get("slug")
        question = market.get("question") or slug
        uma_qid = market.get("questionID")  # exact key from API
        description = market.get("description", "") or ""

        # 1) Basic Info + description‐based resolution source
        print(f"Market: {question} (ID {market_id})")
        print(f"UMA Question ID: {uma_qid or 'Not available'}")
        res_src = extract_resolution_source(description)
        print(f"Resolution Source (from description): {res_src or '— not stated explicitly —'}")

        # 2) If we have a questionID, fetch ancillaryData & URLs
        if uma_qid:
            anc = fetch_ancillary_data(uma_qid)
            if anc:
                print("\n  Full ancillaryData fetched from subgraph.")
                urls = extract_urls(anc)
                if urls:
                    print("  URLs mentioned in ancillaryData:")
                    for u in urls:
                        print(f"    • {u}")
                else:
                    print("  No URLs found in ancillaryData.")
            else:
                print("  Unable to fetch ancillaryData from subgraph.")
        print("-" * 60)

if __name__ == "__main__":
    main()
