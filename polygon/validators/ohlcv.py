# polygon/validators/ohlcv.py - OHLCV data validation
"""
OHLCV data integrity and continuity validation for the Polygon module.
Provides comprehensive checks for data quality and completeness.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from ..config import get_config, POLYGON_TIMEZONE
from ..exceptions import PolygonDataError
from ..utils import parse_date, parse_timeframe, timestamp_to_datetime
from .data_quality import DataQualityReport


def validate_ohlcv_integrity(df: pd.DataFrame, symbol: Optional[str] = None,
                           expected_timeframe: Optional[str] = None) -> DataQualityReport:
    """
    [FUNCTION SUMMARY]
    Purpose: Comprehensive OHLCV data integrity validation
    Parameters:
        - df (DataFrame): OHLCV data with datetime index
        - symbol (str, optional): Symbol for context
        - expected_timeframe (str, optional): Expected data timeframe
    Returns: DataQualityReport - Detailed validation report
    Example: report = validate_ohlcv_integrity(df, 'AAPL', '5min')
    """
    report = DataQualityReport()
    
    # Check if DataFrame is empty
    if df.empty:
        report.add_issue("DataFrame is empty")
        return report
    
    # Add basic metrics
    report.add_metric('row_count', len(df))
    report.add_metric('date_range', f"{df.index.min()} to {df.index.max()}")
    
    # 1. Check required columns
    required_cols = ['open', 'high', 'low', 'close', 'volume']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        report.add_issue(f"Missing required columns: {missing_cols}")
        return report
    
    # 2. Check for NaN values only in required columns
    nan_counts = df[required_cols].isna().sum()
    if nan_counts.any():
        report.add_issue(f"NaN values found: {nan_counts[nan_counts > 0].to_dict()}")
    
    # 3. Check for negative or zero prices
    price_cols = ['open', 'high', 'low', 'close']
    for col in price_cols:
        negative_count = (df[col] < 0).sum()
        zero_count = (df[col] == 0).sum()
        
        if negative_count > 0:
            report.add_issue(f"Negative values in {col}: {negative_count} rows")
        if zero_count > 0:
            zero_pct = (zero_count / len(df)) * 100
            if zero_pct > 1:  # More than 1% zeros is suspicious
                report.add_issue(f"Zero values in {col}: {zero_count} rows ({zero_pct:.1f}%)")
            else:
                report.add_issue(f"Zero values in {col}: {zero_count} rows", critical=False)
    
    # 4. Validate OHLC relationships
    relationship_issues = {
        'high < low': (df['high'] < df['low']).sum(),
        'open > high': (df['open'] > df['high']).sum(),
        'open < low': (df['open'] < df['low']).sum(),
        'close > high': (df['close'] > df['high']).sum(),
        'close < low': (df['close'] < df['low']).sum(),
    }
    
    for issue, count in relationship_issues.items():
        if count > 0:
            report.add_issue(f"Invalid OHLC relationship ({issue}): {count} rows")
    
    # 5. Check for duplicate timestamps
    duplicate_count = df.index.duplicated().sum()
    if duplicate_count > 0:
        report.add_issue(f"Duplicate timestamps: {duplicate_count}")
    
    # 6. Volume validation
    negative_volume = (df['volume'] < 0).sum()
    if negative_volume > 0:
        report.add_issue(f"Negative volume: {negative_volume} rows")
    
    # Zero volume check (warning only for some bars)
    zero_volume = (df['volume'] == 0).sum()
    zero_volume_pct = (zero_volume / len(df)) * 100
    if zero_volume_pct > 50:
        report.add_issue(f"Excessive zero volume: {zero_volume} rows ({zero_volume_pct:.1f}%)")
    elif zero_volume > 0:
        report.add_issue(f"Zero volume bars: {zero_volume} rows ({zero_volume_pct:.1f}%)", critical=False)
    
    # 7. Statistical anomaly detection (imported from anomalies module)
    from .anomalies import detect_price_anomalies
    anomalies = detect_price_anomalies(df)
    if anomalies['extreme_changes']:
        report.add_issue(
            f"Extreme price changes detected: {len(anomalies['extreme_changes'])} instances",
            critical=False
        )
        report.add_metric('extreme_changes', anomalies['extreme_changes'][:5])  # First 5
    
    # 8. Add quality metrics
    report.add_metric('completeness', 100 - (nan_counts.sum() / (len(df) * len(required_cols)) * 100))
    report.add_metric('zero_volume_pct', zero_volume_pct)
    report.add_metric('avg_volume', df['volume'].mean())
    report.add_metric('price_volatility', df['close'].pct_change(fill_method=None).std() * 100)
    
    # 9. Suggestions
    if zero_volume_pct > 10:
        report.suggestions.append("Consider filtering out zero-volume bars for analysis")
    if report.metrics['price_volatility'] > 10:
        report.suggestions.append("High volatility detected - consider additional outlier filtering")
    
    return report


def validate_data_continuity(df: pd.DataFrame, symbol: str, 
                           start_date: datetime, end_date: datetime,
                           expected_timeframe: str) -> Dict[str, Any]:
    """
    [FUNCTION SUMMARY]
    Purpose: Validate data continuity and completeness for a date range
    Parameters:
        - df (DataFrame): OHLCV data
        - symbol (str): Symbol being validated
        - start_date (datetime): Expected start date
        - end_date (datetime): Expected end date
        - expected_timeframe (str): Expected data timeframe
    Returns: dict - Continuity validation results
    Example: result = validate_data_continuity(df, 'AAPL', start, end, '5min')
    """
    result = {
        'is_continuous': True,
        'coverage_pct': 0,
        'missing_dates': [],
        'issues': []
    }
    
    if df.empty:
        result['is_continuous'] = False
        result['issues'].append("No data available")
        return result
    
    # Ensure dates are UTC
    start_date = parse_date(start_date)
    end_date = parse_date(end_date)
    
    # Check actual vs expected date range
    actual_start = df.index.min()
    actual_end = df.index.max()
    
    # Date range validation
    if actual_start > start_date + timedelta(days=1):
        result['issues'].append(
            f"Data starts late: expected {start_date.date()}, got {actual_start.date()}"
        )
        result['is_continuous'] = False
    
    if actual_end < end_date - timedelta(days=1):
        result['issues'].append(
            f"Data ends early: expected {end_date.date()}, got {actual_end.date()}"
        )
        result['is_continuous'] = False
    
    # Parse timeframe for analysis
    multiplier, timespan = parse_timeframe(expected_timeframe)
    
    # For daily or higher timeframes, check for missing dates
    if timespan in ['day', 'week', 'month']:
        expected_dates = pd.date_range(
            start=max(start_date, actual_start),
            end=min(end_date, actual_end),
            freq='B' if timespan == 'day' else 'W' if timespan == 'week' else 'M'
        )
        
        actual_dates = pd.to_datetime(df.index.date).unique()
        missing_dates = set(expected_dates.date) - set(actual_dates)
        
        if missing_dates:
            result['missing_dates'] = sorted([str(d) for d in missing_dates])
            result['issues'].append(f"Missing {len(missing_dates)} expected dates")
            result['is_continuous'] = False
    
    # Calculate coverage percentage
    config = get_config()
    if timespan in ['minute', 'hour']:
        # For intraday, calculate based on market hours
        market_hours_per_day = 6.5  # Regular trading hours
        trading_days = pd.bdate_range(start_date, end_date)
        expected_market_hours = len(trading_days) * market_hours_per_day
        
        if timespan == 'minute':
            expected_bars = expected_market_hours * 60 / multiplier
        else:  # hour
            expected_bars = expected_market_hours / multiplier
        
        result['coverage_pct'] = min((len(df) / expected_bars) * 100, 100)
    else:
        # For daily+, simple calculation
        days_expected = (end_date - start_date).days
        if timespan == 'day':
            expected_bars = days_expected * 0.71  # ~71% of days are trading days
        else:
            expected_bars = days_expected / (7 if timespan == 'week' else 30)
        
        result['coverage_pct'] = min((len(df) / expected_bars) * 100, 100)
    
    # Gap detection (imported from gaps module)
    from .gaps import detect_gaps
    gaps = detect_gaps(df, expected_timeframe)
    if gaps['gap_count'] > 0:
        result['gaps'] = gaps
        if gaps['gap_count'] > 10:
            result['issues'].append(f"Significant gaps detected: {gaps['gap_count']} gaps")
            result['is_continuous'] = False
    
    # Add metadata
    result['metadata'] = {
        'symbol': symbol,
        'actual_start': str(actual_start),
        'actual_end': str(actual_end),
        'row_count': len(df),
        'expected_timeframe': expected_timeframe
    }
    
    return result