import yfinance as yf
from datetime import datetime, date
import pandas as pd
import time
import urllib.request
import urllib.parse
import json
import math
from typing import Optional, List, Dict, Any, Tuple
import streamlit as st
from api_monitor import api_monitor, is_market_open_now

def norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution function N(x)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

def calculate_option_greeks_and_probabilities(S: float, K: float, iv_pct: float, dte: int, r: float = 0.045):
    """
    Calculate Black-Scholes Call Delta (N(d1)),
    Probability of Expiring In-The-Money (ITM % = N(d2)), and 
    Probability of Hitting/Touching Strike Price before expiration (%).
    """
    if not S or not K or not iv_pct or iv_pct <= 0 or dte <= 0:
        return None, None, None
        
    try:
        sigma = iv_pct / 100.0
        T = dte / 365.0
        
        d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        
        delta = round(norm_cdf(d1), 3)
        prob_itm = norm_cdf(d2)
        
        prob_itm_pct = round(prob_itm * 100.0, 2)
        prob_touch_pct = round(min(100.0, 2.0 * prob_itm_pct), 2)
        
        return delta, prob_itm_pct, prob_touch_pct
    except Exception:
        return None, None, None

def calculate_option_probabilities(S: float, K: float, iv_pct: float, dte: int, r: float = 0.045):
    """Backward compatibility wrapper returning (prob_itm_pct, prob_touch_pct)."""
    _, prob_itm, prob_touch = calculate_option_greeks_and_probabilities(S, K, iv_pct, dte, r)
    return prob_itm, prob_touch

# TMC (Technology, Media & Telecommunications) Sub-Sector Taxonomy for Institutional Research
TMC_TAXONOMY = {
    "Semiconductors & AI Hardware": {
        "description": "GPU/CPU designers, foundries, fabless semi, memory, and semiconductor equipment",
        "tickers": ["NVDA", "TSM", "AMD", "AVGO", "QCOM", "ARM", "INTC", "MU", "AMAT", "ASML", "LRCX", "MRVL"]
    },
    "Enterprise SaaS & Cloud Infrastructure": {
        "description": "Hyperscalers, cloud infrastructure, enterprise B2B SaaS, data platforms, and cybersecurity",
        "tickers": ["MSFT", "CRM", "NOW", "ADBE", "ORCL", "PLTR", "SNOW", "PANW", "CRWD", "WDAY", "DDOG", "NET"]
    },
    "Digital Media, Streaming & Ad-Tech": {
        "description": "Digital ad-tech ecosystems, connected TV, global streaming networks, and consumer internet platforms",
        "tickers": ["GOOGL", "META", "NFLX", "SPOT", "DIS", "TTD", "PINS", "SNAP", "ROKU", "UBER"]
    },
    "Telecom & Digital Infrastructure": {
        "description": "5G wireless carriers, cellular tower REITs, hyper-scale data centers, and enterprise networking",
        "tickers": ["T", "VZ", "TMUS", "AMT", "CCI", "EQIX", "DLR", "CSCO", "ANET"]
    },
    "Tech & Sector Benchmarks": {
        "description": "Benchmark ETFs for Nasdaq-100, Tech, Software, Semiconductors, and Broad S&P 500",
        "tickers": ["QQQ", "XLK", "SOXX", "SMH", "IGV", "SPY"]
    }
}

TMC_ALL_TICKERS = sorted(list(set(
    ticker for group in TMC_TAXONOMY.values() for ticker in group["tickers"]
)))

def get_tmc_subsector_for_ticker(ticker: str) -> str:
    """Return TMC sub-sector name for a given ticker symbol."""
    upper = ticker.upper()
    for sector_name, data in TMC_TAXONOMY.items():
        if upper in data["tickers"]:
            return sector_name
    return "General Tech / S&P 500"

import re

