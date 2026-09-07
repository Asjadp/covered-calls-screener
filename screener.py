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
            move_data = calculate_earnings_implied_move(ref_price, iv_pct, cushion_pct, earnings_risk['days_to_earnings'])

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
                'earnings_risk_detail': earnings_risk['detail'],
                'expected_move_pct': move_data['expected_move_pct'],
                'expected_move_dollar': move_data['expected_move_dollar'],
                'cushion_coverage_ratio': move_data['cushion_coverage_ratio'],
                'implied_move_badge': move_data['badge'],
                'implied_move_detail': move_data['detail']
            })

    return symbol, current_price, ref_price, earnings_date, results

def calculate_earnings_implied_move(
    stock_price: float,
    iv_pct: Optional[float],
    cushion_pct: Optional[float] = None,
    days_to_earnings: Optional[int] = None
) -> Dict[str, Any]:
    """
    Calculate market-implied 1-day earnings swing from Implied Volatility (IV).
    Rule: 1-Day Earnings Expected Move % ≈ IV * sqrt(1/365) ≈ IV * 5.23%.
    Compares expected move against Covered Call Downside Cushion.
    """
    if not stock_price or stock_price <= 0 or not iv_pct or iv_pct <= 0:
        return {
            "expected_move_pct": None,
            "expected_move_dollar": None,
            "cushion_coverage_ratio": None,
            "status": "UNKNOWN",
            "badge": "ℹ️ No IV Data",
            "badge_color": "gray",
            "detail": "Implied volatility data unavailable to compute expected move."
        }
    
    expected_move_pct = round((iv_pct / 100.0) * math.sqrt(1.0 / 365.0) * 100.0, 2)
    expected_move_dollar = round(stock_price * (expected_move_pct / 100.0), 2)
    
    coverage_ratio = None
    if cushion_pct is not None and cushion_pct > 0 and expected_move_pct > 0:
        coverage_ratio = round(cushion_pct / expected_move_pct, 2)
        
    if coverage_ratio is not None:
        if coverage_ratio >= 1.0:
            status = "PROTECTED"
            badge = f"🛡️ Protected ({coverage_ratio:.1f}x Coverage)"
            badge_color = "green"
            detail = f"Downside cushion ({cushion_pct:.1f}%) covers market-implied 1-day earnings move (±{expected_move_pct:.1f}% / ${expected_move_dollar:.2f}). Option premium fully absorbs expected swing."
        elif coverage_ratio >= 0.70:
            status = "MODERATE_COVERAGE"
            badge = f"⚖️ Moderate ({coverage_ratio:.1f}x Coverage)"
            badge_color = "orange"
            detail = f"Downside cushion ({cushion_pct:.1f}%) partially absorbs expected earnings swing (±{expected_move_pct:.1f}% / ${expected_move_dollar:.2f})."
        else:
            status = "EXPOSED"
            badge = f"⚠️ Tail Risk ({coverage_ratio:.1f}x Coverage)"
            badge_color = "red"
            detail = f"Market implies ±{expected_move_pct:.1f}% (${expected_move_dollar:.2f}) move, exceeding downside cushion ({cushion_pct:.1f}%). High tail-risk into event."
    else:
        status = "ESTIMATED"
        badge = f"📊 Implied Move ±{expected_move_pct:.1f}%"
        badge_color = "blue"
        detail = f"Market-implied 1-day volatility swing is ±{expected_move_pct:.1f}% (${expected_move_dollar:.2f})."
        
    return {
        "expected_move_pct": expected_move_pct,
        "expected_move_dollar": expected_move_dollar,
        "cushion_coverage_ratio": coverage_ratio,
        "status": status,
        "badge": badge,
        "badge_color": badge_color,
        "detail": detail
    }

