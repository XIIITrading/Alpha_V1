# polygon/validators/__init__.py - Public API for validation functions
"""
Validation module for the Polygon data integration.
Provides comprehensive data quality checks and anomaly detection.
"""

# Import all public functions from submodules
from .data_quality import DataQualityReport, generate_validation_summary
from .symbol import validate_symbol_detailed
from .ohlcv import validate_ohlcv_integrity, validate_data_continuity
from .gaps import detect_gaps
from .anomalies import detect_price_anomalies, validate_volume_profile
from .market_hours import validate_market_hours_data

# Public API exports - maintains backward compatibility
__all__ = [
    # Core classes
    'DataQualityReport',
    
    # Validation functions
    'validate_symbol_detailed',
    'validate_ohlcv_integrity',
    'detect_gaps',
    'detect_price_anomalies',
    'validate_data_continuity',
    'validate_volume_profile',
    'validate_market_hours_data',
    'generate_validation_summary'
]