POPULAR_SYMBOLS_MAP = {
    'UBER': 'UBER',
    'UBER TECHNOLOGIES': 'UBER',
    'LYFT': 'LYFT',
    'LYFT INC': 'LYFT',
    'TESLA': 'TSLA',
    'TSLA': 'TSLA',
    'TESLA INC': 'TSLA',
    'APPLE': 'AAPL',
    'AAPL': 'AAPL',
    'APPLE INC': 'AAPL',
    'MICROSOFT': 'MSFT',
    'MSFT': 'MSFT',
    'MICROSOFT CORP': 'MSFT',
    'NVIDIA': 'NVDA',
    'NVDA': 'NVDA',
    'NVIDIA CORP': 'NVDA',
    'AMAZON': 'AMZN',
    'AMZN': 'AMZN',
    'AMAZON.COM': 'AMZN',
    'GOOGLE': 'GOOGL',
    'ALPHABET': 'GOOGL',
    'GOOG': 'GOOGL',
    'GOOGL': 'GOOGL',
    'META': 'META',
    'FACEBOOK': 'META',
    'AMD': 'AMD',
    'ADVANCED MICRO DEVICES': 'AMD',
    'SPY': 'SPY',
    'S&P 500': 'SPY',
    'QQQ': 'QQQ',
    'NASDAQ': 'QQQ',
    'PLTR': 'PLTR',
    'PALANTIR': 'PLTR',
    'NETFLIX': 'NFLX',
    'NFLX': 'NFLX',
    'DISNEY': 'DIS',
    'DIS': 'DIS',
    'COINBASE': 'COIN',
    'COIN': 'COIN',
    'SOFI': 'SOFI',
    'JPMORGAN': 'JPM',
    'JPM': 'JPM',
    'BERKSHIRE': 'BRK-B',
    'BROADCOM': 'AVGO',
    'AVGO': 'AVGO',
    'TAIWAN SEMI': 'TSM',
    'TSM': 'TSM',
    'SALESFORCE': 'CRM',
    'CRM': 'CRM',
    'SERVICENOW': 'NOW',
    'NOW': 'NOW',
    'ADOBE': 'ADBE',
    'ADBE': 'ADBE',
    'ORACLE': 'ORCL',
    'ORCL': 'ORCL',
    'SNOWFLAKE': 'SNOW',
    'SNOW': 'SNOW',
    'SPOTIFY': 'SPOT',
    'SPOT': 'SPOT',
    'TRADE DESK': 'TTD',
    'TTD': 'TTD',
    'PALO ALTO': 'PANW',
    'PANW': 'PANW',
    'CROWDSTRIKE': 'CRWD',
    'CRWD': 'CRWD',
    'T-MOBILE': 'TMUS',
    'TMUS': 'TMUS',
    'VERIZON': 'VZ',
    'VZ': 'VZ',
    'AT&T': 'T',
    'T': 'T',
    'AMERICAN TOWER': 'AMT',
    'AMT': 'AMT',
    'EQUINIX': 'EQIX',
    'EQIX': 'EQIX',
    'CISCO': 'CSCO',
    'CSCO': 'CSCO',
    'ARISTA': 'ANET',
    'ANET': 'ANET',
    'QUALCOMM': 'QCOM',
    'QCOM': 'QCOM',
    'ARM': 'ARM',
    'ARM HOLDINGS': 'ARM',
    'INTEL': 'INTC',
    'INTC': 'INTC',
    'MICRON': 'MU',
    'MU': 'MU',
    'APPLIED MATERIALS': 'AMAT',
    'AMAT': 'AMAT',
    'ASML': 'ASML',
    'ASML HOLDING': 'ASML',
    'LAM RESEARCH': 'LRCX',
    'LRCX': 'LRCX',
    'MARVELL': 'MRVL',
    'MRVL': 'MRVL',
    'WORKDAY': 'WDAY',
    'WDAY': 'WDAY',
    'DATADOG': 'DDOG',
    'DDOG': 'DDOG',
    'CLOUDFLARE': 'NET',
    'NET': 'NET',
    'PINTEREST': 'PINS',
    'PINS': 'PINS',
    'SNAP': 'SNAP',
    'SNAP INC': 'SNAP',
    'ROKU': 'ROKU',
    'CROWN CASTLE': 'CCI',
    'CCI': 'CCI',
    'DIGITAL REALTY': 'DLR',
    'DLR': 'DLR',
    'XLK': 'XLK',
    'SOXX': 'SOXX',
    'SMH': 'SMH',
    'IGV': 'IGV',
    'ELI LILLY': 'LLY',
    'LLY': 'LLY',
    'COSTCO': 'COST',
    'COST': 'COST'
}

