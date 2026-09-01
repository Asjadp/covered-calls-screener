"""
Weekly Batch Scanner: Top 50 S&P 500 (SPY) Covered Call Ideas Engine
---------------------------------------------------------------------
Scans Top 50 SPY constituents after-market hours, applies quantitative
scoring (Annualized ROI, Downside Cushion, Black-Scholes Probability),
deduplicates per company, and publishes Top 5 / Top 10 lists for +5% OTM
and +10% OTM strike targets with exact generation timestamps.
"""

import os
import sys
import json
import time
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional, Callable

# Ensure UTF-8 console output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from screener import screen_covered_calls, calculate_covered_call_score
from database import init_db, save_weekly_top_picks, get_latest_weekly_top_picks, get_db_status

# Top 50 S&P 500 (SPY) Constituents by Market Cap & Liquidity
TOP_50_SPY = [
    "AAPL", "NVDA", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "BRK-B", "AVGO", "LLY",
    "JPM", "V", "UNH", "XOM", "MA", "COST", "HD", "PG", "NFLX", "JNJ",
    "ABBV", "BAC", "CRM", "WMT", "CVX", "MRK", "KO", "AMD", "QCOM", "PEP",
    "LIN", "TMO", "DIS", "ACN", "CSCO", "MCD", "ABT", "GE", "INTU", "IBM",
    "TXN", "PM", "AMAT", "NOW", "CAT", "VZ", "MS", "GS", "BKNG", "SPY"
]

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
WEEKLY_CSV_PATH = os.path.join(DATA_DIR, "weekly_top_picks.csv")
WEEKLY_JSON_PATH = os.path.join(DATA_DIR, "weekly_top_picks.json")

def run_weekly_scan(
    tickers: Optional[List[str]] = None,
    delay_seconds: float = 1.5,
    top_n: int = 10,
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Execute batch screening across universe, scoring and extracting non-duplicate
    Top N covered call contracts for both +5% OTM and +10% OTM target groups.
    """
    if tickers is None:
        tickers = TOP_50_SPY

    os.makedirs(DATA_DIR, exist_ok=True)
    init_db()

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    batch_id = f"weekly-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    print("=" * 65)
    print(f" Weekly Covered Call Screener: SPY Top 50 Scanner")
    print(f" Batch ID: {batch_id} | Timestamp: {timestamp}")
    print(f" Universe Size: {len(tickers)} tickers | Delay: {delay_seconds}s per ticker")
    print("=" * 65)

    candidates_5pct: List[Dict[str, Any]] = []
    candidates_10pct: List[Dict[str, Any]] = []

    total = len(tickers)
    for idx, ticker in enumerate(tickers, start=1):
        if progress_callback:
            progress_callback(idx, total, ticker)
        
        print(f"[{idx}/{total}] Screening {ticker}...", end=" ", flush=True)
        try:
            ticker_scan_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            symbol, curr_price, ref_price, earnings_date, results = screen_covered_calls(ticker)
            if not results:
                print("No option contracts found.")
                continue

            # Separate contracts by target type
            opts_5 = [r for r in results if r.get('target_type') == '5% OTM']
            opts_10 = [r for r in results if r.get('target_type') == '10% OTM']

            # Deduplication: Pick the single highest scoring contract for each category per company
            if opts_5:
                best_5 = max(opts_5, key=lambda x: x.get('score', 0.0))
                candidates_5pct.append({
                    "ticker": symbol,
                    "stock_price": curr_price,
                    "earnings_date": earnings_date,
                    "generated_at": ticker_scan_time,
                    **best_5
                })

            if opts_10:
                best_10 = max(opts_10, key=lambda x: x.get('score', 0.0))
                candidates_10pct.append({
                    "ticker": symbol,
                    "stock_price": curr_price,
                    "earnings_date": earnings_date,
                    "generated_at": ticker_scan_time,
                    **best_10
                })

            print(f"Success ({len(results)} contracts).")
        except Exception as e:
            print(f"Error: {e}")

        if idx < total and delay_seconds > 0:
            time.sleep(delay_seconds)

    # Sort each category by Score descending
    candidates_5pct.sort(key=lambda x: x.get('score', 0.0), reverse=True)
    candidates_10pct.sort(key=lambda x: x.get('score', 0.0), reverse=True)

    top_5pct = candidates_5pct[:top_n]
    top_10pct = candidates_10pct[:top_n]

    # Save to Database
    save_weekly_top_picks(batch_id, top_5pct, top_10pct, timestamp=timestamp)

    # Export CSV & JSON
    export_rows = []
    for rank, item in enumerate(top_5pct, start=1):
        export_rows.append({"list": "+5% OTM", "rank": rank, **item})
    for rank, item in enumerate(top_10pct, start=1):
        export_rows.append({"list": "+10% OTM", "rank": rank, **item})

    if export_rows:
        df_export = pd.DataFrame(export_rows)
        df_export.to_csv(WEEKLY_CSV_PATH, index=False)
        with open(WEEKLY_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(export_rows, f, indent=2)

    print("\n" + "=" * 65)
    print(f" SCAN COMPLETE: {len(top_5pct)} (+5% OTM) & {len(top_10pct)} (+10% OTM) ideas saved.")
    print(f" Exported to: {WEEKLY_CSV_PATH}")
    print("=" * 65)

    return top_5pct, top_10pct

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Covered Call Weekly Top Ideas Scanner")
    parser.add_argument("--test", action="store_true", help="Run fast test scan with 10 benchmark tickers")
    parser.add_argument("--delay", type=float, default=1.5, help="Delay between API requests in seconds")
    parser.add_argument("--top", type=int, default=10, help="Number of top ideas to output per list")
    args = parser.parse_args()

    test_basket = ["AAPL", "MSFT", "NVDA", "AMZN", "META", "TSLA", "GOOGL", "SPY", "JPM", "AMD"] if args.test else None
    run_weekly_scan(tickers=test_basket, delay_seconds=args.delay, top_n=args.top)
