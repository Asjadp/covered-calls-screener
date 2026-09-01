import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import os
import time

from screener import screen_covered_calls, resolve_to_symbol, calculate_covered_call_score
from database import (
    init_db, save_screen_results, load_history, get_db_status,
    get_latest_snapshot, get_latest_weekly_top_picks, swap_weekly_pick, save_weekly_top_picks,
    save_subscriber, get_subscribers
)
from weekly_scanner import run_weekly_scan, TOP_50_SPY
from api_monitor import api_monitor, is_market_open_now, is_snapshot_frozen_after_market_close

st.set_page_config(
    page_title="Covered Call Screener & Yield Engine",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Google Site Verification
st.html(
    """
    <meta name="google-site-verification" content="aeh8M7yV4lN0RZ1lxcNmrtwQ2b5fXklTWP4Mz2zivaM" />
    <meta name="google-site-verification" content="google2cc9c81477b8b47c" />
    """
)

# Initialize database schema (SQLite or Cloud PostgreSQL)
init_db()
db_status = get_db_status()

# ----------------- SIDEBAR CONTROLS -----------------
with st.sidebar:
    st.title("📈 Screener Controls")
    
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
        
        api_monitor.record_cache_hit(symbol, "User Fast DB Mode")
        st.session_state['results'] = (symbol, ticker_input, curr_price, ref_price, earnings_date, results, snapshot_id, "db", snap_time)
        loaded_from_db = True

    # 3. Live Option Chain Screening
    else:
        can_proceed, limit_reason = api_monitor.can_make_api_call(symbol_resolved)
        
        if not can_proceed:
            if existing_snapshot:
                snap_meta, snap_results = existing_snapshot
                symbol = snap_meta['ticker']
                curr_price = snap_meta['current_price']
                ref_price = custom_price if (custom_price and custom_price > 0) else snap_meta['purchase_price']
                earnings_date = snap_meta.get('earnings_date', 'N/A')
                results = snap_results
                snapshot_id = snap_meta['id']
                snap_time = snap_meta['timestamp']
                
                api_monitor.record_cache_hit(symbol, f"Rate Limit Fallback ({limit_reason})")
                st.session_state['results'] = (symbol, ticker_input, curr_price, ref_price, earnings_date, results, snapshot_id, "rate_limit_fallback", snap_time, limit_reason)
                loaded_from_db = True
            else:
                st.error(f"⚠️ **Rate Limit**: {limit_reason}. No prior database snapshot found for '{symbol_resolved}'.")
        
        if not loaded_from_db and can_proceed:
            with st.spinner(f"🔍 Screening live option chains for {symbol_resolved}..."):
                try:
                    symbol, curr_price, ref_price, earnings_date, results = screen_covered_calls(
                        ticker_input, custom_purchase_price=custom_price
                    )
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

# Helper for newsletter generation
def generate_newsletter_markdown(weekly_data: dict) -> str:
    gen_at = weekly_data.get("generated_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    batch_id = weekly_data.get("batch_id", "N/A")
    lines = [
        "# 📊 Weekly Top Covered Call Ideas (SPY Top 50)",
        f"**Generated / Captured**: `{gen_at}` | **Universe**: S&P 500 Top 50 Mega-Caps",
        "**Settlement Baseline**: Official Regular Market Closing Settlement Prices\n",
        "### 🎯 Top 5 Picks: +5% OTM (High Yield & Downside Cushion)",
        "| Rank | Ticker | Stock Price | Strike | Exp Date | DTE | Premium | Premium ROI | Ann. Max ROI | Cushion | Prob. ITM | Score |",
        "| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |"
    ]
    for p in weekly_data.get("5% OTM", [])[:5]:
        prem_roi = p.get('premium_roi_pct') or (round((p['premium'] / p['stock_price']) * 100.0, 2) if p.get('stock_price') else 0.0)
        lines.append(f"| #{p.get('rank', 1)} | **{p['ticker']}** | ${p['stock_price']:.2f} | ${p['strike_price']:.2f} | {p['expiration_date']} | {p['dte']}d | ${p['premium']:.2f} | **{prem_roi:.2f}%** | **{p['ann_max_roi_pct']:.1f}%** | {p.get('cushion_pct', 0.0):.1f}% | {p.get('prob_itm_pct', 'N/A')}% | **{p.get('score', 0.0)}** |")
    
    lines.append("\n### 🚀 Top 5 Picks: +10% OTM (Capital Growth & Low Assignment Risk)")
    lines.append("| Rank | Ticker | Stock Price | Strike | Exp Date | DTE | Premium | Premium ROI | Ann. Max ROI | Cushion | Prob. ITM | Score |")
    lines.append("| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
    for p in weekly_data.get("10% OTM", [])[:5]:
        prem_roi = p.get('premium_roi_pct') or (round((p['premium'] / p['stock_price']) * 100.0, 2) if p.get('stock_price') else 0.0)
        lines.append(f"| #{p.get('rank', 1)} | **{p['ticker']}** | ${p['stock_price']:.2f} | ${p['strike_price']:.2f} | {p['expiration_date']} | {p['dte']}d | ${p['premium']:.2f} | **{prem_roi:.2f}%** | **{p['ann_max_roi_pct']:.1f}%** | {p.get('cushion_pct', 0.0):.1f}% | {p.get('prob_itm_pct', 'N/A')}% | **{p.get('score', 0.0)}** |")
        
    lines.append("\n---\n*Disclaimer: Options trading involves substantial risk. Quantitative scores reflect mathematical models based on Black-Scholes and are not investment recommendations.*")
    return "\n".join(lines)

# ----------------- MAIN DASHBOARD TABS -----------------
st.title("📈 Covered Call Screener & Yield Engine")
st.markdown("Quantitative Covered Call screening across the S&P 500, Black-Scholes probability modeling, and weekly idea publisher.")

tab_weekly, tab_live, tab_methodology = st.tabs([
    "⭐ Weekly Top Ideas (+5% & +10% OTM)",
    "🎯 On-Demand Screener & Yield Matrix",
    "📐 Quantitative Methodology & Formulas"
])

# ----------------- TAB 1: WEEKLY TOP IDEAS -----------------
with tab_weekly:
    st.subheader("⭐ Weekly Best Covered Call Ideas (SPY Top 50 Universe)")
    st.caption("Screened after-market hours from the top 50 S&P 500 constituents. Evaluated for maximum risk-adjusted ROI, downside cushion, and non-duplicative quality.")

    # Load latest weekly ideas from Database
    weekly_data = get_latest_weekly_top_picks()
    gen_time = weekly_data.get("generated_at")
    batch_id = weekly_data.get("batch_id")
    picks_5 = weekly_data.get("5% OTM", [])
    picks_10 = weekly_data.get("10% OTM", [])

    # Header Status Banner
    if gen_time:
        st.info(f"🕒 **Weekly Batch Generated**: `{gen_time}` | 📦 **Batch ID**: `{batch_id}` | 🏛️ **Universe**: Top 50 SPY Constituents | 🔒 **Price Basis**: Official Regular Market Close")
    else:
        st.warning("⚠️ No weekly batch scan records found yet. Click below to run an initial scan across the universe.")

    # Top Controls & Batch Refresh
    with st.expander("⚙️ Weekly Scanner Controls & Batch Refresh", expanded=not bool(gen_time)):
        col_scan1, col_scan2, col_scan3 = st.columns([2, 1, 1])
        with col_scan1:
            st.markdown("""
            **Scheduled Refresh**: Refreshes weekly on Tuesday evening after market close (5:00 PM ET).
            Spreads requests with gentle pacing to ensure full API compliance.
            """)
        with col_scan2:
            scan_mode = st.selectbox("Scan Scope", ["Fast Test Basket (10 Tickers)", "Full Universe (Top 50 SPY)"])
        with col_scan3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🚀 Run Batch Scan Now", type="primary"):
                target_tickers = ["AAPL", "MSFT", "NVDA", "AMZN", "META", "TSLA", "GOOGL", "SPY", "JPM", "AMD"] if "Fast" in scan_mode else TOP_50_SPY
                delay_val = 1.0 if "Fast" in scan_mode else 1.5
                
                progress_bar = st.progress(0, text="Initializing scan...")
                status_text = st.empty()
                
                def update_prog(idx, total, ticker):
                    pct = int((idx / total) * 100)
                    progress_bar.progress(pct, text=f"[{idx}/{total}] Screening {ticker}...")
                    status_text.caption(f"Currently processing: **{ticker}**")
                
                with st.spinner("Running batch scanner across universe..."):
                    new_5, new_10 = run_weekly_scan(
                        tickers=target_tickers,
                        delay_seconds=delay_val,
                        top_n=10,
                        progress_callback=update_prog
                    )
                    progress_bar.progress(100, text="Scan Complete!")
                    st.success(f"Scan complete! Captured {len(new_5)} (+5% OTM) and {len(new_10)} (+10% OTM) top ideas.")
                    time.sleep(1)
                    st.rerun()

    # Dynamic Challenger / Swap Section
    if 'results' in st.session_state:
        res_data = st.session_state['results']
        active_symbol = res_data[0]
        active_results = res_data[5]
        active_curr_price = res_data[2]
        active_e_date = res_data[4]

        cand_5 = [r for r in active_results if r.get('target_type') == '5% OTM']
        cand_10 = [r for r in active_results if r.get('target_type') == '10% OTM']

        challenger_alerts = []

        if cand_5 and picks_5:
            best_cand_5 = max(cand_5, key=lambda x: x.get('score', 0.0))
            score_5 = best_cand_5.get('score', 0.0)
            lowest_5 = picks_5[-1]
            
            existing_tickers_5 = [p['ticker'].upper() for p in picks_5]
            if active_symbol.upper() not in existing_tickers_5 and score_5 > lowest_5.get('score', 0.0):
                challenger_alerts.append({
                    "target_type": "5% OTM",
                    "ticker": active_symbol,
                    "score": score_5,
                    "beaten_rank": lowest_5.get('rank', len(picks_5)),
                    "beaten_ticker": lowest_5['ticker'],
                    "beaten_score": lowest_5.get('score', 0.0),
                    "contract": {
                        "ticker": active_symbol,
                        "stock_price": active_curr_price,
                        "earnings_date": active_e_date,
                        **best_cand_5
                    }
                })

        if cand_10 and picks_10:
            best_cand_10 = max(cand_10, key=lambda x: x.get('score', 0.0))
            score_10 = best_cand_10.get('score', 0.0)
            lowest_10 = picks_10[-1]
            
            existing_tickers_10 = [p['ticker'].upper() for p in picks_10]
            if active_symbol.upper() not in existing_tickers_10 and score_10 > lowest_10.get('score', 0.0):
                challenger_alerts.append({
                    "target_type": "10% OTM",
                    "ticker": active_symbol,
                    "score": score_10,
                    "beaten_rank": lowest_10.get('rank', len(picks_10)),
                    "beaten_ticker": lowest_10['ticker'],
                    "beaten_score": lowest_10.get('score', 0.0),
                    "contract": {
                        "ticker": active_symbol,
                        "stock_price": active_curr_price,
                        "earnings_date": active_e_date,
                        **best_cand_10
                    }
                })

        if challenger_alerts:
            with st.container(border=True):
                st.markdown("### 🔥 Dynamic Challenger Opportunity Detected")
                for alert in challenger_alerts:
                    c_col1, c_col2 = st.columns([3, 1])
                    with c_col1:
                        st.markdown(f"""
                        **`{alert['ticker']}`** ({alert['target_type']}) achieved a Composite Score of **`{alert['score']}`**, outperforming **#{alert['beaten_rank']} `{alert['beaten_ticker']}`** (Score: `{alert['beaten_score']}`) by **+{alert['score'] - alert['beaten_score']:.1f} pts**!
                        """)
                    with c_col2:
                        btn_key = f"swap_btn_{alert['target_type']}_{alert['ticker']}"
                        if st.button(f"🔄 Swap into {alert['target_type']} Top List", key=btn_key, type="primary"):
                            swap_weekly_pick(alert['target_type'], alert['beaten_ticker'], alert['contract'])
                            st.success(f"Swapped {alert['ticker']} into the {alert['target_type']} list!")
                            time.sleep(1)
                            st.rerun()

    # Top & Bottom Stacked Tables (+5% OTM and +10% OTM)
    st.markdown("---")

    def render_top_picks_table(picks: list, list_label: str):
        if not picks:
            st.info(f"No {list_label} picks recorded. Run a batch scan to populate.")
            return

        df_picks = pd.DataFrame(picks)
        
        # Calculate premium_roi_pct if missing from earlier batches
        if 'premium_roi_pct' not in df_picks.columns and 'premium' in df_picks.columns and 'stock_price' in df_picks.columns:
            df_picks['premium_roi_pct'] = ((df_picks['premium'] / df_picks['stock_price']) * 100.0).round(2)
        
        cols = [
            'rank', 'ticker', 'stock_price', 'strike_price', 'term', 'expiration_date',
            'premium', 'premium_roi_pct', 'ann_max_roi_pct', 'cushion_pct', 'prob_itm_pct', 'score', 'generated_at'
        ]
        available_cols = [c for c in cols if c in df_picks.columns]
        table_df = df_picks[available_cols].copy()
        
        rename_map = {
            'rank': 'Rank',
            'ticker': 'Ticker',
            'stock_price': 'Stock Price ($)',
            'strike_price': 'Strike ($)',
            'term': 'Term',
            'expiration_date': 'Expiration',
            'premium': 'Premium ($)',
            'premium_roi_pct': 'Premium ROI (%)',
            'ann_max_roi_pct': 'Ann. Max ROI (%)',
            'cushion_pct': 'Cushion (%)',
            'prob_itm_pct': 'Prob. ITM (%)',
            'score': 'Score (0-100)',
            'generated_at': 'Captured At'
        }
        table_df.rename(columns=rename_map, inplace=True)
        
        st.dataframe(table_df, width="stretch", hide_index=True)

    # 1. Top Table: +5% OTM Target
    st.markdown("### 🎯 List 1: Top 5% OTM Covered Call Opportunities")
    st.caption("Targets strikes ~5% above closing price for strong option premium yield and higher downside buffer. Strictly 1 contract per company.")
    render_top_picks_table(picks_5, "5% OTM")

    st.markdown("---")

    # 2. Bottom Table: +10% OTM Target
    st.markdown("### 🚀 List 2: Top 10% OTM Covered Call Opportunities")
    st.caption("Targets strikes ~10% above closing price for capital upside room and lower probability of assignment. Strictly 1 contract per company.")
    render_top_picks_table(picks_10, "10% OTM")

    st.markdown("---")

    # 3. Email Delivery & Newsletter Subscription Form
    with st.container(border=True):
        st.markdown("### 📧 Send Weekly Top 10 Report & Subscribe")
        st.markdown("Get our curated **Weekly Top 10 Covered Call Ideas** (+5% & +10% OTM matrices, Black-Scholes Greeks, and downside breakevens) delivered directly to your inbox every Tuesday after market close.")
        
        col_em1, col_em2, col_em3 = st.columns([2, 2, 1.5])
        with col_em1:
            sub_email = st.text_input("Your Email Address", placeholder="investor@example.com", key="weekly_sub_email")
        with col_em2:
            sub_name = st.text_input("Your Name (Optional)", placeholder="Alex Morgan", key="weekly_sub_name")
        with col_em3:
            st.markdown("<br>", unsafe_allow_html=True)
            send_sub_btn = st.button("✉️ Send Report & Subscribe", type="primary", key="btn_sub_weekly")
            
        if send_sub_btn:
            if sub_email and "@" in sub_email and "." in sub_email:
                saved = save_subscriber(sub_email, sub_name, "Weekly Top 10 Ideas")
                if saved:
                    st.success(f"✅ **Success!** The Weekly Top Covered Call Ideas report has been queued for **{sub_email.strip()}**. You are now subscribed to Tuesday evening closing updates.")
                else:
                    st.error("Could not save email. Please try again.")
            else:
                st.warning("⚠️ Please enter a valid email address (e.g. name@domain.com).")

    # 4. 1-Click Newsletter & Social Publisher (Collapsible Preview)
    with st.expander("📰 View Formatted Newsletter / Social Post Preview", expanded=False):
        st.caption("Ready-to-publish Markdown summary formatted for Substack, Medium, Email Newsletters, and financial blogs.")
        newsletter_md = generate_newsletter_markdown(weekly_data)
        st.text_area("Formatted Markdown (Click inside and press Ctrl+A, Ctrl+C to copy):", value=newsletter_md, height=300)

# ----------------- TAB 2: ON-DEMAND COVERED CALL SCREENER -----------------
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
            st.info(f"🕒 **Data Sourced**: `{snap_time}` | 🔒 **Market Closed**: Option prices reflect regular session settlement. Served closing snapshot (0 API calls).")
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
            st.metric("Closing Market Price", f"${curr_price:.2f}")
        with kpi3:
            st.metric("Reference Cost Basis", f"${ref_price:.2f}", help="Cost basis used for yield and ROI calculations")
        with kpi4:
            st.metric("Next Earnings Date", earnings_date)

        st.markdown("---")
        st.subheader(f"Option Chains & Yield Matrix for {symbol}")
        
        if results:
            df = pd.DataFrame(results)
            
            cols_to_include = [
                'term', 'expiration_date', 'target_type', 'strike_price', 'premium', 'premium_roi_pct',
                'ann_max_roi_pct', 'cushion_pct', 'implied_volatility_pct', 'delta', 'prob_itm_pct', 'prob_touch_pct',
                'ann_premium_roi_pct', 'max_roi_pct', 'score', 'breakeven_price'
            ]
            existing_cols = [c for c in cols_to_include if c in df.columns]
            display_df = df[existing_cols].copy()

            rename_dict = {
                'term': 'Term',
                'expiration_date': 'Expiration',
                'target_type': 'Target Strike',
                'strike_price': 'Strike ($)',
                'premium': 'Premium ($)',
                'premium_roi_pct': 'Premium ROI (%)',
                'ann_max_roi_pct': 'Ann. Max ROI (%)',
                'cushion_pct': 'Cushion (%)',
                'implied_volatility_pct': 'IV (%)',
                'delta': 'Delta',
                'prob_itm_pct': 'Prob. ITM (%)',
                'prob_touch_pct': 'Prob. Hit Strike (%)',
                'ann_premium_roi_pct': 'Ann. Premium Yield (%)',
                'max_roi_pct': 'Max ROI (%)',
                'score': 'Score (0-100)',
                'breakeven_price': 'Breakeven ($)'
            }
            display_df.rename(columns=rename_dict, inplace=True)

            st.dataframe(display_df, width="stretch", hide_index=True)

            # Email Delivery for Single Ticker Option Matrix
            with st.container(border=True):
                st.markdown(f"**📧 Email Me This `{symbol}` Option Matrix & Strategy Report**")
                col_t2_em1, col_t2_em2 = st.columns([3, 1])
                with col_t2_em1:
                    t2_email = st.text_input("Enter your email to receive this full report & yield table", placeholder="trader@example.com", key=f"t2_email_{symbol}")
                with col_t2_em2:
                    st.markdown("<br>", unsafe_allow_html=True)
                    t2_send_btn = st.button(f"✉️ Email {symbol} Report", type="primary", key=f"btn_email_{symbol}")
                
                if t2_send_btn:
                    if t2_email and "@" in t2_email and "." in t2_email:
                        saved = save_subscriber(t2_email, "", f"{symbol} Option Matrix")
                        if saved:
                            st.success(f"✅ **Sent!** Option analysis for **{symbol}** has been queued for **{t2_email.strip()}**.")
                        else:
                            st.error("Could not save email. Please try again.")
                    else:
                        st.warning("⚠️ Please enter a valid email address.")

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
            st.dataframe(hist_df, width="stretch", hide_index=True)
        else:
            st.info(f"No historical records saved for {symbol} yet.")

# ----------------- TAB 3: QUANTITATIVE METHODOLOGY -----------------
with tab_methodology:
    st.subheader("📐 Quantitative Formulas & Mathematical Modeling")
    
    st.markdown(r"""
    ### 1. Composite Covered Call Quality Score (0–100)
    To rank the best covered call opportunities without falling into speculative volatility traps, each contract is scored on a risk-adjusted scale:
    $$\text{Score} = \text{Yield Score} (40\%) + \text{Cushion Score} (30\%) + \text{Probability Score} (30\%) - \text{Earnings Penalty}$$
    
    - **Yield Score (40 pts)**: Rewards high Annualized Max ROI ($\min(40, \frac{\text{Ann Max ROI}}{25\%} \times 40)$).
    - **Downside Cushion Score (30 pts)**: Rewards downside buffer ($\min(30, \frac{\text{Cushion \%}}{6\%} \times 30)$).
    - **Probability Sweet Spot (30 pts)**: Scored on Black-Scholes $P(\text{ITM})$ targeting ideal range ($15\% - 35\%$).
    - **Earnings Penalty (-15 pts)**: Deducted if earnings announcement falls within option lifespan ($\le \text{DTE}$).

    ---

    ### 2. Black-Scholes In-The-Money Probability ($N(d_2)$)
    The probability that an Out-of-the-Money call option expires In-The-Money (ITM) under risk-neutral Black-Scholes dynamics is given by $N(d_2)$:
    $$d_2 = \frac{\ln(S / K) + (r - \frac{1}{2}\sigma^2)T}{\sigma \sqrt{T}}$$
    $$\text{Prob. ITM} = N(d_2) = \frac{1}{2} \left[ 1 + \text{erf}\left(\frac{d_2}{\sqrt{2}}\right) \right]$$
    Where:
    - $S$ = Stock Reference Price (Closing Settlement)
    - $K$ = Option Strike Price
    - $\sigma$ = Implied Volatility ($\text{IV} / 100$)
    - $T = \text{DTE} / 365$ (Time to expiration in years)
    - $r$ = Risk-free rate ($\approx 4.5\%$)

    ---

    ### 3. Probability of Touching / Hitting Strike Price
    By the **Reflection Principle** of Brownian motion with drift, the probability that the underlying stock price touches or exceeds the strike price $K$ at *any point* prior to expiration is approximately:
    $$\text{Prob. Hit Strike} \approx \min\left(100\%, 2 \times N(d_2)\right)$$

    ---

    ### 4. Covered Call Yield & ROI Metrics
    - **Premium Yield (%)**: $\frac{\text{Option Premium}}{\text{Reference Price}} \times 100$
    - **Annualized Premium Yield (%)**: $\text{Premium Yield} \times \frac{365}{\text{DTE}}$
    - **Max ROI (%)**: $\frac{(K - \text{Reference Price}) + \text{Option Premium}}{\text{Reference Price}} \times 100$
    - **Annualized Max ROI (%)**: $\text{Max ROI} \times \frac{365}{\text{DTE}}$
    - **Downside Breakeven Price ($)**: $\text{Reference Price} - \text{Option Premium}$
    - **Downside Cushion (%)**: $\frac{\text{Option Premium}}{\text{Reference Price}} \times 100$
    """)
