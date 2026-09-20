"""
Typo-Resilient Mapping & Fuzzy Pre-Processing Module
Maps noisy, misspelled, or colloquial company names/tickers to valid ticker symbols.
"""
from typing import Optional, Tuple
import re

try:
    from rapidfuzz import process, fuzz
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False


# Local text lookup dictionary mapping company strings, synonyms, and colloquial terms to valid tickers
TICKER_DICTIONARY = {
    # Mega Tech
    "apple": "AAPL",
    "aapl": "AAPL",
    "iphone": "AAPL",
    "mac": "AAPL",
    "microsoft": "MSFT",
    "msft": "MSFT",
    "windows": "MSFT",
    "xbox": "MSFT",
    "google": "GOOGL",
    "googl": "GOOGL",
    "goog": "GOOGL",
    "alphabet": "GOOGL",
    "youtube": "GOOGL",
    "amazon": "AMZN",
    "amzn": "AMZN",
    "aws": "AMZN",
    "tesla": "TSLA",
    "tsla": "TSLA",
    "elon": "TSLA",
    "nvidia": "NVDA",
    "nvda": "NVDA",
    "meta": "META",
    "facebook": "META",
    "fb": "META",
    "instagram": "META",
    "netflix": "NFLX",
    "nflx": "NFLX",
    "broadcom": "AVGO",
    "avgo": "AVGO",
    "amd": "AMD",
    "advanced micro devices": "AMD",
    "intel": "INTC",
    "intc": "INTC",
    "qualcomm": "QCOM",
    "qcom": "QCOM",
    "oracle": "ORCL",
    "orcl": "ORCL",
    "salesforce": "CRM",
    "crm": "CRM",
    "adobe": "ADBE",
    "adbe": "ADBE",

    # Finance & Payments
    "jpmorgan": "JPM",
    "jp morgan": "JPM",
    "chase": "JPM",
    "jpm": "JPM",
    "visa": "V",
    "mastercard": "MA",
    "berkshire": "BRK-B",
    "berkshire hathaway": "BRK-B",
    "buffett": "BRK-B",
    "bank of america": "BAC",
    "bofa": "BAC",
    "bac": "BAC",
    "wells fargo": "WFC",
    "goldman sachs": "GS",
    "morgan stanley": "MS",
    "paypal": "PYPL",

    # Consumer & Retail
    "walmart": "WMT",
    "wmt": "WMT",
    "costco": "COST",
    "cost": "COST",
    "home depot": "HD",
    "hd": "HD",
    "nike": "NKE",
    "nke": "NKE",
    "coca cola": "KO",
    "coke": "KO",
    "ko": "KO",
    "pepsi": "PEP",
    "pepsico": "PEP",
    "starbucks": "SBUX",
    "sbux": "SBUX",
    "mcdonalds": "MCD",
    "mcdonald's": "MCD",
    "disney": "DIS",
    "dis": "DIS",

    # Indices & ETFs
    "sp500": "SPY",
    "s&p 500": "SPY",
    "spy": "SPY",
    "nasdaq": "QQQ",
    "qqq": "QQQ",
    "dow": "DIA",
    "dow jones": "DIA",
    "dia": "DIA",
    "russell 2000": "IWM",
    "iwm": "IWM",

    # Crypto Proxies
    "bitcoin": "BTC-USD",
    "btc": "BTC-USD",
    "ethereum": "ETH-USD",
    "eth": "ETH-USD",
}

# Display names for clean transparency feedback
TICKER_NAMES = {
    "AAPL": "Apple Inc.",
    "MSFT": "Microsoft Corp.",
    "GOOGL": "Alphabet Inc. (Google)",
    "AMZN": "Amazon.com Inc.",
    "TSLA": "Tesla Inc.",
    "NVDA": "NVIDIA Corp.",
    "META": "Meta Platforms Inc.",
    "NFLX": "Netflix Inc.",
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


class TickerMatcher:
    """
    High-speed fuzzy ticker resolution engine.
    Applies direct dictionary lookup followed by RapidFuzz probabilistic matching with >= 55% confidence.
    """

    def __init__(self, confidence_threshold: float = 55.0):
        self.threshold = confidence_threshold
        self.dictionary = TICKER_DICTIONARY
        self.keys = list(self.dictionary.keys())

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
        words = cleaned.split()

        # 1. Direct match on tokens or whole query
        if cleaned in self.dictionary:
            ticker = self.dictionary[cleaned]
            return ticker, 100.0, TICKER_NAMES.get(ticker, ticker), False

        for word in words:
            if word in self.dictionary:
                ticker = self.dictionary[word]
                return ticker, 100.0, TICKER_NAMES.get(ticker, ticker), False

        # 2. Check uppercase 2-5 letter raw tickers in original query (e.g., "$AAPL" or "TSLA")
        raw_ticker_pattern = re.findall(r"\b\$?([A-Z]{1,5}(?:-[A-Z]{1,4})?)\b", query)
        for cand in raw_ticker_pattern:
            cand_clean = cand.strip("$").upper()
            if cand_clean.lower() in self.dictionary:
                ticker = self.dictionary[cand_clean.lower()]
                return ticker, 100.0, TICKER_NAMES.get(ticker, ticker), False
            # Allow direct uppercase ticker standard
            if len(cand_clean) >= 2 and cand_clean.isalpha():
                return cand_clean, 90.0, cand_clean, False

        # 3. Probabilistic RapidFuzz best-guess evaluation
        if RAPIDFUZZ_AVAILABLE and self.keys:
            # Check candidate n-grams / words against dictionary
            best_match = None
            best_score = 0.0
            best_key = None

            candidates = [cleaned] + words
            # Include 2-word combinations
            if len(words) >= 2:
                for i in range(len(words) - 1):
                    candidates.append(f"{words[i]} {words[i+1]}")

            for cand in candidates:
                if len(cand) < 2:
                    continue
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
                        best_match = self.dictionary[match_key]

            if best_match and best_score >= self.threshold:
                matched_name = TICKER_NAMES.get(best_match, best_key.capitalize())
                return best_match, round(best_score, 1), matched_name, True

        return None, 0.0, None, False
