"""
Edge-AI Stock Email Bot - Main Application Entrypoint
FastAPI web application configured for Hugging Face Spaces (Basic CPU Tier).
Exposes /webhook/email for inbound email relays, dispatches real SMTP replies,
and provides /health for container liveness.
"""
import os
import urllib.parse
import logging
import threading
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import pandas as pd
from dotenv import load_dotenv

from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, EmailStr

from storage import FirestoreContextManager
from agent import NeedleStockAgent
from market import MarketEngine
from email_service import EmailBotService

load_dotenv()

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("stock_bot")

app = FastAPI(
    title="Edge-AI Stock Email Bot",
    description="Ultra-lightweight conversational stock email assistant powered by Needle 3 & Yahoo Finance.",
    version="1.0.0"
)

# Initialize persistent context manager, AI agent, market engine & email service
context_manager = FirestoreContextManager()
agent = NeedleStockAgent(context_manager=context_manager)
market = MarketEngine()
email_service = EmailBotService()
bot_email = os.environ.get("EMAIL_ADDRESS", "stonks.gro@gmail.com").strip()
email_listener_thread: Optional[threading.Thread] = None


@app.on_event("startup")
def start_cloud_listener():
    """
    Automatically starts the IMAP email polling daemon in a background thread
    when deployed to Hugging Face Spaces (or any cloud container).
    Allows the bot to continuously listen and reply to Gmail inbox 24/7.
    """
    global email_listener_thread
    enable_listener = os.environ.get("ENABLE_EMAIL_LISTENER", "true").strip().lower() in ("1", "true", "yes")

    if enable_listener and email_service.is_configured():
        from stock_bot import StockEmailBot
        bot = StockEmailBot()
        interval = int(os.environ.get("EMAIL_CHECK_INTERVAL", "10"))
        email_listener_thread = threading.Thread(
            target=bot.run_email_listener,
            kwargs={"interval": interval},
            daemon=True,
            name="CloudEmailListener"
        )
        email_listener_thread.start()
        logger.info(f"🚀 Cloud IMAP Email Listener started in background (polling every {interval}s).")
    else:
        logger.info("ℹ️ Cloud IMAP Email Listener inactive (configure EMAIL_ADDRESS and EMAIL_PASSWORD in Space Secrets).")


# Email Webhook Payload Schema
class EmailWebhookPayload(BaseModel):

    from_email: str
    subject: Optional[str] = ""
    body: Optional[str] = ""


class QueryPayload(BaseModel):
    query: str
    user_email: Optional[str] = "guest@example.com"


