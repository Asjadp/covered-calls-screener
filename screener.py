import yfinance as yf
from datetime import datetime, date
import pandas as pd
import time
import urllib.request
import urllib.parse
import json
import math
import streamlit as st

def norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution function N(x)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

def calculate_option_probabilities(S: float, K: float, iv_pct: float, dte: int, r: float = 0.045):
    """
    Calculate Probability of Expiring In-The-Money (ITM %) and 
    Probability of Hitting/Touching Strike Price before expiration (%).
    """
    if not S or not K or not iv_pct or iv_pct <= 0 or dte <= 0:
        return None, None
        
    try:
        sigma = iv_pct / 100.0
        T = dte / 365.0
        
        d2 = (math.log(S / K) + (r - 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        prob_itm = norm_cdf(d2)
        
        prob_itm_pct = round(prob_itm * 100.0, 2)
        prob_touch_pct = round(min(100.0, 2.0 * prob_itm_pct), 2)
        
        return prob_itm_pct, prob_touch_pct
    except Exception:
        return None, None

def resolve_to_symbol(query: str) -> str:
    """Convert company names (e.g., 'apple') to ticker symbols ('AAPL')."""
    cleaned = query.strip()
    if not cleaned:
        return cleaned

    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={urllib.parse.quote(cleaned)}&quotesCount=5"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
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
        
    return cleaned.upper()

@st.cache_data(ttl=300, show_spinner=False)
def fetch_ticker_data_cached(input_query: str):
    """Fetch ticker info resolving company names or ticker symbols."""
    time.sleep(0.5)
    symbol = resolve_to_symbol(input_query)
    ticker = yf.Ticker(symbol)
    
    try:
        info = ticker.fast_info
        current_price = info.get('lastPrice') or info.get('previousClose')
    except Exception:
        raise ValueError(f"Could not find stock ticker for '{input_query}'. Please check the company name or symbol.")
        
    if not current_price or pd.isna(current_price):
        raise ValueError(f"Could not retrieve stock price for '{symbol}' ({input_query}).")
        
    earnings_date = get_earnings_date(ticker)
    
    try:
        expirations = ticker.options
    except Exception:
        expirations = None
    
    if not expirations:
        raise ValueError(f"No option chain data available for '{symbol}'. Check if options are traded for this stock.")

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

def screen_covered_calls(input_query: str, custom_purchase_price: float = None):
    """Fetch stock price, options data, and calculate ROIs supporting names and symbols."""
    symbol, current_price, earnings_date, expirations = fetch_ticker_data_cached(input_query)
    
    ref_price = custom_purchase_price if (custom_purchase_price and custom_purchase_price > 0) else current_price
    target_exps = find_target_expirations(expirations)
    results = []

    ticker = yf.Ticker(symbol)

    for term_label, (exp_date_str, dte) in target_exps.items():
        time.sleep(0.3)
        try:
            chain = ticker.option_chain(exp_date_str)
            calls = chain.calls
        except Exception:
            continue
        
        if calls is None or calls.empty:
            continue

        strikes = calls['strike'].values
        targets = [
            ('5% OTM', ref_price * 1.05),
            ('10% OTM', ref_price * 1.10)
        ]

        for target_label, target_val in targets:
            strike = get_nearest_strike(strikes, target_val)
            option_row = calls[calls['strike'] == strike].iloc[0]
            
            bid = float(option_row.get('bid', 0.0))
            ask = float(option_row.get('ask', 0.0))
            last_price = float(option_row.get('lastPrice', 0.0))

            iv_raw = option_row.get('impliedVolatility', None)
            iv_pct = round(float(iv_raw) * 100.0, 2) if (iv_raw is not None and not pd.isna(iv_raw)) else None

            delta_raw = option_row.get('delta', None)
            delta_val = round(float(delta_raw), 3) if (delta_raw is not None and not pd.isna(delta_raw)) else None
            
            premium = (bid + ask) / 2.0 if (bid > 0 and ask > 0) else last_price
            if premium <= 0:
                continue

            premium_roi = (premium / ref_price) * 100.0
            ann_premium_roi = premium_roi * (365.0 / dte)
            
            max_gain = (strike - ref_price) + premium
            max_roi = (max_gain / ref_price) * 100.0
            ann_max_roi = max_roi * (365.0 / dte)
            
            breakeven = ref_price - premium
            
            prob_itm_pct, prob_touch_pct = calculate_option_probabilities(ref_price, strike, iv_pct, dte)

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
                'breakeven_price': round(breakeven, 2)
            })

    return symbol, current_price, ref_price, earnings_date, results