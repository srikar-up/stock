"""
📈 Edge-AI Stock Email Bot - Standalone Poller & Email Dispatcher
100% Free Edge Execution • No Paid Cloud AI Tokens • Runs in < 28 MB RAM

Features:
- Needle 3 (Cactus Compute) Edge Tool-Calling Model
- RapidFuzz Typo-Resilient Mapping (>= 55% confidence)
- Firebase Firestore Context Persistence (merge=True)
- Yahoo Finance (yfinance) Real-Time Quotes & Historical Data
- Matplotlib Vector PNG Charts & Pandas CSV Generators
- Automated Inbound IMAP Email Listener & SMTP Auto-Responder
"""
import os
import time
import logging
from typing import Optional

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
    with zero cloud LLM cost.
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
        transparency_note = result.get("transparency_note")
        attachments = []

        # 1. Prepare attachments based on resolved intent
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

        elif intent == "COMPARE":
            tickers = result.get("tickers", ["AAPL", "MSFT"])
            # If comparing, also generate side-by-side chart
            if len(tickers) >= 2:
                chart_bytes = self.market.generate_trend_chart(tickers[0], period="1mo")
                if chart_bytes:
                    attachments.append({
                        "type": "image",
                        "data": chart_bytes,
                        "filename": f"{tickers[0]}_trend.png"
                    })

        # 2. Build email body
        email_body = self._build_email_body(result, from_email)

        # 3. Send email reply if SMTP is configured
        if self.email_service.is_configured():
            subject = "Re: Your Stock Assistant 📈"
            self.email_service.send_email(
                to_email=from_email,
                subject=subject,
                message=email_body,
                attachments=attachments
            )
            logger.info(f"✅ Response email dispatched to {from_email}")
        else:
            logger.info(f"ℹ️ Email credentials not configured in .env. Outputting response locally:\n{email_body}")

    def _build_email_body(self, result: dict, user_email: str) -> str:
        """Constructs an aesthetic HTML/text response message."""
        intent = result.get("intent", "CHAT")
        transparency_note = result.get("transparency_note")

        note_prefix = f"ℹ️ <i>{transparency_note}</i><br><br>" if transparency_note else ""

        if intent == "QUOTE":
            quote = result.get("data", {})
            if not quote.get("success"):
                return f"{note_prefix}❌ Unable to find stock data: {quote.get('error', 'Unknown error')}"

            is_up = (quote.get("change") or 0) >= 0
            emoji = "🟢" if is_up else "🔴"
            sign = "+" if is_up else ""

            return f"""{note_prefix}
{emoji} <b>{quote.get('company_name')} ({quote.get('ticker')})</b><br><br>
💰 <b>Price:</b> ${quote.get('current_price')} {quote.get('currency')}<br>
📈 <b>Change:</b> {sign}{quote.get('change')} ({sign}{quote.get('pct_change')}%)<br>
📊 <b>Day Range:</b> ${quote.get('day_low')} - ${quote.get('day_high')}<br>
📅 <b>52-Wk Range:</b> ${quote.get('fifty_two_week_low')} - ${quote.get('fifty_two_week_high')}<br>
🏢 <b>P/E Ratio:</b> {quote.get('pe_ratio', 'N/A')}<br><br>
<i>Need a visual? Reply with "send chart" or "compare with TSLA"!</i>
"""

        elif intent == "CHART":
            ticker = result.get("ticker")
            period = result.get("period", "1mo").upper()
            quote = result.get("quote", {})
            price_str = f" (${quote.get('current_price')})" if quote.get("current_price") else ""
            return f"""{note_prefix}
📈 <b>Technical Trend Chart: {ticker}{price_str}</b><br><br>
Here is the <b>{period}</b> price & volume chart you requested attached below.<br><br>
<i>You can also ask: "Compare {ticker} vs MSFT" or "Show 1 year chart".</i>
"""

        elif intent == "COMPARE":
            comp = result.get("data", {})
            items = comp.get("data", [])
            lines = [f"{note_prefix}📊 <b>Stock Comparison</b><br>"]
            for item in items:
                sign = "+" if (item.get("change") or 0) >= 0 else ""
                lines.append(
                    f"• <b>{item.get('ticker')}</b>: ${item.get('current_price')} ({sign}{item.get('pct_change')}%) | P/E: {item.get('pe_ratio', 'N/A')}"
                )
            return "<br>".join(lines)

        else:
            return f"""{note_prefix}
Hello! I am your <b>Edge-AI Stock Assistant</b> 📈<br><br>
Running 100% locally with zero cloud API overhead. You can ask me:<br>
• <i>"What is Apple's price today?"</i><br>
• <i>"Show me the TSLA chart"</i><br>
• <i>"Compare GOOGL vs MSFT"</i><br>
• <i>"What about Nvidia?"</i> (I remember context!)
"""

    def run_email_listener(self, interval: int = 15):
        """Monitors Gmail inbox via IMAP and auto-replies to user emails."""
        if not self.email_service.is_configured():
            logger.warning("EMAIL_ADDRESS or EMAIL_PASSWORD not set in .env. Cannot start listener.")
            print("\n👉 Please configure EMAIL_ADDRESS and EMAIL_PASSWORD in .env to enable email listening.")
            return

        logger.info(f"🎧 Listening for incoming emails every {interval} seconds...")
        while True:
            self.email_service.poll_inbox_and_respond(handler_callback=self.process_request)
            time.sleep(interval)


if __name__ == "__main__":
    bot = StockEmailBot()
    if bot.email_service.is_configured():
        bot.run_email_listener(interval=int(os.environ.get("EMAIL_CHECK_INTERVAL", 15)))
    else:
        print("=" * 60)
        print("📈 EDGE-AI STOCK BOT - LOCAL TEST SIMULATION")
        print("No cloud API keys needed! Running 100% free edge inference.")
        print("=" * 60)
        test_email = "investor@hedgefund.com"

        print("\n--- Test Query 1: Apple quote ---")
        bot.process_request(test_email, "Can you check apple price for me?")

        print("\n--- Test Query 2: Context continuation (chart without ticker) ---")
        bot.process_request(test_email, "Send me the chart")

        print("\n--- Test Query 3: Typo matching ('gool') ---")
        bot.process_request(test_email, "gool price today")
