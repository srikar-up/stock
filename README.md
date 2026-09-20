---
title: Edge AI Stock Email Bot
emoji: 📈
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# 📈 Edge-AI Stock Email Bot

Ultra-lightweight, production-ready, conversational stock email assistant powered by Needle 3 (Cactus Compute) and Yahoo Finance, designed for zero infrastructure cost and minimal data footprint on Hugging Face Spaces.

## ✨ Features

- **Needle 3 Edge AI Engine:** 2-bit edge extraction & tool calling running locally in under 28 MB RAM.
- **Typo-Resilient Pre-Processing:** RapidFuzz token matching with $\ge 55\%$ probabilistic confidence threshold.
- **Persistent State:** Firebase Firestore tracking pointers (`last_ticker`, `last_action`, `updated_at`) with `merge=True`.
- **Downstream Market Analytics:** Real-time quotes and historical technical charts via `yfinance`, `pandas`, and `matplotlib`.
- **Hugging Face Spaces Ready:** Native Docker deployment on Basic CPU Tier with `/webhook/email` relay endpoint.

## 🚀 Environment Variables

In your Hugging Face Space Settings (under **Repository Secrets**):

| Variable | Required | Description |
|---|---|---|
| `FIREBASE_CREDENTIALS_JSON` | Optional | Raw JSON string or file path to Firebase Service Account Key. If omitted, uses fast in-memory persistence. |

## 📡 API Endpoints

### 1. Inbound Email Webhook
```http
POST /webhook/email
Content-Type: application/json

{
  "from_email": "investor@example.com",
  "subject": "Apple Quote",
  "body": "What's the price of AAPL today?"
}
```

### 2. Interactive Direct Query
```http
POST /query
Content-Type: application/json

{
  "query": "Show me the TSLA chart for 1 month",
  "user_email": "investor@example.com"
}
```

### 3. Health Probe
```http
GET /health
```

## 🧪 Local Testing

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 7860
```
