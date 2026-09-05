import pytest
from datetime import datetime, date, timedelta
from screener import (
    TMC_TAXONOMY,
    get_tmc_subsector_for_ticker,
    evaluate_earnings_risk,
    calculate_covered_call_score,
    resolve_to_symbol,
    calculate_option_greeks_and_probabilities
)

def test_tmc_subsector_mapping():
    assert get_tmc_subsector_for_ticker("NVDA") == "Semiconductors & AI Hardware"
    assert get_tmc_subsector_for_ticker("TSM") == "Semiconductors & AI Hardware"
    assert get_tmc_subsector_for_ticker("MSFT") == "Enterprise SaaS & Cloud Infrastructure"
    assert get_tmc_subsector_for_ticker("CRM") == "Enterprise SaaS & Cloud Infrastructure"
    assert get_tmc_subsector_for_ticker("GOOGL") == "Digital Media, Streaming & Ad-Tech"
    assert get_tmc_subsector_for_ticker("META") == "Digital Media, Streaming & Ad-Tech"
    assert get_tmc_subsector_for_ticker("TMUS") == "Telecom & Digital Infrastructure"
    assert get_tmc_subsector_for_ticker("QQQ") == "Tech & Sector Benchmarks"
    assert get_tmc_subsector_for_ticker("UNKNOWN_TICKER") == "General Tech / S&P 500"

def test_resolve_to_symbol_extended():
    assert resolve_to_symbol("taiwan semi") == "TSM"
    assert resolve_to_symbol("salesforce") == "CRM"
    assert resolve_to_symbol("servicenow") == "NOW"
    assert resolve_to_symbol("crowdstrike") == "CRWD"
    assert resolve_to_symbol("t-mobile") == "TMUS"

def test_evaluate_earnings_risk_inside_expiry():
    today = date.today()
    # Earnings in 20 days, contract expires in 60 days
    e_date_str = (today + timedelta(days=20)).strftime("%Y-%m-%d")
    risk = evaluate_earnings_risk(e_date_str, dte=60)
    
    assert risk["has_earnings"] is True
    assert risk["inside_expiry"] is True
    assert risk["days_to_earnings"] == 20
    assert "🔥" in risk["badge"]
    assert risk["severity"] == "warning"

def test_evaluate_earnings_risk_safe_window():
    today = date.today()
    # Earnings in 80 days, contract expires in 45 days
    e_date_str = (today + timedelta(days=80)).strftime("%Y-%m-%d")
    risk = evaluate_earnings_risk(e_date_str, dte=45)
    
    assert risk["has_earnings"] is True
    assert risk["inside_expiry"] is False
    assert risk["days_to_earnings"] == 80
    assert "✅" in risk["badge"]
    assert risk["severity"] == "success"

def test_evaluate_earnings_risk_past_earnings():
    today = date.today()
    # Earnings was 10 days ago
    e_date_str = (today - timedelta(days=10)).strftime("%Y-%m-%d")
    risk = evaluate_earnings_risk(e_date_str, dte=60)
    
    assert risk["inside_expiry"] is False
    assert "Past" in risk["badge"]
    assert risk["severity"] == "success"

def test_evaluate_earnings_risk_missing_date():
    risk = evaluate_earnings_risk("N/A", dte=60)
    assert risk["inside_expiry"] is False
    assert risk["days_to_earnings"] is None
    assert "No Confirmed" in risk["badge"]

def test_calculate_covered_call_score_with_earnings_penalty():
    today = date.today()
    # Base score without earnings (20% Ann ROI, 4% cushion, 25% Prob ITM)
    score_safe = calculate_covered_call_score(
        ann_max_roi_pct=20.0,
        cushion_pct=4.0,
        prob_itm_pct=25.0,
        dte=60,
        earnings_date="N/A"
    )
    
    # Score with earnings inside 60-day expiry
    e_date_inside = (today + timedelta(days=25)).strftime("%Y-%m-%d")
    score_with_earnings = calculate_covered_call_score(
        ann_max_roi_pct=20.0,
        cushion_pct=4.0,
        prob_itm_pct=25.0,
        dte=60,
        earnings_date=e_date_inside
    )
    
    # Score should be exactly 15.0 points lower due to binary risk penalty
    assert round(score_safe - score_with_earnings, 1) == 15.0

if __name__ == "__main__":
    test_tmc_subsector_mapping()
    test_resolve_to_symbol_extended()
    test_evaluate_earnings_risk_inside_expiry()
    test_evaluate_earnings_risk_safe_window()
    test_evaluate_earnings_risk_past_earnings()
    test_evaluate_earnings_risk_missing_date()
    test_calculate_covered_call_score_with_earnings_penalty()
    print("All TMC & Earnings Risk Pipeline tests passed successfully!")