def create_suggestions_card(suggestions: List[str], reply_subject: str = "Re: stocks") -> str:
    """
    Renders an interactive quick-reply suggestions card.
    Instructs the user to reply directly in the current email thread,
    avoiding disruptive mailto: compose popups that break email threading.
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


def format_html_email_response(res: Dict[str, Any], user_email: str, reply_subject: str = "Re: stocks") -> str:
    """
    Constructs an interactive, high-aesthetic HTML email template with follow-up suggestions.
    """
    intent = res.get("intent", "CHAT")
    transparency_note = res.get("transparency_note")
    ticker = res.get("ticker", "AAPL")

    note_html = ""
    if transparency_note:
        note_html = f"""
        <div style="background-color: #f1f5f9; border-left: 4px solid #3b82f6; padding: 8px 12px; margin-bottom: 16px; border-radius: 4px; font-size: 12px; color: #475569;">
            ℹ️ {transparency_note}
        </div>
        """

    content_html = ""
    suggestions_html = ""

    if intent == "QUOTE":
        quote = res.get("data", {})
        if not quote.get("success", False):
            content_html = f"<p style='color: #ef4444;'>Sorry, unable to retrieve market data: {quote.get('error', 'Unknown error')}</p>"
        else:
            ticker = quote.get("ticker", ticker)
            name = quote.get("company_name", ticker)
            price = quote.get("current_price", 0.0)
            currency = quote.get("currency", "USD")
            change = quote.get("change", 0.0)
            pct = quote.get("pct_change", 0.0)
            is_pos = change >= 0
            badge_color = "#10b981" if is_pos else "#ef4444"
            sign = "+" if is_pos else ""

            content_html = f"""
            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.04);">
                <div style="display: flex; justify-content: space-between; align-items: baseline;">
                    <div>
                        <h2 style="margin: 0 0 4px 0; font-size: 20px; color: #0f172a;">{name} ({ticker})</h2>
                        <div style="font-size: 26px; font-weight: 700; color: #0f172a;">${price:,.2f} <span style="font-size: 13px; color: #64748b; font-weight: 400;">{currency}</span></div>
                    </div>
                    <div style="background: {badge_color}; color: white; padding: 6px 12px; border-radius: 20px; font-weight: 600; font-size: 13px;">
                        {sign}{change:.2f} ({sign}{pct:.2f}%)
                    </div>
                </div>
                <hr style="border: none; border-top: 1px solid #f1f5f9; margin: 16px 0;" />
                <table style="width: 100%; border-collapse: collapse; font-size: 13px; color: #475569;">
                    <tr>
                        <td style="padding: 6px 0;"><strong>Day Range:</strong></td>
                        <td style="text-align: right;">${quote.get('day_low', '-')} - ${quote.get('day_high', '-')}</td>
                    </tr>
                    <tr>
                        <td style="padding: 6px 0;"><strong>52-Week Range:</strong></td>
                        <td style="text-align: right;">${quote.get('fifty_two_week_low', '-')} - ${quote.get('fifty_two_week_high', '-')}</td>
                    </tr>
                    <tr>
                        <td style="padding: 6px 0;"><strong>Previous Close:</strong></td>
                        <td style="text-align: right;">${quote.get('previous_close', '-')}</td>
                    </tr>
                    <tr>
                        <td style="padding: 6px 0;"><strong>P/E Ratio:</strong></td>
                        <td style="text-align: right;">{quote.get('pe_ratio', 'N/A')}</td>
                    </tr>
                </table>
            </div>
            """

            suggestions_html = create_suggestions_card([
                f"Show 6 month chart for {ticker}",
                f"Show 1 year chart for {ticker}",
                f"Send me CSV data for {ticker}",
                f"Compare {ticker} and SPY"
            ], reply_subject=reply_subject)

    elif intent == "CHART":
        chart_data_uri = res.get("chart_base64")
        ticker = res.get("ticker", "Stock")
        period = res.get("period", "1mo").upper()

        img_html = ""
        if chart_data_uri:
            img_html = f"""
            <div style="margin-top: 16px; text-align: center;">
                <img src="{chart_data_uri}" alt="{ticker} {period} Chart" style="max-width: 100%; height: auto; border-radius: 8px; border: 1px solid #0f172a;" />
            </div>
            """

        content_html = f"""
        <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px;">
            <h2 style="margin: 0 0 8px 0; font-size: 20px; color: #0f172a;">{ticker} • {period} Technical Trend</h2>
            <p style="margin: 0; color: #64748b; font-size: 13px;">High-resolution vector trend plot attached below.</p>
            {img_html}
        </div>
        """

        suggestions_html = create_suggestions_card([
            f"Show 6 month chart for {ticker}",
            f"Show 1 year chart for {ticker}",
            f"Download CSV data for {ticker}",
            f"What is current price?"
        ], reply_subject=reply_subject)

    elif intent == "CSV":
        period = res.get("period", "1mo").upper()
        rows_count = len(res.get("rows", []))
        content_html = f"""
        <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px;">
            <h2 style="margin: 0 0 6px 0; font-size: 20px; color: #0f172a;">{ticker} • Historical CSV Export ({period})</h2>
            <p style="margin: 0; color: #475569; font-size: 13px;">Compiled <strong>{rows_count} sessions</strong> of historical financial data into the attached CSV spreadsheet.</p>
        </div>
        """
        suggestions_html = create_suggestions_card([
            f"Show 6 month chart for {ticker}",
            f"Send CSV data for 1 year",
            f"What is {ticker} current price?"
        ], reply_subject=reply_subject)

    elif intent == "COMPARE":
        comp = res.get("data", {})
        items = comp.get("data", [])
        cards_html = ""
        for item in items:
            t = item.get("ticker")
            p = item.get("current_price", 0.0)
            chg = item.get("change", 0.0)
            pct = item.get("pct_change", 0.0)
            is_pos = chg >= 0
            sign = "+" if is_pos else ""
            color = "#10b981" if is_pos else "#ef4444"
            cards_html += f"""
            <div style="flex: 1; min-width: 160px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 12px; margin: 4px;">
                <div style="font-weight: 700; font-size: 15px; color: #0f172a;">{t}</div>
                <div style="font-size: 18px; font-weight: 700; margin: 4px 0;">${p:,.2f}</div>
                <div style="color: {color}; font-size: 12px; font-weight: 600;">{sign}{chg:.2f} ({sign}{pct:.2f}%)</div>
                <div style="font-size: 11px; color: #64748b; margin-top: 4px;">P/E: {item.get('pe_ratio', 'N/A')}</div>
            </div>
            """

        content_html = f"""
        <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px;">
            <h2 style="margin: 0 0 12px 0; font-size: 20px; color: #0f172a;">Side-by-Side Stock Comparison</h2>
            <div style="display: flex; flex-wrap: wrap; margin: -4px;">
                {cards_html}
            </div>
        </div>
        """
        tickers = res.get("tickers", [])
        suggestions_html = create_suggestions_card([
            "Show CSV data for both",
            "Show 6 month comparison chart",
            f"Show {tickers[0]} chart" if len(tickers) >= 1 else "Show chart",
            f"Show {tickers[1]} chart" if len(tickers) >= 2 else "Show chart"
        ], reply_subject=reply_subject)

    elif intent == "COMPARATIVE_CSV":
        tickers = res.get("tickers", [])
        period = res.get("period", "1mo").upper()
        names_str = " and ".join(tickers)
        content_html = f"""
        <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px;">
            <h2 style="margin: 0 0 6px 0; font-size: 20px; color: #0f172a;">Comparative CSV Data Export ({period})</h2>
            <p style="margin: 0; color: #475569; font-size: 13px;">Aligned multi-stock historical data for <strong>{names_str}</strong> compiled into the attached CSV spreadsheet.</p>
        </div>
        """
        suggestions_html = create_suggestions_card([
            "Show 6 month comparison chart",
            f"Show {tickers[0]} analysis" if len(tickers) >= 1 else "Show analysis",
            f"Show {tickers[1]} analysis" if len(tickers) >= 2 else "Show analysis"
        ], reply_subject=reply_subject)

    else:
        msg = res.get("message", "Hello! Send a stock query or ticker name to get started.")
        content_html = f"""
        <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; line-height: 1.6; color: #334155;">
            <p style="margin-top: 0;">{msg}</p>
        </div>
        """
        suggestions_html = create_suggestions_card([
            "What is Apple price today?",
            "Show 6 month chart for TSLA",
            "Compare AAPL and NVDA",
            "Send CSV data for MSFT"
        ], reply_subject=reply_subject)
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
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background-color: #f8fafc;
            color: #0f172a;
        }}
        .email-outer {{
            width: 100% !important;
            padding: 12px 8px !important;
            box-sizing: border-box !important;
        }}
        .email-container {{
            width: 100% !important;
            max-width: 580px !important;
            margin: 0 auto !important;
            box-sizing: border-box !important;
        }}
        img {{
            max-width: 100% !important;
            height: auto !important;
            display: block !important;
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
        }}
    </style>
</head>
<body>
    <div class="email-outer">
        <div class="email-container">
            <div style="margin-bottom: 14px;">
                <span style="font-size: 20px;">📈</span>
                <span style="font-size: 15px; font-weight: 700; color: #0f172a; margin-left: 4px;">Edge-AI Stock Assistant</span>
            </div>
            {note_html}
            {content_html}
            {suggestions_html}
            <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0 16px 0;" />
            <div style="text-align: center; font-size: 11px; color: #94a3b8; word-break: break-word;">
                Powered by Needle 3 & Yahoo Finance • 100% Free Edge Execution
            </div>
        </div>
    </div>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def root():
    """Enhanced interactive dashboard & live tester for Hugging Face Spaces."""
    is_listener_active = email_listener_thread is not None and email_listener_thread.is_alive()
    listener_badge = '<span style="background: #10b981; color: white; padding: 3px 8px; border-radius: 12px; font-size: 11px; font-weight: 600;">ACTIVE 🟢</span>' if is_listener_active else '<span style="background: #f59e0b; color: white; padding: 3px 8px; border-radius: 12px; font-size: 11px; font-weight: 600;">AWAITING SECRETS ⚠️</span>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>📈 Edge-AI Stock Email Bot</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * {{ box-sizing: border-box; }}
        body {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; background: #0b0f19; color: #f8fafc; margin: 0; padding: 30px 16px; display: flex; justify-content: center; }}
        .card {{ max-width: 720px; width: 100%; background: #151e2e; border: 1px solid #1e293b; border-radius: 14px; padding: 32px; box-shadow: 0 15px 35px rgba(0,0,0,0.4); }}
        .header-badge {{ display: inline-block; background: #0ea5e9; color: white; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; margin-bottom: 14px; letter-spacing: 0.5px; }}
        h1 {{ margin: 0 0 8px 0; font-size: 26px; color: #ffffff; }}
        p.subtitle {{ color: #94a3b8; line-height: 1.6; font-size: 14px; margin: 0 0 24px 0; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 24px; }}
        .stat-item {{ background: #0d131f; padding: 14px; border-radius: 8px; border: 1px solid #1e293b; }}
        .stat-label {{ font-size: 11px; color: #64748b; text-transform: uppercase; font-weight: 600; }}
        .stat-value {{ font-size: 15px; font-weight: 700; color: #f8fafc; margin-top: 4px; }}
        .section-title {{ color: #cbd5e1; font-size: 14px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; margin: 24px 0 10px 0; display: flex; align-items: center; gap: 6px; }}
        .tester-box {{ background: #0d131f; border: 1px solid #1e293b; border-radius: 10px; padding: 18px; margin-bottom: 24px; }}
        .input-group {{ display: flex; gap: 8px; margin-bottom: 12px; }}
        .input-group input {{ flex: 1; background: #151e2e; border: 1px solid #334155; border-radius: 6px; padding: 10px 14px; color: #ffffff; font-size: 14px; font-family: inherit; }}
        .input-group input:focus {{ outline: none; border-color: #38bdf8; }}
        .btn {{ background: #2563eb; color: white; border: none; border-radius: 6px; padding: 10px 18px; font-weight: 600; font-size: 14px; cursor: pointer; transition: background 0.2s; }}
        .btn:hover {{ background: #1d4ed8; }}
        .pills {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 14px; }}
        .pill {{ background: #1e293b; color: #94a3b8; border: 1px solid #334155; border-radius: 16px; padding: 4px 10px; font-size: 12px; cursor: pointer; }}
        .pill:hover {{ background: #334155; color: #f8fafc; }}
        #output-container {{ display: none; margin-top: 14px; padding: 14px; background: #ffffff; border-radius: 8px; color: #0f172a; max-height: 450px; overflow-y: auto; }}
        .endpoint-box {{ background: #0d131f; border: 1px solid #1e293b; border-radius: 6px; padding: 12px; font-family: monospace; font-size: 13px; color: #38bdf8; margin: 8px 0; }}
        .info-callout {{ background: #132338; border-left: 4px solid #0284c7; padding: 12px; border-radius: 4px; font-size: 13px; color: #bae6fd; line-height: 1.5; }}
    </style>
</head>
<body>
    <div class="card">
        <span class="header-badge">● PRODUCTION DEPLOYMENT</span>
        <h1>📈 Edge-AI Stock Email Bot</h1>
        <p class="subtitle">Ultra-lightweight conversational stock email assistant powered by Needle 3 & Yahoo Finance.</p>
        
        <div class="grid">
            <div class="stat-item">
                <div class="stat-label">Core Engine</div>
                <div class="stat-value">Needle 3 (Edge 2-Bit)</div>
            </div>
            <div class="stat-item">
                <div class="stat-label">RAM Footprint</div>
                <div class="stat-value">&lt; 28 MB</div>
            </div>
            <div class="stat-item">
                <div class="stat-label">IMAP Listener</div>
                <div class="stat-value">{listener_badge}</div>
            </div>
            <div class="stat-item">
                <div class="stat-label">Market Engine</div>
                <div class="stat-value">Yahoo Finance API</div>
            </div>
        </div>

        <div class="section-title">⚡ Interactive Live Test Sandbox</div>
        <div class="tester-box">
            <div class="pills">
                <span class="pill" onclick="setQuery('What is Apple price?')">🍎 Apple Price</span>
                <span class="pill" onclick="setQuery('show 6 month chart for tsla')">📈 TSLA 6-Month Chart</span>
                <span class="pill" onclick="setQuery('Compare AAPL and MSFT')">📊 Compare AAPL & MSFT</span>
                <span class="pill" onclick="setQuery('Send CSV data for NVDA')">💾 NVDA CSV</span>
            </div>
            <div class="input-group">
                <input type="text" id="query-input" placeholder="Type a stock query (e.g. 'What is NVDA price?')" value="What is Apple price?" onkeydown="if(event.key==='Enter') runQuery()" />
                <button class="btn" id="run-btn" onclick="runQuery()">Run Query</button>
            </div>
            <div id="output-container"></div>
        </div>

        <div class="section-title">✉️ How to Interact via Email</div>
        <div class="info-callout">
            Send an email to <strong>{bot_email}</strong> with <strong>"stocks"</strong> in the subject line.
            The bot will reply with real-time stats, vector charts, or CSV exports. Simply hit <strong>Reply</strong> in your email client to continue the conversation in the same thread!
        </div>

        <div class="section-title">🔗 Webhook & Health Endpoints</div>
        <div class="endpoint-box">POST /webhook/email</div>
        <p style="font-size: 12px; color: #64748b; margin-top: 4px;">Accepts JSON payload: <code>{{"from_email": "user@domain.com", "subject": "stocks", "body": "Apple price"}}</code></p>
        <div class="endpoint-box"><a href="/health" style="color: #38bdf8; text-decoration: none;">GET /health</a></div>
    </div>

    <script>
        function setQuery(text) {{
            document.getElementById('query-input').value = text;
            runQuery();
        }}

        async function runQuery() {{
            const input = document.getElementById('query-input');
            const btn = document.getElementById('run-btn');
            const out = document.getElementById('output-container');
            const q = input.value.trim();
            if (!q) return;

            btn.disabled = true;
            btn.innerText = 'Analyzing...';
            out.style.display = 'block';
            out.innerHTML = '<div style="color: #475569; font-size: 13px;">Processing on-device query via Needle 3...</div>';

            try {{
                const res = await fetch('/query', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ query: q, user_email: 'web-demo@huggingface.space' }})
                }});
                const data = await res.json();
                out.innerHTML = data.html_response || '<pre style="font-size: 12px;">' + JSON.stringify(data, null, 2) + '</pre>';
            }} catch (err) {{
                out.innerHTML = '<div style="color: #ef4444; font-size: 13px;">Error: ' + err.message + '</div>';
            }} finally {{
                btn.disabled = false;
                btn.innerText = 'Run Query';
            }}
        }}
    </script>
</body>
</html>
"""


