"""
scraper.py — Daily gold price scraper for Indian cities
Sources: GoodReturns.in (city-wise 22K & 24K rates)

Parsing strategy (in order):
  1. "Today Gold Price Per Gram" table  → columns: Gram | 24K | 22K | 18K
  2. "Last 10 Days" table               → columns: Date | 24K | 22K  (most recent row)
  3. File cache                         → last successful scrape saved to output/price_cache.json

On weekends / market holidays GoodReturns sometimes doesn't update the Today table,
so strategies 2 and 3 ensure we always return the last closing price.
"""

import json
import time
import requests
from bs4 import BeautifulSoup
from datetime import date
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

CACHE_FILE = Path(__file__).parent / "output" / "price_cache.json"

STATE_CITIES = {
    "tamil_nadu": [
        ("Chennai", "chennai"),
        ("Coimbatore", "coimbatore"),
        ("Madurai", "madurai"),
    ],
    "andhra_pradesh": [
        ("Vijayawada", "vijayawada"),
        ("Visakhapatnam", "visakhapatnam"),
        ("Guntur", "guntur"),
    ],
    "telangana": [
        ("Hyderabad", "hyderabad"),
        ("Warangal", "warangal"),
    ],
    "karnataka": [
        ("Bengaluru", "bangalore"),
        ("Mysuru", "mysore"),
        ("Mangaluru", "mangalore"),
    ],
    "kerala": [
        ("Kochi", "kochi"),
        ("Thiruvananthapuram", "thiruvananthapuram"),
        ("Kozhikode", "calicut"),
    ],
    "maharashtra": [
        ("Mumbai", "mumbai"),
        ("Pune", "pune"),
        ("Nagpur", "nagpur"),
    ],
    "west_bengal": [("Kolkata", "kolkata")],
    "delhi":       [("Delhi", "delhi")],
    "gujarat": [
        ("Ahmedabad", "ahmedabad"),
        ("Surat", "surat"),
    ],
    "rajasthan": [
        ("Jaipur", "jaipur"),
        ("Jodhpur", "jodhpur"),
    ],
    "punjab": [
        ("Amritsar", "amritsar"),
        ("Ludhiana", "ludhiana"),
    ],
    "uttar_pradesh": [
        ("Lucknow", "lucknow"),
        ("Agra", "agra"),
        ("Kanpur", "kanpur"),
    ],
    "madhya_pradesh": [
        ("Bhopal", "bhopal"),
        ("Indore", "indore"),
    ],
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

REQUEST_RETRIES = 3
REQUEST_BACKOFF_SECONDS = 2


# ── Price parsing helpers ─────────────────────────────────────────────────────

def _parse_price(text: str) -> int:
    """Extract integer from text like '₹14,275  (+142)' or 'Rs. 55,000'."""
    import re
    # Strip everything after '(' to ignore the change indicator
    text = re.sub(r'\(.*', '', text)
    cleaned = text.replace("₹", "").replace("Rs.", "").replace(",", "").strip()
    try:
        return int(float(cleaned))
    except (ValueError, TypeError):
        return 0


def _city_url(city_slug: str) -> str:
    return f"https://www.goodreturns.in/gold-rates/{city_slug}.html"


def _get_with_retries(url: str) -> requests.Response:
    last_error = None
    for attempt in range(1, REQUEST_RETRIES + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            last_error = e
            if attempt == REQUEST_RETRIES:
                break
            wait_seconds = REQUEST_BACKOFF_SECONDS * attempt
            logger.warning(
                f"Fetch failed for {url} on attempt {attempt}/{REQUEST_RETRIES}: {e}. "
                f"Retrying in {wait_seconds}s"
            )
            time.sleep(wait_seconds)
    raise last_error


def _col_index(headers: list, *keywords) -> int | None:
    """Return first column index whose header contains any of the keywords."""
    for kw in keywords:
        for i, h in enumerate(headers):
            if kw in h:
                return i
    return None


# ── Table parsers ─────────────────────────────────────────────────────────────

def _parse_today_table(soup) -> dict:
    """
    Parse the 'Today Gold Price Per Gram' table.
    New format:  Gram | 24K | 22K | 18K  — find the row where Gram == "1"
    Old format:  row labels are '22 Carat Gold' / '24 Carat Gold'
    """
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        header_cells = rows[0].find_all(["th", "td"])
        headers = [c.get_text(strip=True).lower() for c in header_cells]

        # ── New format ──────────────────────────────────────────────────────
        idx_22 = _col_index(headers, "22k", "22 k")
        idx_24 = _col_index(headers, "24k", "24 k")

        if idx_22 is not None or idx_24 is not None:
            for row in rows[1:]:
                cols = row.find_all("td")
                if not cols:
                    continue
                if cols[0].get_text(strip=True).strip() == "1":   # 1-gram row
                    prices = {}
                    if idx_22 is not None and idx_22 < len(cols):
                        v = _parse_price(cols[idx_22].get_text(strip=True))
                        if v > 1000:
                            prices["22k_per_gram"] = v
                            prices["22k_per_10g"]  = v * 10
                    if idx_24 is not None and idx_24 < len(cols):
                        v = _parse_price(cols[idx_24].get_text(strip=True))
                        if v > 1000:
                            prices["24k_per_gram"] = v
                            prices["24k_per_10g"]  = v * 10
                    if prices.get("22k_per_gram", 0) > 0:
                        return prices

        # ── Old format ──────────────────────────────────────────────────────
        prices = {}
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 2:
                continue
            label = cols[0].get_text(strip=True)
            if "22" in label and ("carat" in label.lower() or "karat" in label.lower()):
                v = _parse_price(cols[1].get_text(strip=True))
                if v > 1000:
                    prices["22k_per_10g"]  = v
                    prices["22k_per_gram"] = round(v / 10)
            elif "24" in label and ("carat" in label.lower() or "karat" in label.lower()):
                v = _parse_price(cols[1].get_text(strip=True))
                if v > 1000:
                    prices["24k_per_10g"]  = v
                    prices["24k_per_gram"] = round(v / 10)
        if prices.get("22k_per_gram", 0) > 0:
            return prices

    return {}


def _parse_historical_table(soup) -> dict:
    """
    Parse the 'Last 10 Days' table and return the most recent row.
    Format:  Date | 24K | 22K
    Returns prices dict with an extra '_source_date' key.
    """
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        header_cells = rows[0].find_all(["th", "td"])
        headers = [c.get_text(strip=True).lower() for c in header_cells]

        idx_date = _col_index(headers, "date")
        idx_22   = _col_index(headers, "22k", "22 k")
        idx_24   = _col_index(headers, "24k", "24 k")

        # Must have a Date column AND at least one price column
        if idx_date is None or (idx_22 is None and idx_24 is None):
            continue

        # First data row = most recent market day
        first = rows[1]
        cols  = first.find_all("td")
        if not cols:
            continue

        prices = {}
        source_date = cols[idx_date].get_text(strip=True) if idx_date < len(cols) else "unknown"

        if idx_22 is not None and idx_22 < len(cols):
            v = _parse_price(cols[idx_22].get_text(strip=True))
            if v > 1000:
                prices["22k_per_gram"] = v
                prices["22k_per_10g"]  = v * 10

        if idx_24 is not None and idx_24 < len(cols):
            v = _parse_price(cols[idx_24].get_text(strip=True))
            if v > 1000:
                prices["24k_per_gram"] = v
                prices["24k_per_10g"]  = v * 10

        if prices.get("22k_per_gram", 0) > 0:
            prices["_source_date"] = source_date
            return prices

    return {}


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _load_cache() -> dict:
    try:
        if CACHE_FILE.exists():
            return json.loads(CACHE_FILE.read_text())
    except Exception:
        pass
    return {}


def _save_cache(state_key: str, result: dict) -> None:
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        cache = _load_cache()
        # Don't cache a result that is itself from cache
        if not result.get("cached"):
            cache[state_key] = result
            CACHE_FILE.write_text(json.dumps(cache, indent=2, ensure_ascii=False))
    except Exception as e:
        logger.warning(f"Could not save price cache: {e}")


def _prices_are_valid(result: dict) -> bool:
    cities = result.get("cities", {})
    if not cities:
        return False
    required_fields = ("22k_per_gram", "24k_per_gram", "22k_per_10g", "24k_per_10g")
    return all(
        all((prices or {}).get(field_name, 0) > 0 for field_name in required_fields)
        for prices in cities.values()
    )


# ── Core city scraper ─────────────────────────────────────────────────────────

def fetch_city_gold_price(city_slug: str) -> dict:
    """
    Fetch 22K / 24K gold price for a city from GoodReturns.
    Returns: {"22k_per_gram": int, "24k_per_gram": int, "22k_per_10g": int,
              "24k_per_10g": int}
    Also returns "_source_date" key (only set when using historical data).
    Returns {} on complete failure.
    """
    url = _city_url(city_slug)
    logger.info(f"  Source URL: {url}")
    try:
        resp = _get_with_retries(url)
        soup = BeautifulSoup(resp.text, "html.parser")

        # 1️⃣  Today's price table
        prices = _parse_today_table(soup)
        if prices.get("22k_per_gram", 0) > 0:
            return prices

        # 2️⃣  Last 10 days table (same page, no extra request)
        prices = _parse_historical_table(soup)
        if prices.get("22k_per_gram", 0) > 0:
            src = prices.get("_source_date", "previous session")
            logger.info(f"  ℹ️  {city_slug}: using last closing price from {src}")
            return prices

        logger.warning(f"  ⚠️  {city_slug}: no prices found on page ({url})")
        return {}

    except Exception as e:
        logger.exception(f"Failed to fetch {city_slug} from {url}: {e}")
        return {}


# ── Public API ────────────────────────────────────────────────────────────────

def get_state_prices(state_key: str) -> dict:
    """
    Get prices for a single state.

    Result always includes:
      "cached"      — True if we fell back to the file cache
      "cached_date" — date string of the cached data (when cached=True)

    When individual cities use the on-page historical table (weekend / holiday),
    that is reflected per-city via '_source_date' in the city dict.
    """
    today = date.today().strftime("%d %b %Y")
    result = {
        "date": today,
        "state": state_key,
        "cities": {},
        "source_urls": {},
        "cached": False,
        "cached_date": None,
    }

    cities = STATE_CITIES.get(state_key, [])
    for city_name, city_slug in cities:
        logger.info(f"  Fetching {city_name}...")
        result["source_urls"][city_name] = _city_url(city_slug)
        result["cities"][city_name] = fetch_city_gold_price(city_slug)

    if _prices_are_valid(result):
        _save_cache(state_key, result)
        # Check if any city used on-page historical data
        historical_dates = {
            v.pop("_source_date", None)
            for v in result["cities"].values()
            if "_source_date" in v
        }
        if historical_dates:
            most_recent = sorted(historical_dates)[-1]
            logger.info(
                f"  ⚠️  Market data from last open day ({most_recent}) — "
                f"market was closed on {today}"
            )
            result["cached"] = True
            result["cached_date"] = most_recent
        return result

    # 3️⃣  Fall back to file cache
    logger.warning(f"  No prices from web for {state_key} — trying file cache...")
    cache = _load_cache()
    if state_key in cache and _prices_are_valid(cache[state_key]):
        cached = cache[state_key]
        cached_date = cached.get("date", "previous session")
        logger.info(f"  📦 Using file-cached prices from {cached_date}")
        return {
            "date": today,
            "state": state_key,
            "cities": cached["cities"],
            "source_urls": result["source_urls"],
            "cached": True,
            "cached_date": cached_date,
        }

    logger.error(f"  ❌ No prices available (web or cache) for {state_key}")
    return result


def get_all_state_prices() -> dict:
    today = date.today().strftime("%d %b %Y")
    result = {"date": today, "states": {}}
    for state_key in STATE_CITIES:
        result["states"][state_key] = get_state_prices(state_key)
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import json as _json
    prices = get_state_prices("andhra_pradesh")
    print(_json.dumps(prices, indent=2, ensure_ascii=False))
    if prices.get("cached"):
        print(f"\n⚠️  Using closing prices from {prices['cached_date']}")
