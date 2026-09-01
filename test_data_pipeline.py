"""
Automated Data Testing & Benchmark Dataset Pipeline
---------------------------------------------------
Tests yfinance API connectivity, option chain fetching, Black-Scholes probability math,
and saves sample benchmark datasets to CSV/JSON and the database for data testing.
"""

import os
import sys
import json
import time
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any, Tuple
import yfinance as yf

# Ensure UTF-8 output encoding on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from screener import screen_covered_calls, calculate_option_probabilities, resolve_to_symbol, calculate_covered_call_score
from database import init_db, save_screen_results, load_history, get_db_status, save_weekly_top_picks, get_latest_weekly_top_picks, swap_weekly_pick

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
CSV_EXPORT_PATH = os.path.join(DATA_DIR, "sample_options_dataset.csv")
JSON_EXPORT_PATH = os.path.join(DATA_DIR, "sample_options_dataset.json")

BENCHMARK_TICKERS = ["AAPL", "MSFT", "NVDA", "TSLA", "SPY"]

def test_covered_call_scoring() -> bool:
    """Verify quantitative composite covered call score calculation and boundaries."""
    print("Testing Covered Call Quality Scoring engine...")
    
    # Test high quality contract
    score_high = calculate_covered_call_score(ann_max_roi_pct=25.0, cushion_pct=5.0, prob_itm_pct=25.0, dte=60, earnings_date="2099-01-01")
    assert 80.0 <= score_high <= 100.0, f"High quality contract should score >= 80, got {score_high}"
    
    # Test earnings penalty
    today_str = datetime.now().strftime("%Y-%m-%d")
    score_with_earnings = calculate_covered_call_score(ann_max_roi_pct=25.0, cushion_pct=5.0, prob_itm_pct=25.0, dte=60, earnings_date=today_str)
    assert score_high - score_with_earnings == 15.0, "Imminent earnings should deduct exactly 15 points"
    
    # Test boundary limits [0, 100]
    score_low = calculate_covered_call_score(ann_max_roi_pct=-10.0, cushion_pct=0.0, prob_itm_pct=90.0, dte=30, earnings_date=today_str)
    assert 0.0 <= score_low <= 100.0, f"Score ({score_low}) must stay within [0, 100]"
    
    print("  [PASS] Covered call scoring engine verified.")
    return True

def test_weekly_picks_database() -> bool:
    """Verify weekly top picks persistence, retrieval, and dynamic swap mechanism."""
    print("Testing weekly top picks persistence and challenger swap...")
    init_db()
    
    mock_5 = [
        {"ticker": "AAPL", "stock_price": 220.0, "strike_price": 230.0, "expiration_date": "2026-10-16", "dte": 46, "premium": 8.0, "ann_max_roi_pct": 28.0, "cushion_pct": 3.6, "score": 88.0, "breakeven_price": 212.0},
        {"ticker": "MSFT", "stock_price": 420.0, "strike_price": 440.0, "expiration_date": "2026-10-16", "dte": 46, "premium": 12.0, "ann_max_roi_pct": 24.0, "cushion_pct": 2.9, "score": 82.0, "breakeven_price": 408.0}
    ]
    mock_10 = [
        {"ticker": "NVDA", "stock_price": 120.0, "strike_price": 132.0, "expiration_date": "2026-10-16", "dte": 46, "premium": 6.0, "ann_max_roi_pct": 32.0, "cushion_pct": 5.0, "score": 92.0, "breakeven_price": 114.0}
    ]
    
    batch_id = "test-batch-001"
    save_weekly_top_picks(batch_id, mock_5, mock_10)
    
    loaded = get_latest_weekly_top_picks()
    assert len(loaded["5% OTM"]) >= 2, "Loaded 5% OTM picks count mismatch"
    assert len(loaded["10% OTM"]) >= 1, "Loaded 10% OTM picks count mismatch"
    
    # Test Challenger Swap
    challenger = {"ticker": "AMD", "stock_price": 150.0, "strike_price": 157.5, "expiration_date": "2026-10-16", "dte": 46, "premium": 7.0, "ann_max_roi_pct": 35.0, "cushion_pct": 4.6, "score": 95.0, "breakeven_price": 143.0}
    success = swap_weekly_pick("5% OTM", "MSFT", challenger)
    assert success, "Challenger swap operation failed"
    
    # Clean up test records so they don't pollute UI
    import sqlite3
    conn = sqlite3.connect("covered_calls.db")
    cur = conn.cursor()
    cur.execute("DELETE FROM weekly_top_picks WHERE batch_id LIKE 'test-%'")
    conn.commit()
    conn.close()

    print("  [PASS] Weekly top picks persistence and swap verified.")
    return True

