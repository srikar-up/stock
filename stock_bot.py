"""
📈 Edge-AI Stock Email Bot - Standalone Poller & Email Dispatcher
100% Free Edge Execution • No Paid Cloud AI Tokens • Runs in < 28 MB RAM

Features:
- Needle 3 Structural Intelligence Layer
- RapidFuzz Typo-Resilient Mapping (Stopwords & Collision Protected)
- Firebase Firestore Context Persistence (merge=True)
- Yahoo Finance (yfinance) Real-Time Quotes & Historical Data
- Matplotlib Vector PNG Charts & Pandas CSV Generators
- Interactive One-Click Action Buttons (Chart, CSV, Compare) in HTML Replies
- Automated Inbound IMAP Email Listener & SMTP Auto-Responder
"""
import os
import re
import io
import time
import urllib.parse
import logging
from typing import Optional, List, Dict, Any
import pandas as pd
from dotenv import load_dotenv

from matcher import TickerMatcher
from storage import FirestoreContextManager
from market import MarketEngine
from agent import NeedleStockAgent
from email_service import EmailBotService

# Load environment variables from .env
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("StockEmailBot")


class StockEmailBot:
    """
    Automated Stock Email Bot running purely on edge models (Needle 3)
    with zero cloud LLM cost and interactive email action buttons.
    """

    def __init__(self):
        # 1. State Persistence
        self.context_manager = FirestoreContextManager()
        # 2. Market Analytics & Charts
        self.market = MarketEngine()
        # 3. Needle 3 Edge AI Agent
        self.agent = NeedleStockAgent(context_manager=self.context_manager)
        # 4. Email Communication Service (SMTP/IMAP)
        self.email_service = EmailBotService()
        self.bot_email = os.environ.get("EMAIL_ADDRESS", "stonks.gro@gmail.com").strip()

    def process_request(
        self,
        from_email: str,
        user_message: str,
        subject: str = "",
        message_id: str = "",
        references: str = ""
    ):
        """
        Processes an incoming query via Needle 3 and dispatches the response email.
        """
        logger.info(f"📧 Processing query from {from_email}: '{user_message}' (Subject: '{subject}')")
        try:
            # Process through Needle 3 agent with full query & subject context
            result = self.agent.process_message(
                user_email=from_email,
                subject=subject,
                body=user_message
            )

            intent = result.get("intent", "CHAT")
            attachments = []

            # ---------------------------------------------------------------------
            # 1. Prepare Attachments (Charts or CSVs)
            # ---------------------------------------------------------------------
            msg_lower = user_message.lower()
            is_unknown_or_chat = intent in ("NOT_FOUND", "CHAT")
            wants_chart = not is_unknown_or_chat and ((intent == "CHART") or any(w in msg_lower for w in ["chart", "graph", "plot", "trend", "visual"]))
            wants_csv = not is_unknown_or_chat and ((intent in ("CSV", "COMPARATIVE_CSV")) or any(
                w in msg_lower for w in ["csv", "sheet", "sheets", "spreadsheet", "spreadsheets", "excel", "raw data", "tabular", "data sheet", "datasheet", "table", "historical data"]
            ))

            if intent == "COMPARE":
                tickers = result.get("tickers", ["AAPL", "MSFT"])
                period = result.get("period", "1mo")
                if len(tickers) >= 2:
                    chart_bytes = self.market.generate_comparison_chart(tickers, period=period)
                    if chart_bytes:
                        attachments.append({
                            "type": "image",
                            "data": chart_bytes,
                            "filename": f"{tickers[0]}_{tickers[1]}_comparison_{period}.png"
                        })
                    if wants_csv:
                        comp_df = self.market.get_comparative_csv(tickers, period=period)
                        if comp_df is not None and not comp_df.empty:
                            csv_bytes = comp_df.to_csv(index=False).encode("utf-8")
                            attachments.append({
                                "type": "csv",
                                "data": csv_bytes,
                                "filename": f"{tickers[0]}_{tickers[1]}_comparison_{period}.csv"
                            })

            elif intent == "COMPARATIVE_CSV":
                tickers = result.get("tickers", ["AAPL", "MSFT"])
                period = result.get("period", "1mo")
                if len(tickers) >= 2:
                    comp_df = self.market.get_comparative_csv(tickers, period=period)
                    if comp_df is not None and not comp_df.empty:
                        csv_bytes = comp_df.to_csv(index=False).encode("utf-8")
                        attachments.append({
                            "type": "csv",
                            "data": csv_bytes,
                            "filename": f"{tickers[0]}_{tickers[1]}_comparison_{period}.csv"
                        })
                    if wants_chart:
                        chart_bytes = self.market.generate_comparison_chart(tickers, period=period)
                        if chart_bytes:
                            attachments.append({
                                "type": "image",
                                "data": chart_bytes,
                                "filename": f"{tickers[0]}_{tickers[1]}_comparison_{period}.png"
                            })
            elif not is_unknown_or_chat:
                ticker = result.get("ticker", "AAPL")
                period = result.get("period", "1mo")

                if wants_chart:
                    chart_bytes = self.market.generate_trend_chart(ticker, period=period)
                    if chart_bytes:
                        attachments.append({
                            "type": "image",
                            "data": chart_bytes,
                            "filename": f"{ticker}_chart_{period}.png"
                        })

                if wants_csv:
                    rows = result.get("rows") or self.market.get_historical_table(ticker, period=period)
                    if rows:
                        df = pd.DataFrame(rows)
                        csv_bytes = df.to_csv(index=False).encode("utf-8")
                        attachments.append({
                            "type": "csv",
                            "data": csv_bytes,
                            "filename": f"{ticker}_historical_{period}.csv"
                        })

            # ---------------------------------------------------------------------
            # 2. Determine Thread Reply Subject (Prevent 'Re: Re: Re:' stacking)
            # ---------------------------------------------------------------------
            if subject and subject.strip():
                clean_subj = subject.strip()
                base_subj = re.sub(r"^(?:re:\s*|fwd:\s*)+", "", clean_subj, flags=re.IGNORECASE).strip()
                reply_subject = f"Re: {base_subj}"
            else:
                reply_subject = f"Re: Stock Update ({result.get('ticker', 'Assistant')}) 📈"

            # ---------------------------------------------------------------------
            # 3. Build Interactive Email Body with Thread-Safe Suggestions
            # ---------------------------------------------------------------------
            email_body = self._build_email_body(result, from_email, reply_subject=reply_subject)

            # ---------------------------------------------------------------------
            # 4. Deliver via SMTP
            # ---------------------------------------------------------------------
            if self.email_service.is_configured():
                self.email_service.send_email(
                    to_email=from_email,
                    subject=reply_subject,
                    message=email_body,
                    attachments=attachments,
                    in_reply_to=message_id if message_id else None,
                    references=references if references else None
                )
                logger.info(f"✅ Response email successfully dispatched to {from_email} (In-Reply-To: {message_id})")
            else:
                logger.info(f"ℹ️ Email credentials not configured in .env. Outputting response locally:\n{email_body}")
        except Exception as e:
            logger.exception(f"❌ Unhandled error processing query from {from_email}: {e}")


    def _create_suggestions_card(self, suggestions: List[str], reply_subject: str = "Re: stocks") -> str:
        """
        Renders a clean, 100% mobile-responsive suggestions card.
        Uses full-width vertical stacked blocks with word-break to completely eliminate horizontal mobile overflow.
        """
        items_html = ""
        for s in suggestions:
            items_html += f"""
            <div style="margin: 6px 0; background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; padding: 10px 14px; font-size: 13px; color: #0f172a; font-weight: 500; display: block; width: 100%; box-sizing: border-box; word-break: break-word;">
                💬 &ldquo;{s}&rdquo;
            </div>
            """

        return f"""
        <div style="margin-top: 18px; background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px; box-sizing: border-box; width: 100%; max-width: 100%;">
            <div style="font-size: 11px; font-weight: 700; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px;">
                💡 Suggested Follow-up Questions & Choices:
            </div>
            <div style="display: block; width: 100%; box-sizing: border-box;">
                {items_html}
            </div>
            <div style="margin-top: 10px; font-size: 12px; color: #475569; border-top: 1px dashed #e2e8f0; padding-top: 8px; line-height: 1.4; word-break: break-word;">
                ↩️ <em>To continue in this same thread, simply click <strong>Reply</strong> in your email app and send any question above!</em>
            </div>
        </div>
        """

    def _build_email_body(self, result: dict, user_email: str, reply_subject: str = "Re: stocks") -> str:
        """Constructs an aesthetic, interactive HTML email with contextual suggestions."""
        intent = result.get("intent", "CHAT")
        transparency_note = result.get("transparency_note")
        ticker = result.get("ticker", "AAPL")

        note_html = ""
        if transparency_note:
            note_html = f"""
            <div style="background-color: #f1f5f9; border-left: 4px solid #3b82f6; padding: 8px 12px; margin-bottom: 16px; border-radius: 4px; font-size: 12px; color: #475569;">
                ℹ️ {transparency_note}
            </div>
            """

        content_html = ""
        suggestions_html = ""

        # =====================================================================
        # INTENT: QUOTE (Real-time financial asset card)
        # =====================================================================
        if intent == "QUOTE":
            quote = result.get("data", {})
            if not quote.get("success"):
                err = quote.get("error", "Company or market data not found.")
                content_html = f"""
                <div style="background-color: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 16px; margin-bottom: 12px;">
                    <div style="font-weight: 700; color: #b91c1c; font-size: 15px; margin-bottom: 6px;">
                        ❌ Unable to Retrieve Stock Data for '{ticker}'
                    </div>
                    <div style="font-size: 13px; color: #7f1d1d; line-height: 1.5;">
                        {err} This company may not exist in our database of ~8,000+ companies, could be unlisted, or market data is currently unavailable.
                    </div>
                </div>
                """
                suggestions_html = self._create_suggestions_card([
                    "What is Apple price?",
                    "Show Tesla 6 month chart",
                    "What is Microsoft price?"
                ], reply_subject=reply_subject)
            else:
                is_up = (quote.get("change") or 0) >= 0
                dot = "🟢" if is_up else "🔴"
                sign = "+" if is_up else ""
                curr_price = quote.get("current_price", 0.0)
                change = quote.get("change", 0.0)
                pct_change = quote.get("pct_change", 0.0)
                name = quote.get("company_name", ticker)

                content_html = f"""
                <p style="margin: 0 0 12px 0; font-size: 14px; color: #334155; line-height: 1.5;">
                    Here's the current market summary for <strong>{name} ({ticker})</strong> 📊
                </p>
                <div style="margin: 12px 0;">
                    <div style="font-size: 13px; font-weight: 700; color: #475569; margin-bottom: 6px;">
                        📊 Quick Stats:
                    </div>
                    <div style="font-size: 14px; font-weight: 600; color: #0f172a; margin-bottom: 8px;">
                        {dot} {ticker}: ${curr_price:,.2f} ({sign}{pct_change:.2f}%)
                    </div>
                    <table style="width: 100%; border-collapse: collapse; font-size: 13px; color: #475569;">
                        <tr style="border-top: 1px solid #f1f5f9;">
                            <td style="padding: 5px 0;"><strong>Day Range:</strong></td>
                            <td style="text-align: right;">${quote.get('day_low', '-')} - ${quote.get('day_high', '-')}</td>
                        </tr>
                        <tr style="border-top: 1px solid #f1f5f9;">
                            <td style="padding: 5px 0;"><strong>52-Week Range:</strong></td>
                            <td style="text-align: right;">${quote.get('fifty_two_week_low', '-')} - ${quote.get('fifty_two_week_high', '-')}</td>
                        </tr>
                        <tr style="border-top: 1px solid #f1f5f9;">
                            <td style="padding: 5px 0;"><strong>P/E Ratio:</strong></td>
                            <td style="text-align: right;">{quote.get('pe_ratio', 'N/A')}</td>
                        </tr>
                    </table>
                </div>
                """

                suggestions_html = self._create_suggestions_card([
                    f"Show 6 month chart for {ticker}",
                    f"Show 1 year chart for {ticker}",
                    f"Send me CSV data for {ticker}",
                    f"Compare {ticker} and SPY"
                ], reply_subject=reply_subject)

        # =====================================================================
        # INTENT: CHART (Visual Trend Plot)
        # =====================================================================
        elif intent == "CHART":
            period = result.get("period", "1mo").lower()
            quote = result.get("quote", {})
            chart_data_uri = result.get("chart_base64")

            if not chart_data_uri and not quote.get("success"):
                content_html = f"""
                <div style="background-color: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 16px; margin-bottom: 12px;">
                    <div style="font-weight: 700; color: #b91c1c; font-size: 15px; margin-bottom: 6px;">
                        ❌ Unable to Generate Chart for '{ticker}'
                    </div>
                    <div style="font-size: 13px; color: #7f1d1d; line-height: 1.5;">
                        Market history is unavailable for ticker '{ticker}'. This company may not exist in our database of ~8,000+ companies, or the exchange is temporarily unreachable.
                    </div>
                </div>
                """
                suggestions_html = self._create_suggestions_card([
                    "Show Apple 6 month chart",
                    "Show Tesla 1 year chart",
                    "What is Microsoft price?"
                ], reply_subject=reply_subject)
            else:
                curr_price = quote.get("current_price")
                pct_change = quote.get("pct_change", 0.0)
                is_up = pct_change >= 0
                dot = "🟢" if is_up else "🔴"
                sign = "+" if is_up else ""

                price_stat = f"<div style='font-size: 14px; font-weight: 600; color: #0f172a; margin-top: 6px;'>{dot} {ticker}: ${curr_price:,.2f} ({sign}{pct_change:.2f}%)</div>" if curr_price else ""

                content_html = f"""
                <p style="margin: 0 0 8px 0; font-size: 14px; color: #334155; line-height: 1.5;">
                    Here's the performance chart for <strong>{ticker}</strong> ({period.upper()}) 📊
                </p>
                <p style="margin: 0 0 12px 0; color: #0284c7; font-size: 13px; font-weight: 600;">
                    📊 Performance chart attached ({period})
                </p>
                <div style="margin: 12px 0;">
                    <div style="font-size: 13px; font-weight: 700; color: #475569; margin-bottom: 4px;">
                        📊 Quick Stats:
                    </div>
                    {price_stat}
                </div>
                """

                chart_sugg = [
                    f"Show 1 year chart for {ticker}",
                    f"Compare {ticker} and AAPL ({period})",
                    f"Compare {ticker} and GOOGL ({period})",
                    f"Download {period.upper()} CSV spreadsheet for {ticker}",
                ]
                if period != "6mo":
                    chart_sugg.insert(0, f"Show 6 month chart for {ticker}")
                suggestions_html = self._create_suggestions_card(chart_sugg, reply_subject=reply_subject)

        # =====================================================================
        # INTENT: CSV (Tabular Historical Export)
        # =====================================================================
        elif intent == "CSV":
            period = result.get("period", "1mo").lower()
            rows_count = len(result.get("rows", []))
            if rows_count == 0:
                content_html = f"""
                <div style="background-color: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 16px; margin-bottom: 12px;">
                    <div style="font-weight: 700; color: #b91c1c; font-size: 15px; margin-bottom: 6px;">
                        ❌ Unable to Compile CSV for '{ticker}'
                    </div>
                    <div style="font-size: 13px; color: #7f1d1d; line-height: 1.5;">
                        No historical trading sessions were found for period '{period.upper()}'. Market data is currently unavailable for this ticker.
                    </div>
                </div>
                """
                suggestions_html = self._create_suggestions_card([
                    "Download Apple CSV data",
                    "Show Tesla 6 month chart",
                    "What is Microsoft price?"
                ], reply_subject=reply_subject)
            else:
                content_html = f"""
                <p style="margin: 0 0 8px 0; font-size: 14px; color: #334155; line-height: 1.5;">
                    Here's the historical CSV data export for <strong>{ticker}</strong> 📊
                </p>
                <p style="margin: 0 0 12px 0; color: #0284c7; font-size: 13px; font-weight: 600;">
                    💾 Historical CSV spreadsheet attached ({period})
                </p>
                <p style="margin: 0; color: #475569; font-size: 13px;">
                    Compiled <strong>{rows_count} trading sessions</strong> including Date, Open, High, Low, Close, and Volume.
                </p>
                """

                suggestions_html = self._create_suggestions_card([
                    f"Show 6 month chart for {ticker}",
                    f"Send CSV data for 1 year",
                    f"What is {ticker} current price?"
                ], reply_subject=reply_subject)

        # =====================================================================
        # INTENT: COMPARE (Multi-stock comparative)
        # =====================================================================
        elif intent == "COMPARE":
            comp = result.get("data", {})
            items = comp.get("data", [])
            tickers = result.get("tickers", [])
            period = result.get("period", "1mo").lower()
            names_str = " and ".join(tickers)

            if not comp.get("success") or len(items) == 0:
                content_html = f"""
                <div style="background-color: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 16px; margin-bottom: 12px;">
                    <div style="font-weight: 700; color: #b91c1c; font-size: 15px; margin-bottom: 6px;">
                        ❌ Unable to Compare Stocks ({names_str})
                    </div>
                    <div style="font-size: 13px; color: #7f1d1d; line-height: 1.5;">
                        Could not retrieve market comparison data for <strong>{names_str}</strong>. One or both companies may not exist in our database or might be inactive.
                    </div>
                </div>
                """
                suggestions_html = self._create_suggestions_card([
                    "Compare Apple and Microsoft",
                    "Compare NVDA and AMD",
                    "Show Tesla 6 month chart"
                ], reply_subject=reply_subject)
            else:
                stats_lines = ""
                for item in items:
                    sign = "+" if (item.get("change") or 0) >= 0 else ""
                    dot = "🟢" if (item.get("change") or 0) >= 0 else "🔴"
                    stats_lines += f"""
                    <div style="font-size: 14px; font-weight: 600; color: #0f172a; margin-bottom: 6px;">
                        {dot} {item.get('ticker')}: ${item.get('current_price', 0):,.2f} ({sign}{item.get('pct_change', 0):.2f}%)
                    </div>
                    """

                content_html = f"""
                <p style="margin: 0 0 8px 0; font-size: 14px; color: #334155; line-height: 1.5;">
                    Here's the comparison for <strong>{names_str}</strong> 📊
                </p>
                <p style="margin: 0 0 12px 0; color: #0284c7; font-size: 13px; font-weight: 600;">
                    📊 Performance comparison chart attached ({period})
                </p>
                <div style="margin: 12px 0;">
                    <div style="font-size: 13px; font-weight: 700; color: #475569; margin-bottom: 6px;">
                        📊 Quick Stats:
                    </div>
                    {stats_lines}
                </div>
                """

                suggestions_html = self._create_suggestions_card([
                    "Show CSV data for both",
                    "Show 6 month comparison chart",
                    f"Show {tickers[0]} chart" if len(tickers) >= 1 else "Show chart",
                    f"Show {tickers[1]} chart" if len(tickers) >= 2 else "Show chart"
                ], reply_subject=reply_subject)

        # =====================================================================
        # INTENT: COMPARATIVE_CSV (Merged historical tabular export)
        # =====================================================================
        elif intent == "COMPARATIVE_CSV":
            tickers = result.get("tickers", [])
            period = result.get("period", "1mo").lower()
            names_str = " and ".join(tickers)

            content_html = f"""
            <p style="margin: 0 0 8px 0; font-size: 14px; color: #334155; line-height: 1.5;">
                Here's the merged comparative CSV export for <strong>{names_str}</strong> 📊
            </p>
            <p style="margin: 0 0 12px 0; color: #0284c7; font-size: 13px; font-weight: 600;">
                💾 Merged comparative CSV spreadsheet attached ({period})
            </p>
            <p style="margin: 0; color: #475569; font-size: 13px;">
                Includes aligned daily Close, High, Low, Open, and Volume columns for both <strong>{names_str}</strong>.
            </p>
            """

            suggestions_html = self._create_suggestions_card([
                "Show 6 month comparison chart",
                f"Show {tickers[0]} analysis" if len(tickers) >= 1 else "Show analysis",
                f"Show {tickers[1]} analysis" if len(tickers) >= 2 else "Show analysis"
            ], reply_subject=reply_subject)

        # =====================================================================
        # INTENT: NOT_FOUND (Company or stock not in 8000+ database)
        # =====================================================================
        elif intent == "NOT_FOUND":
            msg = result.get("message", "Company was not found in our database.")
            content_html = f"""
            <div style="background-color: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 16px; margin-bottom: 12px;">
                <div style="font-weight: 700; color: #b91c1c; font-size: 15px; margin-bottom: 6px; display: flex; align-items: center;">
                    <span style="margin-right: 6px;">🔍</span> Company Not Found in Database
                </div>
                <div style="font-size: 13px; color: #7f1d1d; line-height: 1.5;">
                    {msg}
                </div>
            </div>
            """

            suggestions_html = self._create_suggestions_card([
                "What is Apple price?",
                "Show Tesla 6 month chart",
                "What is Microsoft price?"
            ], reply_subject=reply_subject)

        # =====================================================================
        # INTENT: CHAT / HELP
        # =====================================================================
        else:
            msg = result.get("message", "Hello! How can I assist you with financial assets today?")
            content_html = f"""
            <p style="margin: 0 0 12px 0; font-size: 14px; color: #334155; line-height: 1.5;">
                {msg}
            </p>
            """

            suggestions_html = self._create_suggestions_card([
                "What is Apple price and 6 month chart?",
                "Compare NVDA and AMD",
                "Show Tesla 1 year chart"
            ], reply_subject=reply_subject)

        # Assemble Master Email Layout (Mobile-Responsive, Overflow-Proof)
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <style type="text/css">
        *, *:before, *:after {{
            box-sizing: border-box !important;
        }}
        html, body {{
            margin: 0 !important;
            padding: 0 !important;
            width: 100% !important;
            -webkit-text-size-adjust: 100% !important;
            -ms-text-size-adjust: 100% !important;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background-color: #f8fafc;
            color: #1e293b;
        }}
        .email-outer {{
            width: 100% !important;
            padding: 12px 8px !important;
            box-sizing: border-box !important;
            background-color: #f8fafc;
        }}
        .email-container {{
            width: 100% !important;
            max-width: 580px !important;
            margin: 0 auto !important;
            background-color: #ffffff !important;
            border: 1px solid #e2e8f0 !important;
            border-radius: 8px !important;
            overflow: hidden !important;
            box-sizing: border-box !important;
            box-shadow: 0 1px 3px rgba(0,0,0,0.04) !important;
        }}
        .email-header {{
            background-color: #f1f5f9 !important;
            padding: 12px 18px !important;
            border-bottom: 1px solid #e2e8f0 !important;
            box-sizing: border-box !important;
        }}
        .email-body {{
            padding: 16px 18px !important;
            box-sizing: border-box !important;
            width: 100% !important;
        }}
        img {{
            max-width: 100% !important;
            height: auto !important;
            display: block !important;
            border-radius: 6px !important;
        }}
        table {{
            width: 100% !important;
            max-width: 100% !important;
            table-layout: fixed !important;
            box-sizing: border-box !important;
        }}
        td, th {{
            word-break: break-word !important;
        }}
        @media only screen and (max-width: 600px) {{
            .email-outer {{
                padding: 4px !important;
            }}
            .email-container {{
                width: 100% !important;
                border-radius: 6px !important;
            }}
            .email-header {{
                padding: 10px 14px !important;
            }}
            .email-body {{
                padding: 12px 14px !important;
            }}
            h2 {{
                font-size: 15px !important;
            }}
        }}
    </style>
