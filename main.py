"""
Edge-AI Stock Email Bot - Main Application Entrypoint
FastAPI web application configured for Hugging Face Spaces (Basic CPU Tier).
Exposes /webhook/email for inbound email relays and /health for container liveness.
"""
import os
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, EmailStr

from storage import FirestoreContextManager
from agent import NeedleStockAgent

from dotenv import load_dotenv

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

# Initialize persistent context manager & AI agent
context_manager = FirestoreContextManager()
agent = NeedleStockAgent(context_manager=context_manager)


# Email Webhook Payload Schema
class EmailWebhookPayload(BaseModel):
    from_email: str
    subject: Optional[str] = ""
    body: Optional[str] = ""


class QueryPayload(BaseModel):
    query: str
    user_email: Optional[str] = "guest@example.com"


def format_html_email_response(res: Dict[str, Any], user_email: str) -> str:
    """
    Constructs a responsive, high-aesthetic HTML email template for the user.
    """
    intent = res.get("intent", "CHAT")
    transparency_note = res.get("transparency_note")

    # Banner note if fuzzy matching or context pointer was used
    note_html = ""
    if transparency_note:
        note_html = f"""
        <div style="background-color: #f1f5f9; border-left: 4px solid #3b82f6; padding: 10px 14px; margin-bottom: 20px; border-radius: 4px; font-size: 13px; color: #334155;">
            <strong>ℹ️ Note:</strong> {transparency_note}
        </div>
        """

    content_html = ""

    if intent == "QUOTE":
        quote = res.get("data", {})
        if not quote.get("success", False):
            content_html = f"<p style='color: #ef4444;'>Sorry, unable to retrieve market data: {quote.get('error', 'Unknown error')}</p>"
        else:
            ticker = quote.get("ticker")
            name = quote.get("company_name", ticker)
            price = quote.get("current_price")
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
                        <h2 style="margin: 0 0 4px 0; font-size: 22px; color: #0f172a;">{name} ({ticker})</h2>
                        <div style="font-size: 28px; font-weight: 700; color: #0f172a;">${price:,.2f} <span style="font-size: 14px; color: #64748b; font-weight: 400;">{currency}</span></div>
                    </div>
                    <div style="background: {badge_color}; color: white; padding: 6px 12px; border-radius: 20px; font-weight: 600; font-size: 14px;">
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

    elif intent == "CHART":
        chart_data_uri = res.get("chart_base64")
        ticker = res.get("ticker", "Stock")
        period = res.get("period", "1mo").upper()
        quote = res.get("quote", {})
        price_str = f"${quote.get('current_price', '-'):.2f}" if quote.get("current_price") else ""

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
            <p style="margin: 0; color: #64748b; font-size: 14px;">Latest Price: <strong>{price_str}</strong></p>
            {img_html}
        </div>
        """

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
            <div style="flex: 1; min-width: 180px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 14px; margin: 6px;">
                <div style="font-weight: 700; font-size: 16px; color: #0f172a;">{t}</div>
                <div style="font-size: 20px; font-weight: 700; margin: 4px 0;">${p:,.2f}</div>
                <div style="color: {color}; font-size: 13px; font-weight: 600;">{sign}{chg:.2f} ({sign}{pct:.2f}%)</div>
                <div style="font-size: 12px; color: #64748b; margin-top: 6px;">P/E: {item.get('pe_ratio', 'N/A')}</div>
            </div>
            """

        content_html = f"""
        <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px;">
            <h2 style="margin: 0 0 16px 0; font-size: 20px; color: #0f172a;">Side-by-Side Stock Comparison</h2>
            <div style="display: flex; flex-wrap: wrap; margin: -6px;">
                {cards_html}
            </div>
        </div>
        """

    else:
        # Standard Chat / Help
        msg = res.get("message", "Hello! Send a stock query or ticker name to get started.")
        content_html = f"""
        <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; line-height: 1.6; color: #334155;">
            <p style="margin-top: 0;">{msg}</p>
            <div style="background: #f8fafc; border-radius: 6px; padding: 12px; font-size: 13px; margin-top: 14px;">
                <strong>💡 Examples to reply with:</strong>
                <ul style="margin: 6px 0 0 0; padding-left: 20px; color: #475569;">
                    <li>"What is Apple's price today?"</li>
                    <li>"Show me the chart for TSLA"</li>
                    <li>"Compare GOOGL and MSFT"</li>
                    <li>"What about Nvidia?"</li>
                </ul>
            </div>
        </div>
        """

    # Wrap in email container
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 24px; color: #0f172a;">
    <div style="max-width: 600px; margin: 0 auto;">
        <div style="text-align: left; margin-bottom: 16px;">
            <span style="font-size: 20px;">📈</span>
            <span style="font-size: 16px; font-weight: 700; color: #0f172a; margin-left: 6px;">Edge-AI Stock Assistant</span>
        </div>
        {note_html}
        {content_html}
        <div style="text-align: center; font-size: 12px; color: #94a3b8; margin-top: 24px;">
            Powered by Needle 3 & Yahoo Finance • Near-Zero Infrastructure Footprint
        </div>
    </div>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def root():
    """
    Service landing page for Hugging Face Spaces.
    """
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>📈 Edge-AI Stock Email Bot</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Inter', sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 40px 20px; display: flex; justify-content: center; }
        .card { max-width: 680px; width: 100%; background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 32px; box-shadow: 0 10px 25px rgba(0,0,0,0.3); }
        .badge { display: inline-block; background: #10b981; color: white; padding: 4px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; margin-bottom: 16px; }
        h1 { margin: 0 0 10px 0; font-size: 24px; color: #ffffff; }
        p { color: #94a3b8; line-height: 1.6; font-size: 14px; }
        .endpoint-box { background: #0f172a; border: 1px solid #334155; border-radius: 6px; padding: 14px; font-family: monospace; font-size: 13px; color: #38bdf8; margin: 12px 0; }
        .grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin: 20px 0; }
        .stat-item { background: #0f172a; padding: 12px 16px; border-radius: 6px; border: 1px solid #334155; }
        .stat-label { font-size: 11px; color: #64748b; text-transform: uppercase; font-weight: 600; }
        .stat-value { font-size: 16px; font-weight: 700; color: #f8fafc; margin-top: 4px; }
    </style>
</head>
<body>
    <div class="card">
        <span class="badge">● SERVICE ACTIVE</span>
        <h1>📈 Edge-AI Stock Email Bot</h1>
        <p>Ultra-lightweight conversational stock email assistant optimized for Hugging Face Spaces CPU tier.</p>
        
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
                <div class="stat-label">State Persistence</div>
                <div class="stat-value">Firebase Firestore</div>
            </div>
            <div class="stat-item">
                <div class="stat-label">Market Engine</div>
                <div class="stat-value">Yahoo Finance API</div>
            </div>
        </div>

        <h3 style="color: #cbd5e1; font-size: 15px; margin-top: 24px;">Webhook Integration Endpoint:</h3>
        <div class="endpoint-box">POST /webhook/email</div>
        <p style="font-size: 12px;">Accepts JSON payload: <code>{"from_email": "user@domain.com", "subject": "Apple stock", "body": "What's the price?"}</code></p>
        
        <h3 style="color: #cbd5e1; font-size: 15px; margin-top: 20px;">Health Status:</h3>
        <div class="endpoint-box"><a href="/health" style="color: #38bdf8; text-decoration: none;">GET /health</a></div>
    </div>
</body>
</html>
"""


@app.get("/health")
async def health():
    """Liveness probe for container orchestration."""
    return {
        "status": "healthy",
        "service": "edge-ai-stock-bot",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "firestore_connected": context_manager.db is not None
    }


@app.post("/webhook/email")
async def email_webhook(request: Request):
    """
    Secure endpoint triggered by incoming email relays (SendGrid, Mailgun, Postmark, AWS SES).
    Accepts application/json or application/x-www-form-urlencoded payloads.
    """
    from_email = None
    subject = ""
    body = ""

    content_type = request.headers.get("content-type", "")

    try:
        if "application/json" in content_type:
            payload = await request.json()
            from_email = payload.get("from_email") or payload.get("from") or payload.get("sender")
            subject = payload.get("subject", "")
            body = payload.get("body") or payload.get("text") or payload.get("html") or ""
        else:
            form = await request.form()
            from_email = form.get("from_email") or form.get("from") or form.get("sender")
            subject = form.get("subject", "")
            body = form.get("body") or form.get("text") or form.get("html") or ""
    except Exception as e:
        logger.error(f"Failed to parse incoming email webhook: {e}")
        raise HTTPException(status_code=400, detail="Invalid webhook payload format.")

    if not from_email:
        raise HTTPException(status_code=422, detail="Missing required 'from_email' field in payload.")

    # Process through Edge AI pipeline
    result = agent.process_message(user_email=str(from_email), subject=str(subject), body=str(body))

    # Generate formatted email response
    html_email = format_html_email_response(result, user_email=str(from_email))

    return {
        "status": "success",
        "user_email": from_email,
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
        "raw_result": result,
        "html_response": html_email
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=7860, reload=True)
