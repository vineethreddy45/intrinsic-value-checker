# Intrinsic Value Checker

Search any stock ticker — US stocks like `AAPL` or `MSFT`, or NSE India
stocks with the `.NS` suffix like `RELIANCE.NS` — and see its estimated
**intrinsic value** next to the latest price, with an
Undervalued / Fairly valued / Overvalued verdict and margin of safety.

## How it values a stock

Five classic models run on the company's published fundamentals
(EPS, book value, free cash flow, dividend, growth). The headline
intrinsic value is the **median** of the models that can be computed —
a model whose inputs are missing shows as unavailable rather than
inventing a number.

1. **DCF** — free cash flow per share projected 5 years, discounted,
   plus a terminal value.
2. **Graham growth formula** — EPS × (8.5 + 2g).
3. **Graham Number** — √(22.5 × EPS × book value per share).
4. **Fair P/E** — EPS × a fair P/E multiple.
5. **Dividend discount** — Gordon growth model on the dividend.

Sidebar sliders (growth, discount rate, terminal growth, fair P/E)
recompute every model instantly, so you can stress-test the assumptions
instead of trusting one set of numbers.

## Run it locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy free on Streamlit Cloud

1. Push this repo to GitHub.
2. Go to [share.streamlit.io](https://share.streamlit.io) and sign in
   with GitHub.
3. **New app** → pick this repository, branch `main`, main file
   `app.py` → **Deploy**.

## Note

Built for learning and screening. Intrinsic value is an estimate that
moves with the assumptions — it is not financial advice.
