"""
Typo-Resilient Mapping & Fuzzy Pre-Processing Module
Maps noisy, misspelled, or colloquial company names/tickers to valid ticker symbols.
Dynamically ingests companies.json (~8,000+ major global companies) for comprehensive coverage.
Protected against stopword collisions, email signatures, and HTML artifacts.
"""
import os
import json
import re
import logging
import unicodedata
from typing import Optional, Tuple, List, Dict, Set

logger = logging.getLogger(__name__)

try:
    from rapidfuzz import process, fuzz
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False


# High-priority primary company names mapping (Always checked first!)
PRIMARY_COMPANY_NAMES = {
    "apple": "AAPL",
    "iphone": "AAPL",
    "ipad": "AAPL",
    "macbook": "AAPL",
    "microsoft": "MSFT",
    "windows": "MSFT",
    "xbox": "MSFT",
    "google": "GOOGL",
    "alphabet": "GOOGL",
    "youtube": "GOOGL",
    "amazon": "AMZN",
    "aws": "AMZN",
    "tesla": "TSLA",
    "elon": "TSLA",
    "nvidia": "NVDA",
    "meta": "META",
    "facebook": "META",
    "instagram": "META",
    "netflix": "NFLX",
    "amd": "AMD",
    "intel": "INTC",
    "salesforce": "CRM",
    "coca cola": "KO",
    "coke": "KO",
    "pepsi": "PEP",
    "disney": "DIS",
    "walmart": "WMT",
    "costco": "COST",
    "jpmorgan": "JPM",
    "chase": "JPM",
    "visa": "V",
    "mastercard": "MA",
    "bitcoin": "BTC-USD",
    "ethereum": "ETH-USD",
    "sp500": "SPY",
    "nasdaq": "QQQ",
    "tata motors": "TATAMOTORS.NS",
    "tatamotors": "TATAMOTORS.NS",
    "tata consultancy services": "TCS.NS",
    "tata consultancy": "TCS.NS",
    "tata sons": "TCS.NS",
    "tata steel": "TATASTEEL.NS",
    "tata power": "TATAPOWER.NS",
    "reliance": "RELIANCE.NS",
    "reliance industries": "RELIANCE.NS",
    "tcs": "TCS.NS",
    "infosys": "INFY.NS",
    "hdfc": "HDFCBANK.NS",
    "icici": "ICICIBANK.NS",
    "wipro": "WIPRO.NS",
}

# Words that should NEVER be loosely matched to tickers (prevents collisions like for->FOR, can->CAN, it->IT)
STOPWORDS = {
    "from", "com", "org", "net", "mail", "email", "gmail", "sent", "iphone",
    "price", "stock", "stocks", "cost", "quote", "chart", "data", "send", "show",
    "what", "is", "the", "for", "me", "to", "at", "in", "on", "a", "an", "and",
    "or", "it", "its", "that", "this", "can", "you", "please", "check", "tell",
    "hi", "hello", "hey", "thanks", "thank", "bye", "good", "morning", "re", "fwd",
    "give", "get", "view", "both", "all", "compare", "vs", "versus", "against",
    "now", "see", "are", "be", "do", "by", "if", "not", "so", "up", "us", "we",
    "max", "min", "two", "one", "three", "both", "csv", "sheet", "sheets", "excel", "table",
    # Time expressions & typos that must NEVER match stock tickers (prevents 'monts' -> MNTS)
    "month", "months", "mont", "monts", "nont", "nonts", "mon", "mons", "mo", "mos",
    "year", "years", "yr", "yrs", "week", "weeks", "wk", "wks", "day", "days",
    "daily", "weekly", "monthly", "yearly", "annual", "annually",
    "last", "past", "next", "ago", "period", "time", "date", "dates", "range",
    "session", "sessions", "history", "historical", "latest", "recent",
    "intraday", "today", "yesterday", "tomorrow", "quarter", "quarterly"
}

# Regex to strip time intervals before extracting tickers
TIME_PATTERN_REGEX = re.compile(
    r"\b(?:last|past|next|in)?\s*\d*\s*(?:month|months|mont|monts|nont|nonts|mon|mons|mo|mos|year|years|yr|yrs|week|weeks|wk|wks|day|days|quarter|quarterly)\b",
    re.IGNORECASE
)

