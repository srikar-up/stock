"""
Market Engine & Visuals Module
Retrieves financial assets using yfinance and creates vector trend charts via pandas and matplotlib.
"""
import io
import base64
import logging
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import pandas as pd

# Safe headless matplotlib configuration
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter
import matplotlib.gridspec as gridspec

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

logger = logging.getLogger(__name__)


def format_volume_ticks(x, pos):
    """Formats numeric volume values cleanly into K, M, B strings."""
    if x >= 1e9:
        return f"{x*1e-9:.1f}B"
    elif x >= 1e6:
        return f"{x*1e-6:.1f}M"
    elif x >= 1e3:
        return f"{x*1e-3:.0f}K"
    else:
        return f"{int(x)}"


COMPANY_TICKER_MAP = {
    "APPLE": "AAPL",
    "MICROSOFT": "MSFT",
    "GOOGLE": "GOOGL",
    "ALPHABET": "GOOGL",
    "AMAZON": "AMZN",
    "TESLA": "TSLA",
    "NVIDIA": "NVDA",
    "META": "META",
    "FACEBOOK": "META",
    "NETFLIX": "NFLX",
    "SALESFORCE": "CRM",
    "INTEL": "INTC",
    "AMD": "AMD",
    "DISNEY": "DIS",
    "COCA COLA": "KO",
    "COCA-COLA": "KO",
    "PEPSI": "PEP",
    "WALMART": "WMT",
    "COSTCO": "COST",
    "JPMORGAN": "JPM",
    "VISA": "V",
    "MASTERCARD": "MA",
    "BITCOIN": "BTC-USD",
    "ETHEREUM": "ETH-USD",
    "SP500": "SPY",
    "S&P500": "SPY",
    "NASDAQ": "QQQ",
    "TATAMOTORS": "TATAMOTORS.NS",
    "TATA MOTORS": "TATAMOTORS.NS",
    "TATA CONSULTANCY SERVICES": "TCS.NS",
    "TATA CONSULTANCY": "TCS.NS",
    "TATA STEEL": "TATASTEEL.NS",
    "TATA POWER": "TATAPOWER.NS",
    "RELIANCE": "RELIANCE.NS",
    "TCS": "TCS.NS",
    "INFOSYS": "INFY.NS",
    "HDFC": "HDFCBANK.NS",
}


def resolve_ticker(raw_ticker: str) -> str:
    """Normalizes colloquial company names into official exchange tickers."""
    clean = (raw_ticker or "AAPL").upper().strip()
    return COMPANY_TICKER_MAP.get(clean, clean)


def sanitize_period(raw_period: Any) -> str:
    """Sanitizes user, tool, or LLM period input into a valid yfinance period."""
    if not raw_period:
        return "1mo"
    p = str(raw_period).lower().strip()
    if p in {"1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"}:
        return p
    aliases = {
        "1m": "1mo", "month": "1mo", "1month": "1mo", "monthly": "1mo", "montly": "1mo",
        "3m": "3mo", "quarter": "3mo", "quarterly": "3mo",
        "6m": "6mo", "halfyear": "6mo", "6month": "6mo", "6months": "6mo", "6mont": "6mo", "6monts": "6mo", "6nont": "6mo",
        "1w": "5d", "week": "5d", "weekly": "5d", "5days": "5d",
        "1y": "1y", "1year": "1y", "year": "1y", "yearly": "1y", "annual": "1y",
        "2": "2y", "2y": "2y", "2year": "2y", "2years": "2y",
        "5": "5y", "5y": "5y", "5year": "5y", "5years": "5y",
        "all": "max", "alltime": "max", "all-time": "max"
    }
    return aliases.get(p, "1mo")


