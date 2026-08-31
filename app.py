import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import os

from screener import screen_covered_calls, resolve_to_symbol
from database import init_db, save_screen_results, load_history, get_db_status, get_latest_snapshot
from test_data_pipeline import load_sample_dataset, CSV_EXPORT_PATH, JSON_EXPORT_PATH

st.set_page_config(
    page_title="Covered Call Screener & Yield Engine",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize database schema (SQLite or Cloud PostgreSQL)
init_db()
db_status = get_db_status()

# ----------------- SIDEBAR CONTROLS -----------------
with st.sidebar:
    st.title("📈 Screener Controls")
    
    # Storage Backend Status Badge
    with st.container(border=True):
        st.caption("Active Data Persistence")
        st.markdown(f"**{db_status['label']}**")
        with st.expander("Cloud Database Info"):
            st.markdown("""
            **Dual-Backend Architecture**:
            - **Local Mode**: Zero-config SQLite (`covered_calls.db`).
            - **Cloud Mode**: Free **Supabase** or **Neon PostgreSQL** via `st.secrets["DATABASE_URL"]`.
            All screening runs are automatically timestamped and indexed for backtesting.
            """)

    st.markdown("### Select or Enter Ticker")
    
    # Quick Pick Pills for Recruiter Testing
    popular_tickers = ["AAPL", "NVDA", "TSLA", "MSFT", "SPY", "AMD"]
    selected_pill = st.pills("Quick Picks", popular_tickers, default=None)
    
    default_ticker = selected_pill if selected_pill else "AAPL"
    ticker_input = st.text_input(
        "Stock Symbol or Company Name",
        value=default_ticker,
        help="Enter any US stock ticker (e.g. AAPL, NVDA) or company name (e.g. Apple, Microsoft)."
    ).strip()

    use_custom_cost = st.checkbox("Custom Purchase Price", help="Calculate ROIs against your own historical buy price instead of current market price.")
    custom_price = None
    if use_custom_cost:
        custom_price = st.number_input("Your Purchase Price ($)", min_value=0.01, value=150.0, step=0.50)

    # Data Fetching Mode (Cached Database vs Live Refresh)
    data_mode = st.radio(
        "Data Mode",
        options=["⚡ Fast Database Snapshot", "🔄 Live Market Refresh"],
        index=0,
        help="⚡ Fast Database Snapshot loads pre-saved database records instantly without calling yfinance API. 🔄 Live Market Refresh queries live market option chains."
    )

    run_button = st.button("Run Screener", type="primary")
    
    st.markdown("---")
    st.caption("Developed by **Asjad P.** ([GitHub @asjadp](https://github.com/asjadp))")

# ----------------- SESSION STATE & SCREENING EXECUTION -----------------
last_ticker = st.session_state.get('last_ticker')
last_price = st.session_state.get('last_price')
last_mode = st.session_state.get('last_mode')

should_run = (
    run_button or 
    'results' not in st.session_state or 
    ticker_input.upper() != str(last_ticker).upper() or 
    custom_price != last_price or
    data_mode != last_mode
)

if should_run and ticker_input:
    st.session_state['last_ticker'] = ticker_input
    st.session_state['last_price'] = custom_price
    st.session_state['last_mode'] = data_mode
    
    symbol_resolved = resolve_to_symbol(ticker_input)
    is_live = (data_mode == "🔄 Live Market Refresh")
    
    loaded_from_db = False
    
    # 1. Try Database Snapshot First if in Cached Mode
    if not is_live:
        existing_snapshot = get_latest_snapshot(symbol_resolved)
        if existing_snapshot:
            snap_meta, snap_results = existing_snapshot
            symbol = snap_meta['ticker']
            curr_price = snap_meta['current_price']
            ref_price = custom_price if (custom_price and custom_price > 0) else snap_meta['purchase_price']
            earnings_date = snap_meta.get('earnings_date', 'N/A')
            results = snap_results
            snapshot_id = snap_meta['id']
            snap_time = snap_meta['timestamp']
            
            st.session_state['results'] = (symbol, ticker_input, curr_price, ref_price, earnings_date, results, snapshot_id, "db", snap_time)
            loaded_from_db = True

    # 2. Live Fetch via yfinance with Automatic DB Fallback
    if not loaded_from_db:
        with st.spinner(f"Fetching real-time option chains for '{ticker_input}' via yfinance..."):
            try:
                symbol, curr_price, ref_price, earnings_date, results = screen_covered_calls(ticker_input, custom_price)
                snapshot_id = save_screen_results(symbol, curr_price, ref_price, earnings_date, results)
                snap_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                st.session_state['results'] = (symbol, ticker_input, curr_price, ref_price, earnings_date, results, snapshot_id, "live", snap_time)
            except Exception as e:
                # Automatic Resilience: If live fetch fails, check if we have an existing DB snapshot
                fallback_snapshot = get_latest_snapshot(symbol_resolved)
                if fallback_snapshot:
                    snap_meta, snap_results = fallback_snapshot
                    symbol = snap_meta['ticker']
                    curr_price = snap_meta['current_price']
                    ref_price = custom_price if (custom_price and custom_price > 0) else snap_meta['purchase_price']
                    earnings_date = snap_meta.get('earnings_date', 'N/A')
                    results = snap_results
                    snapshot_id = snap_meta['id']
                    snap_time = snap_meta['timestamp']
                    st.session_state['results'] = (symbol, ticker_input, curr_price, ref_price, earnings_date, results, snapshot_id, "fallback", snap_time)
                else:
                    st.error(f"Could not fetch options data for '{ticker_input}': {str(e)}")

# ----------------- MAIN DASHBOARD TABS -----------------
st.title("📈 Covered Call Screener & Yield Engine")
st.markdown("Quantitative Covered Call screening, Black-Scholes probability modeling, and multi-backend data persistence.")

tab_live, tab_data_testing, tab_methodology = st.tabs([
    "🎯 Live Option Screener",
    "🧪 Data Testing & Benchmark Datasets",
    "📐 Quantitative Methodology & Architecture"
])

# ----------------- TAB 1: LIVE OPTION SCREENER -----------------
with tab_live:
    if 'results' in st.session_state:
        symbol, original_input, curr_price, ref_price, earnings_date, results, snapshot_id, source, snap_time = st.session_state['results']

        if source == "db":
            st.info(f"⚡ **Loaded instantly from Database Snapshot** (#{snapshot_id}, saved on `{snap_time}`). 0 external API calls used.")
        elif source == "fallback":
            st.warning(f"⚠️ Live market API is currently rate-limited. **Seamlessly loaded latest verified snapshot from database** (#{snapshot_id} from `{snap_time}`).")
        else:
            st.success(f"🔄 **Live market data fetched & saved** to database (#{snapshot_id} at `{snap_time}`).")

        # Top KPI Metrics Cards
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        with kpi1:
            st.metric("Stock Symbol", symbol)
        with kpi2:
            st.metric("Current Market Price", f"${curr_price:.2f}")
        with kpi3:
            st.metric("Reference Cost Basis", f"${ref_price:.2f}", help="Cost basis used for yield and ROI calculations")
        with kpi4:
            st.metric("Next Earnings Date", earnings_date)

        st.markdown("---")
        st.subheader(f"Option Chains & Yield Matrix for {symbol}")
        
        if results:
            df = pd.DataFrame(results)
            
            # Format display columns
            cols_to_include = [
                'term', 'expiration_date', 'target_type', 'strike_price', 'premium',
                'implied_volatility_pct', 'delta', 'prob_itm_pct', 'prob_touch_pct',
                'premium_roi_pct', 'ann_premium_roi_pct', 'max_roi_pct', 'ann_max_roi_pct', 'breakeven_price'
            ]
            existing_cols = [c for c in cols_to_include if c in df.columns]
            display_df = df[existing_cols].copy()

            rename_dict = {
                'term': 'Term',
                'expiration_date': 'Expiration',
                'target_type': 'Target Strike',
                'strike_price': 'Strike ($)',
                'premium': 'Premium ($)',
                'implied_volatility_pct': 'IV (%)',
                'delta': 'Delta',
                'prob_itm_pct': 'Prob. ITM (%)',
                'prob_touch_pct': 'Prob. Hit Strike (%)',
                'premium_roi_pct': 'Premium Yield (%)',
                'ann_premium_roi_pct': 'Ann. Premium Yield (%)',
                'max_roi_pct': 'Max ROI (%)',
                'ann_max_roi_pct': 'Ann. Max ROI (%)',
                'breakeven_price': 'Breakeven ($)'
            }
            display_df.rename(columns=rename_dict, inplace=True)

            st.dataframe(display_df, width="stretch")

            # CSV Export
            csv_data = display_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label=f"📥 Export {symbol} Screen Results (CSV)",
                data=csv_data,
                file_name=f"{symbol}_covered_calls_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                key="download_current_screen"
            )

            # Interactive Plotly Chart
            st.markdown("---")
            st.subheader("📊 Visual ROI, Yield & Probability Comparisons")
            
            chart_df = df.copy()
            chart_df['Option Contract'] = chart_df['term'] + " (" + chart_df['target_type'] + ")"

            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=chart_df['Option Contract'],
                y=chart_df['ann_premium_roi_pct'],
                name='Ann. Premium Yield (%)',
                marker_color='#2563eb',
                text=chart_df['ann_premium_roi_pct'].apply(lambda v: f"{v:.1f}%" if pd.notna(v) else ""),
                textposition='auto'
            ))

            fig.add_trace(go.Bar(
                x=chart_df['Option Contract'],
                y=chart_df['ann_max_roi_pct'],
                name='Ann. Max ROI (%)',
                marker_color='#10b981',
                text=chart_df['ann_max_roi_pct'].apply(lambda v: f"{v:.1f}%" if pd.notna(v) else ""),
                textposition='auto'
            ))

            if 'prob_touch_pct' in chart_df.columns:
                fig.add_trace(go.Bar(
                    x=chart_df['Option Contract'],
                    y=chart_df['prob_touch_pct'],
                    name='Prob. Hit Strike (%)',
                    marker_color='#f59e0b',
                    text=chart_df['prob_touch_pct'].apply(lambda v: f"{v:.1f}%" if pd.notna(v) else "N/A"),
                    textposition='auto'
                ))

            fig.update_layout(
                barmode='group',
                title=f"Annualized Yield, Max Upside & Strike Hit Probability for {symbol}",
                xaxis_title="Option Expiration & Strike Target",
                yaxis_title="Percentage (%)",
                legend_title="Metric",
                template="plotly_white",
                height=480,
                margin=dict(l=40, r=40, t=60, b=40)
            )

            st.plotly_chart(fig)

        else:
            st.warning(f"No suitable options found matching criteria for {symbol}.")

        # Historical Snapshots Viewer
        st.markdown("---")
        st.subheader(f"📜 Historical Snapshots & Backtest Records ({symbol})")

        hist_df = load_history(symbol)
        if not hist_df.empty:
            st.dataframe(hist_df, width="stretch")
            
            hist_csv = hist_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label=f"📥 Export Historical Records for {symbol} (CSV)",
                data=hist_csv,
                file_name=f"{symbol}_historical_records_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                key="download_hist_records"
            )
        else:
            st.info(f"No historical records saved for {symbol} yet.")

