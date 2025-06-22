# polygon/validators/data_quality.py - Core validation infrastructure
"""
Data quality validation framework for the Polygon module.
Provides the DataQualityReport class and orchestration of all validators.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any

from ..config import get_config, POLYGON_TIMEZONE
from ..exceptions import PolygonDataError, PolygonSymbolError
from ..utils import parse_date, parse_timeframe, timestamp_to_datetime


class DataQualityReport:
    """
    [CLASS SUMMARY]
    Purpose: Container for data quality validation results
    Attributes:
        - is_valid: Overall validity status
        - issues: List of identified issues
        - warnings: List of warnings (non-critical)
        - metrics: Dictionary of quality metrics
        - suggestions: Recommendations for data improvement
    """
    
    def __init__(self):
        """Initialize empty quality report"""
        self.is_valid = True
        self.issues: List[str] = []
        self.warnings: List[str] = []
        self.metrics: Dict[str, Any] = {}
        self.suggestions: List[str] = []
        
    def add_issue(self, issue: str, critical: bool = True):
        """
        Add an issue to the report
        
        Parameters:
            - issue (str): Description of the issue
            - critical (bool): If True, marks report as invalid
        """
        if critical:
            self.issues.append(issue)
            self.is_valid = False
        else:
            self.warnings.append(issue)
            
    def add_metric(self, name: str, value: Any):
        """
        Add a quality metric
        
        Parameters:
            - name (str): Metric name
            - value (Any): Metric value
        """
        self.metrics[name] = value
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert report to dictionary"""
        return {
            'is_valid': self.is_valid,
            'issues': self.issues,
            'warnings': self.warnings,
            'metrics': self.metrics,
            'suggestions': self.suggestions,
            'issue_count': len(self.issues),
            'warning_count': len(self.warnings)
        }


def generate_validation_summary(df: pd.DataFrame, symbol: str,
                               expected_timeframe: str,
                               start_date: Optional[datetime] = None,
                               end_date: Optional[datetime] = None) -> Dict[str, Any]:
    """
    [FUNCTION SUMMARY]
    Purpose: Generate comprehensive validation summary for dataset
    Parameters:
        - df (DataFrame): OHLCV data to validate
        - symbol (str): Symbol being validated
        - expected_timeframe (str): Expected timeframe
        - start_date (datetime, optional): Expected start
        - end_date (datetime, optional): Expected end
    Returns: dict - Complete validation summary
    Example: summary = generate_validation_summary(df, 'AAPL', '5min', start, end)
    """
    # Import other validators here to avoid circular imports
    from .symbol import validate_symbol_detailed
    from .ohlcv import validate_ohlcv_integrity, validate_data_continuity
    from .gaps import detect_gaps
    from .anomalies import detect_price_anomalies, validate_volume_profile
    from .market_hours import validate_market_hours_data
    
    summary = {
        'symbol': symbol,
        'timeframe': expected_timeframe,
        'validation_timestamp': datetime.now(POLYGON_TIMEZONE).isoformat(),
        'overall_quality': 'UNKNOWN',
        'reports': {}
    }
    
    # 1. Basic integrity check
    integrity_report = validate_ohlcv_integrity(df, symbol, expected_timeframe)
    summary['reports']['integrity'] = integrity_report.to_dict()
    
    # 2. Gap detection
    if not df.empty:
        gaps = detect_gaps(df, expected_timeframe)
        summary['reports']['gaps'] = gaps
    
    # 3. Anomaly detection
    if not df.empty:
        anomalies = detect_price_anomalies(df)
        summary['reports']['anomalies'] = anomalies
    
    # 4. Volume profile
    volume_profile = validate_volume_profile(df)
    summary['reports']['volume'] = volume_profile
    
    # 5. Market hours validation (for intraday)
    multiplier, timespan = parse_timeframe(expected_timeframe)
    if timespan in ['second', 'minute', 'hour']:
        market_hours_report = validate_market_hours_data(df, strict=False)
        summary['reports']['market_hours'] = market_hours_report.to_dict()
    
    # 6. Continuity check (if dates provided)
    if start_date and end_date and not df.empty:
        continuity = validate_data_continuity(df, symbol, start_date, end_date, expected_timeframe)
        summary['reports']['continuity'] = continuity
    
    # Calculate overall quality score
    quality_score = 100
    quality_factors = []
    
    # Deduct points for issues
    if not integrity_report.is_valid:
        quality_score -= 30
        quality_factors.append("Failed integrity checks")
    
    if 'gaps' in summary['reports'] and summary['reports']['gaps']['gap_count'] > 10:
        quality_score -= 15
        quality_factors.append("Significant data gaps")
    
    if 'anomalies' in summary['reports']:
        anomaly_rate = summary['reports']['anomalies']['summary']['anomaly_rate_pct']
        if anomaly_rate > 5:
            quality_score -= 10
            quality_factors.append("High anomaly rate")
    
    if 'volume' in summary['reports'] and summary['reports']['volume'].get('zero_volume_pct', 0) > 20:
        quality_score -= 10
        quality_factors.append("Excessive zero-volume bars")
    
    # Determine quality rating
    if quality_score >= 90:
        summary['overall_quality'] = 'EXCELLENT'
    elif quality_score >= 75:
        summary['overall_quality'] = 'GOOD'
    elif quality_score >= 60:
        summary['overall_quality'] = 'FAIR'
    else:
        summary['overall_quality'] = 'POOR'
    
    summary['quality_score'] = quality_score
    summary['quality_factors'] = quality_factors
    
    # Add recommendations
    recommendations = []
    if quality_score < 75:
        recommendations.append("Consider additional data cleaning before analysis")
    if 'gaps' in summary['reports'] and summary['reports']['gaps']['gap_count'] > 0:
        recommendations.append("Fill or interpolate data gaps if appropriate for your use case")
    if integrity_report.warnings:
        recommendations.append("Review warnings and address if necessary")
    
    summary['recommendations'] = recommendations
    
    return summary