def resolve_to_symbol(query: str) -> str:
    """Convert company names (e.g., 'uber', 'apple', 'taiwan semi') to ticker symbols ('UBER', 'AAPL', 'TSM')."""
    cleaned = query.strip()
    if not cleaned:
        return cleaned

    upper_clean = cleaned.upper()
    # Fast path 1: Pre-mapped popular tickers and names
    if upper_clean in POPULAR_SYMBOLS_MAP:
        return POPULAR_SYMBOLS_MAP[upper_clean]

    # Fast path 2: Standard US equity ticker pattern (1-5 letters, optional dot/dash)
    if re.match(r'^[A-Z0-9.\-=]{1,5}$', upper_clean):
        return upper_clean

    # Fallback to Yahoo Finance search for multi-word queries
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={urllib.parse.quote(cleaned)}&quotesCount=5"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            quotes = data.get('quotes', [])
            for q in quotes:
                if q.get('quoteType') in ['EQUITY', 'ETF']:
                    return q.get('symbol').upper()
    except Exception:
        pass
        
    return upper_clean

def evaluate_earnings_risk(earnings_date: str, dte: int) -> Dict[str, Any]:
    """
    Evaluate binary earnings event risk for an option contract.
    Returns structured risk metadata, badge string, days-to-earnings, and analyst notes.
    """
    if not earnings_date or earnings_date == "N/A":
        return {
            "has_earnings": False,
            "inside_expiry": False,
            "days_to_earnings": None,
            "badge": "ℹ️ No Confirmed Earnings",
            "badge_short": "ℹ️ No Date",
            "severity": "info",
            "detail": "No confirmed quarterly earnings date reported for this expiration period."
        }
    
    try:
        today = date.today()
        e_dt = datetime.strptime(earnings_date, "%Y-%m-%d").date()
        days = (e_dt - today).days
        
        if 0 <= days <= dte:
            return {
                "has_earnings": True,
                "inside_expiry": True,
                "days_to_earnings": days,
                "badge": f"🔥 EARNINGS INSIDE ({days}d)",
                "badge_short": f"🔥 Inside ({days}d)",
                "severity": "warning",
                "detail": f"Binary event: Earnings announcement is in {days} days, prior to option expiration ({dte}d DTE). Premium includes volatility event risk."
            }
        elif days > dte:
            return {
                "has_earnings": True,
                "inside_expiry": False,
                "days_to_earnings": days,
                "badge": f"✅ Post-Earnings Safe ({days}d)",
                "badge_short": f"✅ Safe ({days}d)",
                "severity": "success",
                "detail": f"Safe window: Option contract expires in {dte}d before earnings report in {days} days."
            }
        else:
            return {
                "has_earnings": False,
                "inside_expiry": False,
                "days_to_earnings": days,
                "badge": "✅ Past Earnings Safe",
                "badge_short": "✅ Past Safe",
                "severity": "success",
                "detail": f"Earnings report was {abs(days)} days ago. Trading in normal post-earnings volatility regime."
            }
    except Exception:
        return {
            "has_earnings": False,
            "inside_expiry": False,
            "days_to_earnings": None,
            "badge": "ℹ️ Unconfirmed Date",
            "badge_short": "ℹ️ Unconfirmed",
            "severity": "info",
            "detail": "Could not parse earnings date format."
        }

