"""
Typo-Resilient Mapping & Fuzzy Pre-Processing Module
Maps noisy, misspelled, or colloquial company names/tickers to valid ticker symbols.
Protected against stopword collisions, email signatures, and HTML artifacts.
"""
from typing import Optional, Tuple
import re

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
}

# Full dictionary including tickers
TICKER_DICTIONARY = {
    **PRIMARY_COMPANY_NAMES,
    "aapl": "AAPL",
    "msft": "MSFT",
    "googl": "GOOGL",
    "goog": "GOOGL",
    "amzn": "AMZN",
    "tsla": "TSLA",
    "nvda": "NVDA",
    "crm": "CRM",
    "nflx": "NFLX",
    "intc": "INTC",
    "spy": "SPY",
    "qqq": "QQQ",
    "dia": "DIA",
    "iwm": "IWM",
    "btc": "BTC-USD",
    "eth": "ETH-USD",
}

TICKER_NAMES = {
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
}

# Words that should NEVER be fuzzy-matched to tickers (prevents collision like com/from -> crm)
STOPWORDS = {
    "from", "com", "org", "net", "mail", "email", "gmail", "sent", "iphone",
    "price", "stock", "stocks", "cost", "quote", "chart", "data", "send", "show",
    "what", "is", "the", "for", "me", "to", "at", "in", "on", "a", "an", "and",
    "or", "it", "its", "that", "this", "can", "you", "please", "check", "tell",
    "hi", "hello", "hey", "thanks", "thank", "bye", "good", "morning", "re", "fwd"
}


class TickerMatcher:
    """
    High-speed fuzzy ticker resolution engine.
    Applies exact company matching first, followed by safe typo fuzzy matching.
    """

    def __init__(self, confidence_threshold: float = 70.0):
        # Set conservative threshold to 70% to prevent false positives
        self.threshold = confidence_threshold
        self.primary_names = PRIMARY_COMPANY_NAMES
        self.dictionary = TICKER_DICTIONARY
        self.keys = list(self.primary_names.keys())

    def clean_text(self, text: str) -> str:
        """Sanitizes text for token comparison."""
        cleaned = re.sub(r"[^\w\s\-\.]", " ", text.lower())
        return " ".join(cleaned.split())

    def extract_ticker_from_text(self, query: str) -> Tuple[Optional[str], float, Optional[str], bool]:
        """
        Extracts the most probable ticker symbol from query text.
        Returns:
            (ticker, confidence, matched_name, is_fuzzy)
        """
        if not query or not query.strip():
            return None, 0.0, None, False

        cleaned = self.clean_text(query)
        words = [w for w in cleaned.split() if w]

        # 1. PRIORITY CHECK: Exact word match for primary company names (e.g., "apple", "tesla")
        for word in words:
            if word in self.primary_names:
                ticker = self.primary_names[word]
                return ticker, 100.0, TICKER_NAMES.get(ticker, ticker), False

        # 2. Check uppercase explicit tickers with dollar sign or stand-alone ($AAPL, TSLA)
        explicit_tickers = re.findall(r"\$([A-Z]{1,5})\b", query)
        if explicit_tickers:
            t = explicit_tickers[0].upper()
            return t, 100.0, TICKER_NAMES.get(t, t), False

        # 3. Check exact word in full dictionary (excluding common English stopwords)
        for word in words:
            if word not in STOPWORDS and word in self.dictionary:
                ticker = self.dictionary[word]
                return ticker, 100.0, TICKER_NAMES.get(ticker, ticker), False

        # 4. Check uppercase words (e.g., AAPL) that match known tickers
        raw_words = query.split()
        for rw in raw_words:
            clean_rw = rw.strip("$.,!?:;\"'()[]{}").upper()
            if clean_rw in TICKER_NAMES:
                return clean_rw, 100.0, TICKER_NAMES[clean_rw], False

        # 5. Typo-resilient fuzzy matching on meaningful candidate tokens (>= 70% threshold)
        if RAPIDFUZZ_AVAILABLE and self.keys:
            best_match = None
            best_score = 0.0
            best_key = None

            # Only evaluate words that are NOT common English stopwords
            candidate_tokens = [w for w in words if w not in STOPWORDS and len(w) >= 3]

            for cand in candidate_tokens:
                result = process.extractOne(
                    cand,
                    self.keys,
                    scorer=fuzz.ratio,
                    score_cutoff=self.threshold
                )
                if result:
                    match_key, score, _ = result
                    if score > best_score:
                        best_score = score
                        best_key = match_key
                        best_match = self.primary_names[match_key]

            if best_match and best_score >= self.threshold:
                matched_name = TICKER_NAMES.get(best_match, best_key.capitalize())
                return best_match, round(best_score, 1), matched_name, True

        return None, 0.0, None, False
