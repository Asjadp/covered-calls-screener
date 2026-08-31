# Project Notes: Covered Call Screener & Yield Tracker
**Location**: `D:\Covered Calls`  
**GitHub**: `https://github.com/asjadp/covered-calls-screener`  
**Last Updated**: August 31, 2026

---

## 📌 Project Overview
A Streamlit web application, Black-Scholes quantitative probability modeling engine, and multi-backend historical database system for screening stock Covered Calls using `yfinance`. It calculates yield metrics, option Greeks (IV & Delta), and Black-Scholes probabilities, storing screening snapshots for historical backtesting and visual ROI comparisons.

---

## 📁 Key Components & Files

1. **`screener.py`**:
   - Resolves company names (e.g. `'apple'`) to tickers (`'AAPL'`).
   - Identifies target expiration dates closest to 60 days (~2-month) and 90 days (~3-month).
   - Finds nearest strikes for **+5% OTM** and **+10% OTM** targets.
   - **Yield Calculations**: Premium Yield (%), Ann. Premium Yield (%), Max ROI (%), Ann. Max ROI (%), Breakeven ($).
   - **Option Metrics**: Implied Volatility (`IV %`) and Delta.
   - **Quantitative Probabilities (Black-Scholes)**:
     - `norm_cdf(x)`: Standard normal cumulative distribution using `math.erf()`.
     - `Prob. ITM (%)`: $N(d_2)$ probability of expiring in-the-money.
     - `Prob. Hit Strike (%)`: $\min(100\%, 2 \times N(d_2))$ probability of stock price touching/hitting strike price at any point before expiration.
   - Includes 5-min caching (`@st.cache_data`) and rate-limiting pauses.

2. **`database.py`**:
   - Manages unified multi-backend data storage: **PostgreSQL (Supabase / Neon)** in the cloud and **SQLite (`covered_calls.db`)** locally.
   - Tables: `stock_snapshots` and `option_results`.
   - **Auto-Migration**: Checks existing columns and executes auto-migrations on startup so upgrading database schemas never causes data loss.
   - Functions: `init_db()`, `save_screen_results()`, `load_history()`, `get_db_status()`.

3. **`test_data_pipeline.py`**:
   - Automated data testing suite that verifies `yfinance` connectivity, option chains, and Black-Scholes formulas.
   - Captures benchmark baskets (`AAPL`, `MSFT`, `NVDA`, `TSLA`, `SPY`) and exports sample datasets:
     - `data/sample_options_dataset.csv`
     - `data/sample_options_dataset.json`

4. **`app.py`**:
   - Streamlit interactive web dashboard featuring 3 dedicated tabs:
     - **Tab 1: Live Option Screener**: Quick-pick pills (`AAPL`, `NVDA`, `TSLA`, etc.), metrics, data tables, Plotly comparison charts, and historical snapshots.
     - **Tab 2: Data Testing & Benchmark Datasets**: Offline benchmark dataset viewer & 1-click CSV/JSON exports.
     - **Tab 3: Quantitative Methodology**: Interactive LaTeX breakdown of Black-Scholes formulas and covered call equations.
   - Storage backend indicator showing active SQLite or Cloud DB connection.

5. **`.streamlit/config.toml` & `secrets.toml.example`**:
   - Production UI theme and secrets configuration template for Cloud PostgreSQL.

---

## 🚀 Live Deployment Instructions (Streamlit Community Cloud)

1. **Push to GitHub**:
   ```powershell
   git init
   git add .
   git commit -m "feat: complete covered call screener with cloud persistence and data testing"
   git branch -M main
   git remote add origin https://github.com/asjadp/covered-calls-screener.git
   git push -u origin main
   ```

2. **Deploy on Streamlit Cloud**:
   - Visit [share.streamlit.io](https://share.streamlit.io/)
   - Log in with GitHub username `asjadp`
   - Select repository `asjadp/covered-calls-screener`, branch `main`, file `app.py`
   - Deploy!
