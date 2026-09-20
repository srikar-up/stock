"""
Structural Intelligence Layer - Needle 3 Edge AI Engine
Translates unstructured text into direct system tool calls with absolute precision.
Runs locally under strict resource constraints (< 28 MB RAM).
"""
import re
import logging
from typing import Dict, Any, Optional, List, Tuple

from matcher import TickerMatcher
from storage import FirestoreContextManager
from market import MarketEngine

logger = logging.getLogger(__name__)

try:
    import needle
    NEEDLE_AVAILABLE = True
except ImportError:
    NEEDLE_AVAILABLE = False


class NeedleStockAgent:
    """
    Structural Intelligence Layer:
    Strict mapping of unstructured user input to verified tool execution schemas:
    - get_stock_info
    - show_chart
    - get_csv
    - compare_stocks (MAX 2)
    - chat (Greetings, over-limit fallback, dismissals)
    """

    GREETINGS_PATTERN = re.compile(
        r"^(hi|hello|hey|greetings|howdy|good\s+(morning|afternoon|evening)|thanks|thank\s+you|bye|goodbye|who\s+are\s+you)[\s!.,?]*$",
        re.IGNORECASE
    )

    PRONOUN_PATTERNS = [
        re.compile(r"\b(it|its|that\s+stock|the\s+stock|same\s+stock|this\s+stock)\b", re.IGNORECASE)
    ]

    def __init__(self, context_manager: FirestoreContextManager):
        self.context_manager = context_manager
        self.matcher = TickerMatcher(confidence_threshold=55.0)
        self.market = MarketEngine()
        self.needle_agent = None

        if NEEDLE_AVAILABLE:
            self._init_needle_tools()

    def _init_needle_tools(self):
        """Binds tool execution schemas to Needle 3."""
        try:
            @needle.tool
            def get_stock_info(symbol: str) -> dict:
                """Fetch real-time market matrices, prices, and volumes."""
                return self.market.get_stock_quote(symbol)

            @needle.tool
            def show_chart(symbol: str, period: str = "1mo") -> dict:
                """Generate visual historical data charts."""
                chart_bytes = self.market.generate_trend_chart(symbol, period=period)
                return {"symbol": symbol, "period": period, "has_chart": chart_bytes is not None}

            @needle.tool
            def get_csv(symbol: str, period: str = "1mo") -> dict:
                """Compile raw tabular historical data exports."""
                data = self.market.get_historical_table(symbol, period=period)
                return {"symbol": symbol, "period": period, "rows": len(data)}

            @needle.tool
            def compare_stocks(symbols: List[str], period: str = "1mo") -> dict:
                """Compare exactly 2 tickers simultaneously (MAX 2)."""
                if len(symbols) > 2:
                    return {"action": "chat", "message": "Max 2 tickers allowed for comparison."}
                return self.market.compare_stocks(symbols[:2])

            self.needle_agent = needle.Needle(tools=[
                get_stock_info,
                show_chart,
                get_csv,
                compare_stocks
            ])
            logger.info("Needle 3 structural engine bound to tools.")
        except Exception as e:
            logger.warning(f"Needle engine initialization: {e}")
            self.needle_agent = None

    def route_intent(self, text: str, user_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Translates unstructured input into direct system calls with absolute precision.
        """
        query = text.strip()
        query_lower = query.lower()
        last_ticker = user_context.get("last_ticker")

        # ---------------------------------------------------------------------
        # DIRECTIVE 1: GREETING & INTRO ROUTING
        # ---------------------------------------------------------------------
        # If payload is greeting or dismissal, instantly route to chat. Do not guess a ticker.
        if self.GREETINGS_PATTERN.match(query_lower):
            return {
                "action": "chat",
                "parameters": {},
                "message": "Hello! I am your Edge-AI Stock Assistant. You can ask for quotes, charts, or 2-stock comparisons."
            }

        # ---------------------------------------------------------------------
        # DIRECTIVE 3: HANDLING OVERLOAD & BOUNDARIES (COMPARE MAX 2)
        # ---------------------------------------------------------------------
        is_compare = any(w in query_lower for w in ["compare", " vs ", " versus ", " against "])
        if is_compare:
            # Extract candidate stock tokens
            tokens = re.split(r"[\s,]+and[\s,]+|[\s,]+vs[\s,]+|[\s,]+versus[\s,]+|[,;]", query_lower)
            found_tickers = []
            for token in tokens:
                token_clean = token.replace("compare", "").strip()
                if not token_clean:
                    continue
                t, conf, _, _ = self.matcher.extract_ticker_from_text(token_clean)
                if t and t not in found_tickers:
                    found_tickers.append(t)

            # BOUNDARY CHECK: More than 2 stocks -> drop directly into chat
            if len(found_tickers) > 2:
                return {
                    "action": "chat",
                    "parameters": {"rejected_tickers": found_tickers},
                    "message": f"I can compare a maximum of 2 stocks at a time to ensure clear analysis! Which 2 would you like to compare among {', '.join(found_tickers)}?"
                }

            if len(found_tickers) == 2:
                return {
                    "action": "compare_stocks",
                    "parameters": {"symbols": found_tickers, "period": "1mo"}
                }

        # ---------------------------------------------------------------------
        # DIRECTIVE 2: METADATA CONTEXT MEMORY (Pronoun substitution)
        # ---------------------------------------------------------------------
        has_pronoun = any(p.search(query_lower) for p in self.PRONOUN_PATTERNS)
        matched_ticker, confidence, matched_name, is_fuzzy = self.matcher.extract_ticker_from_text(query)

        resolved_ticker = None
        context_substituted = False

        if matched_ticker:
            resolved_ticker = matched_ticker
        elif (has_pronoun or not matched_ticker) and last_ticker:
            # Substitute "it" or "that stock" with tracked historical ticker
            resolved_ticker = last_ticker
            context_substituted = True

        if not resolved_ticker:
            # Cannot safely infer parameters within structural bounds
            return {
                "action": "chat",
                "parameters": {},
                "message": "I didn't detect a recognized stock ticker. Try asking: 'What is Apple's price?' or 'TSLA chart'."
            }

        # Extract Time Period if present
        period = "1mo"
        if any(w in query_lower for w in ["1y", "1 year", "year", "12m"]):
            period = "1y"
        elif any(w in query_lower for w in ["6m", "6 month", "half year"]):
            period = "6mo"
        elif any(w in query_lower for w in ["3m", "3 month", "quarter"]):
            period = "3mo"
        elif any(w in query_lower for w in ["5d", "1w", "week", "5 days"]):
            period = "5d"

        # ---------------------------------------------------------------------
        # SCHEMA: get_csv
        # ---------------------------------------------------------------------
        if any(w in query_lower for w in ["csv", "data export", "raw data", "tabular", "download data"]):
            return {
                "action": "get_csv",
                "parameters": {"symbol": resolved_ticker, "period": period},
                "context_used": context_substituted
            }

        # ---------------------------------------------------------------------
        # SCHEMA: show_chart
        # ---------------------------------------------------------------------
        if any(w in query_lower for w in ["chart", "graph", "plot", "trend", "technical", "visual"]):
            return {
                "action": "show_chart",
                "parameters": {"symbol": resolved_ticker, "period": period},
                "context_used": context_substituted
            }

        # ---------------------------------------------------------------------
        # SCHEMA: get_stock_info (Default for valid ticker queries)
        # ---------------------------------------------------------------------
        transparency_note = None
        if context_substituted:
            transparency_note = f"Context memory referenced: {resolved_ticker}"
        elif is_fuzzy:
            transparency_note = f"Resolved '{matched_name}' as {resolved_ticker} ({confidence}% match)"

        return {
            "action": "get_stock_info",
            "parameters": {"symbol": resolved_ticker},
            "transparency_note": transparency_note
        }

    def process_message(self, user_email: str, subject: str, body: str) -> Dict[str, Any]:
        """
        Executes the routed system tool call and packages the payload.
        """
        combined = f"{subject} {body}".strip()
        context = self.context_manager.get_user_context(user_email)

        call = self.route_intent(combined, context)
        action = call.get("action")
        params = call.get("parameters", {})

        if action == "get_stock_info":
            symbol = params.get("symbol")
            data = self.market.get_stock_quote(symbol)
            self.context_manager.update_user_context(user_email, last_ticker=symbol, last_action="get_stock_info")
            return {
                "status": "success",
                "action": "get_stock_info",
                "intent": "QUOTE",
                "ticker": symbol,
                "data": data,
                "transparency_note": call.get("transparency_note")
            }

        elif action == "show_chart":
            symbol = params.get("symbol")
            period = params.get("period", "1mo")
            chart_bytes = self.market.generate_trend_chart(symbol, period=period)
            quote = self.market.get_stock_quote(symbol)
            self.context_manager.update_user_context(user_email, last_ticker=symbol, last_action="show_chart")
            return {
                "status": "success",
                "action": "show_chart",
                "intent": "CHART",
                "ticker": symbol,
                "period": period,
                "chart_base64": self.market.chart_to_base64_data_uri(chart_bytes) if chart_bytes else None,
                "quote": quote
            }

        elif action == "get_csv":
            symbol = params.get("symbol")
            period = params.get("period", "1mo")
            rows = self.market.get_historical_table(symbol, period=period)
            self.context_manager.update_user_context(user_email, last_ticker=symbol, last_action="get_csv")
            return {
                "status": "success",
                "action": "get_csv",
                "intent": "CSV",
                "ticker": symbol,
                "period": period,
                "rows": rows
            }

        elif action == "compare_stocks":
            symbols = params.get("symbols", [])
            data = self.market.compare_stocks(symbols)
            if symbols:
                self.context_manager.update_user_context(user_email, last_ticker=symbols[0], last_action="compare_stocks")
            return {
                "status": "success",
                "action": "compare_stocks",
                "intent": "COMPARE",
                "tickers": symbols,
                "data": data
            }

        else:
            # action == "chat"
            return {
                "status": "success",
                "action": "chat",
                "intent": "CHAT",
                "message": call.get("message", "Hello! How can I assist with financial data today?")
            }
