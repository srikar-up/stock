# 📈 Edge-AI Stock Email Bot: Project Blueprint

## 🎯 Project Goal & Scope
The goal of this project is to build and deploy an **ultra-lightweight, production-ready, conversational stock email assistant**. The bot intercepts user emails, infers intent (fetching data, charts, or comparison summaries), tracks light context pointers, and responds with real-time financial assets—all while maintaining a **near-zero infrastructure cost** and **minimal data footprint**.

---

## 🛠️ Technology Stack & Core Systems

### 1. The Core AI Engine: **Needle 3**
* **Why We Use It:** Instead of heavy cloud LLMs, we deploy Needle 3—an ultra-small open-source foundation model optimized by Cactus Compute for **2-bit edge extraction** and tool calling.
* **Footprint:** Runs completely locally in Python using **under 28 MB of RAM**.
* **Ready-Made Dependency:** We rely on the raw C++ inference wrapped inside the `cactus-needle` package. **No massive PyTorch runtime is needed**, protecting container storage.

### 2. Typo-Resilient Mapping: **Fuzzy Pre-Processing**
* **Why We Use It:** Needle 3 focuses strictly on execution schemas, not vast text vocabularies. We map messy phrasing (e.g., *"apple"* or *"gool"*) to valid tickers (*"AAPL"*, *"GOOGL"*).
* **The Tools:** A local, fast text lookup dictionary mapping company strings paired with `rapidfuzz`. 
* **Confidence Mechanics:** If a direct match fails, the code evaluates a **probabilistic best guess**. If a query clears a ≥ 55% threshold, it provides transparent model feedback to the user; otherwise, it handles it safely as standard `CHAT`.

### 3. State Persistence & Storage: **Firebase Firestore**
* **Why We Use It:** Hugging Face Space containers sleep or restart periodically. Firestore ensures persistent memory.
* **Storage Footprint:** We optimized the data schema down to **lightweight tracking metadata pointers** (`last_ticker`, `last_action`, `updated_at`) using flat key-value document overwrites (`merge=True`). No row accumulation ensures it stays inside the free tier indefinitely.

### 4. Data Harvesting & Delivery: **Downstream Engines**
* **Market Engine:** Pulls real-time prices and financial information directly from Yahoo Finance via `yfinance`.
* **Visuals:** Generates clean historical data tables and vector trend line plots locally using `pandas` and `matplotlib`.

---

## 🚀 Hosting & Deployment Strategy

* **The Platform:** **Hugging Face Spaces** (Basic CPU Tier).
* **Environment Architecture:** Configured via a **FastAPI** Python application wrapped in a lightweight web container.
* **Webhooks:** Exposes a secure endpoint (`/webhook/email`) triggered by incoming email relays.
* **Security Guardrails:** Production database access tokens and Firebase configuration certificates are completely isolated from code as **Hugging Face Secret Environment Variables** (`FIREBASE_CREDENTIALS_JSON`).