# ----------------- TAB 2: DATA TESTING & BENCHMARK DATASETS -----------------
with tab_data_testing:
    st.subheader("🧪 Benchmark Options Dataset for Offline Data Testing")
    st.markdown("""
    This section contains structured options datasets automatically captured and validated via the `test_data_pipeline.py` testing engine.
    Recruiters and data testers can download or inspect these datasets to perform offline quantitative backtesting.
    """)

    sample_df = load_sample_dataset()
    if not sample_df.empty:
        col_t1, col_t2, col_t3 = st.columns(3)
        col_t1.metric("Benchmark Stocks", f"{len(sample_df['ticker'].unique())} Unique Tickers")
        col_t2.metric("Total Captured Contracts", f"{len(sample_df)} Option Rows")
        col_t3.metric("Avg. Ann. Premium Yield", f"{sample_df['ann_premium_roi_pct'].mean():.2f}%")

        st.dataframe(sample_df, width="stretch")

        col_d1, col_d2 = st.columns(2)
        with col_d1:
            st.download_button(
                label="📥 Download Benchmark Dataset (CSV)",
                data=open(CSV_EXPORT_PATH, "rb").read() if os.path.exists(CSV_EXPORT_PATH) else b"",
                file_name="sample_options_dataset.csv",
                mime="text/csv"
            )
        with col_d2:
            st.download_button(
                label="📥 Download Benchmark Dataset (JSON)",
                data=open(JSON_EXPORT_PATH, "rb").read() if os.path.exists(JSON_EXPORT_PATH) else b"",
                file_name="sample_options_dataset.json",
                mime="application/json"
            )
    else:
        st.info("No benchmark dataset found. Run `python test_data_pipeline.py` to generate the test datasets.")