# Corporate suffixes to strip for canonical matching
SUFFIX_PATTERN = re.compile(
    r"\b(inc\.?|incorporated|corp\.?|corporation|ltd\.?|limited|co\.?|company|plc|pjsc|group|holdings|class\s+[a-z]|sa|nv|ag|se|spa|ab|oyj)\b",
    re.IGNORECASE
)


def normalize_text(text: str) -> str:
    """Decomposes accents (e.g., Nestlé -> nestle) and normalizes whitespace."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_text = nfkd.encode("ASCII", "ignore").decode("utf-8")
    cleaned = re.sub(r"[^\w\s\-\.]", " ", ascii_text.lower())
    return " ".join(cleaned.split())


# Global storage for dynamically loaded companies dataset
COMPANY_NAMES_MAP: Dict[str, str] = dict(PRIMARY_COMPANY_NAMES)
TICKER_NAMES: Dict[str, str] = {
    "AAPL": "Apple Inc.",
    "MSFT": "Microsoft Corp.",
    "GOOGL": "Alphabet Inc. (Google)",
    "AMZN": "Amazon.com Inc.",
    "TSLA": "Tesla Inc.",
    "NVDA": "NVIDIA Corp.",
    "META": "Meta Platforms Inc.",
    "NFLX": "Netflix Inc.",
    "CRM": "Salesforce, Inc.",
    "AMD": "Advanced Micro Devices",
    "INTC": "Intel Corp.",
    "SPY": "SPDR S&P 500 ETF Trust",
    "QQQ": "Invesco QQQ Trust",
    "DIS": "The Walt Disney Company",
    "KO": "The Coca-Cola Company",
    "PEP": "PepsiCo Inc.",
    "COST": "Costco Wholesale",
    "WMT": "Walmart Inc.",
    "JPM": "JPMorgan Chase & Co.",
    "V": "Visa Inc.",
    "BTC-USD": "Bitcoin USD",
    "ETH-USD": "Ethereum USD",
    "TATAMOTORS.NS": "Tata Motors Ltd.",
    "RELIANCE.NS": "Reliance Industries Ltd.",
    "TCS.NS": "Tata Consultancy Services",
    "INFY.NS": "Infosys Ltd.",
    "HDFCBANK.NS": "HDFC Bank Ltd.",
}
KNOWN_TICKERS: Set[str] = set(TICKER_NAMES.keys())
TICKER_DICTIONARY: Dict[str, str] = {k.lower(): k for k in KNOWN_TICKERS}


def _load_companies_dataset():
    """
    Dynamically loads companies.json into the matcher dictionaries.
    Handles ~8,000+ global company names, parenthetical aliases, and suffix stripping.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(script_dir, "companies.json"),
        os.path.join(script_dir, "companies.jason"),
        "companies.json",
        "companies.jason"
    ]

    loaded = False
    for path in candidates:
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    companies_data = json.load(f)

                count = 0
                for item in companies_data:
                    cname = item.get("company_name", "").strip()
                    code = item.get("stock_code", "").strip().upper()
                    if not cname or not code:
                        continue

                    count += 1
                    KNOWN_TICKERS.add(code)
                    TICKER_DICTIONARY[code.lower()] = code
                    if code not in TICKER_NAMES:
                        TICKER_NAMES[code] = cname

                    # 1. Full normalized name
                    norm_name = normalize_text(cname)
                    if norm_name and norm_name not in COMPANY_NAMES_MAP and norm_name not in STOPWORDS:
                        COMPANY_NAMES_MAP[norm_name] = code

                    # 2. Parentheses names (e.g., 'Alphabet (Google)' -> 'google' & 'alphabet')
                    parens = re.findall(r"\((.*?)\)", cname)
                    for p in parens:
                        norm_p = normalize_text(p)
                        if norm_p and norm_p not in COMPANY_NAMES_MAP and norm_p not in STOPWORDS:
                            COMPANY_NAMES_MAP[norm_p] = code

                    base_name = re.sub(r"\(.*?\)", "", cname).strip()
                    norm_base = normalize_text(base_name)
                    if norm_base and norm_base not in COMPANY_NAMES_MAP and norm_base not in STOPWORDS:
                        COMPANY_NAMES_MAP[norm_base] = code

                    # 3. Strip corporate suffixes (e.g. 'Toshiba Corp' -> 'toshiba')
                    stripped = SUFFIX_PATTERN.sub("", norm_base).strip()
                    cleaned_stripped = re.sub(r"\s+", " ", stripped).strip()
                    if cleaned_stripped and len(cleaned_stripped) >= 3:
                        if cleaned_stripped not in COMPANY_NAMES_MAP and cleaned_stripped not in STOPWORDS:
                            COMPANY_NAMES_MAP[cleaned_stripped] = code

                logger.info(f"Loaded {count} companies from {os.path.basename(path)}. Total mapped company aliases: {len(COMPANY_NAMES_MAP)}")
                loaded = True
                break
            except Exception as e:
                logger.warning(f"Failed loading companies list from {path}: {e}")

    if not loaded:
        logger.info("companies.json not found; continuing with built-in primary stock dictionary.")