def calculate_covered_call_score(
    ann_max_roi_pct: float,
    cushion_pct: float,
    prob_itm_pct: float,
    dte: int,
    earnings_date: str = "N/A"
) -> float:
    """
    Calculate Composite Covered Call Score (0 - 100).
    Formula:
      - Yield Score (40%): Normalized Annualized Max ROI
      - Cushion / Safety Score (30%): Downside breakeven buffer percentage
      - Probability Score (30%): Probability of success sweet spot (OTM / Delta)
      - Earnings Penalty: -15 points if earnings falls before contract expiration
    """
    if ann_max_roi_pct is None or cushion_pct is None:
        return 0.0
    
    # 1. Yield component (40 pts max) - 25% Ann ROI yields full 40 pts
    yield_component = min(40.0, max(0.0, (ann_max_roi_pct / 25.0) * 40.0))
    
    # 2. Cushion / Downside buffer component (30 pts max) - 6% buffer yields full 30 pts
    cushion_component = min(30.0, max(0.0, (cushion_pct / 6.0) * 30.0))
    
    # 3. Probability of Success component (30 pts max)
    if prob_itm_pct is not None:
        if 15.0 <= prob_itm_pct <= 40.0:
            prob_component = 30.0
        elif prob_itm_pct < 15.0:
            prob_component = max(10.0, 30.0 - (15.0 - prob_itm_pct) * 1.5)
        else:
            prob_component = max(10.0, 30.0 - (prob_itm_pct - 40.0) * 0.8)
    else:
        prob_component = 20.0
        
    score = yield_component + cushion_component + prob_component
    
    # 4. Earnings risk penalty (-15 pts if binary event falls inside contract lifespan)
    earnings_risk = evaluate_earnings_risk(earnings_date, dte)
    if earnings_risk.get("inside_expiry"):
        score -= 15.0
            
    return round(max(0.0, min(100.0, score)), 1)

@st.cache_data(ttl=900, show_spinner=False)
def fetch_ticker_data_cached(input_query: str):
    """Fetch ticker info with 15-minute in-memory caching and background throttling."""
    symbol = resolve_to_symbol(input_query)
    ticker = yf.Ticker(symbol)
    
    current_price = None
    expirations = None
    t0 = time.time()
    
    # Retry up to 3 times for API stability
    for attempt in range(3):
        try:
            api_monitor.apply_throttle()
            info = ticker.fast_info
            if is_market_open_now():
                live_px = info.get('lastPrice') or info.get('regularMarketPrice') or info.get('previousClose')
            else:
                live_px = info.get('lastPrice') or info.get('previousClose') or info.get('regularMarketPreviousClose')
            if live_px and not pd.isna(live_px) and float(live_px) > 0:
                current_price = float(live_px)
                break
        except Exception:
            ticker = yf.Ticker(symbol)
        time.sleep(0.2 * (attempt + 1))
        
    if not current_price or pd.isna(current_price):
        # Fallback to recent history
        try:
            hist = ticker.history(period="5d")
            if not hist.empty and 'Close' in hist:
                current_price = float(hist['Close'].iloc[-1])
        except Exception:
            pass

    if not current_price or pd.isna(current_price):
        lat = (time.time() - t0) * 1000.0
        api_monitor.record_api_call("FastInfo", symbol, False, lat, "Price not found")
        raise ValueError(f"Could not retrieve stock price for '{symbol}' ({input_query}). Please verify the ticker.")
        
    earnings_date = get_earnings_date(ticker)
    
    # Retry fetching option expirations
    for attempt in range(3):
        try:
            api_monitor.apply_throttle()
            opts = ticker.options
            if opts and len(opts) > 0:
                expirations = list(opts)
                break
        except Exception:
            ticker = yf.Ticker(symbol)
        time.sleep(0.2 * (attempt + 1))
    
    lat = (time.time() - t0) * 1000.0
    if not expirations:
        api_monitor.record_api_call("OptionsList", symbol, False, lat, "Empty option chain")
        raise ValueError(f"No option chain data available for '{symbol}'. Check if options are traded for this stock.")

    api_monitor.record_api_call("OptionsList", symbol, True, lat)
    return symbol, current_price, earnings_date, expirations