# ----------------- TAB 3: QUANTITATIVE METHODOLOGY -----------------
with tab_methodology:
    st.subheader("📐 Quantitative Formulas & Mathematical Modeling")
    
    st.markdown(r"""
    ### 1. Black-Scholes In-The-Money Probability ($N(d_2)$)
    The probability that an Out-of-the-Money call option expires In-The-Money (ITM) under risk-neutral Black-Scholes dynamics is given by $N(d_2)$:
    $$d_2 = \frac{\ln(S / K) + (r - \frac{1}{2}\sigma^2)T}{\sigma \sqrt{T}}$$
    $$\text{Prob. ITM} = N(d_2) = \frac{1}{2} \left[ 1 + \text{erf}\left(\frac{d_2}{\sqrt{2}}\right) \right]$$
    Where:
    - $S$ = Stock Reference Price
    - $K$ = Option Strike Price
    - $\sigma$ = Implied Volatility ($\text{IV} / 100$)
    - $T = \text{DTE} / 365$ (Time to expiration in years)
    - $r$ = Risk-free rate ($\approx 4.5\%$)

    ---

    ### 2. Probability of Touching / Hitting Strike Price
    By the **Reflection Principle** of Brownian motion with drift, the probability that the underlying stock price touches or exceeds the strike price $K$ at *any point* prior to expiration is approximately:
    $$\text{Prob. Hit Strike} \approx \min\left(100\%, 2 \times N(d_2)\right)$$

    ---

    ### 3. Covered Call Yield & ROI Metrics
    - **Premium Yield (%)**: $\frac{\text{Option Premium}}{\text{Reference Price}} \times 100$
    - **Annualized Premium Yield (%)**: $\text{Premium Yield} \times \frac{365}{\text{DTE}}$
    - **Max ROI (%)**: $\frac{(K - \text{Reference Price}) + \text{Option Premium}}{\text{Reference Price}} \times 100$
    - **Annualized Max ROI (%)**: $\text{Max ROI} \times \frac{365}{\text{DTE}}$
    - **Downside Breakeven Price ($)**: $\text{Reference Price} - \text{Option Premium}$
    """)
