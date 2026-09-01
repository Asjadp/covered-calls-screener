# Project Notes: Covered Call Screener & Yield Tracker
**Location**: `D:\Covered Calls`  
**GitHub**: `https://github.com/asjadp/covered-calls-screener`  
**Last Updated**: August 31, 2026

---

## 📌 Project Overview
A quantitative Python web application, options mathematical engine, and historical database system for screening stock Covered Calls using `yfinance`, Streamlit, Plotly, SQLite, and cloud PostgreSQL (Supabase/Neon). It calculates yield metrics, option Greeks (IV & Delta), and Black-Scholes risk-neutral probabilities, featuring intelligent rate-limiting and market-hours caching.

---

## 📁 Key Components & Architecture

1. **`app.py`**:
   - Streamlit interactive web dashboard with 2 focused tabs:
     - **Tab 1: 🎯 Covered Call Screener & Yield Matrix**: Quick-pick pills (`AAPL`, `NVDA`, `TSLA`, `MSFT`, `SPY`, `AMD`), live metrics, options table, CSV export, Plotly comparison charts, and historical snapshots.
     - **Tab 2: 📐 Quantitative Methodology & Formulas**: LaTeX formulas for Black-Scholes $N(d_2)$, Strike Touch probability, and yield calculations.
   - Prominent **Data Sourced Timestamp** banner with origin indicators (`Database Snapshot` vs `Real-Time Live Quote`).
   - Clean UI with all rate limiting and controls handled invisibly in the background.

2. **`screener.py`**:
   - Ticker and company name resolution.
   - Dynamic expiration target selection (~60-day & ~90-day cycles) and OTM strike resolution (+5% & +10% OTM).
   - Quantitative mathematical calculations:
     - Implied Volatility (`IV %`) & Delta.
     - `Prob. ITM (%)` ($N(d_2)$) & `Prob. Hit Strike (%)` ($\approx 2 \times N(d_2)$).
     - Premium Yield (%), Ann. Premium Yield (%), Max ROI (%), Ann. Max ROI (%), and Breakeven ($).
   - In-memory 15-minute caching (`@st.cache_data(ttl=900)`).
   - 3-attempt exponential backoff retry loop for Yahoo Finance API stability.

3. **`database.py`**:
   - Unified multi-backend persistence: **Local SQLite (`covered_calls.db`)** by default, with auto-detection for free **Cloud PostgreSQL (Supabase / Neon)** via `DATABASE_URL`.
   - Tables: `stock_snapshots` and `option_results` with automated column migrations.
   - Functions: `init_db()`, `save_screen_results()`, `load_history()`, `get_latest_snapshot()`, `get_db_status()`.

4. **`api_monitor.py` (Background Traffic & Rate Limiting Engine)**:
   - **Market-Closed Smart Freeze**: When US markets are closed (after 4:00 PM ET or weekends), once a closing snapshot is captured, 0 API calls are made for that ticker until the next market open at 9:30 AM ET.
   - **Burst Rate Limiting**: Maximum 5 live calls per 60-second rolling window.
   - **Session Cap**: Maximum 10 live calls per session.
   - **Cooldown Delay**: Enforces 1.2-second pause between sequential requests.
   - **Automatic DB Fallback**: Seamlessly loads verified database snapshots if rate limits or API throttles are encountered.

5. **`test_data_pipeline.py` & `data/`**:
   - Local automated testing suite validating `yfinance` connectivity, option chains, and Black-Scholes math.
   - Generates benchmark test datasets (`data/sample_options_dataset.csv` and `.json`).

6. **Deployment & Config Files**:
   - `requirements.txt`: Production dependencies (`streamlit`, `yfinance`, `pandas`, `plotly`, `SQLAlchemy`, etc.).
   - `.gitignore`: Ignoring caches, virtual environments, and secrets.
   - `.streamlit/config.toml`: Clean financial dashboard dark theme.
   - `.streamlit/secrets.toml.example`: Template for Supabase/Neon connection URI.
   - `LICENSE`: MIT License.

---

## 🚀 Live Deployment Instructions (Streamlit Community Cloud)

1. **Push to GitHub**:
   ```powershell
   git remote add origin https://github.com/asjadp/covered-calls-screener.git
   git push -u origin main
   ```

2. **Deploy on Streamlit Cloud**:
   - Go to [share.streamlit.io](https://share.streamlit.io/)
   - Sign in with GitHub (`asjadp`)
   - Select repository `asjadp/covered-calls-screener`, branch `main`, main file `app.py`
   - Deploy!

3. **(Optional) Connect Free Supabase / Neon Cloud Database**:
   - In Streamlit Cloud **App Settings > Secrets**:
     ```toml
     DATABASE_URL = "postgresql://postgres:[PASSWORD]@[HOST]:5432/postgres"
     ```
