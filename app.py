import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import os

from screener import screen_covered_calls, resolve_to_symbol
from database import init_db, save_screen_results, load_history, get_db_status, get_latest_snapshot
from api_monitor import api_monitor, is_market_open_now, is_snapshot_frozen_after_market_close

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
    
    # Active Storage Status
    with st.container(border=True):
        st.caption("Active Data Persistence")
        st.markdown(f"**{db_status['label']}**")
        with st.expander("Cloud Database Architecture"):
            st.markdown("""
            **Dual-Backend Engine**:
            - **Local Persistence**: SQLite (`covered_calls.db`).
            - **Cloud Persistence**: Free **Supabase** or **Neon PostgreSQL** via `DATABASE_URL`.
            All option scans are timestamped and indexed for trade analysis.
            """)

    st.markdown("### Stock Selection")
    
    # Quick Pick Pills for Rapid Trade Analysis
    popular_tickers = ["AAPL", "NVDA", "TSLA", "MSFT", "SPY", "AMD"]
    selected_pill = st.pills("Quick Picks", popular_tickers, default=None)
    
    default_ticker = selected_pill if selected_pill else "AAPL"
    ticker_input = st.text_input(
        "Ticker Symbol or Company Name",
        value=default_ticker,
        help="Enter any US stock ticker (e.g. AAPL, NVDA, TSLA) or company name."
    ).strip()

    use_custom_cost = st.checkbox("Custom Purchase Price", help="Calculate yields against your personal purchase price instead of current market price.")
    custom_price = None
    if use_custom_cost:
        custom_price = st.number_input("Your Purchase Price ($)", min_value=0.01, value=150.0, step=0.50)

    # Data Mode
    market_open = is_market_open_now()
    data_mode = st.radio(
        "Data Mode",
        options=["⚡ Fast Database Snapshot", "🔄 Live Market Refresh"],
        index=0,
        help="⚡ Fast Database Snapshot instantly loads saved option records (0 API calls). 🔄 Live Market Refresh queries live market option chains."
    )

    run_button = st.button("Run Screener", type="primary")

    st.markdown("---")
    st.caption("Developed by **Asjad P.** ([GitHub @asjadp](https://github.com/asjadp))")

# ----------------- SCREENING EXECUTION & SMART MARKET-CLOSED CACHING -----------------
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
    is_live_requested = (data_mode == "🔄 Live Market Refresh")
    
    loaded_from_db = False
    existing_snapshot = get_latest_snapshot(symbol_resolved)
    
    # 1. Market-Closed Smart Freeze Rule:
    # If market is closed and we already have a snapshot captured after market close,
    # NEVER make a live API call because option settlement prices are frozen until 9:30 AM ET.
    if existing_snapshot and is_snapshot_frozen_after_market_close(existing_snapshot[0]['timestamp']):
        snap_meta, snap_results = existing_snapshot
        symbol = snap_meta['ticker']
        curr_price = snap_meta['current_price']
        ref_price = custom_price if (custom_price and custom_price > 0) else snap_meta['purchase_price']
        earnings_date = snap_meta.get('earnings_date', 'N/A')
        results = snap_results
        snapshot_id = snap_meta['id']
        snap_time = snap_meta['timestamp']
        
        api_monitor.record_cache_hit(symbol, "Market Closed Freeze")
        st.session_state['results'] = (symbol, ticker_input, curr_price, ref_price, earnings_date, results, snapshot_id, "market_closed_freeze", snap_time)
        loaded_from_db = True

    # 2. If user specifically requested Fast Database Snapshot and snapshot exists
    elif not is_live_requested and existing_snapshot:
        snap_meta, snap_results = existing_snapshot
        symbol = snap_meta['ticker']
        curr_price = snap_meta['current_price']
        ref_price = custom_price if (custom_price and custom_price > 0) else snap_meta['purchase_price']
        earnings_date = snap_meta.get('earnings_date', 'N/A')
        results = snap_results
        snapshot_id = snap_meta['id']
        snap_time = snap_meta['timestamp']
        
        api_monitor.record_cache_hit(symbol, "Database Snapshot")
        st.session_state['results'] = (symbol, ticker_input, curr_price, ref_price, earnings_date, results, snapshot_id, "db", snap_time)
        loaded_from_db = True

    # 3. Live Fetch via yfinance (if market is open OR if no closing snapshot exists yet for this ticker)
    if not loaded_from_db:
        can_call, limit_reason = api_monitor.can_make_api_call()
        
        if not can_call:
            if existing_snapshot:
                snap_meta, snap_results = existing_snapshot
                symbol = snap_meta['ticker']
                curr_price = snap_meta['current_price']
                ref_price = custom_price if (custom_price and custom_price > 0) else snap_meta['purchase_price']
                earnings_date = snap_meta.get('earnings_date', 'N/A')
                results = snap_results
                snapshot_id = snap_meta['id']
                snap_time = snap_meta['timestamp']
                api_monitor.record_cache_hit(symbol, "Rate Limit Fallback")
                st.session_state['results'] = (symbol, ticker_input, curr_price, ref_price, earnings_date, results, snapshot_id, "rate_limit_fallback", snap_time, limit_reason)
            else:
                st.error(f"Rate limit active ({limit_reason}) and no cached data available for '{ticker_input}'.")
        else:
            with st.spinner(f"Fetching option chains for '{ticker_input}' via yfinance..."):
                try:
                    symbol, curr_price, ref_price, earnings_date, results = screen_covered_calls(ticker_input, custom_price)
                    snapshot_id = save_screen_results(symbol, curr_price, ref_price, earnings_date, results)
                    snap_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    st.session_state['results'] = (symbol, ticker_input, curr_price, ref_price, earnings_date, results, snapshot_id, "live", snap_time)
                except Exception as e:
                    if existing_snapshot:
                        snap_meta, snap_results = existing_snapshot
                        symbol = snap_meta['ticker']
                        curr_price = snap_meta['current_price']
                        ref_price = custom_price if (custom_price and custom_price > 0) else snap_meta['purchase_price']
                        earnings_date = snap_meta.get('earnings_date', 'N/A')
                        results = snap_results
                        snapshot_id = snap_meta['id']
                        snap_time = snap_meta['timestamp']
                        api_monitor.record_cache_hit(symbol, "Error Recovery Snapshot")
                        st.session_state['results'] = (symbol, ticker_input, curr_price, ref_price, earnings_date, results, snapshot_id, "error_fallback", snap_time)
                    else:
                        st.error(f"Could not fetch options data for '{ticker_input}': {str(e)}")

