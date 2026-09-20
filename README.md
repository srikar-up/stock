---
title: Edge AI Stock Email Bot
emoji: 📈
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# 📈 Edge-AI Stock Email Bot: Complete Architecture & Implementation Guide

> An ultra-lightweight, production-ready, conversational financial email assistant powered by **Edge AI (Needle 3 / Cactus Compute)** and **Yahoo Finance**. Engineered for **near-zero infrastructure cost**, **zero cloud LLM API bills**, and a **sub-28 MB RAM footprint**.

---

## 📖 Table of Contents
1. [Core Philosophy: Why Edge AI instead of Cloud LLMs?](#-core-philosophy-why-edge-ai-instead-of-cloud-llms)
2. [High-Level System Architecture](#-high-level-system-architecture)
3. [Component Breakdown](#-component-breakdown)
   - [1. Structural Intelligence Layer (Needle 3 Tool Router)](#1-structural-intelligence-layer-agentpy)
   - [2. Typo-Resilient Mapping & Stopwords Protection](#2-typo-resilient-mapping-matcherpy)
   - [3. Downstream Financial Engine & Visuals](#3-downstream-financial-engine--visuals-marketpy)
   - [4. State Persistence & Context Memory](#4-state-persistence--context-memory-storagepy)
   - [5. Email Transmission & Defensive Parsing](#5-email-transmission--defensive-parsing-email_servicepy)
   - [6. Interactive In-Email UI (Quick Action Buttons)](#6-interactive-in-email-ui-quick-action-buttons)
4. [File & Directory Structure](#-file--directory-structure)
5. [Getting Started & Local Setup](#-getting-started--local-setup)
6. [Hugging Face Spaces Cloud Deployment](#-hugging-face-spaces-cloud-deployment)
7. [Security & Privacy Guardrails](#-security--privacy-guardrails)

---

## 💡 Core Philosophy: Why Edge AI instead of Cloud LLMs?

Traditional AI applications rely on heavy cloud LLMs (OpenAI GPT-4, Google Gemini, Anthropic Claude). While great for open-ended creative writing, cloud LLMs introduce critical flaws for automated financial bots:
* **Ongoing API Invoices:** Pay-per-token pricing models quickly accumulate recurring costs.
* **Rate Limits & Downtime:** Free tiers throttle requests or expire completely.
* **Hallucination Risk:** Generative language models frequently invent fake stock prices or invalid ratios.
* **Massive Footprint:** Running full local LLMs requires 16+ GB of VRAM and high-tier GPUs.

### The Edge Solution:
Instead of treating the AI as an essay writer, we deploy an **Action & Tool-Calling Foundation Model (Needle 3)**:
* **Ultra-Lightweight Footprint:** Operates completely on basic CPU in **under 28 MB of RAM**.
* **Zero Cloud Bills ($0.00 Forever):** Operates on-device without external token charges.
* **100% Mathematically Accurate:** The AI acts as a **structural switchboard** that extracts user intent (`get_stock_info`, `show_chart`, `get_csv`, `compare_stocks`), while verified Python data engines (`yfinance`, `matplotlib`, `pandas`) supply real-time numbers and graphics without hallucination.

---

## 🏗️ High-Level System Architecture

```mermaid
flowchart TD
    subgraph Inbound["1. Inbound Ingestion"]
        EmailUser["Investor / User Email"] -->|IMAP Polling / Webhook| Ingest["Defensive Email Cleaner"]
        Ingest -->|Strip HTML, Signatures & Quoted History| SanitizedText["Sanitized Query String"]
    end

    subgraph Intelligence["2. Structural Intelligence Layer"]
        SanitizedText --> Pre["Typo Resolver (RapidFuzz >= 70%)"]
        Pre --> Stopwords{"Stopwords Guardrail?"}
        Stopwords -->|Blocks 'from', 'com', 'sent'| Matcher["Verified Ticker Symbol"]
        Matcher --> Context["Firestore Context Pointer (last_ticker)"]
        Context --> Needle["Needle 3 Edge Engine"]
        Needle --> IntentRouter{Intent Router}
    end

    subgraph Execution["3. Financial Analytics Engine"]
        IntentRouter -->|get_stock_info| YF_Quote["yfinance Real-Time Quotes"]
        IntentRouter -->|show_chart| Matplot["Matplotlib Dark-Mode PNG Chart"]
        IntentRouter -->|get_csv| PandasCSV["Pandas Historical Data Export"]
        IntentRouter -->|compare_stocks| Comp["Multi-Ticker Comparative Engine"]
        IntentRouter -->|chat| Fallback["Greeting / Educational Response"]
    end

    subgraph Outbound["4. Outbound Delivery"]
        YF_Quote --> MailComposer["Interactive HTML Card Generator"]
        Matplot --> MailComposer
        PandasCSV --> MailComposer
        Comp --> MailComposer
        Fallback --> MailComposer
        MailComposer --> Buttons["Pre-filled 'mailto:' Action Buttons"]
        Buttons --> StateSave["Firestore Pointer Update (merge=True)"]
        Buttons --> SMTP["SMTP Dispatcher (Gmail Port 587)"]
        SMTP --> Delivery["User's Email Inbox"]
    end
```

---

## 🧩 Component Breakdown

### 1. Structural Intelligence Layer (`agent.py`)
Acts as the central router that converts unstructured user text into verified system calls.
* **Supported Schemas:**
  * `get_stock_info(symbol)`: Retrieves real-time prices, percentage changes, day range, 52-week range, and P/E ratios.
  * `show_chart(symbol, period)`: Generates high-resolution PNG price and volume trend plots.
  * `get_csv(symbol, period)`: Exports multi-session historical data into a spreadsheet.
  * `compare_stocks(symbols, period)`: Side-by-side performance analysis (enforces a hard limit of **maximum 2 tickers** to prevent chart clutter).
  * `chat`: Fallback for greetings (*"hi"*, *"hello"*) or parameter education (e.g., asking to compare 3+ tickers).
* **Pronoun & Context Continuation:** If a user first inquires about Apple and then sends *"Show me its chart"*, the agent inspects the user's metadata pointer in storage and resolves *"its"* to `AAPL`.

---

### 2. Typo-Resilient Mapping (`matcher.py`)
Because on-device edge models prioritize tool syntax over vast text vocabularies, `matcher.py` normalizes informal company names and noisy typos into official stock tickers.
* **Priority Matching:** Primary companies (*Apple $\rightarrow$ AAPL*, *Tesla $\rightarrow$ TSLA*, *Google $\rightarrow$ GOOGL*, *Nvidia $\rightarrow$ NVDA*) are evaluated first.
* **Stopwords Protection:** Explicitly ignores common conversational words and email artifacts (*from, com, org, net, price, stock, cost, send, me, for*) to prevent false ticker triggers (e.g. preventing the word `.com` or `from` from colliding with Salesforce `CRM`).
* **Probabilistic Threshold:** Uses `rapidfuzz.process.extractOne` with a conservative **$\ge 70\%$ confidence threshold** to correct genuine misspellings (*"gool"* $\rightarrow$ *GOOGL*, *"amazn"* $\rightarrow$ *AMZN*).

---

### 3. Downstream Financial Engine & Visuals (`market.py`)
* **Real-Time Data:** Direct integration with `yfinance` to pull live prices, previous closes, daily high/lows, and market capitalization.
* **Dark-Mode Technical Visuals:** Built on headless `matplotlib` (`Agg` backend). Draws modern slate-themed (`#0f172a`) charts with volume subplots, glowing price markers, grid lines, and adaptive emerald green / coral red fills based on net performance.
* **Tabular CSV Generator:** Uses `pandas` to compile date, open, high, low, close, and volume records into downloadable `.csv` attachments.

---

### 4. State Persistence & Context Memory (`storage.py`)
Hugging Face Space containers sleep and restart periodically. Standard in-memory variables are lost upon container sleep.
* **Zero Row Accumulation:** Operates on **Firebase Firestore** using key-value document overwrites with `merge=True`.
* **Minimal Data Footprint:** Tracks only three lightweight pointers per user email:
  ```json
  {
    "last_ticker": "AAPL",
    "last_action": "get_stock_info",
    "updated_at": "2026-09-20T19:00:00Z"
  }
  ```
* **Offline / Local Fallback:** If `FIREBASE_CREDENTIALS_JSON` is not provided during local testing, it automatically defaults to an in-memory dictionary so local execution never crashes.

---

### 5. Email Transmission & Defensive Parsing (`email_service.py`)
* **Inbound (IMAP):** Connects via SSL over port 993 to check for `UNSEEN` messages.
* **Defensive Sanitation:**
  * Strips HTML markup (`<style>`, `<script>`, `<tags>`).
  * Cuts off quoted email threads (lines starting with `>` or `On ... wrote:`) so the bot never re-reads previous bot responses.
  * Ignores emails sent from the bot's own address (`stonks.gro@gmail.com`) to prevent infinite automated loops.
* **Outbound (SMTP):** Sends replies over TLS (port 587) using `MIMEMultipart`, seamlessly attaching `.png` charts and `.csv` files.

---

### 6. Interactive In-Email UI (Quick Action Buttons)
Because email clients block JavaScript, our bot embeds **one-click pre-filled `mailto:` buttons** into the HTML cards:

```html
<!-- Interactive Quick-Action Example -->
<a href="mailto:stonks.gro@gmail.com?subject=AAPL%20Chart&body=Show%20me%20the%20chart%20for%20AAPL"
   style="background: #2563eb; color: #fff; padding: 9px 15px; border-radius: 6px; text-decoration: none; font-weight: 600;">
   📈 Get 1M Chart
</a>
```

When an investor opens an email on mobile or desktop, they can simply tap:
* **`[ 📈 Get 1M Chart ]`** $\rightarrow$ Instantly pre-fills a reply requesting the chart.
* **`[ 💾 Download CSV ]`** $\rightarrow$ Pre-fills a reply requesting the raw spreadsheet.
* **`[ 📊 Compare vs SPY ]`** $\rightarrow$ Pre-fills a reply comparing the stock to the S&P 500.

---

## 📁 File & Directory Structure

```
e:\code\stock\
├── .env                  # Private credentials (Gmail, App Password, Firestore key)
├── .env.example          # Safe template for version control
├── .gitignore            # Protects secrets, venvs, and cache files
├── requirements.txt      # Open-source Python dependencies
├── matcher.py            # Typo-resilient fuzzy resolver & stopwords filter
├── storage.py            # Firestore persistent context manager (merge=True)
├── market.py             # Yahoo Finance extraction & Matplotlib chart renderer
├── agent.py              # Needle 3 Structural Intelligence Layer
├── email_service.py      # IMAP email listener & SMTP sender with quote-stripping
├── stock_bot.py          # Standalone background email bot listener
├── main.py               # FastAPI webhook server for cloud deployments
├── Dockerfile            # Lightweight CPU container spec for Hugging Face Spaces
├── README.md             # Architecture blueprint & setup documentation
└── test_bot.py           # Automated unit test suite
```

---

## 🚀 Getting Started & Local Setup

### 1. Prerequisites
* Python 3.11+
* A Gmail account with 2-Step Verification enabled.

### 2. Installation
Activate your virtual environment and install the required dependencies:
```powershell
# Activate your environment
stocks\Scripts\Activate.ps1

# Install pinned dependencies
pip install -r requirements.txt
```

### 3. Configure Credentials in `.env`
Create or edit your [`.env`](file:///e:/code/stock/.env) file:
```ini
# Gmail Account to receive and send emails
EMAIL_ADDRESS=stonks.gro@gmail.com

# 16-character Google App Password (https://myaccount.google.com/apppasswords)
EMAIL_PASSWORD=your_16_char_password

# Outbound & Inbound Server Settings
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
IMAP_SERVER=imap.gmail.com
IMAP_PORT=993
EMAIL_CHECK_INTERVAL=5

# Optional: Firebase Service Account Key (for persistent cloud storage)
FIREBASE_CREDENTIALS_JSON=okso-5d0d0-firebase-adminsdk-fbsvc-5f515b88d3.json
```

### 4. Running the Bot Locally
To start the live email listener:
```powershell
python stock_bot.py
```
Send an email from your phone or personal address to **`stonks.gro@gmail.com`**:
* **Subject:** `Apple`
* **Body:** `What is Apple's price today?`

Watch your terminal log the incoming message and deliver the financial card back to your inbox in seconds!

---

## ☁️ Hugging Face Spaces Cloud Deployment

This repository is pre-configured for deployment on **Hugging Face Spaces** (Free CPU Tier):

1. Create a new Space on [Hugging Face](https://huggingface.co/spaces) and select **Docker** as the SDK.
2. Push this repository to your Space.
3. In your Space **Settings** $\rightarrow$ **Variables and Secrets**, add:
   * `EMAIL_ADDRESS`
   * `EMAIL_PASSWORD`
   * `FIREBASE_CREDENTIALS_JSON` (Paste the raw JSON content of your service account key).
4. The Space will automatically build the container via [`Dockerfile`](file:///e:/code/stock/Dockerfile) and expose:
   * `GET /health` — Health check endpoint.
   * `POST /webhook/email` — Secure webhook endpoint for incoming email relays (SendGrid, Mailgun, Postmark).

---

## 🔒 Security & Privacy Guardrails

1. **Zero Secret Leakage:**
   * [`.gitignore`](file:///e:/code/stock/.gitignore) strictly prevents `.env`, `*firebase*.json`, and `*adminsdk*.json` from ever being pushed to public repositories.
2. **Infinite Loop Prevention:**
   * `email_service.py` verifies the sender header and discards any messages originating from the bot's own address.
3. **Quoted Thread Isolation:**
   * All email responses strip previous reply threads (`> ...`), preventing circular context degradation.
4. **Data Isolation:**
   * Firebase keys and tokens are stored in environment variables, never hardcoded into source code.
