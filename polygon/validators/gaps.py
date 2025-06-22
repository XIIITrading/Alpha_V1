# polygon/validators/gaps.py - Gap detection functionality
"""
Gap detection and analysis for time series data in the Polygon module.
Identifies missing data points and market closure gaps.
"""

import pandas as pd
from datetime import datetime, time as dt_time
from typing import Dict, Any

from ..config import get_config
from ..utils import parse_timeframe


def detect_gaps(df: pd.DataFrame, timeframe: str, 
                market_hours_only: bool = True) -> Dict[str, Any]:
    """
    [FUNCTION SUMMARY]
    Purpose: Detect missing data gaps in time series
    Parameters:
        - df (DataFrame): OHLCV data with datetime index
        - timeframe (str): Data timeframe (e.g., '5min')
        - market_hours_only (bool): Only check during market hours
    Returns: dict - Gap analysis results
    Example: gaps = detect_gaps(df, '5min')
    """
    if df.empty or len(df) < 2:
        return {'gaps': [], 'gap_count': 0, 'total_missing_bars': 0}
    
    # Parse timeframe
    multiplier, timespan = parse_timeframe(timeframe)
    
    # Get expected frequency
    freq_mapping = {
        'second': f'{multiplier}S',
        'minute': f'{multiplier}min',
        'hour': f'{multiplier}H',
        'day': f'{multiplier}D'
    }
    
    if timespan not in freq_mapping:
        return {'error': f"Gap detection not supported for timespan: {timespan}"}
    
    freq = freq_mapping[timespan]
    
    # Sort index
    df_sorted = df.sort_index()
    
    gaps = []
    config = get_config()
    
    # Check each consecutive pair
    for i in range(len(df_sorted) - 1):
        current_time = df_sorted.index[i]
        next_time = df_sorted.index[i + 1]
        
        # Calculate expected next time
        expected_next = current_time + pd.Timedelta(freq)
        
        # If there's a gap
        if next_time > expected_next:
            # For intraday data, check if gap spans non-market hours
            if market_hours_only and timespan in ['second', 'minute', 'hour']:
                # Check if gap is just market closure
                if is_market_closure_gap(current_time, next_time, config):
                    continue
            
            # Calculate gap size
            gap_duration = next_time - current_time
            expected_duration = pd.Timedelta(freq)
            missing_bars = int(gap_duration / expected_duration) - 1
            
            if missing_bars > 0:
                gaps.append({
                    'start': current_time,
                    'end': next_time,
                    'duration': str(gap_duration),
                    'missing_bars': missing_bars
                })
    
    # Summary statistics
    total_missing = sum(gap['missing_bars'] for gap in gaps)
    
    return {
        'gaps': gaps,
        'gap_count': len(gaps),
        'total_missing_bars': total_missing,
        'data_completeness_pct': (len(df) / (len(df) + total_missing)) * 100 if total_missing > 0 else 100,
        'largest_gap': max(gaps, key=lambda x: x['missing_bars']) if gaps else None
    }


def is_market_closure_gap(time1: datetime, time2: datetime, config) -> bool:
    """
    [FUNCTION SUMMARY]
    Purpose: Check if a time gap is due to market closure
    Parameters:
        - time1 (datetime): Earlier time
        - time2 (datetime): Later time
        - config: Configuration object
    Returns: bool - True if gap is expected market closure
    """
    # If gap spans different days
    if time1.date() != time2.date():
        # Check if it's weekend
        if time1.weekday() == 4 and time2.weekday() == 0:  # Friday to Monday
            return True
        # Check if next day is weekend
        if time1.weekday() >= 5 or time2.weekday() >= 5:
            return True
    
    # Check if gap is around market close/open times
    time1_time = time1.time()
    time2_time = time2.time()
    
    # If first time is after market close and second is pre-market or regular hours
    if (time1_time >= config.market_hours['regular_end'] and 
        time2_time >= config.market_hours['pre_market_start']):
        return True
    
    return False