def get_earnings_date(ticker_obj):
    """Extract next upcoming earnings date safely."""
    try:
        cal = ticker_obj.calendar
        if isinstance(cal, pd.DataFrame) and not cal.empty:
            if 'Earnings Date' in cal.index:
                e_date = cal.loc['Earnings Date'][0]
                return pd.to_datetime(e_date).strftime('%Y-%m-%d')
        elif isinstance(cal, dict) and 'Earnings Date' in cal:
            return pd.to_datetime(cal['Earnings Date'][0]).strftime('%Y-%m-%d')
    except Exception:
        pass
    return "N/A"

def find_target_expirations(expirations):
    """Find expiration dates closest to 60 days (~2m) and 90 days (~3m)."""
    today = date.today()
    exp_dates = []
    
    for exp_str in expirations:
        try:
            exp_dt = datetime.strptime(exp_str, "%Y-%m-%d").date()
            dte = (exp_dt - today).days
            if dte > 0:
                exp_dates.append((exp_str, dte))
        except Exception:
            continue
            
    if not exp_dates:
        return {}

    exp_2m = min(exp_dates, key=lambda x: abs(x[1] - 60))
    exp_3m = min(exp_dates, key=lambda x: abs(x[1] - 90))

    result = {'2-Month': exp_2m}
    if exp_3m[0] != exp_2m[0]:
        result['3-Month'] = exp_3m
    return result

def get_nearest_strike(available_strikes, target_price):
    """Find nearest strike price at or above target price."""
    valid_strikes = [s for s in available_strikes if s >= target_price]
    if not valid_strikes:
        return min(available_strikes, key=lambda s: abs(s - target_price))
    return min(valid_strikes, key=lambda s: abs(s - target_price))

@st.cache_data(ttl=900, show_spinner=False)
def fetch_option_chain_cached(symbol: str, exp_date_str: str) -> Optional[pd.DataFrame]:
    """Fetch option calls table for a given expiration with caching and retries."""
    ticker = yf.Ticker(symbol)
    t_opt = time.time()
    for attempt in range(3):
        try:
            api_monitor.apply_throttle()
            chain = ticker.option_chain(exp_date_str)
            if chain is not None and chain.calls is not None and not chain.calls.empty:
                lat_opt = (time.time() - t_opt) * 1000.0
                api_monitor.record_api_call(f"Chain ({exp_date_str})", symbol, True, lat_opt)
                return chain.calls
        except Exception:
            ticker = yf.Ticker(symbol)
        time.sleep(0.2 * (attempt + 1))
    
    lat_opt = (time.time() - t_opt) * 1000.0
    api_monitor.record_api_call(f"Chain ({exp_date_str})", symbol, False, lat_opt, "Empty call table")
    return None

