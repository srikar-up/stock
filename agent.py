"""
Needle 3 Edge AI Engine Module
Integrates Cactus Compute's lightweight tool-calling model (cactus-needle) with fallback intent parsing.
Uses under 28 MB RAM on edge CPU runtimes.
"""
import re
import logging
from typing import Dict, Any, Optional, List, Tuple
from matcher import TickerMatcher
from storage import FirestoreContextManager
from market import MarketEngine

logger = logging.getLogger(__name__)

# Check for cactus-needle package
try:
    import needle
    NEEDLE_AVAILABLE = True
except ImportError:
    NEEDLE_AVAILABLE = False


class NeedleStockAgent:
    """
    Intelligent agent that decodes user intent from email text and context,
    invokes downstream market engines, and produces structured responses.
    """

    def __init__(self, context_manager: FirestoreContextManager):
        self.context_manager = context_manager
        self.matcher = TickerMatcher(confidence_threshold=55.0)
        self.market = MarketEngine()
        self.needle_agent = None

        if NEEDLE_AVAILABLE:
            self._init_needle_tools()

    def _init_needle_tools(self):
        """Registers tools with the Needle 3 runtime."""
        try:
            @needle.tool
            def tool_get_stock_quote(ticker: str) -> dict:
                """Get real-time price and financial details for a stock ticker."""
                return self.market.get_stock_quote(ticker)

            @needle.tool
            def tool_get_stock_chart(ticker: str, period: str = "1mo") -> dict:
                """Generate a visual trend chart for a stock ticker over a time period."""
                chart_bytes = self.market.generate_trend_chart(ticker, period=period)
                return {"ticker": ticker, "has_chart": chart_bytes is not None}

            @needle.tool
            def tool_compare_tickers(tickers: List[str]) -> dict:
                """Compare financial metrics for two or more stock tickers."""
                return self.market.compare_stocks(tickers)

            self.needle_agent = needle.Needle(tools=[
                tool_get_stock_quote,
                tool_get_stock_chart,
                tool_compare_tickers
            ])
            logger.info("Needle 3 edge AI agent initialized successfully.")
        except Exception as e:
            logger.warning(f"Needle initialization warning: {e}. Fallback parser will be used.")
            self.needle_agent = None

    def _extract_intent_and_tickers(
        self,
        query: str,
        user_context: Dict[str, Any]
    ) -> Tuple[str, List[str], Optional[str], Optional[str]]:
        """
        Determines the intent, resolves tickers, and generates transparency notes.
        Returns:
            (intent, tickers, transparency_note, period)
        """
        cleaned_lower = query.lower()
        last_ticker = user_context.get("last_ticker")

        # 1. Check for Comparison Intent (e.g., "compare apple and tesla", "aapl vs msft")
        if any(w in cleaned_lower for w in ["compare", " vs ", " versus ", " against "]):
            # Extract multiple tickers
            found_tickers = []
            notes = []
            tokens = re.split(r"[\s,]+and[\s,]+|[\s,]+vs[\s,]+|[\s,]+versus[\s,]+|[,;]", cleaned_lower)
            for token in tokens:
                t, conf, name, is_fuzzy = self.matcher.extract_ticker_from_text(token)
                if t and t not in found_tickers:
                    found_tickers.append(t)
                    if is_fuzzy:
                        notes.append(f"Interpreted '{token.strip()}' as {name} ({t}) with {conf}% confidence")

            if len(found_tickers) >= 2:
                note_str = " | ".join(notes) if notes else None
                return "COMPARE", found_tickers, note_str, "1mo"

        # 2. Check for Chart Intent
        is_chart_intent = any(w in cleaned_lower for w in ["chart", "graph", "plot", "trend", "visual", "technical", "history", "historical"])

        # Determine period if chart requested
        period = "1mo"
        if "1y" in cleaned_lower or "year" in cleaned_lower:
            period = "1y"
        elif "6m" in cleaned_lower or "6 month" in cleaned_lower:
            period = "6mo"
        elif "5d" in cleaned_lower or "week" in cleaned_lower:
            period = "5d"
        elif "3m" in cleaned_lower or "quarter" in cleaned_lower:
            period = "3mo"

        # 3. Extract Single Ticker via Matcher
        matched_ticker, confidence, matched_name, is_fuzzy = self.matcher.extract_ticker_from_text(query)

        # Context Pointer fallback: If user didn't specify a ticker but asked for chart or quote, use last_ticker
        transparency_note = None
        if not matched_ticker and last_ticker:
            matched_ticker = last_ticker
            transparency_note = f"Using context from previous conversation: {last_ticker}"
        elif matched_ticker and is_fuzzy:
            transparency_note = f"Identified '{matched_name}' ({matched_ticker}) based on best-match confidence ({confidence}%)"

        if matched_ticker:
            if is_chart_intent:
                return "CHART", [matched_ticker], transparency_note, period
            return "QUOTE", [matched_ticker], transparency_note, period

        # 4. Standard conversational fallback if no ticker was resolved
        return "CHAT", [], None, None

    def process_message(self, user_email: str, subject: str, body: str) -> Dict[str, Any]:
        """
        Main execution pipeline for incoming emails.
        """
        combined_text = f"{subject} {body}".strip()
        user_context = self.context_manager.get_user_context(user_email)

        # Attempt Needle 3 execution if available
        intent = None
        tickers = []
        transparency_note = None
        period = "1mo"

        if self.needle_agent:
            try:
                # Needle 3 local inference
                needle_res = self.needle_agent.run(combined_text)
                results = needle_res.get("results", [])
                if results:
                    # Needle successfully selected and ran a tool
                    first_res = results[0]
                    t = first_res.get("ticker")
                    if t:
                        self.context_manager.update_user_context(user_email, last_ticker=t, last_action="NEEDLE_TOOL")
                        return {
                            "status": "success",
                            "engine": "Needle 3 Edge Model",
                            "intent": "TOOL_EXECUTION",
                            "results": results
                        }
            except Exception as e:
                logger.warning(f"Needle execution exception: {e}. Utilizing fallback matcher pipeline.")

        # Robust Fallback & Pre-processing Pipeline
        intent, tickers, transparency_note, period = self._extract_intent_and_tickers(combined_text, user_context)

        # Execute downstream action based on resolved intent
        if intent == "QUOTE" and tickers:
            primary_ticker = tickers[0]
            quote = self.market.get_stock_quote(primary_ticker)
            self.context_manager.update_user_context(user_email, last_ticker=primary_ticker, last_action="QUOTE")

            return {
                "status": "success",
                "intent": "QUOTE",
                "ticker": primary_ticker,
                "data": quote,
                "transparency_note": transparency_note,
                "context_used": user_context.get("last_ticker") == primary_ticker and "previous conversation" in (transparency_note or "")
            }

        elif intent == "CHART" and tickers:
            primary_ticker = tickers[0]
            chart_bytes = self.market.generate_trend_chart(primary_ticker, period=period)
            quote = self.market.get_stock_quote(primary_ticker)
            self.context_manager.update_user_context(user_email, last_ticker=primary_ticker, last_action="CHART")

            data_uri = self.market.chart_to_base64_data_uri(chart_bytes) if chart_bytes else None

            return {
                "status": "success",
                "intent": "CHART",
                "ticker": primary_ticker,
                "period": period,
                "chart_base64": data_uri,
                "quote": quote,
                "transparency_note": transparency_note
            }

        elif intent == "COMPARE" and len(tickers) >= 2:
            comp_data = self.market.compare_stocks(tickers)
            self.context_manager.update_user_context(user_email, last_ticker=tickers[0], last_action="COMPARE")

            return {
                "status": "success",
                "intent": "COMPARE",
                "tickers": tickers,
                "data": comp_data,
                "transparency_note": transparency_note
            }

        else:
            # Friendly conversational fallback
            return {
                "status": "success",
                "intent": "CHAT",
                "message": (
                    "Hello! I am your Edge-AI Stock Email Assistant. "
                    "You can ask me for real-time stock quotes, trend charts, or company comparisons. "
                    "For example, email me: 'What is Apple's current price?', 'Show me the TSLA chart for 1 month', "
                    "or 'Compare GOOGL and MSFT'."
                ),
                "last_context": user_context
            }
