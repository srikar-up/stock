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

    def process_request(self, from_email: str, user_message: str):
        """
        Processes an incoming query via Needle 3 and dispatches the response email.
        """
        logger.info(f"📧 Processing query from {from_email}: '{user_message}'")

        # Process through Needle 3 agent
        result = self.agent.process_message(
            user_email=from_email,
            subject="",
            body=user_message
        )

        intent = result.get("intent", "CHAT")
        attachments = []

        # ---------------------------------------------------------------------
        # 1. Prepare Attachments (Charts or CSVs)
        # ---------------------------------------------------------------------
        if intent == "CHART":
            ticker = result.get("ticker", "AAPL")
            period = result.get("period", "1mo")
            chart_bytes = self.market.generate_trend_chart(ticker, period=period)
            if chart_bytes:
                attachments.append({
                    "type": "image",
                    "data": chart_bytes,
                    "filename": f"{ticker}_chart_{period}.png"
                })

        elif intent == "CSV":
            ticker = result.get("ticker", "AAPL")
            period = result.get("period", "1mo")
            rows = result.get("rows", [])
            if rows:
                df = pd.DataFrame(rows)
                csv_bytes = df.to_csv(index=False).encode("utf-8")
                attachments.append({
                    "type": "csv",
                    "data": csv_bytes,
                    "filename": f"{ticker}_historical_{period}.csv"
                })

        elif intent == "COMPARE":
            tickers = result.get("tickers", ["AAPL", "MSFT"])
            if len(tickers) >= 2:
                chart_bytes = self.market.generate_trend_chart(tickers[0], period="1mo")
                if chart_bytes:
                    attachments.append({
                        "type": "image",
                        "data": chart_bytes,
                        "filename": f"{tickers[0]}_trend.png"
                    })

        # ---------------------------------------------------------------------
        # 2. Build Interactive Email Body with Action Buttons
        # ---------------------------------------------------------------------
        email_body = self._build_email_body(result, from_email)

        # ---------------------------------------------------------------------
        # 3. Deliver via SMTP
        # ---------------------------------------------------------------------
        if self.email_service.is_configured():
            subject = f"Re: Stock Update ({result.get('ticker', 'Assistant')}) 📈"
            self.email_service.send_email(
                to_email=from_email,
                subject=subject,
                message=email_body,
                attachments=attachments
            )
            logger.info(f"✅ Response email successfully dispatched to {from_email}")
        else:
            logger.info(f"ℹ️ Email credentials not configured in .env. Outputting response locally:\n{email_body}")

    def _create_mailto_button(self, label: str, subject: str, body: str, bg_color: str = "#2563eb", text_color: str = "#ffffff") -> str:
        """Generates a pre-filled, one-click interactive mailto button for email clients."""
        encoded_subj = urllib.parse.quote(subject)
        encoded_body = urllib.parse.quote(body)
        mailto_url = f"mailto:{self.bot_email}?subject={encoded_subj}&body={encoded_body}"

        return f"""
        <a href="{mailto_url}" target="_blank" style="
            display: inline-block;
            background-color: {bg_color};
            color: {text_color};
            padding: 9px 15px;
            margin: 4px;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 600;
            text-decoration: none;
            box-shadow: 0 1px 2px rgba(0,0,0,0.08);
        ">{label}</a>
        """

    def _build_email_body(self, result: dict, user_email: str) -> str:
        """Constructs an aesthetic, interactive HTML email with action buttons."""
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
        action_buttons_html = ""

        # =====================================================================
        # INTENT: QUOTE (Real-time financial asset card)
        # =====================================================================
        if intent == "QUOTE":
            quote = result.get("data", {})
            if not quote.get("success"):
                content_html = f"<p style='color: #ef4444;'>❌ Unable to find stock data: {quote.get('error', 'Unknown error')}</p>"
            else:
                is_up = (quote.get("change") or 0) >= 0
                badge_color = "#10b981" if is_up else "#ef4444"
                sign = "+" if is_up else ""
                curr_price = quote.get("current_price", 0.0)
                change = quote.get("change", 0.0)
                pct_change = quote.get("pct_change", 0.0)
                name = quote.get("company_name", ticker)

                content_html = f"""
                <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.03);">
                    <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 12px;">
                        <div>
                            <h2 style="margin: 0; font-size: 20px; color: #0f172a;">{name} ({ticker})</h2>
                            <div style="font-size: 26px; font-weight: 700; color: #0f172a; margin-top: 4px;">
                                ${curr_price:,.2f} <span style="font-size: 13px; color: #64748b; font-weight: 400;">{quote.get('currency', 'USD')}</span>
                            </div>
                        </div>
                        <div style="background: {badge_color}; color: white; padding: 6px 12px; border-radius: 20px; font-weight: 600; font-size: 13px;">
                            {sign}{change:.2f} ({sign}{pct_change:.2f}%)
                        </div>
                    </div>
                    <table style="width: 100%; border-collapse: collapse; font-size: 13px; color: #475569; margin-top: 12px;">
                        <tr style="border-top: 1px solid #f1f5f9;">
                            <td style="padding: 6px 0;"><strong>Day Range:</strong></td>
                            <td style="text-align: right;">${quote.get('day_low', '-')} - ${quote.get('day_high', '-')}</td>
                        </tr>
                        <tr style="border-top: 1px solid #f1f5f9;">
                            <td style="padding: 6px 0;"><strong>52-Week Range:</strong></td>
                            <td style="text-align: right;">${quote.get('fifty_two_week_low', '-')} - ${quote.get('fifty_two_week_high', '-')}</td>
                        </tr>
                        <tr style="border-top: 1px solid #f1f5f9;">
                            <td style="padding: 6px 0;"><strong>P/E Ratio:</strong></td>
                            <td style="text-align: right;">{quote.get('pe_ratio', 'N/A')}</td>
                        </tr>
                    </table>
                </div>
                """

                # Interactive Action Buttons
                btn_chart = self._create_mailto_button("📈 Get 1M Chart", f"{ticker} Chart Request", f"Show me the chart for {ticker}", bg_color="#2563eb")
                btn_csv = self._create_mailto_button("💾 Download CSV", f"{ticker} CSV Export", f"Send me CSV data for {ticker}", bg_color="#0f172a")
                btn_compare_spy = self._create_mailto_button("📊 Compare vs SPY", f"Compare {ticker} vs SPY", f"Compare {ticker} and SPY", bg_color="#475569")
                btn_compare_tsla = self._create_mailto_button("⚡ Compare vs Tesla", f"Compare {ticker} vs TSLA", f"Compare {ticker} and TSLA", bg_color="#475569")

                action_buttons_html = f"""
                <div style="margin-top: 20px;">
                    <div style="font-size: 12px; font-weight: 700; color: #64748b; text-transform: uppercase; margin-bottom: 8px;">
                        ⚡ Quick Interactive Actions (Tap to Reply):
                    </div>
                    <div style="display: flex; flex-wrap: wrap; margin: -4px;">
                        {btn_chart}
                        {btn_csv}
                        {btn_compare_spy}
                        {btn_compare_tsla}
                    </div>
                </div>
                """

        # =====================================================================
        # INTENT: CHART (Visual Trend Plot)
        # =====================================================================
        elif intent == "CHART":
            period = result.get("period", "1mo").upper()
            content_html = f"""
            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px;">
                <h2 style="margin: 0 0 6px 0; font-size: 20px; color: #0f172a;">{ticker} • {period} Technical Chart</h2>
                <p style="margin: 0 0 14px 0; color: #64748b; font-size: 13px;">Your requested price & volume trend plot is attached below as a high-resolution PNG.</p>
            </div>
            """

            btn_csv = self._create_mailto_button("💾 Download Raw CSV", f"{ticker} CSV Export", f"Send me CSV data for {ticker}", bg_color="#0f172a")
            btn_1y_chart = self._create_mailto_button("📅 1-Year Trend", f"{ticker} 1Y Chart", f"Show me the 1y chart for {ticker}", bg_color="#2563eb")
            btn_quote = self._create_mailto_button("💰 Refresh Price", f"{ticker} Quote", f"What is {ticker} price today?", bg_color="#10b981")

            action_buttons_html = f"""
            <div style="margin-top: 20px;">
                <div style="font-size: 12px; font-weight: 700; color: #64748b; text-transform: uppercase; margin-bottom: 8px;">
                    ⚡ Next Steps:
                </div>
                <div>{btn_csv} {btn_1y_chart} {btn_quote}</div>
            </div>
            """

        # =====================================================================
        # INTENT: CSV (Tabular Historical Export)
        # =====================================================================
        elif intent == "CSV":
            period = result.get("period", "1mo").upper()
            rows_count = len(result.get("rows", []))
            content_html = f"""
            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px;">
                <h2 style="margin: 0 0 6px 0; font-size: 20px; color: #0f172a;">{ticker} • Historical Data Export ({period})</h2>
                <p style="margin: 0; color: #475569; font-size: 13px;">
                    Compiled <strong>{rows_count} trading sessions</strong> into an attached CSV spreadsheet (includes Date, Open, High, Low, Close, Volume).
                </p>
            </div>
            """

            btn_chart = self._create_mailto_button("📈 View Chart Instead", f"{ticker} Chart", f"Show me the chart for {ticker}", bg_color="#2563eb")
            btn_quote = self._create_mailto_button("💰 Get Current Price", f"{ticker} Quote", f"What is {ticker} price today?", bg_color="#10b981")
            action_buttons_html = f"<div style='margin-top: 20px;'>{btn_chart} {btn_quote}</div>"

        # =====================================================================
        # INTENT: COMPARE (Multi-stock comparative)
        # =====================================================================
        elif intent == "COMPARE":
            comp = result.get("data", {})
            items = comp.get("data", [])
            cards_html = ""
            for item in items:
                sign = "+" if (item.get("change") or 0) >= 0 else ""
                color = "#10b981" if (item.get("change") or 0) >= 0 else "#ef4444"
                cards_html += f"""
                <div style="flex: 1; min-width: 160px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 12px; margin: 4px;">
                    <div style="font-weight: 700; font-size: 15px; color: #0f172a;">{item.get('ticker')}</div>
                    <div style="font-size: 18px; font-weight: 700; margin: 4px 0;">${item.get('current_price', 0):,.2f}</div>
                    <div style="color: {color}; font-size: 12px; font-weight: 600;">{sign}{item.get('pct_change', 0):.2f}%</div>
                    <div style="font-size: 11px; color: #64748b; margin-top: 4px;">P/E: {item.get('pe_ratio', 'N/A')}</div>
                </div>
                """

            content_html = f"""
            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px;">
                <h2 style="margin: 0 0 12px 0; font-size: 20px; color: #0f172a;">Stock Comparison</h2>
                <div style="display: flex; flex-wrap: wrap; margin: -4px;">
                    {cards_html}
                </div>
            </div>
            """

        # =====================================================================
        # INTENT: CHAT / HELP
        # =====================================================================
        else:
            msg = result.get("message", "Hello! How can I assist you with financial assets today?")
            content_html = f"""
            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; line-height: 1.6; color: #334155;">
                <p style="margin-top: 0;">{msg}</p>
            </div>
            """
            btn_apple = self._create_mailto_button("🍎 Check Apple Price", "Apple Quote", "What is Apple price today?", bg_color="#0f172a")
            btn_tesla = self._create_mailto_button("⚡ Check Tesla Price", "Tesla Quote", "What is Tesla price today?", bg_color="#0f172a")
            btn_nvda = self._create_mailto_button("🎮 Check Nvidia Price", "Nvidia Quote", "What is Nvidia price today?", bg_color="#0f172a")
            action_buttons_html = f"<div style='margin-top: 16px;'>{btn_apple} {btn_tesla} {btn_nvda}</div>"

        # Assemble Master Email Layout
        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 24px; color: #0f172a;">
    <div style="max-width: 600px; margin: 0 auto;">
        <div style="margin-bottom: 14px;">
            <span style="font-size: 20px;">📈</span>
            <span style="font-size: 15px; font-weight: 700; color: #0f172a; margin-left: 4px;">Edge-AI Stock Assistant</span>
        </div>
        {note_html}
        {content_html}
        {action_buttons_html}
        <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0 16px 0;" />
        <div style="text-align: center; font-size: 11px; color: #94a3b8;">
            Powered by Needle 3 & Yahoo Finance • 100% Free Edge Execution
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
