"""Intrinsic Value Checker — Streamlit app.

Search any ticker (US, or India with the .NS suffix), see its estimated
intrinsic value from five classic models next to the current price,
with the verdict and margin of safety. For learning and screening —
not financial advice.
"""

import pandas as pd
import streamlit as st

from valuation import fetch_fundamentals, value_stock

st.set_page_config(page_title="Intrinsic Value Checker", page_icon="📊")
st.title("📊 Intrinsic Value Checker")
st.caption(
    "Type a ticker — AAPL, MSFT, or an NSE India stock like RELIANCE.NS — "
    "and see its estimated intrinsic value beside the latest price. "
    "For learning and screening only, not financial advice."
)


def money(x, currency=""):
    if x is None:
        return "—"
    return f"{currency}{x:,.2f}"


with st.sidebar:
    st.header("Assumptions")
    growth_pct = st.slider("Growth rate (%)", 0.0, 25.0, 10.0, 0.5)
    discount_pct = st.slider("Discount rate (%)", 5.0, 20.0, 10.0, 0.5)
    terminal_pct = st.slider("Terminal growth (%)", 0.0, 5.0, 2.5, 0.25)
    fair_pe = st.slider("Fair P/E multiple", 5.0, 40.0, 25.0, 0.5)
    st.caption("Moving a slider recomputes every model instantly.")

col1, col2 = st.columns([3, 1])
ticker_in = col1.text_input("Stock ticker", value="AAPL", label_visibility="collapsed",
                            placeholder="e.g. AAPL or RELIANCE.NS")
go = col2.button("Analyze", type="primary", use_container_width=True)

if go or "fund" in st.session_state:
    ticker = (ticker_in or "").strip().upper()
    if go or st.session_state.get("ticker") != ticker:
        with st.spinner(f"Fetching {ticker}…"):
            try:
                st.session_state["fund"] = fetch_fundamentals(ticker)
                st.session_state["ticker"] = ticker
            except Exception as exc:  # network / bad ticker
                st.error(f"Could not fetch {ticker}: {exc}")
                st.session_state.pop("fund", None)
    fund = st.session_state.get("fund")
    if fund is not None:
        result = value_stock(
            fund,
            growth=growth_pct / 100,
            discount=discount_pct / 100,
            terminal=terminal_pct / 100,
            fair_pe=fair_pe,
        )
        iv = result["intrinsic"]
        st.subheader(f"{fund.name or fund.ticker} ({fund.ticker})")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Latest price", money(fund.price))
        m2.metric("Intrinsic value (median)", money(iv))
        mos = result["margin_of_safety"]
        m3.metric("Margin of safety", f"{mos:+.1f}%" if mos is not None else "—")
        m4.metric("Verdict", result["verdict"] or "—")
        if fund.price:
            st.caption("Price is the latest available quote — the last close when the market is shut.")

        rows = [
            {"Model": name, "Value": (f"{v:,.2f}" if v is not None else "unavailable")}
            for name, v in result["models"].items()
        ]
        st.table(pd.DataFrame(rows))

        facts = {
            "EPS (trailing)": fund.eps,
            "Book value / share": fund.bvps,
            "FCF / share": fund.fcf_per_share,
            "Dividend / share": fund.dividend,
            "P/E (trailing)": fund.pe,
            "Beta": fund.beta,
        }
        st.write("**Inputs used**")
        st.table(pd.DataFrame(
            [{"Figure": k, "Value": (f"{v:,.2f}" if v is not None else "—")}
             for k, v in facts.items()]
        ))
        if fund.growth_is_default:
            st.caption("No published growth figure was found, so the growth slider's "
                       "default stands in — set it yourself in the sidebar.")

        if fund.history:
            chart = pd.DataFrame({"Weekly close (1y)": fund.history})
            if iv:
                chart["Intrinsic value"] = iv
            st.line_chart(chart)

        if st.button("📌 Pin to watchlist"):
            wl = st.session_state.setdefault("watchlist", [])
            if fund.ticker not in wl:
                wl.append(fund.ticker)
            st.success(f"{fund.ticker} is on your watchlist.")

st.divider()
st.subheader("Watchlist")
wl = st.session_state.get("watchlist", [])
if not wl:
    st.caption("Nothing pinned yet. Analyze a stock and pin it.")
else:
    rows = []
    for t in wl:
        try:
            f = fetch_fundamentals(t)
            r = value_stock(f)
            rows.append({
                "Ticker": t,
                "Price": money(f.price),
                "Intrinsic value": money(r["intrinsic"]),
                "Verdict": r["verdict"] or "—",
            })
        except Exception:
            rows.append({"Ticker": t, "Price": "—", "Intrinsic value": "—", "Verdict": "—"})
    st.table(pd.DataFrame(rows))
    if st.button("Clear watchlist"):
        st.session_state["watchlist"] = []
        st.rerun()
