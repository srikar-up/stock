"""
Structural Intelligence Layer - Needle 3 Edge AI Engine
Translates unstructured text into direct system tool calls with absolute precision.
Prioritizes on-device Needle 3 foundation model inference with resilient schema fallback.
Runs locally under strict resource constraints (< 28 MB RAM).
"""
import re
import logging
from typing import Dict, Any, Optional, List, Tuple

from matcher import TickerMatcher, STOPWORDS
from storage import FirestoreContextManager
from market import MarketEngine, sanitize_period

logger = logging.getLogger(__name__)

try:
    import needle
    NEEDLE_AVAILABLE = True
except ImportError:
    NEEDLE_AVAILABLE = False


class NeedleStockAgent:
    """
    Structural Intelligence Layer:
    Executes tool calling via Needle 3 with deterministic fallback.
    Supported Schemas:
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
        # Align confidence threshold to 70.0 to match matcher.py
        self.matcher = TickerMatcher(confidence_threshold=70.0)
        self.market = MarketEngine()
        self.needle_agent = None

        if NEEDLE_AVAILABLE:
            self._init_needle_tools()

    def _resolve_symbol(self, raw_symbol: str) -> Optional[str]:
        """Resolves raw company names or tickers (e.g., 'apple' -> 'AAPL', 'tesla' -> 'TSLA')."""
        if not raw_symbol:
            return None
        clean = raw_symbol.strip().replace("$", "")
        # Reject stopwords (e.g. SHOW, MAX, BOTH, IT, ITS, DATA, CSV)
        if clean.lower() in STOPWORDS:
            return None
        matched_ticker, _, _, _ = self.matcher.extract_ticker_from_text(clean)
        if matched_ticker:
            return matched_ticker.upper()
        clean_upper = clean.upper()
        if clean_upper in self.matcher.known_tickers:
            return clean_upper
        return None

    @staticmethod
    def extract_period(text: str) -> str:
        """
        Extracts financial historical time range from user queries with typo resilience.
        Supports:
        - 5y / 5 years / max / all time
        - 2y / 2 years
        - 1y / 1 year / yearly / annual / 12 months / 12m
        - 6mo / 6 months / 6 month / half year / 6m / '6 nont' (typo) / '6 mont'
        - 3mo / 3 months / 3 month / quarter / quarterly / 3m
        - 1mo / 1 month / monthly / 'montly' (typo) / past month / 1m
        - 5d / 1 week / weekly / 5 days / 1w
        - 1d / today / intraday
        Defaults to '1mo'.
        """
        t = (text or "").lower()

        # 5 Years / All Time / Max
        if any(k in t for k in ["5y", "5 year", "5 years", "five year", "all time", "max"]):
            return "5y"

        # 2 Years
        if any(k in t for k in ["2y", "2 year", "2 years", "two year"]):
            return "2y"

        # 1 Year / Yearly / Annual
        if any(k in t for k in ["1y", "1 year", "1 years", "one year", "yearly", "annual", "12m", "12 month", "12 months"]) or re.search(r"\b(year|yearly|annual|1y)\b", t):
            return "1y"

        # 6 Months / Half Year / Typos ("6 nont", "6 mont", "6m", "6mo")
        if any(k in t for k in [
            "6m", "6mo", "6 month", "6 months", "six month", "six months", "half year", "half-year", "semi annual",
            "6 nont", "6nont", "6 mont", "6mont", "6 mon", "6mon"
        ]) or re.search(r"\b6\s*(m|mo|mon|month|months|nont|nonts|mont|monts)\b", t):
            return "6mo"

        # 3 Months / Quarter
        if any(k in t for k in [
            "3m", "3mo", "3 month", "3 months", "three month", "three months", "quarter", "quarterly", "3 mont", "3 mon"
        ]) or re.search(r"\b3\s*(m|mo|mon|month|months)\b", t):
            return "3mo"

        # 1 Month / Monthly / Typos ("montly")
        if any(k in t for k in [
            "1m", "1mo", "1 month", "1 months", "one month", "monthly", "montly", "past month", "last month", "30 days", "30d"
        ]) or re.search(r"\b(month|monthly|montly|1mo|1m)\b", t):
            return "1mo"

        # 1 Week / 5 Days / Weekly
        if any(k in t for k in [
            "1w", "1 week", "1 weeks", "one week", "weekly", "5d", "5 day", "5 days", "past week", "last week"
        ]) or re.search(r"\b(week|weekly|1w|5d)\b", t):
            return "5d"

        # 1 Day / Intraday
        if any(k in t for k in ["1d", "1 day", "today", "intraday"]):
            return "1d"

        return "1mo"

    def _init_needle_tools(self):
        """Binds tool execution schemas to Needle 3."""
        try:
            @needle.tool
            def get_stock_info(symbol: str) -> dict:
                """Fetch real-time market matrices, prices, and volumes for a stock ticker."""
                ticker = self._resolve_symbol(symbol)
                if not ticker:
                    return {"_tool": "get_stock_info", "ticker": None, "status": "failed"}
                data = self.market.get_stock_quote(ticker)
                return {
                    "_tool": "get_stock_info",
                    "ticker": ticker,
                    "data": data,
                    "status": "success"
                }

            @needle.tool
            def show_chart(symbol: str, period: str = "1mo") -> dict:
                """Generate visual historical price and volume trend charts for a stock ticker."""
                ticker = self._resolve_symbol(symbol)
                clean_period = sanitize_period(period)
                if not ticker:
                    return {"_tool": "show_chart", "ticker": None, "status": "failed"}
                chart_bytes = self.market.generate_trend_chart(ticker, period=clean_period)
                quote = self.market.get_stock_quote(ticker)
                return {
                    "_tool": "show_chart",
                    "ticker": ticker,
                    "period": clean_period,
                    "chart_base64": self.market.chart_to_base64_data_uri(chart_bytes) if chart_bytes else None,
                    "quote": quote,
                    "status": "success"
                }

            @needle.tool
            def get_csv(symbol: str, period: str = "1mo") -> dict:
                """Compile raw tabular historical data exports into CSV rows."""
                ticker = self._resolve_symbol(symbol)
                clean_period = sanitize_period(period)
                if not ticker:
                    return {"_tool": "get_csv", "ticker": None, "status": "failed"}
                rows = self.market.get_historical_table(ticker, period=clean_period)
                return {
                    "_tool": "get_csv",
                    "ticker": ticker,
                    "period": clean_period,
                    "rows": rows,
                    "status": "success"
                }

            @needle.tool
            def compare_stocks(symbols: List[str], period: str = "1mo") -> dict:
                """Compare two stock tickers side by side."""
                resolved = [s for s in (self._resolve_symbol(x) for x in (symbols or [])) if s]
                if len(resolved) > 2:
                    return {
                        "_tool": "chat",
                        "status": "success",
                        "message": "I can only compare a maximum of 2 stocks at a time to ensure clear analysis. Please select 2 stocks."
                    }
                clean_period = sanitize_period(period)
                data = self.market.compare_stocks(resolved[:2])
                return {
                    "_tool": "compare_stocks",
                    "tickers": resolved[:2],
                    "period": clean_period,
                    "data": data,
                    "status": "success"
                }

            @needle.tool
            def get_comparative_csv(symbols: List[str], period: str = "1mo") -> dict:
                """Generate merged comparative historical CSV data for two stock tickers."""
                resolved = [s for s in (self._resolve_symbol(x) for x in (symbols or [])) if s][:2]
                clean_period = sanitize_period(period)
                return {
                    "_tool": "get_comparative_csv",
                    "tickers": resolved,
                    "period": clean_period,
                    "status": "success"
                }

            @needle.tool
            def chat(message: str) -> dict:
                """Handle general greetings, pleasantries, or parameter education."""
                return {
                    "_tool": "chat",
                    "status": "success",
                    "message": "Hello! I am your Edge-AI Stock Assistant. You can ask me for stock quotes, charts, or 2-stock comparisons."
                }

            self.needle_agent = needle.Needle(tools=[
                get_stock_info,
                show_chart,
                get_csv,
                compare_stocks,
                get_comparative_csv,
                chat
            ])
            logger.info("Needle 3 edge AI agent successfully initialized and bound to tools.")
        except Exception as e:
            logger.warning(f"Needle 3 initialization warning: {e}. Resilient schema router will be used.")
            self.needle_agent = None

    def _inject_context(self, text: str, user_context: Dict[str, Any]) -> str:
        """Substitutes pronouns ('it', 'that stock') with the tracked context ticker."""
        last_ticker = user_context.get("last_ticker")
        if not last_ticker:
            return text

        enriched = text
        for p in self.PRONOUN_PATTERNS:
            enriched = p.sub(last_ticker, enriched)
        return enriched

    def route_intent(self, text: str, user_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resilient schema router (Fallback when Needle 3 is not available).
        """
        query = text.strip()
        query_lower = query.lower()
        last_ticker = user_context.get("last_ticker")

        # 1. GREETING & INTRO ROUTING
        if self.GREETINGS_PATTERN.match(query_lower):
            return {
                "action": "chat",
                "parameters": {},
                "message": "Hello! I am your Edge-AI Stock Assistant. You can ask for quotes, charts, or 2-stock comparisons."
            }

        # Robust time period extraction (supporting monthly, 6mo, 1y, 5d, and typos like '6 nont')
        period = self.extract_period(query_lower)

        # 2. MULTI-TICKER CONTEXT MEMORY ("both", "these two", "two stocks")
        last_tickers = user_context.get("last_tickers") or []
        if isinstance(last_tickers, str):
            last_tickers = [last_tickers]
        wants_both = any(w in query_lower for w in ["both", "these two", "the two", "two stocks", "both stocks", "both of them"])
        if wants_both and len(last_tickers) >= 2:
            wants_csv = any(w in query_lower for w in ["csv", "data", "export", "tabular", "excel", "spreadsheet", "raw"])
            if wants_csv:
                return {
                    "action": "get_comparative_csv",
                    "parameters": {"symbols": last_tickers[:2], "period": period},
                    "context_used": True
                }
            else:
                return {
                    "action": "compare_stocks",
                    "parameters": {"symbols": last_tickers[:2], "period": period},
                    "context_used": True
                }

        # 3. BOUNDARY CHECK: Compare MAX 2 (with typo resilience and automatic 2-ticker detection)
        is_compare = any(w in query_lower for w in [
            "compare", "comparison", "comparision", "comparing", "comparative",
            " vs ", " vs. ", " versus ", " against ", " diff ", " difference "
        ])
        all_tickers = self.matcher.extract_all_tickers(query)
        found_tickers = [t for t, _ in all_tickers]

        if is_compare or len(found_tickers) >= 2:
            if len(found_tickers) > 2:
                return {
                    "action": "chat",
                    "parameters": {"rejected_tickers": found_tickers},
                    "message": f"I can compare a maximum of 2 stocks at a time to ensure clear analysis! Which 2 would you like to compare among {', '.join(found_tickers)}?"
                }

            if len(found_tickers) == 2:
                wants_csv = any(w in query_lower for w in [
                    "csv", "sheet", "sheets", "spreadsheet", "spreadsheets", "excel",
                    "data", "export", "tabular", "raw", "table", "datasheet", "data sheet"
                ])
                if wants_csv:
                    return {
                        "action": "get_comparative_csv",
                        "parameters": {"symbols": found_tickers, "period": period}
                    }
                return {
                    "action": "compare_stocks",
                    "parameters": {"symbols": found_tickers, "period": period}
                }

        # 4. SINGLE TICKER METADATA CONTEXT MEMORY
        has_pronoun = any(p.search(query_lower) for p in self.PRONOUN_PATTERNS)
        matched_ticker, confidence, matched_name, is_fuzzy = self.matcher.extract_ticker_from_text(query)

        resolved_ticker = None
        context_substituted = False

        if matched_ticker:
            resolved_ticker = matched_ticker
        elif (has_pronoun or not matched_ticker) and last_ticker:
            resolved_ticker = last_ticker
            context_substituted = True

        if not resolved_ticker:
            wants_stock = any(w in query_lower for w in [
                "price", "stock", "stocks", "chart", "trend", "quote", "cost",
                "csv", "sheet", "sheets", "spreadsheet", "excel", "share", "shares", "company", "table"
            ])
            if wants_stock:
                clean_target = re.sub(
                    r"\b(what|is|the|price|stock|stocks|of|for|check|show|me|chart|graph|trend|csv|sheet|sheets|spreadsheet|excel|table|data|tell|about|current|please|send|upload|give)\b",
                    " ",
                    query_lower
                ).strip()
                target_display = f"'{clean_target}'" if clean_target else "the requested company"
                return {
                    "action": "not_found",
                    "parameters": {"query": clean_target},
                    "message": f"Company {target_display} was not found in our database of ~8,000+ global companies. It may be private, delisted, or unlisted. Try searching by exact company name or provide the ticker symbol directly (e.g. $AAPL, $TSLA, $TATAMOTORS.NS, $TCS.NS)."
                }
            return {
                "action": "chat",
                "parameters": {},
                "message": "I didn't detect a recognized stock ticker. Try asking: 'What is Apple's price?' or 'TSLA chart'."
            }

        # SCHEMA: get_csv (matches csv, sheet, sheets, spreadsheet, excel, table)
        if any(w in query_lower for w in [
            "csv", "sheet", "sheets", "spreadsheet", "spreadsheets", "excel",
            "data export", "raw data", "tabular", "download data", "datasheet", "data sheet", "historical data", "table"
        ]):
            return {
                "action": "get_csv",
                "parameters": {"symbol": resolved_ticker, "period": period},
                "context_used": context_substituted
            }

        # SCHEMA: show_chart
        if any(w in query_lower for w in ["chart", "graph", "plot", "trend", "technical", "visual"]):
            return {
                "action": "show_chart",
                "parameters": {"symbol": resolved_ticker, "period": period},
                "context_used": context_substituted
            }

        # SCHEMA: get_stock_info
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
        Main execution pipeline:
        1. Evaluates via Needle 3 Edge AI Agent if available.
        2. Falls back to resilient schema router if Needle is unavailable or raises an exception.
        3. Persists tracking context to Firestore.
        """
        # Strip recursive "Re:" and "Fwd:" prefixes to avoid query degradation
        clean_subj = re.sub(r"^(?:re:\s*|fwd:\s*)+", "", (subject or "").strip(), flags=re.IGNORECASE).strip()
        clean_body = (body or "").strip()
        if clean_subj.lower() in clean_body.lower():
            combined = clean_body
        else:
            combined = f"{clean_subj} {clean_body}".strip() if clean_subj else clean_body

        context = self.context_manager.get_user_context(user_email)
        enriched_query = self._inject_context(combined, context)
        extracted_period = self.extract_period(combined)

        # ---------------------------------------------------------------------
        # 0. MULTI-TICKER / COMPARISON / CONTEXT MEMORY PRIORITY CHECK
        # Guarantee 2-stock queries, "both", and comparisons are never collapsed
        # ---------------------------------------------------------------------
        all_tickers = self.matcher.extract_all_tickers(combined)
        found_tickers = [t for t, _ in all_tickers]
        is_compare = any(w in combined.lower() for w in [
            "compare", "comparison", "comparision", "comparing", "comparative",
            " vs ", " vs. ", " versus ", " against ", " diff ", " difference "
        ])
        last_tickers = context.get("last_tickers") or []
        if isinstance(last_tickers, str):
            last_tickers = [last_tickers]
        wants_both = any(w in combined.lower() for w in ["both", "these two", "the two", "two stocks", "both stocks", "both of them"])

        if is_compare or len(found_tickers) >= 2 or (wants_both and len(last_tickers) >= 2):
            call = self.route_intent(combined, context)
            action = call.get("action")
            params = call.get("parameters", {})
            if action == "compare_stocks":
                symbols = params.get("symbols", [])
                period = params.get("period", "1mo")
                data = self.market.compare_stocks(symbols)
                if symbols:
                    self.context_manager.update_user_context(user_email, last_ticker=symbols[0], last_tickers=symbols, last_action="compare_stocks")
                return {
                    "status": "success",
                    "engine": "Deterministic Route",
                    "action": "compare_stocks",
                    "intent": "COMPARE",
                    "tickers": symbols,
                    "period": period,
                    "data": data
                }
            elif action == "get_comparative_csv":
                symbols = params.get("symbols", [])
                period = params.get("period", "1mo")
                if symbols:
                    self.context_manager.update_user_context(user_email, last_ticker=symbols[0], last_tickers=symbols, last_action="get_comparative_csv")
                return {
                    "status": "success",
                    "engine": "Deterministic Route",
                    "action": "get_comparative_csv",
                    "intent": "COMPARATIVE_CSV",
                    "tickers": symbols,
                    "period": period
                }
            elif action == "chat":
                return {
                    "status": "success",
                    "engine": "Deterministic Route",
                    "action": "chat",
                    "intent": "CHAT",
                    "message": call.get("message", "I can compare a maximum of 2 stocks at a time.")
                }

        # ---------------------------------------------------------------------
        # 1. PRIMARY EXECUTION: Needle 3 Edge AI Engine
        # ---------------------------------------------------------------------
        if self.needle_agent:
            try:
                logger.info(f"🤖 Needle 3 edge model inferring intent for: '{enriched_query}'")
                needle_output = self.needle_agent.run(enriched_query)
                results = needle_output.get("results", [])

                if results:
                    tool_res = results[0]
                    tool_name = tool_res.get("_tool", "")

                    if tool_name == "get_stock_info":
                        ticker = tool_res.get("ticker")
                        if not ticker or ticker.lower() in STOPWORDS:
                            logger.info(f"Needle returned non-ticker '{ticker}', routing via deterministic matcher...")
                        else:
                            self.context_manager.update_user_context(user_email, last_ticker=ticker, last_action="get_stock_info")
                            return {
                                "status": "success",
                                "engine": "Needle 3 (Cactus Compute)",
                                "action": "get_stock_info",
                                "intent": "QUOTE",
                                "ticker": ticker,
                                "data": tool_res.get("data", {}),
                                "transparency_note": None
                            }

                    elif tool_name == "show_chart":
                        ticker = tool_res.get("ticker")
                        if not ticker or ticker.lower() in STOPWORDS:
                            logger.info(f"Needle returned non-ticker '{ticker}', routing via deterministic matcher...")
                        else:
                            period = extracted_period if extracted_period != "1mo" else tool_res.get("period", "1mo")
                            period = sanitize_period(period)
                            self.context_manager.update_user_context(user_email, last_ticker=ticker, last_action="show_chart")
                            return {
                                "status": "success",
                                "engine": "Needle 3 (Cactus Compute)",
                                "action": "show_chart",
                                "intent": "CHART",
                                "ticker": ticker,
                                "period": period,
                                "chart_base64": tool_res.get("chart_base64"),
                                "quote": tool_res.get("quote", {})
                            }

                    elif tool_name == "get_csv":
                        ticker = tool_res.get("ticker")
                        if not ticker or ticker.lower() in STOPWORDS:
                            logger.info(f"Needle returned non-ticker '{ticker}', routing via deterministic matcher...")
                        else:
                            period = extracted_period if extracted_period != "1mo" else tool_res.get("period", "1mo")
                            period = sanitize_period(period)
                            self.context_manager.update_user_context(user_email, last_ticker=ticker, last_action="get_csv")
                            return {
                                "status": "success",
                                "engine": "Needle 3 (Cactus Compute)",
                                "action": "get_csv",
                                "intent": "CSV",
                                "ticker": ticker,
                                "period": period,
                                "rows": tool_res.get("rows", [])
                            }

                    elif tool_name == "compare_stocks":
                        tickers = [t for t in tool_res.get("tickers", []) if t and t.lower() not in STOPWORDS]
                        if len(tickers) < 2:
                            logger.info(f"Needle returned insufficient tickers {tickers}, routing via deterministic matcher...")
                        else:
                            period = extracted_period if extracted_period != "1mo" else tool_res.get("period", "1mo")
                            period = sanitize_period(period)
                            self.context_manager.update_user_context(user_email, last_ticker=tickers[0], last_tickers=tickers, last_action="compare_stocks")
                            return {
                                "status": "success",
                                "engine": "Needle 3 (Cactus Compute)",
                                "action": "compare_stocks",
                                "intent": "COMPARE",
                                "tickers": tickers,
                                "period": period,
                                "data": tool_res.get("data", {})
                            }

                    elif tool_name == "get_comparative_csv":
                        tickers = [t for t in tool_res.get("tickers", []) if t and t.lower() not in STOPWORDS]
                        if len(tickers) < 2:
                            logger.info(f"Needle returned insufficient tickers {tickers}, routing via deterministic matcher...")
                        else:
                            period = extracted_period if extracted_period != "1mo" else tool_res.get("period", "1mo")
                            period = sanitize_period(period)
                            self.context_manager.update_user_context(user_email, last_ticker=tickers[0], last_tickers=tickers, last_action="get_comparative_csv")
                            return {
                                "status": "success",
                                "engine": "Needle 3 (Cactus Compute)",
                                "action": "get_comparative_csv",
                                "intent": "COMPARATIVE_CSV",
                                "tickers": tickers,
                                "period": period
                            }

                    elif tool_name == "chat":
                        return {
                            "status": "success",
                            "engine": "Needle 3 (Cactus Compute)",
                            "action": "chat",
                            "intent": "CHAT",
                            "message": tool_res.get("message", "Hello! I am your Edge-AI Stock Assistant.")
                        }
            except Exception as e:
                logger.warning(f"Needle 3 execution exception: {e}. Utilizing resilient fallback router.")

        # ---------------------------------------------------------------------
        # 2. RESILIENT FALLBACK: Deterministic Schema Router
        # ---------------------------------------------------------------------
        call = self.route_intent(combined, context)
        action = call.get("action")
        params = call.get("parameters", {})

        if action == "get_stock_info":
            symbol = params.get("symbol")
            data = self.market.get_stock_quote(symbol)
            self.context_manager.update_user_context(user_email, last_ticker=symbol, last_action="get_stock_info")
            return {
                "status": "success",
                "engine": "Deterministic Fallback",
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
                "engine": "Deterministic Fallback",
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
                "engine": "Deterministic Fallback",
                "action": "get_csv",
                "intent": "CSV",
                "ticker": symbol,
                "period": period,
                "rows": rows
            }

        elif action == "compare_stocks":
            symbols = params.get("symbols", [])
            period = params.get("period", "1mo")
            data = self.market.compare_stocks(symbols)
            if symbols:
                self.context_manager.update_user_context(user_email, last_ticker=symbols[0], last_tickers=symbols, last_action="compare_stocks")
            return {
                "status": "success",
                "engine": "Deterministic Fallback",
                "action": "compare_stocks",
                "intent": "COMPARE",
                "tickers": symbols,
                "period": period,
                "data": data
            }

        elif action == "get_comparative_csv":
            symbols = params.get("symbols", [])
            period = params.get("period", "1mo")
            if symbols:
                self.context_manager.update_user_context(user_email, last_ticker=symbols[0], last_tickers=symbols, last_action="get_comparative_csv")
            return {
                "status": "success",
                "engine": "Deterministic Fallback",
                "action": "get_comparative_csv",
                "intent": "COMPARATIVE_CSV",
                "tickers": symbols,
                "period": period
            }

        elif action == "not_found":
            return {
                "status": "not_found",
                "engine": "Deterministic Route",
                "action": "not_found",
                "intent": "NOT_FOUND",
                "message": call.get("message")
            }

        else:
            # action == "chat"
            return {
                "status": "success",
                "engine": "Deterministic Fallback",
                "action": "chat",
                "intent": "CHAT",
                "message": call.get("message", "Hello! How can I assist with financial data today?")
            }
