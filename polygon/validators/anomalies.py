# polygon/validators/anomalies.py - Anomaly detection functionality
"""
Statistical anomaly detection and volume profile analysis for the Polygon module.
Identifies outliers, extreme changes, and volume irregularities.
"""

import numpy as np
import pandas as pd
from typing import Dict, Any

from ..config import get_config, POLYGON_TIMEZONE
from ..exceptions import PolygonDataError


def detect_price_anomalies(df: pd.DataFrame, 
                          zscore_threshold: float = 3.0,
                          pct_change_threshold: float = 0.2) -> Dict[str, Any]:
    """
    [FUNCTION SUMMARY]
    Purpose: Detect price anomalies using statistical methods
    Parameters:
        - df (DataFrame): OHLCV data
        - zscore_threshold (float): Z-score threshold for outliers
        - pct_change_threshold (float): Percentage change threshold (0.2 = 20%)
    Returns: dict - Detected anomalies and statistics
    Example: anomalies = detect_price_anomalies(df, zscore_threshold=3.0)
    """
    anomalies = {
        'extreme_changes': [],
        'statistical_outliers': [],
        'volume_spikes': [],
        'spread_anomalies': []
    }
    
    if df.empty or len(df) < 10:  # Need minimum data for statistics
        return anomalies
    
    # 1. Detect extreme price changes
    close_pct_change = df['close'].pct_change(fill_method=None).abs()
    extreme_mask = close_pct_change > pct_change_threshold
    
    if extreme_mask.any():
        extreme_indices = df.index[extreme_mask].tolist()
        for idx in extreme_indices:
            loc = df.index.get_loc(idx)
            if loc > 0:
                anomalies['extreme_changes'].append({
                    'timestamp': idx,
                    'pct_change': close_pct_change.iloc[loc] * 100,
                    'close': df['close'].iloc[loc],
                    'prev_close': df['close'].iloc[loc - 1]
                })
    
    # 2. Statistical outliers using z-score
    close_mean = df['close'].mean()
    close_std = df['close'].std()
    
    if close_std > 0:
        z_scores = np.abs((df['close'] - close_mean) / close_std)
        outlier_mask = z_scores > zscore_threshold
        
        if outlier_mask.any():
            outlier_indices = df.index[outlier_mask].tolist()
            for idx in outlier_indices:
                loc = df.index.get_loc(idx)
                anomalies['statistical_outliers'].append({
                    'timestamp': idx,
                    'close': df['close'].iloc[loc],
                    'z_score': z_scores.iloc[loc],
                    'deviation_from_mean': df['close'].iloc[loc] - close_mean
                })
    
    # 3. Volume spikes
    if 'volume' in df.columns:
        volume_mean = df['volume'].mean()
        volume_std = df['volume'].std()
        
        if volume_std > 0 and volume_mean > 0:
            # Volume spikes: more than 3 standard deviations above mean
            volume_z_scores = (df['volume'] - volume_mean) / volume_std
            volume_spike_mask = volume_z_scores > 3
            
            if volume_spike_mask.any():
                spike_indices = df.index[volume_spike_mask].tolist()
                for idx in spike_indices:
                    loc = df.index.get_loc(idx)
                    anomalies['volume_spikes'].append({
                        'timestamp': idx,
                        'volume': df['volume'].iloc[loc],
                        'volume_z_score': volume_z_scores.iloc[loc],
                        'volume_vs_avg': df['volume'].iloc[loc] / volume_mean
                    })
    
    # 4. Abnormal spreads (high-low)
    df['spread_pct'] = ((df['high'] - df['low']) / df['close']) * 100
    spread_mean = df['spread_pct'].mean()
    spread_std = df['spread_pct'].std()
    
    if spread_std > 0:
        spread_z_scores = (df['spread_pct'] - spread_mean) / spread_std
        spread_anomaly_mask = spread_z_scores > 3
        
        if spread_anomaly_mask.any():
            spread_indices = df.index[spread_anomaly_mask].tolist()
            for idx in spread_indices:
                loc = df.index.get_loc(idx)
                anomalies['spread_anomalies'].append({
                    'timestamp': idx,
                    'spread_pct': df['spread_pct'].iloc[loc],
                    'high': df['high'].iloc[loc],
                    'low': df['low'].iloc[loc]
                })
    
    # Add summary statistics
    summary = {
        'extreme_change_count': len(anomalies['extreme_changes']),
        'outlier_count': len(anomalies['statistical_outliers']),
        'volume_spike_count': len(anomalies['volume_spikes']),
        'spread_anomaly_count': len(anomalies['spread_anomalies']),
        'total_anomalies': sum(len(v) for v in anomalies.values()),
        'anomaly_rate_pct': (sum(len(v) for v in anomalies.values()) / len(df)) * 100
    }
    
    anomalies['summary'] = summary
    
    return anomalies