class MarketEngine:
    """
    Handles financial quote extraction, tabular historical data, and chart rendering.
    """

    @staticmethod
    def get_stock_quote(ticker: str) -> Dict[str, Any]:
        """
        Fetches real-time price, change, range, and financial stats.
        Includes fast_info extraction, weekend/holiday history fallback, and .NS <-> .BO exchange fallback.
        """
        ticker = resolve_ticker(ticker)
        if not YFINANCE_AVAILABLE:
            return {
                "ticker": ticker,
                "error": "yfinance library not installed",
                "success": False
            }

        candidates = [ticker]
        if ticker.endswith(".NS"):
            candidates.append(ticker.replace(".NS", ".BO"))
        elif ticker.endswith(".BO"):
            candidates.append(ticker.replace(".BO", ".NS"))

        last_error = f"No market data found for ticker '{ticker}'"

        for cand in candidates:
            try:
                t = yf.Ticker(cand)

                # Try 5d, fallback to 1mo if empty (handles weekends, holidays, closed exchanges)
                hist = t.history(period="5d")
                if hist.empty:
                    hist = t.history(period="1mo")

                fast_info = getattr(t, "fast_info", None)
                curr_price = None
                prev_close = None
                day_high = None
                day_low = None
                volume = None
                currency = None
                market_cap = None

                if fast_info:
                    try:
                        curr_price = getattr(fast_info, "last_price", None)
                        prev_close = getattr(fast_info, "previous_close", None) or getattr(fast_info, "regular_market_previous_close", None)
                        day_high = getattr(fast_info, "day_high", None)
                        day_low = getattr(fast_info, "day_low", None)
                        currency = getattr(fast_info, "currency", None)
                        market_cap = getattr(fast_info, "market_cap", None)
                    except Exception:
                        pass

                # Fallback to history dataframe if fast_info missing price
                if (curr_price is None or curr_price == 0) and not hist.empty:
                    curr_price = float(hist["Close"].iloc[-1])
                if (prev_close is None or prev_close == 0) and len(hist) >= 2:
                    prev_close = float(hist["Close"].iloc[-2])
                elif (prev_close is None or prev_close == 0) and not hist.empty:
                    prev_close = float(hist["Open"].iloc[-1])

                if day_high is None and not hist.empty:
                    day_high = float(hist["High"].iloc[-1])
                if day_low is None and not hist.empty:
                    day_low = float(hist["Low"].iloc[-1])
                if volume is None and not hist.empty:
                    volume = int(hist["Volume"].iloc[-1])

                if curr_price is None and hist.empty:
                    # Neither fast_info nor history yielded price, check next exchange
                    continue

                company_name = None
                pe_ratio = None
                fifty_two_week_high = None
                fifty_two_week_low = None

                try:
                    info = t.info or {}
                    company_name = info.get("longName") or info.get("shortName")
                    pe_ratio = info.get("trailingPE")
                    fifty_two_week_high = info.get("fiftyTwoWeekHigh")
                    fifty_two_week_low = info.get("fiftyTwoWeekLow")
                    if not currency:
                        currency = info.get("currency")
                except Exception:
                    pass

                if not currency:
                    currency = "INR" if cand.endswith((".NS", ".BO")) else "USD"

                if not company_name:
                    company_name = COMPANY_TICKER_MAP.get(ticker, ticker)

                change = (curr_price - prev_close) if (curr_price is not None and prev_close is not None) else 0.0
                pct_change = (change / prev_close * 100) if (prev_close and prev_close > 0) else 0.0

                return {
                    "success": True,
                    "ticker": ticker,
                    "company_name": company_name,
                    "currency": currency,
                    "current_price": round(curr_price, 2) if curr_price is not None else 0.0,
                    "previous_close": round(prev_close, 2) if prev_close is not None else 0.0,
                    "change": round(change, 2),
                    "pct_change": round(pct_change, 2),
                    "day_high": round(day_high, 2) if day_high is not None else None,
                    "day_low": round(day_low, 2) if day_low is not None else None,
                    "fifty_two_week_high": fifty_two_week_high,
                    "fifty_two_week_low": fifty_two_week_low,
                    "market_cap": market_cap,
                    "pe_ratio": pe_ratio,
                }
            except Exception as e:
                last_error = str(e)
                continue

        return {
            "ticker": ticker,
            "error": last_error,
            "success": False
        }

    @classmethod
    def _fetch_history_resilient(cls, ticker: str, period: str = "1mo") -> Tuple[pd.DataFrame, str]:
        """
        Fetches historical data with fallback across periods (e.g. 1mo -> 3mo)
        and across exchanges (e.g. .NS <-> .BO).
        Returns (history_df, resolved_ticker).
        """
        period = sanitize_period(period)
        cands = [ticker]
        if ticker.endswith(".NS"):
            cands.append(ticker.replace(".NS", ".BO"))
        elif ticker.endswith(".BO"):
            cands.append(ticker.replace(".BO", ".NS"))

        periods_to_try = [period]
        clean_p = period.lower()
        if clean_p in ["5d", "1w"]:
            periods_to_try.extend(["1mo", "3mo"])
        elif clean_p in ["1mo", "1m"]:
            periods_to_try.extend(["3mo", "6mo"])
        elif clean_p in ["3mo", "3m"]:
            periods_to_try.extend(["6mo", "1y"])
        elif clean_p in ["6mo", "6m"]:
            periods_to_try.extend(["1y", "2y"])
        else:
            periods_to_try.extend(["1y", "2y"])

        for cand in cands:
            for p in periods_to_try:
                try:
                    tk = yf.Ticker(cand)
                    h = tk.history(period=p)
                    if not h.empty and len(h) >= 2:
                        return h, cand
                except Exception:
                    continue

        return pd.DataFrame(), ticker

    @classmethod
    def get_historical_table(cls, ticker: str, period: str = "1mo") -> List[Dict[str, Any]]:
        """
        Extracts clean historical table data with resilient exchange and period fallback.
        """
        period = sanitize_period(period)
        ticker = resolve_ticker(ticker)
        if not YFINANCE_AVAILABLE:
            return []

        try:
            hist, used_ticker = cls._fetch_history_resilient(ticker, period=period)
            if hist.empty:
                hist, used_ticker = cls._fetch_history_resilient(ticker, period="1mo")
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

    @classmethod
    def generate_trend_chart(cls, ticker: str, period: str = "1mo") -> Optional[bytes]:
        """
        Renders a state-of-the-art 2-panel stock analysis chart (Screenshot 2).
        Top panel: Close Price line with shaded green fill, 20-day MA, 50-day MA, and current price line.
        Bottom panel: Daily volume bars color-coded green (up) and red (down), formatted in M and K.
        Returns raw PNG bytes.
        """
        period = sanitize_period(period)
        ticker = resolve_ticker(ticker)
        if not YFINANCE_AVAILABLE:
            return None

        try:
            # Fetch extra history so MA20 and MA50 are pre-calculated smoothly from the start
            fetch_map = {
                "1d": "5d",
                "5d": "1mo",
                "1w": "1mo",
                "1mo": "3mo",
                "1m": "3mo",
                "3mo": "6mo",
                "3m": "6mo",
                "6mo": "1y",
                "6m": "1y",
                "1y": "2y",
                "2y": "3y",
                "5y": "6y",
            }
            fetch_period = fetch_map.get(period.lower(), "1y")
            full_hist, used_ticker = cls._fetch_history_resilient(ticker, period=fetch_period)
            if full_hist.empty or len(full_hist) < 2:
                full_hist, used_ticker = cls._fetch_history_resilient(ticker, period=period)
            if full_hist.empty or len(full_hist) < 2:
                return None

            if hasattr(full_hist.index, "tz") and full_hist.index.tz is not None:
                full_hist.index = full_hist.index.tz_localize(None)

            # Calculate Moving Averages on full historical series
            full_hist["MA20"] = full_hist["Close"].rolling(window=20, min_periods=5).mean()
            full_hist["MA50"] = full_hist["Close"].rolling(window=50, min_periods=10).mean()

            # Slice to requested period
            period_days_map = {
                "1d": 2,
                "5d": 7,
                "1w": 9,
                "1mo": 33,
                "1m": 33,
                "3mo": 95,
                "3m": 95,
                "6mo": 185,
                "6m": 185,
                "1y": 370,
                "2y": 740,
                "5y": 1850
            }
            days_back = period_days_map.get(period.lower(), 33)
            cutoff_date = full_hist.index[-1] - pd.Timedelta(days=days_back)
            hist = full_hist[full_hist.index >= cutoff_date].copy()
            if len(hist) < 2:
                hist = full_hist.tail(22).copy()

            # Extract quote statistics
            curr_price = float(hist["Close"].iloc[-1])
            first_close = float(hist["Close"].iloc[0])
            price_change = curr_price - first_close
            pct_change = (price_change / first_close * 100) if first_close > 0 else 0.0
            period_high = float(hist["High"].max())
            period_low = float(hist["Low"].min())
            sign_str = "+" if pct_change >= 0 else ""

            clean_p = period.lower()
            if clean_p in ["6mo", "6m"]:
                period_label = "6-MONTH"
            elif clean_p in ["1mo", "1m"]:
                period_label = "1-MONTH"
            elif clean_p in ["3mo", "3m"]:
                period_label = "3-MONTH"
            elif clean_p in ["1y", "1year", "year"]:
                period_label = "1-YEAR"
            elif clean_p in ["5d", "1w", "week"]:
                period_label = "1-WEEK"
            elif clean_p in ["5y", "5year"]:
                period_label = "5-YEAR"
            else:
                period_label = period.upper()

            # Figure creation (2-panel clean white theme)
            fig, (ax_price, ax_vol) = plt.subplots(
                2, 1,
                figsize=(10, 6.8),
                dpi=150,
                facecolor="#ffffff",
                gridspec_kw={"height_ratios": [3.2, 1]},
                sharex=True
            )
            ax_price.set_facecolor("#ffffff")
            ax_vol.set_facecolor("#ffffff")

            dates = hist.index
            prices = hist["Close"].values

            # Plot Close Price with shaded translucent green area down to 0
            ax_price.plot(dates, prices, color="#059669", linewidth=2.2, label="Close Price")
            ax_price.fill_between(dates, prices, 0, color="#dcfce7", alpha=0.55)

            # Plot Moving Averages
            if "MA20" in hist and hist["MA20"].notna().any():
                ax_price.plot(dates, hist["MA20"], color="#f59e0b", linestyle="--", linewidth=1.5, label="20-day MA")
            if "MA50" in hist and hist["MA50"].notna().any():
                ax_price.plot(dates, hist["MA50"], color="#a855f7", linestyle="--", linewidth=1.5, label="50-day MA")

            # Reference line at current price
            ax_price.axhline(curr_price, color="#6ee7b7", linestyle=":", linewidth=1.0, alpha=0.9)

            # Set axes styling
            ax_price.set_ylabel("Price (USD)", fontsize=10, fontweight="bold", color="#1e293b")
            ax_price.set_ylim(bottom=0, top=period_high * 1.08)
            ax_price.legend(loc="upper left", frameon=True, facecolor="#ffffff", edgecolor="#e2e8f0", fontsize=9)
            ax_price.grid(True, linestyle=":", color="#f1f5f9", alpha=0.8)

            # Titles matching screenshot with explicit period
            ax_price.set_title(
                f"{ticker} Stock Analysis ({period_label})\nCurrent: ${curr_price:.2f} | Change: {sign_str}{pct_change:.2f}% | High: ${period_high:.2f} | Low: ${period_low:.2f}",
                fontsize=12,
                fontweight="bold",
                color="#0f172a",
                pad=12
            )

            # Volume bars (Green for Up day, Red for Down day)
            up_days = hist["Close"] >= hist["Open"]
            vol_colors = np.where(up_days, "#34d399", "#f87171")
            ax_vol.bar(dates, hist["Volume"], color=vol_colors, width=0.8, align="center")

            ax_vol.set_ylabel("Volume", fontsize=10, fontweight="bold", color="#1e293b")
            ax_vol.set_xlabel("Date", fontsize=10, fontweight="bold", color="#1e293b")
            ax_vol.yaxis.set_major_formatter(FuncFormatter(format_volume_ticks))
            ax_vol.grid(True, linestyle=":", color="#f1f5f9", alpha=0.8)

            # Spines cleanup
            for ax in (ax_price, ax_vol):
                for spine in ax.spines.values():
                    spine.set_color("#cbd5e1")
                    spine.set_linewidth(0.8)

            ax_vol.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=8))
            ax_vol.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
            plt.setp(ax_vol.xaxis.get_majorticklabels(), rotation=35, ha="right", fontsize=8)

            plt.tight_layout()
            buf = io.BytesIO()
            fig.savefig(buf, format="png", facecolor="#ffffff", edgecolor="none", bbox_inches="tight", dpi=150)
            plt.close(fig)
            buf.seek(0)
            return buf.getvalue()
        except Exception as e:
            logger.error(f"Error generating trend chart for {ticker}: {e}")
            return None

    @classmethod
    def generate_comparison_chart(cls, tickers: List[str], period: str = "1mo") -> Optional[bytes]:
        """
        Generates a state-of-the-art multi-panel comparative performance chart (Screenshot 1).
        Top panel: Normalized % Change from Start with 0% baseline & shaded area.
        Bottom panels: Side-by-side mini price & volume charts for each stock.
        """
        if not YFINANCE_AVAILABLE or len(tickers) < 2:
            return None

        period = sanitize_period(period)
        t1 = resolve_ticker(tickers[0])
        t2 = resolve_ticker(tickers[1])

        try:
            h1, used_t1 = cls._fetch_history_resilient(t1, period=period)
            h2, used_t2 = cls._fetch_history_resilient(t2, period=period)
            if h1.empty or h2.empty or len(h1) < 2 or len(h2) < 2:
                return None

            if hasattr(h1.index, "tz") and h1.index.tz is not None:
                h1.index = h1.index.tz_localize(None)
            if hasattr(h2.index, "tz") and h2.index.tz is not None:
                h2.index = h2.index.tz_localize(None)

            # Align on common dates
            common_idx = h1.index.intersection(h2.index)
            if len(common_idx) < 2:
                df1 = h1.copy()
                df2 = h2.copy()
            else:
                df1 = h1.loc[common_idx].copy()
                df2 = h2.loc[common_idx].copy()

            # Normalized % change from period start
            base1 = float(df1["Close"].iloc[0])
            base2 = float(df2["Close"].iloc[0])
            pct1 = ((df1["Close"] - base1) / base1) * 100.0
            pct2 = ((df2["Close"] - base2) / base2) * 100.0

            curr1 = float(df1["Close"].iloc[-1])
            curr2 = float(df2["Close"].iloc[-1])
            final1 = float(pct1.iloc[-1])
            final2 = float(pct2.iloc[-1])

            t1_sign = "▲" if final1 >= 0 else "▼"
            t2_sign = "▲" if final2 >= 0 else "▼"
            t1_lbl = f"{t1} {t1_sign} ({'+' if final1 >= 0 else ''}{final1:.2f}%)"
            t2_lbl = f"{t2} {t2_sign} ({'+' if final2 >= 0 else ''}{final2:.2f}%)"

            # Color palette
            c1_line = "#2b7bba"  # Clean blue
            c1_fill = "#3182ce"
            c2_line = "#e04f5f"  # Coral red
            c2_fill = "#e53e3e"

            clean_p = period.lower()
            if clean_p in ["6mo", "6m"]:
                period_label = "6-MONTH"
            elif clean_p in ["1mo", "1m"]:
                period_label = "1-MONTH"
            elif clean_p in ["3mo", "3m"]:
                period_label = "3-MONTH"
            elif clean_p in ["1y", "1year", "year"]:
                period_label = "1-YEAR"
            elif clean_p in ["5d", "1w", "week"]:
                period_label = "1-WEEK"
            elif clean_p in ["5y", "5year"]:
                period_label = "5-YEAR"
            else:
                period_label = period.upper()

            fig = plt.figure(figsize=(11, 8.5), dpi=150, facecolor="#ffffff")
            gs = gridspec.GridSpec(3, 2, height_ratios=[2.4, 1.2, 0.8], hspace=0.38, wspace=0.25)

            # TOP PLOT: Normalized Performance Comparison
            ax_top = fig.add_subplot(gs[0, :])
            ax_top.set_facecolor("#ffffff")
            ax_top.set_title(f"Performance Comparison ({period_label})", fontsize=14, fontweight="bold", pad=12)

            ax_top.plot(df1.index, pct1, color=c1_line, linewidth=2.4, label=t1_lbl)
            ax_top.plot(df2.index, pct2, color=c2_line, linewidth=2.4, label=t2_lbl)

            # Baseline at 0 and shaded fills
            ax_top.axhline(0, color="#64748b", linestyle="--", linewidth=1.1, alpha=0.9)
            ax_top.fill_between(df1.index, pct1, 0, where=(pct1 >= 0), color=c1_fill, alpha=0.18, interpolate=True)
            ax_top.fill_between(df1.index, pct1, 0, where=(pct1 < 0), color="#fed7d7", alpha=0.25, interpolate=True)
            ax_top.fill_between(df2.index, pct2, 0, where=(pct2 >= 0), color=c1_fill, alpha=0.12, interpolate=True)
            ax_top.fill_between(df2.index, pct2, 0, where=(pct2 < 0), color=c2_fill, alpha=0.18, interpolate=True)

            ax_top.set_ylabel("% Change from Start", fontsize=11, fontweight="bold", color="#1e293b")
            ax_top.legend(loc="lower left", frameon=True, facecolor="#ffffff", edgecolor="#cbd5e1", fontsize=10)
            ax_top.grid(True, linestyle=":", color="#e2e8f0", alpha=0.7)
            ax_top.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=5, maxticks=8))
            ax_top.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))

            # BOTTOM LEFT: Ticker 1 Mini Charts
            ax_t1_price = fig.add_subplot(gs[1, 0])
            ax_t1_vol = fig.add_subplot(gs[2, 0], sharex=ax_t1_price)

            ax_t1_price.set_facecolor("#ffffff")
            ax_t1_vol.set_facecolor("#ffffff")

            ax_t1_price.set_title(
                f"{t1_sign} {t1}: ${curr1:.2f} ({'+' if final1 >= 0 else ''}{final1:.2f}%)",
                fontsize=11,
                fontweight="bold",
                color=c1_line
            )
            ax_t1_price.plot(df1.index, df1["Close"], color=c1_line, linewidth=2.0)
            ax_t1_price.fill_between(df1.index, df1["Close"], 0, color=c1_line, alpha=0.15)
            ax_t1_price.set_ylim(bottom=0, top=df1["High"].max() * 1.08)
            ax_t1_price.set_ylabel("Price ($)", fontsize=9, fontweight="bold", color="#1e293b")
            ax_t1_price.grid(True, linestyle=":", color="#f1f5f9", alpha=0.7)
            plt.setp(ax_t1_price.get_xticklabels(), visible=False)

            up1 = df1["Close"] >= df1["Open"]
            vcolors1 = np.where(up1, "#34d399", "#f87171")
            ax_t1_vol.bar(df1.index, df1["Volume"], color=vcolors1, width=0.8, align="center")
            ax_t1_vol.set_ylabel("Volume", fontsize=9, fontweight="bold", color="#1e293b")
            ax_t1_vol.set_xlabel("Date", fontsize=9, fontweight="bold", color="#1e293b")
            ax_t1_vol.yaxis.set_major_formatter(FuncFormatter(format_volume_ticks))
            ax_t1_vol.grid(True, linestyle=":", color="#f1f5f9", alpha=0.7)
            ax_t1_vol.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=6))
            ax_t1_vol.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
            plt.setp(ax_t1_vol.xaxis.get_majorticklabels(), rotation=35, ha="right", fontsize=8)

            # BOTTOM RIGHT: Ticker 2 Mini Charts
            ax_t2_price = fig.add_subplot(gs[1, 1])
            ax_t2_vol = fig.add_subplot(gs[2, 1], sharex=ax_t2_price)

            ax_t2_price.set_facecolor("#ffffff")
            ax_t2_vol.set_facecolor("#ffffff")

            ax_t2_price.set_title(
                f"{t2_sign} {t2}: ${curr2:.2f} ({'+' if final2 >= 0 else ''}{final2:.2f}%)",
                fontsize=11,
                fontweight="bold",
                color=c2_line
            )
            ax_t2_price.plot(df2.index, df2["Close"], color=c2_line, linewidth=2.0)
            ax_t2_price.fill_between(df2.index, df2["Close"], 0, color=c2_line, alpha=0.15)
            ax_t2_price.set_ylim(bottom=0, top=df2["High"].max() * 1.08)
            ax_t2_price.set_ylabel("Price ($)", fontsize=9, fontweight="bold", color="#1e293b")
            ax_t2_price.grid(True, linestyle=":", color="#f1f5f9", alpha=0.7)
            plt.setp(ax_t2_price.get_xticklabels(), visible=False)

            up2 = df2["Close"] >= df2["Open"]
            vcolors2 = np.where(up2, "#34d399", "#f87171")
            ax_t2_vol.bar(df2.index, df2["Volume"], color=vcolors2, width=0.8, align="center")
            ax_t2_vol.set_ylabel("Volume", fontsize=9, fontweight="bold", color="#1e293b")
            ax_t2_vol.set_xlabel("Date", fontsize=9, fontweight="bold", color="#1e293b")
            ax_t2_vol.yaxis.set_major_formatter(FuncFormatter(format_volume_ticks))
            ax_t2_vol.grid(True, linestyle=":", color="#f1f5f9", alpha=0.7)
            ax_t2_vol.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=6))
            ax_t2_vol.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
            plt.setp(ax_t2_vol.xaxis.get_majorticklabels(), rotation=35, ha="right", fontsize=8)

            # Border cleanup
            for ax in [ax_top, ax_t1_price, ax_t1_vol, ax_t2_price, ax_t2_vol]:
                for spine in ax.spines.values():
                    spine.set_color("#cbd5e1")
                    spine.set_linewidth(0.8)

            buf = io.BytesIO()
            fig.savefig(buf, format="png", facecolor="#ffffff", edgecolor="none", bbox_inches="tight", dpi=150)
            plt.close(fig)
            buf.seek(0)
            return buf.getvalue()
        except Exception as e:
            logger.error(f"Error generating comparison chart for {tickers}: {e}")
            return None

    @classmethod
    def get_comparative_csv(cls, tickers: List[str], period: str = "1mo") -> Optional[pd.DataFrame]:
        """
        Creates a merged multi-stock comparative DataFrame (Screenshot 3).
        Columns formatted as:
        Date, {T1}_Close_{T1}, {T1}_High_{T1}, {T1}_Low_{T1}, {T1}_Open_{T1}, {T1}_Volume_{T1},
              {T2}_Close_{T2}, {T2}_High_{T2}, {T2}_Low_{T2}, {T2}_Open_{T2}, {T2}_Volume_{T2}
        """
        if not YFINANCE_AVAILABLE or len(tickers) < 2:
            return None

        period = sanitize_period(period)
        t1 = resolve_ticker(tickers[0])
        t2 = resolve_ticker(tickers[1])

        try:
            h1, used_t1 = cls._fetch_history_resilient(t1, period=period)
            h2, used_t2 = cls._fetch_history_resilient(t2, period=period)
            if h1.empty or h2.empty:
                return None

            if hasattr(h1.index, "tz") and h1.index.tz is not None:
                h1.index = h1.index.tz_localize(None)
            if hasattr(h2.index, "tz") and h2.index.tz is not None:
                h2.index = h2.index.tz_localize(None)

            d1 = h1.reset_index()
            d2 = h2.reset_index()
            d1["Date"] = d1["Date"].dt.strftime("%Y-%m-%d")
            d2["Date"] = d2["Date"].dt.strftime("%Y-%m-%d")

            rename_1 = {
                "Close": f"{t1}_Close_{t1}",
                "High": f"{t1}_High_{t1}",
                "Low": f"{t1}_Low_{t1}",
                "Open": f"{t1}_Open_{t1}",
                "Volume": f"{t1}_Volume_{t1}",
            }
            rename_2 = {
                "Close": f"{t2}_Close_{t2}",
                "High": f"{t2}_High_{t2}",
                "Low": f"{t2}_Low_{t2}",
                "Open": f"{t2}_Open_{t2}",
                "Volume": f"{t2}_Volume_{t2}",
            }

            cols_1 = ["Date"] + list(rename_1.values())
            cols_2 = ["Date"] + list(rename_2.values())

            d1 = d1.rename(columns=rename_1)[cols_1]
            d2 = d2.rename(columns=rename_2)[cols_2]

            merged = pd.merge(d1, d2, on="Date", how="outer").sort_values("Date").reset_index(drop=True)
            return merged
        except Exception as e:
            logger.error(f"Error creating comparative CSV for {tickers}: {e}")
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
            "tickers": tickers[:2],
            "data": results
        }