@st.cache_data(ttl=900, show_spinner=False)
def screen_covered_calls(input_query: str, custom_purchase_price: float = None):
    """Fetch stock price, options data, and calculate ROIs supporting names and symbols."""
    symbol, current_price, earnings_date, expirations = fetch_ticker_data_cached(input_query)
    
    ref_price = custom_purchase_price if (custom_purchase_price and custom_purchase_price > 0) else current_price
    target_exps = find_target_expirations(expirations)
    results = []

    for term_label, (exp_date_str, dte) in target_exps.items():
        calls = fetch_option_chain_cached(symbol, exp_date_str)
        if calls is None or calls.empty:
            continue
        strikes = calls['strike'].values
        targets = [
            ('5% OTM', ref_price * 1.05),
            ('10% OTM', ref_price * 1.10)
        ]

        for target_label, target_val in targets:
            strike = get_nearest_strike(strikes, target_val)
            matching = calls[calls['strike'] == strike]
            if matching.empty:
                continue
            option_row = matching.iloc[0]
            
            bid = float(option_row.get('bid', 0.0))
            ask = float(option_row.get('ask', 0.0))
            last_price = float(option_row.get('lastPrice', 0.0))

            iv_raw = option_row.get('impliedVolatility', None)
            iv_pct = round(float(iv_raw) * 100.0, 2) if (iv_raw is not None and not pd.isna(iv_raw)) else None

            delta_raw = option_row.get('delta', None)
            premium = (bid + ask) / 2.0 if (bid > 0 and ask > 0) else last_price
            if premium <= 0:
                continue

            premium_roi = (premium / ref_price) * 100.0
            ann_premium_roi = premium_roi * (365.0 / dte)
            
            max_gain = (strike - ref_price) + premium
            max_roi = (max_gain / ref_price) * 100.0
            ann_max_roi = max_roi * (365.0 / dte)
            
            breakeven = ref_price - premium
            cushion_pct = round((premium / ref_price) * 100.0, 2)
            
            delta_calc, prob_itm_pct, prob_touch_pct = calculate_option_greeks_and_probabilities(ref_price, strike, iv_pct, dte)
            delta_val = delta_calc if delta_calc is not None else (round(float(delta_raw), 3) if (delta_raw is not None and not pd.isna(delta_raw)) else None)
            score = calculate_covered_call_score(ann_max_roi, cushion_pct, prob_itm_pct, dte, earnings_date)
            earnings_risk = evaluate_earnings_risk(earnings_date, dte)

            results.append({
                'term': f"{term_label} (~{dte}d)",
                'expiration_date': exp_date_str,
                'dte': dte,
                'target_type': target_label,
                'strike_price': round(strike, 2),
                'bid': round(bid, 2),
                'ask': round(ask, 2),
                'premium': round(premium, 2),
                'implied_volatility_pct': iv_pct,
                'delta': delta_val,
                'prob_itm_pct': prob_itm_pct,
                'prob_touch_pct': prob_touch_pct,
                'premium_roi_pct': round(premium_roi, 2),
                'ann_premium_roi_pct': round(ann_premium_roi, 2),
                'max_roi_pct': round(max_roi, 2),
                'ann_max_roi_pct': round(ann_max_roi, 2),
                'breakeven_price': round(breakeven, 2),
                'cushion_pct': cushion_pct,
                'score': score,
                'earnings_inside_expiry': earnings_risk['inside_expiry'],
                'days_to_earnings': earnings_risk['days_to_earnings'],
                'earnings_badge': earnings_risk['badge'],
                'earnings_badge_short': earnings_risk['badge_short'],
                'earnings_risk_detail': earnings_risk['detail']
            })

    return symbol, current_price, ref_price, earnings_date, results

@st.cache_data(ttl=900, show_spinner=False)
def fetch_tmc_peer_summary(tickers: List[str]) -> List[Dict[str, Any]]:
    """
    Fetch fundamental snapshot, performance, volatility, and earnings status
    for a list of TMC peer companies.
    """
    summary_list = []
    for t in tickers:
        try:
            sym = resolve_to_symbol(t)
            ticker_obj = yf.Ticker(sym)
            api_monitor.apply_throttle()
            
            info = ticker_obj.fast_info
            px = info.get('lastPrice') or info.get('regularMarketPrice') or info.get('previousClose')
            if not px or pd.isna(px):
                continue
            curr_px = round(float(px), 2)
            
            hi_52 = info.get('yearHigh')
            lo_52 = info.get('yearLow')
            mkt_cap = info.get('marketCap')
            
            range_str = f"${float(lo_52):.2f} - ${float(hi_52):.2f}" if (hi_52 and lo_52) else "N/A"
            mkt_cap_str = f"${float(mkt_cap)/1e9:.1f}B" if (mkt_cap and mkt_cap > 0) else "N/A"
            
            e_date = get_earnings_date(ticker_obj)
            e_risk = evaluate_earnings_risk(e_date, dte=60)
            subsector = get_tmc_subsector_for_ticker(sym)
            
            summary_list.append({
                "ticker": sym,
                "subsector": subsector,
                "price": curr_px,
                "range_52w": range_str,
                "market_cap": mkt_cap_str,
                "earnings_date": e_date,
                "earnings_badge": e_risk["badge_short"],
                "earnings_inside_60d": e_risk["inside_expiry"]
            })
        except Exception:
            continue
    return summary_list