@st.cache_data(ttl=900, show_spinner=False)
def fetch_fundamental_metrics(symbol: str) -> Dict[str, Any]:
    """
    Fetch comprehensive fundamental valuation multiples, margins, SaaS metrics,
    and Wall Street consensus price targets for institutional research.
    """
    sym = resolve_to_symbol(symbol)
    ticker = yf.Ticker(sym)
    t0 = time.time()
    
    info: Dict[str, Any] = {}
    for attempt in range(3):
        try:
            api_monitor.apply_throttle()
            info = ticker.info or {}
            if info:
                break
        except Exception:
            ticker = yf.Ticker(sym)
        time.sleep(0.2 * (attempt + 1))
    
    lat = (time.time() - t0) * 1000.0
    api_monitor.record_api_call("FundamentalInfo", sym, bool(info), lat)
    
    # 1. Valuation Multiples
    fwd_pe = info.get('forwardPE')
    trail_pe = info.get('trailingPE')
    ev_ebitda = info.get('enterpriseToEbitda')
    ev_sales = info.get('enterpriseToRevenue')
    
    # 2. Growth & Profitability
    rev_growth = info.get('revenueGrowth')
    gross_margins = info.get('grossMargins')
    op_margins = info.get('operatingMargins')
    fcf = info.get('freeCashflow')
    tot_rev = info.get('totalRevenue')
    mkt_cap = info.get('marketCap')
    
    rev_growth_pct = round(float(rev_growth) * 100.0, 2) if (rev_growth is not None and not pd.isna(rev_growth)) else None
    gross_margin_pct = round(float(gross_margins) * 100.0, 2) if (gross_margins is not None and not pd.isna(gross_margins)) else None
    op_margin_pct = round(float(op_margins) * 100.0, 2) if (op_margins is not None and not pd.isna(op_margins)) else None
    
    fcf_margin_pct = None
    if fcf is not None and tot_rev is not None and not pd.isna(fcf) and not pd.isna(tot_rev) and float(tot_rev) > 0:
        fcf_margin_pct = round((float(fcf) / float(tot_rev)) * 100.0, 2)
        
    fcf_yield_pct = None
    if fcf is not None and mkt_cap is not None and not pd.isna(fcf) and not pd.isna(mkt_cap) and float(mkt_cap) > 0:
        fcf_yield_pct = round((float(fcf) / float(mkt_cap)) * 100.0, 2)

    # 3. SaaS Rule of 40: (YoY Rev Growth % + FCF Margin %)
    # If FCF margin unavailable, fallback to (YoY Rev Growth % + Operating Margin %)
    rule_of_40_val = None
    rule_of_40_badge = "N/A"
    rule_of_40_pass = False
    
    if rev_growth_pct is not None:
        if fcf_margin_pct is not None:
            rule_of_40_val = round(rev_growth_pct + fcf_margin_pct, 1)
        elif op_margin_pct is not None:
            rule_of_40_val = round(rev_growth_pct + op_margin_pct, 1)
            
    if rule_of_40_val is not None:
        if rule_of_40_val >= 40.0:
            rule_of_40_badge = f"🌟 Elite SaaS Health ({rule_of_40_val:.1f}% >= 40%)"
            rule_of_40_pass = True
        elif rule_of_40_val >= 20.0:
            rule_of_40_badge = f"⚖️ Balanced Efficiency ({rule_of_40_val:.1f}%)"
        else:
            rule_of_40_badge = f"⚠️ Sub-scale Growth/Margin ({rule_of_40_val:.1f}% < 40%)"

    # 4. Wall Street Consensus Targets & Recommendations
    target_mean = info.get('targetMeanPrice')
    target_high = info.get('targetHighPrice')
    target_low = info.get('targetLowPrice')
    analyst_count = info.get('numberOfAnalystOpinions')
    recom_key = info.get('recommendationKey', 'N/A')
    
    # 5. Company Name & Profile
    short_name = info.get('shortName') or info.get('longName') or sym
    summary = info.get('longBusinessSummary') or "Institutional equity profile for TMC universe constituent."

    return {
        "symbol": sym,
        "company_name": short_name,
        "business_summary": summary,
        "forward_pe": round(float(fwd_pe), 2) if (fwd_pe is not None and not pd.isna(fwd_pe)) else None,
        "trailing_pe": round(float(trail_pe), 2) if (trail_pe is not None and not pd.isna(trail_pe)) else None,
        "ev_ebitda": round(float(ev_ebitda), 2) if (ev_ebitda is not None and not pd.isna(ev_ebitda)) else None,
        "ev_sales": round(float(ev_sales), 2) if (ev_sales is not None and not pd.isna(ev_sales)) else None,
        "revenue_growth_pct": rev_growth_pct,
        "gross_margin_pct": gross_margin_pct,
        "operating_margin_pct": op_margin_pct,
        "fcf_margin_pct": fcf_margin_pct,
        "fcf_yield_pct": fcf_yield_pct,
        "rule_of_40_val": rule_of_40_val,
        "rule_of_40_badge": rule_of_40_badge,
        "rule_of_40_pass": rule_of_40_pass,
        "target_mean_price": round(float(target_mean), 2) if (target_mean is not None and not pd.isna(target_mean)) else None,
        "target_high_price": round(float(target_high), 2) if (target_high is not None and not pd.isna(target_high)) else None,
        "target_low_price": round(float(target_low), 2) if (target_low is not None and not pd.isna(target_low)) else None,
        "analyst_count": int(analyst_count) if (analyst_count is not None and not pd.isna(analyst_count)) else None,
        "recommendation": str(recom_key).replace("_", " ").title() if recom_key else "N/A"
    }