# Execute load once at import time
_load_companies_dataset()


class TickerMatcher:
    """
    High-speed fuzzy ticker resolution engine.
    Applies multi-word company matching across 8,000+ companies first,
    followed by explicit ticker detection and safe typo fuzzy matching.
    """

    def __init__(self, confidence_threshold: float = 70.0):
        self.threshold = confidence_threshold
        self.primary_names = PRIMARY_COMPANY_NAMES
        self.company_names_map = COMPANY_NAMES_MAP
        self.ticker_names = TICKER_NAMES
        self.known_tickers = KNOWN_TICKERS
        self.dictionary = TICKER_DICTIONARY
        self.fuzzy_keys = list(self.company_names_map.keys())

    def clean_text(self, text: str) -> str:
        """Sanitizes text for token comparison."""
        return normalize_text(text)

    def extract_ticker_from_text(self, query: str) -> Tuple[Optional[str], float, Optional[str], bool]:
        """
        Extracts the most probable ticker symbol from query text.
        Returns:
            (ticker, confidence, matched_name, is_fuzzy)
        """
        if not query or not query.strip():
            return None, 0.0, None, False

        # 1. EXPLICIT TICKER CHECK: $AAPL, $TSLA, $2222.SR, $MSFT
        explicit_tickers = re.findall(r"\$([A-Z0-9\.\-]{1,10})\b", query)
        if explicit_tickers:
            t = explicit_tickers[0].upper()
            return t, 100.0, self.ticker_names.get(t, t), False

        cleaned = normalize_text(query)
        words = cleaned.split()
        num_words = len(words)

        # 2. MULTI-WORD GREEDY EXACT MATCHING (4-grams down to 1-grams)
        # Matches: "saudi aramco", "novo nordisk", "johnson & johnson", "tata motors", "apple", etc.
        for n in range(min(5, num_words), 0, -1):
            for i in range(num_words - n + 1):
                phrase = " ".join(words[i:i+n])
                if phrase in STOPWORDS:
                    continue

                # Check primary names first
                if phrase in self.primary_names:
                    ticker = self.primary_names[phrase]
                    return ticker, 100.0, self.ticker_names.get(ticker, phrase.title()), False

                # Check companies dataset
                if phrase in self.company_names_map:
                    ticker = self.company_names_map[phrase]
                    return ticker, 100.0, self.ticker_names.get(ticker, phrase.title()), False

        # 3. UPPERCASE EXACT TICKERS FROM RAW QUERY (e.g., TSLA, NVDA, 6502.T, 005930.KS)
        raw_words = query.split()
        for rw in raw_words:
            clean_rw = rw.strip("$.,!?:;\"'()[]{}").upper()
            # Must be in known tickers and not match innocent English stopwords (like FOR, IN, IS, IT, ME, ON, CAN)
            if clean_rw in self.known_tickers and clean_rw.lower() not in STOPWORDS:
                return clean_rw, 100.0, self.ticker_names.get(clean_rw, clean_rw), False

        # 4. TYPO-RESILIENT FUZZY MATCHING (>= 75% threshold on phrases and words)
        if RAPIDFUZZ_AVAILABLE and self.fuzzy_keys:
            best_match = None
            best_score = 0.0
            best_key = None

            # Generate candidate n-gram phrases (5-grams down to 1-grams)
            candidate_phrases = []
            for n in range(min(5, num_words), 0, -1):
                for i in range(num_words - n + 1):
                    p_words = [w for w in words[i:i+n] if w not in STOPWORDS]
                    if not p_words:
                        continue
                    cand = " ".join(p_words)
                    if len(cand) >= 4 and cand not in candidate_phrases:
                        candidate_phrases.append(cand)

            for cand in candidate_phrases:
                # Use token_sort_ratio for multi-word resilience and ratio for single tokens
                scorer = fuzz.token_sort_ratio if " " in cand else fuzz.ratio
                result = process.extractOne(
                    cand,
                    self.fuzzy_keys,
                    scorer=scorer,
                    score_cutoff=max(self.threshold, 75.0)
                )
                if result:
                    match_key, score, _ = result
                    # Bias towards longer matching candidate phrases to avoid single-word false matches
                    weighted_score = score + (min(len(cand.split()), 3) * 0.5)
                    if weighted_score > best_score:
                        best_score = weighted_score
                        best_key = match_key
                        best_match = self.company_names_map[match_key]

            if best_match and best_score >= max(self.threshold, 75.0):
                matched_name = self.ticker_names.get(best_match, best_key.title())
                return best_match, round(min(best_score, 100.0), 1), matched_name, True

        return None, 0.0, None, False

    def extract_all_tickers(self, query: str) -> List[Tuple[str, str]]:
        """
        Extracts all recognized tickers mentioned in a multi-stock query (e.g. for comparisons).
        Returns a list of tuples: [(ticker, company_name), ...]
        """
        if not query or not query.strip():
            return []

        # Strip explicit time expressions so time words ('last 6 monts') never match tickers (e.g. 'MNTS')
        query_no_time = TIME_PATTERN_REGEX.sub(" ", query)
        query_no_time = " ".join(query_no_time.split())

        results = []
        seen = set()

        # 1. Split on comparison delimiters ('and', '&', 'vs', 'versus', 'against', comma, semicolon)
        segments = re.split(r"[\s,]+(?:and|&|vs|versus|against)[\s,]+|[,;]", query_no_time, flags=re.IGNORECASE)
        for seg in segments:
            seg_clean = seg.strip()
            if not seg_clean:
                continue
            ticker, _, name, _ = self.extract_ticker_from_text(seg_clean)
            if ticker and ticker not in seen:
                seen.add(ticker)
                results.append((ticker, name or ticker))

        # 2. Sequential multi-pass fallback: ONLY run if the query explicitly expressed comparison intent
        has_compare_intent = any(w in query.lower() for w in [
            "compare", "comparison", "comparision", "comparing", "comparative",
            " vs ", " vs. ", " versus ", " against ", " diff ", " difference ", " between ", " both "
        ])
        if len(results) < 2 and has_compare_intent:
            cleaned = normalize_text(query_no_time)
            # Remove intent keywords so they don't corrupt candidate phrases
            cleaned_stripped = re.sub(
                r"\b(stock|stocks|of|price|chart|graph|trend|comparision|comparison|compare|comparing|versus|against|and|both|the|for|in|me|please|between|diff|difference)\b",
                " ",
                cleaned
            )
            sub_words = cleaned_stripped.split()
            for n in range(min(4, len(sub_words)), 0, -1):
                for i in range(len(sub_words) - n + 1):
                    phrase = " ".join(sub_words[i:i+n])
                    if len(phrase) < 3 or phrase in STOPWORDS:
                        continue
                    t, _, n_name, _ = self.extract_ticker_from_text(phrase)
                    if t and t not in seen:
                        seen.add(t)
                        results.append((t, n_name or t))
                        if len(results) >= 2:
                            break
                if len(results) >= 2:
                    break

        return results

