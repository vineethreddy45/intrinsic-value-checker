"""Intrinsic value estimation for a stock ticker.

Fetches fundamentals from Yahoo Finance (via yfinance) and runs five
classic valuation models. Every model that cannot be computed from the
available data returns None instead of inventing a number.

Yahoo rate-limits shared cloud IPs (e.g. Streamlit Cloud), so fetching
uses a browser-like session, retries, and falls back to fast_info,
price history, and the financial statements when the summary endpoint
returns nothing.
"""

from __future__ import annotations

import math
import statistics
import time
from dataclasses import dataclass, field

import yfinance as yf

GROWTH_CAP = 0.25          # models never assume growth above 25%
DEFAULT_GROWTH = 0.10      # used only when no growth figure is published

_SESSION = None


def _session():
    """A browser-like HTTP session (Yahoo blocks plain cloud clients)."""
    global _SESSION
    if _SESSION is None:
        try:
            from curl_cffi import requests as cffi

            _SESSION = cffi.Session(impersonate="chrome")
        except Exception:
            import requests

            s = requests.Session()
            s.headers.update({
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36"
                )
            })
            _SESSION = s
    return _SESSION


@dataclass
class Fundamentals:
    ticker: str
    name: str | None = None
    currency: str | None = None
    price: float | None = None
    eps: float | None = None            # trailing EPS
    bvps: float | None = None           # book value per share
    fcf_per_share: float | None = None  # free cash flow per share
    dividend: float | None = None       # annual dividend per share
    growth: float | None = None         # earnings growth (fraction), if published
    growth_is_default: bool = False
    pe: float | None = None
    market_cap: float | None = None
    beta: float | None = None
    history: list = field(default_factory=list)  # weekly closes, ~1 year
    missing: list = field(default_factory=list)  # figures no source provided


def _pos(value):
    """Return value only when it is a real, finite number."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _row(df, names):
    """First matching row's most recent value from a statements frame."""
    if df is None or getattr(df, "empty", True):
        return None
    for name in names:
        if name in df.index:
            try:
                return _pos(df.loc[name].iloc[0])
            except Exception:
                continue
    return None


def fetch_fundamentals(ticker: str) -> Fundamentals:
    """Pull the fundamentals for one ticker from Yahoo Finance."""
    t = yf.Ticker(ticker, session=_session())

    info: dict = {}
    for _ in range(2):
        try:
            info = t.get_info() or {}
        except Exception:
            info = {}
        if info:
            break
        time.sleep(1.5)

    price = _pos(info.get("currentPrice")) or _pos(info.get("regularMarketPrice")) \
        or _pos(info.get("previousClose"))
    shares = _pos(info.get("sharesOutstanding"))
    market_cap = _pos(info.get("marketCap"))

    # fast_info fallback (a different, lighter Yahoo endpoint)
    try:
        fi = t.fast_info
        if price is None:
            price = _pos(fi.get("lastPrice")) or _pos(fi.get("previousClose"))
        if shares is None:
            shares = _pos(fi.get("shares"))
        if market_cap is None:
            market_cap = _pos(fi.get("marketCap"))
    except Exception:
        pass

    history: list = []
    try:
        hist = t.history(period="1y", interval="1wk")
        if hist is not None and not hist.empty:
            history = [float(x) for x in hist["Close"].dropna().tolist()]
    except Exception:
        history = []
    if price is None and history:
        price = history[-1]  # latest weekly close stands in for the quote

    eps = _pos(info.get("trailingEps"))
    bvps = _pos(info.get("bookValue"))
    fcf = _pos(info.get("freeCashflow"))
    fcf_ps = fcf / shares if (fcf is not None and shares) else None

    # Financial-statement fallbacks when the summary gave nothing
    if shares and (eps is None or bvps is None or fcf_ps is None):
        try:
            if eps is None:
                net_income = _row(t.income_stmt, ["Net Income", "Net Income Common Stockholders"])
                if net_income is not None:
                    eps = net_income / shares
            if bvps is None:
                equity = _row(t.balance_sheet, [
                    "Stockholders Equity", "Total Stockholder Equity",
                    "Common Stock Equity", "Total Equity Gross Minority Interest",
                ])
                if equity is not None:
                    bvps = equity / shares
            if fcf_ps is None:
                cf = t.cashflow
                op = _row(cf, ["Operating Cash Flow", "Total Cash From Operating Activities"])
                capex = _row(cf, ["Capital Expenditure", "Capital Expenditures"])
                if op is not None and capex is not None:
                    fcf_ps = (op + capex) / shares  # capex is negative
        except Exception:
            pass

    growth = _pos(info.get("earningsGrowth"))
    if growth is None:
        growth = _pos(info.get("revenueGrowth"))
    is_default = growth is None
    if is_default:
        growth = DEFAULT_GROWTH

    fund = Fundamentals(
        ticker=ticker.upper(),
        name=info.get("longName") or info.get("shortName"),
        currency=info.get("currency"),
        price=price,
        eps=eps,
        bvps=bvps,
        fcf_per_share=fcf_ps,
        dividend=_pos(info.get("dividendRate")),
        growth=growth,
        growth_is_default=is_default,
        pe=_pos(info.get("trailingPE")),
        market_cap=market_cap,
        beta=_pos(info.get("beta")),
        history=history,
    )
    fund.missing = [
        label for label, val in [
            ("price", price), ("EPS", eps), ("book value", bvps),
            ("free cash flow", fcf_ps), ("dividend", fund.dividend),
        ] if val is None
    ]
    return fund