def validate_volume_profile(df: pd.DataFrame) -> Dict[str, Any]:
    """
    [FUNCTION SUMMARY]
    Purpose: Validate volume profile and detect irregularities
    Parameters:
        - df (DataFrame): OHLCV data with volume column
    Returns: dict - Volume profile analysis
    Example: profile = validate_volume_profile(df)
    """
    if 'volume' not in df.columns or df.empty:
        return {'error': 'No volume data available'}
    
    volume_data = df['volume'].copy()
    
    # Basic statistics
    profile = {
        'mean_volume': volume_data.mean(),
        'median_volume': volume_data.median(),
        'std_volume': volume_data.std(),
        'min_volume': volume_data.min(),
        'max_volume': volume_data.max(),
        'zero_volume_count': (volume_data == 0).sum(),
        'zero_volume_pct': ((volume_data == 0).sum() / len(volume_data)) * 100
    }
    
    # Volume distribution analysis
    if len(volume_data) > 100:
        # Calculate percentiles
        percentiles = [10, 25, 50, 75, 90, 95, 99]
        profile['percentiles'] = {
            f'p{p}': volume_data.quantile(p/100) for p in percentiles
        }
        
        # Detect unusual distribution
        # Check if volume is heavily skewed
        if profile['mean_volume'] > 0:
            skewness = volume_data.skew()
            profile['skewness'] = skewness
            
            if skewness > 2:
                profile['distribution_warning'] = 'Highly right-skewed volume distribution'
            elif skewness < -2:
                profile['distribution_warning'] = 'Highly left-skewed volume distribution'
    
    # Time-based volume patterns (if enough data)
    if len(df) > 100:
        # Check for day-of-week patterns
        if hasattr(df.index, 'dayofweek'):
            dow_volume = df.groupby(df.index.dayofweek)['volume'].mean()
            profile['day_of_week_pattern'] = dow_volume.to_dict()
        
        # Check for time-of-day patterns (for intraday data)
        if hasattr(df.index, 'time'):
            hourly_volume = df.groupby(df.index.hour)['volume'].mean()
            if len(hourly_volume) > 1:
                profile['hourly_pattern'] = hourly_volume.to_dict()
    
    # Volume consistency check
    if len(volume_data) > 20:
        # Rolling coefficient of variation
        rolling_cv = volume_data.rolling(20).std() / volume_data.rolling(20).mean()
        avg_cv = rolling_cv.mean()
        
        profile['volume_consistency'] = {
            'avg_coefficient_variation': avg_cv,
            'is_consistent': avg_cv < 2.0  # CV < 2 indicates relatively consistent volume
        }
    
    # Anomaly detection
    if profile['std_volume'] > 0:
        z_scores = np.abs((volume_data - profile['mean_volume']) / profile['std_volume'])
        anomaly_count = (z_scores > 3).sum()
        profile['volume_anomalies'] = {
            'count': anomaly_count,
            'percentage': (anomaly_count / len(volume_data)) * 100
        }
    
    return profile