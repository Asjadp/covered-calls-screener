# -*- coding: utf-8 -*-
import pytest
import math
from screener import (
    fetch_fundamental_metrics,
    calculate_earnings_implied_move,
    generate_pitch_tear_sheet,
    screen_covered_calls,
    resolve_to_symbol
)

def test_earnings_implied_move_protected():
    """Verify when downside cushion exceeds market-implied 1-day earnings move."""
    stock_price = 100.0
    iv_pct = 35.0
    cushion_pct = 4.5
    
    res = calculate_earnings_implied_move(stock_price, iv_pct, cushion_pct=cushion_pct, days_to_earnings=15)
    
    expected_pct = round(35.0 * math.sqrt(1.0 / 365.0), 2)
    assert res["expected_move_pct"] == expected_pct
    assert res["expected_move_dollar"] == round(stock_price * (expected_pct / 100.0), 2)
    assert res["cushion_coverage_ratio"] is not None
    assert res["cushion_coverage_ratio"] >= 1.0
    assert res["status"] == "PROTECTED"
    assert "Protected" in res["badge"]

def test_earnings_implied_move_exposed_tail_risk():
    """Verify when implied move exceeds downside cushion (tail risk)."""
    stock_price = 200.0
    iv_pct = 80.0
    cushion_pct = 2.0
    
    res = calculate_earnings_implied_move(stock_price, iv_pct, cushion_pct=cushion_pct, days_to_earnings=5)
    
    assert res["expected_move_pct"] > 4.0
    assert res["cushion_coverage_ratio"] < 0.70
    assert res["status"] == "EXPOSED"
    assert "Tail Risk" in res["badge"]

def test_earnings_implied_move_edge_cases():
    """Test defensive handling for 0 or None inputs."""
    res_none = calculate_earnings_implied_move(0.0, None)
    assert res_none["status"] == "UNKNOWN"
    assert res_none["expected_move_pct"] is None
    
    res_zero_iv = calculate_earnings_implied_move(100.0, 0.0)
    assert res_zero_iv["status"] == "UNKNOWN"

def test_pitch_tear_sheet_content():
    """Verify 1-page investment pitch tear sheet contains all institutional sections."""
    symbol = "MSFT"
    stock_price = 450.0
    ref_price = 440.0
    
    fundamentals = {
        "symbol": "MSFT",
        "company_name": "Microsoft Corporation",
        "business_summary": "Global technology and cloud infrastructure company.",
        "forward_pe": 28.5,
        "trailing_pe": 32.1,
        "ev_ebitda": 22.4,
        "ev_sales": 12.8,
        "revenue_growth_pct": 16.5,
        "gross_margin_pct": 69.5,
        "operating_margin_pct": 44.2,
        "fcf_margin_pct": 33.0,
        "fcf_yield_pct": 3.2,
        "rule_of_40_val": 49.5,
        "rule_of_40_badge": "Elite SaaS Health (49.5% >= 40%)",
        "rule_of_40_pass": True,
        "target_mean_price": 500.0,
        "target_high_price": 550.0,
        "target_low_price": 420.0,
        "analyst_count": 48,
        "recommendation": "Strong Buy"
    }
    
    option_row = {
        "term": "2-Month (~60d)",
        "expiration_date": "2026-11-20",
        "dte": 60,
        "target_type": "5% OTM",
        "strike_price": 472.50,
        "premium": 15.20,
        "premium_roi_pct": 3.38,
        "ann_premium_roi_pct": 20.55,
        "max_roi_pct": 8.38,
        "ann_max_roi_pct": 50.97,
        "cushion_pct": 3.38,
        "breakeven_price": 434.80,
        "implied_volatility_pct": 26.5,
        "delta": 0.32,
        "prob_itm_pct": 24.5,
        "prob_touch_pct": 49.0,
        "score": 86.5,
        "earnings_badge": "Safe Window (75d away)",
        "days_to_earnings": 75
    }
    
    sheet_md = generate_pitch_tear_sheet(
        symbol=symbol,
        stock_price=stock_price,
        fundamentals=fundamentals,
        option_row=option_row,
        subsector="Enterprise SaaS & Cloud Infrastructure",
        ref_price=ref_price
    )
    
    assert "INSTITUTIONAL EQUITY RESEARCH" in sheet_md
    assert "MSFT" in sheet_md
    assert "Microsoft Corporation" in sheet_md
    assert "Executive Summary & Overlay Thesis" in sheet_md
    assert "Valuation Multiples & Fundamental Health Scorecard" in sheet_md
    assert "Covered Call Structure & Yield Profile" in sheet_md
    assert "Margin of Safety vs. Wall Street Consensus" in sheet_md
    assert "Binary Earnings Catalyst & Volatility Risk" in sheet_md
    assert "Downside Scenario Analysis & Trade Execution Framework" in sheet_md
    assert "$472.50" in sheet_md
    assert "49.5%" in sheet_md
    assert "$500.00" in sheet_md
    assert "Strong Buy" in sheet_md

def test_fetch_fundamental_metrics_mock():
    """Verify fetch_fundamental_metrics structure and fields."""
    metrics = fetch_fundamental_metrics("AAPL")
    assert isinstance(metrics, dict)
    assert metrics["symbol"] == "AAPL"
    assert "forward_pe" in metrics
    assert "trailing_pe" in metrics
    assert "ev_ebitda" in metrics
    assert "rule_of_40_badge" in metrics
    assert "target_mean_price" in metrics
    assert "recommendation" in metrics

if __name__ == "__main__":
    test_earnings_implied_move_protected()
    test_earnings_implied_move_exposed_tail_risk()
    test_earnings_implied_move_edge_cases()
    test_pitch_tear_sheet_content()
    test_fetch_fundamental_metrics_mock()
    print("All fundamental, implied move, and tear sheet unit tests passed successfully!")
