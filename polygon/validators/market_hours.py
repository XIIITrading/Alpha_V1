# polygon/validators/market_hours.py - Market hours validation
"""
Market hours validation for intraday data in the Polygon module.
Validates that data falls within expected trading sessions.
"""

import pandas as pd
from datetime import time as dt_time
from typing import Dict, Any

from ..config import get_config
from .data_quality import DataQualityReport


def validate_market_hours_data(df: pd.DataFrame, strict: bool = True) -> DataQualityReport:
    """
    [FUNCTION SUMMARY]
    Purpose: Validate that intraday data falls within market hours
    Parameters:
        - df (DataFrame): Intraday OHLCV data
        - strict (bool): If True, flag extended hours data as issues
    Returns: DataQualityReport - Market hours validation report
    Example: report = validate_market_hours_data(df, strict=False)
    """
    report = DataQualityReport()
    config = get_config()
    
    if df.empty:
        report.add_issue("No data to validate")
        return report
    
    # Count bars by market session
    pre_market_count = 0
    regular_hours_count = 0
    after_hours_count = 0
    weekend_count = 0
    overnight_count = 0
    
    for timestamp in df.index:
        # Check weekend
        if timestamp.weekday() >= 5:
            weekend_count += 1
            continue
        
        # Get time component
        time_only = timestamp.time()
        
        # Categorize by session
        if time_only < config.market_hours['pre_market_start']:
            overnight_count += 1
        elif time_only < config.market_hours['regular_start']:
            pre_market_count += 1
        elif time_only <= config.market_hours['regular_end']:
            regular_hours_count += 1
        elif time_only <= config.market_hours['post_market_end']:
            after_hours_count += 1
        else:
            overnight_count += 1
    
    # Calculate percentages
    total_bars = len(df)
    regular_pct = (regular_hours_count / total_bars) * 100
    extended_pct = ((pre_market_count + after_hours_count) / total_bars) * 100
    off_hours_pct = ((weekend_count + overnight_count) / total_bars) * 100
    
    # Add metrics
    report.add_metric('total_bars', total_bars)
    report.add_metric('regular_hours_bars', regular_hours_count)
    report.add_metric('pre_market_bars', pre_market_count)
    report.add_metric('after_hours_bars', after_hours_count)
    report.add_metric('weekend_bars', weekend_count)
    report.add_metric('overnight_bars', overnight_count)
    report.add_metric('regular_hours_pct', regular_pct)
    report.add_metric('extended_hours_pct', extended_pct)
    report.add_metric('off_hours_pct', off_hours_pct)
    
    # Validation checks
    if weekend_count > 0:
        issue_msg = f"Data contains {weekend_count} weekend bars"
        report.add_issue(issue_msg, critical=strict)
    
    if overnight_count > 0:
        issue_msg = f"Data contains {overnight_count} overnight bars"
        report.add_issue(issue_msg, critical=strict)
    
    if strict and (pre_market_count > 0 or after_hours_count > 0):
        report.add_issue(
            f"Data contains {pre_market_count + after_hours_count} extended hours bars",
            critical=False
        )
    
    # Suggestions
    if regular_pct < 50:
        report.suggestions.append(
            "Majority of data is outside regular trading hours. "
            "Consider filtering to regular hours only for analysis."
        )
    
    if off_hours_pct > 10:
        report.suggestions.append(
            "Significant off-hours data detected. "
            "Verify data source and consider filtering."
        )
    
    return report