@app.get("/health")
async def health():
    """Liveness probe for container orchestration."""
    is_listener_alive = email_listener_thread is not None and email_listener_thread.is_alive()
    return {
        "status": "healthy",
        "service": "edge-ai-stock-bot",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "firestore_connected": context_manager.db is not None,
        "email_smtp_ready": email_service.is_configured(),
        "email_listener_running": is_listener_alive,
        "bot_email": bot_email
    }


@app.post("/webhook/email")
async def email_webhook(request: Request):
    """
    Secure endpoint triggered by incoming email relays (SendGrid, Mailgun, Postmark, AWS SES).
    Processes intent via Needle 3, builds interactive HTML card, and dispatches real SMTP email reply.
    """
    from_email = None
    subject = ""
    body = ""
    message_id = None

    content_type = request.headers.get("content-type", "")

    try:
        if "application/json" in content_type:
            payload = await request.json()
            from_email = payload.get("from_email") or payload.get("from") or payload.get("sender")
            subject = payload.get("subject", "")
            body = payload.get("body") or payload.get("text") or payload.get("html") or ""
            message_id = payload.get("message_id") or payload.get("Message-ID")
        else:
            form = await request.form()
            from_email = form.get("from_email") or form.get("from") or form.get("sender")
            subject = form.get("subject", "")
            body = form.get("body") or form.get("text") or form.get("html") or ""
            message_id = form.get("message_id") or form.get("Message-ID")
    except Exception as e:
        logger.error(f"Failed to parse incoming email webhook: {e}")
        raise HTTPException(status_code=400, detail="Invalid webhook payload format.")

    if not from_email:
        raise HTTPException(status_code=422, detail="Missing required 'from_email' field in payload.")

    # 1. Process through Needle 3 / Edge AI pipeline
    result = agent.process_message(user_email=str(from_email), subject=str(subject), body=str(body))
    intent = result.get("intent", "CHAT")

    # 2. Determine Thread Reply Subject & Build email body
    if subject and str(subject).strip():
        clean_subj = str(subject).strip()
        reply_subject = clean_subj if clean_subj.lower().startswith("re:") else f"Re: {clean_subj}"
    else:
        reply_subject = f"Re: Stock Update ({result.get('ticker', 'Assistant')}) 📈"

    html_email = format_html_email_response(result, user_email=str(from_email), reply_subject=reply_subject)

    # 3. Generate attachments (PNG Chart or CSV spreadsheet)
    attachments = []
    combined_query = f"{subject} {body}".lower()
    wants_chart = (intent == "CHART") or any(w in combined_query for w in ["chart", "graph", "plot", "trend", "visual"])
    wants_csv = (intent == "CSV") or any(w in combined_query for w in ["csv", "spreadsheet", "excel", "raw data", "tabular"])

    ticker = result.get("ticker", "AAPL")
    period = result.get("period", "1mo")

    if intent == "COMPARE":
        tickers = result.get("tickers", ["AAPL", "MSFT"])
        period = result.get("period", "1mo")
        if len(tickers) >= 2:
            chart_bytes = market.generate_comparison_chart(tickers, period=period)
            if chart_bytes:
                attachments.append({
                    "type": "image",
                    "data": chart_bytes,
                    "filename": f"{tickers[0]}_{tickers[1]}_comparison_{period}.png"
                })
            if wants_csv:
                comp_df = market.get_comparative_csv(tickers, period=period)
                if comp_df is not None and not comp_df.empty:
                    attachments.append({
                        "type": "csv",
                        "data": comp_df.to_csv(index=False).encode("utf-8"),
                        "filename": f"{tickers[0]}_{tickers[1]}_comparison_{period}.csv"
                    })
    elif intent == "COMPARATIVE_CSV":
        tickers = result.get("tickers", ["AAPL", "MSFT"])
        period = result.get("period", "1mo")
        if len(tickers) >= 2:
            comp_df = market.get_comparative_csv(tickers, period=period)
            if comp_df is not None and not comp_df.empty:
                attachments.append({
                    "type": "csv",
                    "data": comp_df.to_csv(index=False).encode("utf-8"),
                    "filename": f"{tickers[0]}_{tickers[1]}_comparison_{period}.csv"
                })
            if wants_chart:
                chart_bytes = market.generate_comparison_chart(tickers, period=period)
                if chart_bytes:
                    attachments.append({
                        "type": "image",
                        "data": chart_bytes,
                        "filename": f"{tickers[0]}_{tickers[1]}_comparison_{period}.png"
                    })
    else:
        ticker = result.get("ticker", "AAPL")
        period = result.get("period", "1mo")

        if wants_chart:
            chart_bytes = market.generate_trend_chart(ticker, period=period)
            if chart_bytes:
                attachments.append({
                    "type": "image",
                    "data": chart_bytes,
                    "filename": f"{ticker}_chart_{period}.png"
                })

        if wants_csv:
            rows = result.get("rows") or market.get_historical_table(ticker, period=period)
            if rows:
                df = pd.DataFrame(rows)
                attachments.append({
                    "type": "csv",
                    "data": df.to_csv(index=False).encode("utf-8"),
                    "filename": f"{ticker}_historical_{period}.csv"
                })

    # 4. Dispatch actual email via SMTP if configured
    email_dispatched = False
    if email_service.is_configured():
        if subject and str(subject).strip():
            clean_subj = str(subject).strip()
            reply_subject = clean_subj if clean_subj.lower().startswith("re:") else f"Re: {clean_subj}"
        else:
            reply_subject = f"Re: Stock Update ({result.get('ticker', 'Assistant')}) 📈"

        email_dispatched = email_service.send_email(
            to_email=str(from_email),
            subject=reply_subject,
            message=html_email,
            attachments=attachments,
            in_reply_to=message_id if message_id else None
        )
        logger.info(f"Email dispatch to {from_email} status: {email_dispatched}")

    return {
        "status": "success",
        "email_dispatched": email_dispatched,
        "user_email": from_email,
        "engine": result.get("engine"),
        "intent": result.get("intent"),
        "html_response": html_email,
        "raw_result": result
    }


@app.post("/query")
async def query_api(payload: QueryPayload):
    """
    Direct interactive test endpoint for queries.
    """
    result = agent.process_message(
        user_email=payload.user_email or "guest@example.com",
        subject="",
        body=payload.query
    )
    html_email = format_html_email_response(result, user_email=payload.user_email or "guest@example.com")

    return {
        "status": "success",
        "intent": result.get("intent"),
        "engine": result.get("engine"),
        "raw_result": result,
        "html_response": html_email
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=7860, reload=True)