def dcf_value(fcf_ps, growth, discount, terminal, years: int = 5):
    """Discounted cash flow on free cash flow per share."""
    if not fcf_ps or fcf_ps <= 0 or discount <= terminal:
        return None
    g = min(max(growth, 0.0), GROWTH_CAP)
    total = 0.0
    fcf = fcf_ps
    for i in range(1, years + 1):
        fcf = fcf_ps * (1 + g) ** i
        total += fcf / (1 + discount) ** i
    terminal_value = fcf * (1 + terminal) / (discount - terminal)
    total += terminal_value / (1 + discount) ** years
    return total


def graham_growth_value(eps, growth):
    """Benjamin Graham's growth formula: EPS x (8.5 + 2g)."""
    if not eps or eps <= 0:
        return None
    g_pct = min(max(growth, 0.0), GROWTH_CAP) * 100
    return eps * (8.5 + 2 * g_pct)


def graham_number(eps, bvps):
    """Graham Number: sqrt(22.5 x EPS x book value per share)."""
    if not eps or not bvps or eps <= 0 or bvps <= 0:
        return None
    return math.sqrt(22.5 * eps * bvps)


def fair_pe_value(eps, fair_pe):
    """Value at a chosen fair P/E multiple."""
    if not eps or eps <= 0:
        return None
    return eps * fair_pe


def dividend_discount_value(dividend, growth, discount):
    """Gordon growth model on the dividend."""
    if not dividend or dividend <= 0:
        return None
    dg = min(max(growth, 0.0), GROWTH_CAP)
    if dg >= discount:
        dg = discount - 0.01
    if dg < 0:
        return None
    return dividend * (1 + dg) / (discount - dg)


def value_stock(f: Fundamentals, growth=None, discount: float = 0.10,
                terminal: float = 0.025, fair_pe: float = 25.0) -> dict:
    """Run all five models and summarise against the current price."""
    g = f.growth if growth is None else growth
    models = {
        "DCF (free cash flow)": dcf_value(f.fcf_per_share, g, discount, terminal),
        "Graham growth formula": graham_growth_value(f.eps, g),
        "Graham Number": graham_number(f.eps, f.bvps),
        "Fair P/E": fair_pe_value(f.eps, fair_pe),
        "Dividend discount": dividend_discount_value(f.dividend, g, discount),
    }
    available = [v for v in models.values() if v is not None]
    intrinsic = statistics.median(available) if available else None

    verdict = None
    margin_of_safety = None
    if intrinsic and f.price:
        margin_of_safety = (intrinsic - f.price) / intrinsic * 100
        if f.price <= 0.9 * intrinsic:
            verdict = "Undervalued"
        elif f.price >= 1.1 * intrinsic:
            verdict = "Overvalued"
        else:
            verdict = "Fairly valued"

    return {
        "models": models,
        "intrinsic": intrinsic,
        "verdict": verdict,
        "margin_of_safety": margin_of_safety,
    }