# ----------------- MAIN DASHBOARD TABS -----------------
st.title("📈 Covered Call Screener & Yield Engine")
st.markdown("Quantitative Covered Call screening, Black-Scholes probability modeling, and multi-backend data persistence.")

tab_live, tab_methodology = st.tabs([
    "🎯 Covered Call Screener & Yield Matrix",
    "📐 Quantitative Methodology & Formulas"
])

# ----------------- TAB 1: COVERED CALL SCREENER -----------------
with tab_live:
    if 'results' in st.session_state:
        res_data = st.session_state['results']
        symbol = res_data[0]
        original_input = res_data[1]
        curr_price = res_data[2]
        ref_price = res_data[3]
        earnings_date = res_data[4]
        results = res_data[5]
        snapshot_id = res_data[6]
        source = res_data[7]
        snap_time = res_data[8]

        # Prominent Timestamp & Data Origin Banner
        if source == "market_closed_freeze":
            st.info(f"🕒 **Data Sourced**: `{snap_time}` | 🔒 **Market Closed**: Option prices are frozen until next market open (9:30 AM ET). Served closing settlement snapshot (0 API calls).")
        elif source == "db":
            st.info(f"🕒 **Data Sourced**: `{snap_time}` | **Origin**: Saved Database Snapshot (Snapshot #{snapshot_id})")
        elif source == "rate_limit_fallback":
            limit_reason = res_data[9] if len(res_data) > 9 else "Rate limit active"
            st.warning(f"🕒 **Data Sourced**: `{snap_time}` | 🛡️ **Protection**: {limit_reason}. Loaded verified Database Snapshot (#{snapshot_id}).")
        elif source == "error_fallback":
            st.warning(f"🕒 **Data Sourced**: `{snap_time}` | ⚠️ Live API throttled. Loaded latest verified Database Snapshot (#{snapshot_id}).")
        else:
            st.success(f"🕒 **Data Sourced**: `{snap_time}` | **Origin**: Live Real-Time Market Quote (Saved as Snapshot #{snapshot_id})")

        # Key KPI Metrics Cards
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
                label=f"📥 Export {symbol} Option Matrix (CSV)",
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

# ----------------- TAB 2: QUANTITATIVE METHODOLOGY -----------------
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