</head>
<body>
    <div class="email-outer">
        <div class="email-container">
            <div class="email-header">
                <h2 style="margin: 0; font-size: 16px; color: #0284c7; font-weight: 700; display: flex; align-items: center;">
                    <span style="margin-right: 8px;">📊</span> Finance Bot Response
                </h2>
            </div>
            <div class="email-body">
                {note_html}
                {content_html}
                {suggestions_html}
                <div style="margin-top: 18px; border-top: 1px solid #e2e8f0; padding-top: 10px; font-size: 11px; color: #94a3b8; word-break: break-word;">
                    Powered by Needle 3 & Yahoo Finance • 100% Free Edge Execution
                </div>
            </div>
        </div>
    </div>
</body>
</html>
"""

    def run_email_listener(self, interval: int = 5):
        """Monitors Gmail inbox via IMAP and auto-replies to user emails."""
        if not self.email_service.is_configured():
            logger.warning("EMAIL_ADDRESS or EMAIL_PASSWORD not set in .env. Cannot start listener.")
            print("\n👉 Please configure EMAIL_ADDRESS and EMAIL_PASSWORD in .env to enable email listening.")
            return

        logger.info(f"🎧 Listening for incoming emails on {self.bot_email} (checking every {interval}s)...")
        while True:
            self.email_service.poll_inbox_and_respond(handler_callback=self.process_request)
            time.sleep(interval)


if __name__ == "__main__":
    bot = StockEmailBot()
    if bot.email_service.is_configured():
        bot.run_email_listener(interval=int(os.environ.get("EMAIL_CHECK_INTERVAL", 5)))
    else:
        print("=" * 60)
        print("📈 EDGE-AI STOCK BOT - LOCAL TEST SIMULATION")
        print("No cloud API keys needed! Running 100% free edge inference.")
        print("=" * 60)
        test_email = "investor@hedgefund.com"
        bot.process_request(test_email, "What is Apple price?")