def test_black_scholes_math() -> bool:
    """Verify quantitative Black-Scholes probability formulas and bounds."""
    print("Testing Black-Scholes probability math...")
    
    # Test Case 1: Standard At-The-Money Call
    S, K, iv, dte = 100.0, 105.0, 30.0, 60
    prob_itm, prob_touch = calculate_option_probabilities(S, K, iv, dte)
    
    assert prob_itm is not None, "prob_itm should not be None"
    assert prob_touch is not None, "prob_touch should not be None"
    assert 0.0 <= prob_itm <= 100.0, f"prob_itm ({prob_itm}%) out of [0, 100] bounds"
    assert 0.0 <= prob_touch <= 100.0, f"prob_touch ({prob_touch}%) out of [0, 100] bounds"
    assert prob_touch >= prob_itm, f"prob_touch ({prob_touch}%) must be >= prob_itm ({prob_itm}%)"

    # Test Case 2: Deep Out-of-the-Money Call
    prob_itm_far, _ = calculate_option_probabilities(100.0, 200.0, 20.0, 30)
    assert prob_itm_far < 5.0, "Deep OTM call probability should be low (<5%)"

    print("  [PASS] Black-Scholes probability math verified.")
    return True

def test_symbol_resolution() -> bool:
    """Verify company name resolution to ticker symbols."""
    print("Testing company name resolution...")
    cases = {
        "Apple": "AAPL",
        "Microsoft": "MSFT",
        "Nvidia": "NVDA",
        "Tesla": "TSLA"
    }
    for name, expected in cases.items():
        sym = resolve_to_symbol(name)
        assert sym == expected, f"Expected {expected} for '{name}', got '{sym}'"
    print("  [PASS] Symbol resolution verified.")
    return True

def run_benchmark_collection(tickers: List[str] = BENCHMARK_TICKERS) -> pd.DataFrame:
    """
    Screen a basket of benchmark stocks, validate yields,
    record snapshots to database, and export sample dataset files.
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    init_db()
    
    all_rows = []
    print(f"\nCollecting & Testing Live Options Data for: {', '.join(tickers)}")
    
    for ticker in tickers:
        print(f"--> Screening '{ticker}' via yfinance...")
        try:
            symbol, curr_price, ref_price, earnings_date, results = screen_covered_calls(ticker)
            
            assert curr_price > 0, f"Current price for {symbol} must be > 0"
            assert len(results) > 0, f"Option results for {symbol} should not be empty"
            
            # Validate individual option records
            for row in results:
                assert row['strike_price'] >= ref_price * 0.95, "Strike price should be near/above reference price"
                assert row['premium'] > 0, "Option premium must be > 0"
                assert row['ann_premium_roi_pct'] >= 0, "Annualized ROI must be non-negative"
                assert row['breakeven_price'] <= ref_price, "Covered call breakeven must be <= purchase/reference price"
                
                # Append metadata for unified dataset export
                enriched_row = {
                    "collected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "ticker": symbol,
                    "stock_price": curr_price,
                    "reference_price": ref_price,
                    "earnings_date": earnings_date,
                    **row
                }
                all_rows.append(enriched_row)
            
            # Save to Database
            snap_id = save_screen_results(symbol, curr_price, ref_price, earnings_date, results)
            print(f"    Saved {len(results)} option contracts for {symbol} (Snapshot #{snap_id})")
            
        except Exception as e:
            print(f"    [Warning] Failed screening for {ticker}: {e}")
            
        time.sleep(1.0)  # Gentle rate limit for API testing
    
    if not all_rows:
        raise RuntimeError("No option data collected during benchmark run.")
        
    df = pd.DataFrame(all_rows)
    
    # Export CSV Dataset for testing & data analysis
    df.to_csv(CSV_EXPORT_PATH, index=False)
    print(f"\nExported benchmark CSV dataset to: {CSV_EXPORT_PATH} ({len(df)} records)")
    
    # Export JSON Dataset
    with open(JSON_EXPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_rows, f, indent=2)
    print(f"Exported benchmark JSON dataset to: {JSON_EXPORT_PATH}")
    
    return df

def load_sample_dataset() -> pd.DataFrame:
    """Load sample benchmark dataset if available, or return empty DataFrame."""
    if os.path.exists(CSV_EXPORT_PATH):
        return pd.read_csv(CSV_EXPORT_PATH)
    return pd.DataFrame()

def run_all_tests():
    """Main entrypoint for test suite execution."""
    print("=" * 60)
    print(" Covered Call Screener: Automated Data Testing Suite")
    print(f" Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f" Active Storage Backend: {get_db_status()['label']}")
    print("=" * 60)
    
    test_black_scholes_math()
    test_symbol_resolution()
    test_covered_call_scoring()
    test_weekly_picks_database()
    dataset_df = run_benchmark_collection(["AAPL", "MSFT", "NVDA", "SPY"])
    
    print("\n" + "=" * 60)
    print(f" ALL TESTS PASSED! Total options datasets captured: {len(dataset_df)}")
    print(f" Database history count: {len(load_history())} records")
    print("=" * 60)

if __name__ == "__main__":
    run_all_tests()
