"""
Market Engine & Visuals Module
Retrieves financial assets using yfinance and creates vector trend charts via pandas and matplotlib.
"""
import io
import base64
import logging
from typing import Dict, Any, List, Optional
import pandas as pd

# Safe headless matplotlib configuration
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

logger = logging.getLogger(__name__)


class MarketEngine:
    """
    Handles financial quote extraction, tabular historical data, and chart rendering.
    """

    @staticmethod
    def get_stock_quote(ticker: str) -> Dict[str, Any]:
        """
        Fetches real-time price, change, range, and financial stats.
        """
        ticker = ticker.upper().strip()
        if not YFINANCE_AVAILABLE:
            return {
                "ticker": ticker,
                "error": "yfinance library not installed",
                "success": False
            }

        try:
            t = yf.Ticker(ticker)
            info = t.info or {}
            hist = t.history(period="5d")

            if hist.empty and not info.get("currentPrice"):
                return {
                    "ticker": ticker,
                    "error": f"No market data found for ticker '{ticker}'",
                    "success": False
                }

            # Price extraction with fallback to latest history
            curr_price = info.get("currentPrice") or info.get("regularMarketPrice")
            prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose")

            if curr_price is None and not hist.empty:
                curr_price = float(hist["Close"].iloc[-1])
            if prev_close is None and len(hist) >= 2:
                prev_close = float(hist["Close"].iloc[-2])

            change = (curr_price - prev_close) if (curr_price is not None and prev_close is not None) else 0.0
            pct_change = (change / prev_close * 100) if (prev_close and prev_close > 0) else 0.0

            day_high = info.get("dayHigh") or (float(hist["High"].iloc[-1]) if not hist.empty else None)
            day_low = info.get("dayLow") or (float(hist["Low"].iloc[-1]) if not hist.empty else None)
            volume = info.get("volume") or (int(hist["Volume"].iloc[-1]) if not hist.empty else None)

            return {
                "success": True,
                "ticker": ticker,
                "company_name": info.get("longName") or info.get("shortName") or ticker,
                "currency": info.get("currency", "USD"),
                "current_price": round(curr_price, 2) if curr_price is not None else None,
                "previous_close": round(prev_close, 2) if prev_close is not None else None,
                "change": round(change, 2),
                "pct_change": round(pct_change, 2),
                "day_high": round(day_high, 2) if day_high is not None else None,
                "day_low": round(day_low, 2) if day_low is not None else None,
                "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
                "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
                "market_cap": info.get("marketCap"),
                "pe_ratio": info.get("trailingPE"),
            }
        except Exception as e:
            logger.error(f"Error fetching quote for {ticker}: {e}")
            return {
                "ticker": ticker,
                "error": str(e),
                "success": False
            }

    @staticmethod
    def get_historical_table(ticker: str, period: str = "5d") -> List[Dict[str, Any]]:
        """
        Extracts clean historical table data.
        """
        ticker = ticker.upper().strip()
        if not YFINANCE_AVAILABLE:
            return []

        try:
            t = yf.Ticker(ticker)
            hist = t.history(period=period)
            if hist.empty:
                return []

            records = []
            for date_idx, row in hist.iterrows():
                date_str = date_idx.strftime("%Y-%m-%d")
                records.append({
                    "date": date_str,
                    "open": round(float(row["Open"]), 2),
                    "high": round(float(row["High"]), 2),
                    "low": round(float(row["Low"]), 2),
                    "close": round(float(row["Close"]), 2),
                    "volume": int(row["Volume"]),
                })
            return records
        except Exception as e:
            logger.error(f"Error extracting history for {ticker}: {e}")
            return []

    @staticmethod
    def generate_trend_chart(ticker: str, period: str = "1mo") -> Optional[bytes]:
        """
        Renders a modern, high-contrast dark-mode financial trend line plot.
        Returns raw PNG bytes.
        """
        ticker = ticker.upper().strip()
        if not YFINANCE_AVAILABLE:
            return None

        try:
            t = yf.Ticker(ticker)
            hist = t.history(period=period)
            if hist.empty or len(hist) < 2:
                return None

            # Color palette (Modern FinTech Dark)
            bg_color = "#0f172a"      # Deep slate blue
            card_color = "#1e293b"    # Card background
            grid_color = "#334155"    # Subtle grid
            text_color = "#f8fafc"    # Off-white

            first_close = hist["Close"].iloc[0]
            last_close = hist["Close"].iloc[-1]
            is_positive = last_close >= first_close
            line_color = "#10b981" if is_positive else "#ef4444"  # Emerald green or coral red
            fill_color = "#064e3b" if is_positive else "#7f1d1d"

            fig, ax = plt.subplots(figsize=(8, 4.2), dpi=140, facecolor=bg_color)
            ax.set_facecolor(card_color)

            dates = hist.index
            prices = hist["Close"].values

            # Plot line and area fill
            ax.plot(dates, prices, color=line_color, linewidth=2.2, label=f"{ticker} Close")
            ax.fill_between(dates, prices, min(prices) * 0.998, color=fill_color, alpha=0.35)

            # Highlighting current price point
            ax.scatter([dates[-1]], [prices[-1]], color=line_color, s=40, zorder=5)
            ax.annotate(
                f"${prices[-1]:.2f}",
                (dates[-1], prices[-1]),
                textcoords="offset points",
                xytext=(-15, 10),
                color=text_color,
                fontweight="bold",
                fontsize=10,
                bbox=dict(boxstyle="round,pad=0.2", fc=card_color, ec=line_color, lw=1)
            )

            # Styling axes
            title_text = f"{ticker} • {period.upper()} Trend ({'+' if is_positive else ''}{((last_close - first_close)/first_close*100):.2f}%)"
            ax.set_title(title_text, color=text_color, fontsize=12, fontweight="bold", pad=12)
            ax.tick_params(colors="#94a3b8", labelsize=8)
            ax.grid(True, color=grid_color, linestyle="--", linewidth=0.6, alpha=0.6)

            for spine in ax.spines.values():
                spine.set_color(grid_color)
                spine.set_linewidth(0.8)

            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
            fig.autofmt_xdate(rotation=20)
            plt.tight_layout()

            buf = io.BytesIO()
            fig.savefig(buf, format="png", facecolor=bg_color, edgecolor="none")
            plt.close(fig)
            buf.seek(0)
            return buf.getvalue()
        except Exception as e:
            logger.error(f"Error generating chart for {ticker}: {e}")
            return None

    @staticmethod
    def chart_to_base64_data_uri(image_bytes: bytes) -> str:
        """Encodes PNG bytes to base64 data URI for inline email HTML."""
        if not image_bytes:
            return ""
        encoded = base64.b64encode(image_bytes).decode("utf-8")
        return f"data:image/png;base64,{encoded}"

    @classmethod
    def compare_stocks(cls, tickers: List[str]) -> Dict[str, Any]:
        """
        Retrieves side-by-side comparison data for multiple tickers.
        """
        results = []
        for t in tickers[:2]:  # Enforce strict MAX 2 tickers policy
            quote = cls.get_stock_quote(t)
            if quote.get("success"):
                results.append(quote)

        return {
            "success": len(results) > 0,
            "tickers": tickers,
            "data": results
        }