def generate_pitch_tear_sheet(
    symbol: str,
    stock_price: float,
    fundamentals: Dict[str, Any],
    option_row: Dict[str, Any],
    subsector: str = "TMC Universe",
    ref_price: Optional[float] = None
) -> str:
    """
    Generate a 1-Page Institutional Equity Research & Covered Call Pitch Tear Sheet in Markdown.
    Formatted for investment committee memos, buy-side research, and client pitch distribution.
    """
    cost_basis = ref_price if (ref_price and ref_price > 0) else stock_price
    today_str = datetime.now().strftime("%B %d, %Y")
    
    # Extract fundamental metrics
    co_name = fundamentals.get("company_name", symbol)
    fwd_pe_str = f"{fundamentals.get('forward_pe'):.1f}x" if fundamentals.get('forward_pe') else "N/A"
    trail_pe_str = f"{fundamentals.get('trailing_pe'):.1f}x" if fundamentals.get('trailing_pe') else "N/A"
    ev_ebitda_str = f"{fundamentals.get('ev_ebitda'):.1f}x" if fundamentals.get('ev_ebitda') else "N/A"
    ev_sales_str = f"{fundamentals.get('ev_sales'):.1f}x" if fundamentals.get('ev_sales') else "N/A"
    rev_growth_str = f"{fundamentals.get('revenue_growth_pct'):+.1f}%" if fundamentals.get('revenue_growth_pct') is not None else "N/A"
    gross_margin_str = f"{fundamentals.get('gross_margin_pct'):.1f}%" if fundamentals.get('gross_margin_pct') is not None else "N/A"
    op_margin_str = f"{fundamentals.get('operating_margin_pct'):.1f}%" if fundamentals.get('operating_margin_pct') is not None else "N/A"
    fcf_yield_str = f"{fundamentals.get('fcf_yield_pct'):.1f}%" if fundamentals.get('fcf_yield_pct') is not None else "N/A"
    rule_40_str = fundamentals.get("rule_of_40_badge", "N/A")
    analyst_recom = fundamentals.get("recommendation", "N/A")
    target_mean = fundamentals.get("target_mean_price")
    target_high = fundamentals.get("target_high_price")
    target_low = fundamentals.get("target_low_price")
    analyst_count = fundamentals.get("analyst_count", "N/A")
    
    target_mean_str = f"${target_mean:.2f}" if target_mean else "N/A"
    target_range_str = f"${target_low:.2f} - ${target_high:.2f}" if (target_low and target_high) else "N/A"
    
    target_upside_stock_str = f"{((target_mean - stock_price) / stock_price * 100):+.1f}%" if (target_mean and stock_price > 0) else "N/A"
    
    # Extract option row metrics
    term = option_row.get('term', 'Near-term')
    exp_date = option_row.get('expiration_date', 'N/A')
    dte = option_row.get('dte', 60)
    strike = option_row.get('strike_price', 0.0)
    target_type = option_row.get('target_type', 'OTM Call')
    prem = option_row.get('premium', 0.0)
    prem_roi = option_row.get('premium_roi_pct', 0.0)
    ann_prem_roi = option_row.get('ann_premium_roi_pct', 0.0)
    max_roi = option_row.get('max_roi_pct', 0.0)
    ann_max_roi = option_row.get('ann_max_roi_pct', 0.0)
    cushion = option_row.get('cushion_pct', 0.0)
    breakeven = option_row.get('breakeven_price', stock_price - prem)
    iv_val = option_row.get('implied_volatility_pct')
    iv_str = f"{iv_val:.1f}%" if iv_val else "N/A"
    delta_val = option_row.get('delta')
    delta_str = f"{delta_val:.3f}" if delta_val is not None else "N/A"
    prob_itm = option_row.get('prob_itm_pct')
    prob_itm_str = f"{prob_itm:.1f}%" if prob_itm is not None else "N/A"
    prob_touch = option_row.get('prob_touch_pct')
    prob_touch_str = f"{prob_touch:.1f}%" if prob_touch is not None else "N/A"
    score_val = option_row.get('score', 0.0)
    e_badge = option_row.get('earnings_badge', 'N/A')
    
    target_upside_be_str = f"{((target_mean - breakeven) / breakeven * 100):+.1f}%" if (target_mean and breakeven > 0) else "N/A"
    
    # Implied Move
    move_data = calculate_earnings_implied_move(stock_price, iv_val, cushion, option_row.get('days_to_earnings'))
    expected_move_str = f"±{move_data['expected_move_pct']:.1f}% (${move_data['expected_move_dollar']:.2f})" if move_data['expected_move_pct'] else "N/A"
    coverage_badge = move_data.get('badge', 'N/A')

    md = f"""# 📄 INSTITUTIONAL EQUITY RESEARCH & OVERLAY TEAR SHEET
**Target Ticker**: `{symbol}` ({co_name}) | **Sector Vertical**: {subsector}
**Date Generated**: {today_str} | **Current Spot Price**: `${stock_price:.2f}` | **Reference Basis**: `${cost_basis:.2f}`

---

## 🏛️ Executive Summary & Overlay Thesis
* **Structure**: Buy/Hold `{symbol}` Common Equity with a **{term} Covered Call Overlay** at the **${strike:.2f} Strike** ({target_type}).
* **Primary Objective**: Monetize elevated implied volatility ({iv_str} IV) to generate **{ann_prem_roi:.1f}% Annualized Option Yield** while creating a **{cushion:.1f}% Downside Margin of Safety** ($Breakeven: ${breakeven:.2f}).
* **Quantitative Score**: **`{score_val} / 100`** (Yield, Downside Cushion, Black-Scholes Delta, and Binary Catalyst Adjusted).
* **Wall Street Consensus**: **{analyst_recom}** across {analyst_count} analysts with a Mean Target of **{target_mean_str}** ({target_upside_stock_str} Spot Upside).

---

## 📊 Valuation Multiples & Fundamental Health Scorecard

| Fundamental Valuation Metric | Value | Benchmark / Health Context |
| :--- | :---: | :--- |
| **Forward P/E Multiple** | `{fwd_pe_str}` | Trailing P/E: `{trail_pe_str}` |
| **EV / NTM EBITDA** | `{ev_ebitda_str}` | Enterprise Value / Cash Flow Multiple |
| **EV / Sales Multiple** | `{ev_sales_str}` | Top-line Enterprise Valuation |
| **YoY Revenue Growth** | `{rev_growth_str}` | Top-line momentum across trailing periods |
| **Gross Margin %** | `{gross_margin_str}` | Unit economics and pricing power |
| **Operating Margin %** | `{op_margin_str}` | Operating efficiency & operating leverage |
| **FCF Yield %** | `{fcf_yield_str}` | Free Cash Flow yield vs `{ann_prem_roi:.1f}%` Option Yield |
| **SaaS / Tech Rule of 40** | **{rule_40_str}** | Growth % + Cash Flow Margin Efficiency Standard |

---

## 🎯 Covered Call Structure & Yield Profile

| Option Parameter | Specification | Institutional Analysis |
| :--- | :---: | :--- |
| **Expiration Date / DTE** | `{exp_date}` (`{dte}` days) | Optimal liquidity and time-decay ($Theta) horizon |
| **Strike Price ($)** | **`${strike:.2f}`** | **{target_type}** strike structure |
| **Option Premium Bid/Ask Mid** | **`${prem:.2f}`** | **{prem_roi:.2f}%** Flat Option Yield for {dte}d period |
| **Annualized Premium Yield** | **`{ann_prem_roi:.1f}%`** | Pure cash-flow generation if stock remains flat |
| **Max Upside ROI (Annualized)** | **`{ann_max_roi:.1f}%`** | Total return if assigned at strike (${max_roi:.1f}% flat) |
| **Downside Breakeven Price** | **`${breakeven:.2f}`** | **{cushion:.1f}%** Cushion buffer below spot price |
| **Black-Scholes Delta (Δ)** | `{delta_str}` | Sensitivity to $1 move in underlying share price |
| **Probability of Expiring ITM** | `{prob_itm_str}` | Risk-neutral probability of assignment at expiry |
| **Probability of Touching Strike** | `{prob_touch_str}` | Probability of stock hitting strike during contract life |

---

## 🛡️ Margin of Safety vs. Wall Street Consensus

* **Wall Street Mean Target**: **{target_mean_str}** (Range: {target_range_str})
* **Spot Upside to Consensus Target**: `{target_upside_stock_str}`
* **Breakeven Upside to Consensus Target**: **`{target_upside_be_str}`**
> **Overlay Alpha**: Because the covered call creates a downside breakeven at **`${breakeven:.2f}`**, an investor achieves **{target_upside_be_str} upside to consensus fair value** compared to only `{target_upside_stock_str}` on naked equity shares.

---

## ⚡ Binary Earnings Catalyst & Volatility Risk

* **Earnings Catalyst Status**: **{e_badge}**
* **Implied 1-Day Earnings Swing**: `{expected_move_str}`
* **Option Cushion vs. Implied Move**: **{coverage_badge}**
* **Catalyst Assessment**: {move_data['detail']}
* **Post-Earnings IV Crush**: If held through earnings, implied volatility collapses 30–60%, accelerating call option decay in favor of the covered call writer.

---

## ⚖️ Downside Scenario Analysis & Trade Execution Framework

```
[Bear Scenario]: Stock drops to $Breakeven ($${breakeven:.2f}) -> Total Return: 0.0% (Protected by Premium)
[Flat Scenario]: Stock unchanged at $${stock_price:.2f} -> Total Return: +{prem_roi:.2f}% (+{ann_prem_roi:.1f}% Ann.)
[Bull Scenario]: Stock exceeds Strike ($${strike:.2f}) -> Total Return: +{max_roi:.1f}% (+{ann_max_roi:.1f}% Ann. Max Cap)
```

**Trade Execution Rule**: Sell 1 `{symbol} {exp_date} C{strike:.1f}` contract per 100 shares owned. Set GTC limit order to buy back at 80% profit (or roll at 14 DTE).

---
*Generated by Covered Call Screener & TMC Equity Research Engine | Author: Asjad P. (GitHub: @asjadp)*
"""
    return md

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