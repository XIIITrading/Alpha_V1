# polygon/config.py - Configuration and constants for the Polygon module
"""
Configuration module for Polygon API integration.
Handles environment variables, API settings, storage paths, and module constants.
"""

import os
import logging
from pathlib import Path
from datetime import time
from typing import Dict, Any, Optional
import json
import pytz
from dotenv import load_dotenv

# Load environment variables from the parent directory's .env file
# This assumes .env is in the project root (one level up from polygon/)
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

# IMPORTANT: Polygon.io returns all timestamps in UTC
# This module maintains all times in UTC to avoid conversion errors
POLYGON_TIMEZONE = pytz.UTC


class PolygonConfig:
    """
    [CLASS SUMMARY]
    Purpose: Centralized configuration management for the Polygon module
    Responsibilities:
        - Load and validate API credentials
        - Define API endpoints and rate limits
        - Configure storage paths and settings
        - Manage market hours and trading calendars
        - Provide module-wide constants
    Usage: 
        config = PolygonConfig()
        api_key = config.api_key
    """
    
    def __init__(self, config_override: Optional[Dict[str, Any]] = None):
        """
        [FUNCTION SUMMARY]
        Purpose: Initialize configuration with environment variables and optional overrides
        Parameters:
            - config_override (dict, optional): Override default settings for testing
        Example: PolygonConfig({'cache_enabled': False}) -> config with caching disabled
        """
        # Load configuration from environment or use overrides
        self.config_override = config_override or {}
        
        # Initialize core settings
        self._load_api_config()
        self._load_storage_config()
        self._load_rate_limit_config()
        self._load_market_config()
        self._setup_logging()
        
    def _load_api_config(self):
        """
        [FUNCTION SUMMARY]
        Purpose: Load API-related configuration including keys and endpoints
        Sets: api_key, base_url, websocket_url, api_version
        Raises: ValueError if API key is not found
        """
        # Get API key from environment with override capability
        self.api_key = self.config_override.get('api_key', os.getenv('POLYGON_API_KEY'))
        
        # Validate API key exists
        if not self.api_key:
            raise ValueError(
                "POLYGON_API_KEY not found. Please set it in your .env file at: "
                f"{env_path.absolute()}"
            )
        
        # API endpoint configuration
        self.base_url = "https://api.polygon.io"
        self.api_version = "v2"
        
        # Specific endpoint URLs
        self.endpoints = {
            'aggregates': f"{self.base_url}/{self.api_version}/aggs/ticker",
            'ticker_details': f"{self.base_url}/v3/reference/tickers",
            'market_status': f"{self.base_url}/v1/marketstatus/now",
            'exchanges': f"{self.base_url}/v3/reference/exchanges",
            'snapshot': f"{self.base_url}/{self.api_version}/snapshot/locale/us/markets/stocks/tickers"
        }
        
        # WebSocket configuration for real-time data
        self.websocket_url = "wss://socket.polygon.io/stocks"
        
        # Request timeout settings
        self.request_timeout = self.config_override.get('request_timeout', 30)  # seconds
        self.max_retries = self.config_override.get('max_retries', 3)
        
    def _load_storage_config(self):
        """
        [FUNCTION SUMMARY]
        Purpose: Configure local storage paths and caching settings
        Sets: data_dir, cache_dir, parquet_dir, cache settings
        Creates: Required directories if they don't exist
        """
        # Base data directory within the polygon module
        self.data_dir = Path(__file__).parent / 'data'
        self.cache_dir = self.data_dir / 'cache'
        self.parquet_dir = self.data_dir / 'parquet'
        
        # Create directories if they don't exist
        self.data_dir.mkdir(exist_ok=True)
        self.cache_dir.mkdir(exist_ok=True)
        self.parquet_dir.mkdir(exist_ok=True)
        
        # Cache configuration
        self.cache_enabled = self.config_override.get('cache_enabled', True)
        self.cache_ttl_minutes = self.config_override.get('cache_ttl_minutes', 15)  # Real-time data cache
        self.historical_cache_days = self.config_override.get('historical_cache_days', 365)  # Keep 1 year
        
        # Storage settings
        self.use_compression = self.config_override.get('use_compression', True)
        self.compression_type = 'snappy'  # Fast compression for parquet files
        
        # Cache database path
        self.cache_db_path = self.cache_dir / 'polygon_cache.db'
        
    def _load_rate_limit_config(self):
        """
        [FUNCTION SUMMARY]
        Purpose: Configure API rate limiting settings based on Polygon.io limits
        Sets: Rate limits for different subscription tiers
        Note: Polygon has different limits for different subscription levels
        """
        # Determine subscription tier (can be overridden for testing)
        self.subscription_tier = self.config_override.get('subscription_tier', 
                                                         os.getenv('POLYGON_SUBSCRIPTION_TIER', 'advanced'))
        
        # Rate limits per tier (requests per minute)
        self.rate_limits = {
            'basic': {
                'requests_per_minute': 5,
                'requests_per_day': 1000,
                'max_symbols_per_request': 1,
                'max_days_per_request': 730  # 2 years worth of days
            },
            'starter': {
                'requests_per_minute': 100,
                'requests_per_day': 50000,
                'max_symbols_per_request': 10,
                'max_days_per_request': 1825  # 5 years worth of days
            },
            'developer': {
                'requests_per_minute': 1000,
                'requests_per_day': 500000,
                'max_symbols_per_request': 100,
                'max_days_per_request': 3650  # 10 years worth of days
            },
            'advanced': {
                'requests_per_minute': 10000,
                'requests_per_day': 999999999,  # Effectively unlimited
                'max_symbols_per_request': 1000,
                'max_days_per_request': 36500  # 100 years worth of days
            }
        }
        
        # Get limits for current tier
        tier_limits = self.rate_limits.get(self.subscription_tier, self.rate_limits['basic'])
        self.requests_per_minute = tier_limits['requests_per_minute']
        self.requests_per_day = tier_limits['requests_per_day']
        self.max_symbols_per_request = tier_limits['max_symbols_per_request']
        self.max_days_per_request = tier_limits['max_days_per_request']
        
        # Rate limiter settings
        self.rate_limit_buffer = 0.9  # Use 90% of limit to be safe
        self.rate_limit_retry_seconds = 60  # Wait time when rate limited
        
    def _load_market_config(self):
        """
        [FUNCTION SUMMARY]
        Purpose: Configure market hours and trading calendar settings
        Sets: Market hours, timezone info, holiday calendar references
        Note: Used for data validation and filtering - ALL TIMES IN UTC
        """
        # Market timezone - Polygon returns everything in UTC
        self.market_timezone = pytz.UTC
        
        # Regular market hours in UTC (US Markets)
        # Note: These are converted from ET to UTC (ET = UTC-5 in winter, UTC-4 in summer)
        # Using standard time (winter) as base - adjust for DST in application logic if needed
        self.market_hours = {
            'pre_market_start': time(9, 0),     # 4:00 AM ET = 9:00 AM UTC (winter)
            'regular_start': time(14, 30),      # 9:30 AM ET = 2:30 PM UTC (winter)
            'regular_end': time(21, 0),         # 4:00 PM ET = 9:00 PM UTC (winter)
            'post_market_end': time(1, 0),      # 8:00 PM ET = 1:00 AM UTC next day (winter)
        }
        
        # Note about daylight saving time
        self.dst_aware = False  # Set to True if you need DST adjustments
        self.market_hours_dst = {
            'pre_market_start': time(8, 0),     # 4:00 AM ET = 8:00 AM UTC (summer)
            'regular_start': time(13, 30),      # 9:30 AM ET = 1:30 PM UTC (summer)
            'regular_end': time(20, 0),         # 4:00 PM ET = 8:00 PM UTC (summer)
            'post_market_end': time(0, 0),      # 8:00 PM ET = 12:00 AM UTC next day (summer)
        }
        
        # Trading days (0 = Monday, 6 = Sunday)
        self.trading_days = [0, 1, 2, 3, 4]  # Monday through Friday
        
        # Timestamp handling
        self.use_utc_timestamps = True  # Always use UTC for consistency with Polygon API
        self.timestamp_unit = 'ms'      # Polygon returns timestamps in milliseconds
        
        # Timeframe configurations
        self.valid_timespans = ['second', 'minute', 'hour', 'day', 'week', 'month', 'quarter', 'year']
        
        # Common timeframe mappings for user convenience
        self.timeframe_mappings = {
            # User input -> (multiplier, timespan)
            '1min': (1, 'minute'),
            '5min': (5, 'minute'),
            '15min': (15, 'minute'),
            '30min': (30, 'minute'),
            '60min': (60, 'minute'),
            '1h': (1, 'hour'),
            '4h': (4, 'hour'),
            '1d': (1, 'day'),
            'D': (1, 'day'),
            '1w': (1, 'week'),
            'W': (1, 'week'),
            '1m': (1, 'month'),
            'M': (1, 'month'),
        }
        
        # Maximum data points per request (Polygon limit)
        self.max_results_per_request = 50000
        
    def _setup_logging(self):
        """
        [FUNCTION SUMMARY]
        Purpose: Configure logging for the polygon module
        Sets: Logging format, level, and handlers
        Note: Creates module-specific logger configuration
        """
        # Get logging level from environment or default to INFO
        log_level = self.config_override.get(
            'log_level', 
            os.getenv('POLYGON_LOG_LEVEL', 'INFO')
        )
        
        # Configure logger for polygon module
        self.logger_config = {
            'level': getattr(logging, log_level.upper()),
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S'
        }
        
        # Log file configuration
        self.log_dir = self.data_dir / 'logs'
        self.log_dir.mkdir(exist_ok=True)
        self.log_file = self.log_dir / 'polygon.log'
        self.max_log_size = 10 * 1024 * 1024  # 10 MB
        self.log_backup_count = 5
        
    def get_logger(self, name: str) -> logging.Logger:
        """
        [FUNCTION SUMMARY]
        Purpose: Create a configured logger for a module component
        Parameters:
            - name (str): Logger name (usually __name__ of the calling module)
        Returns: logging.Logger - Configured logger instance
        Example: logger = config.get_logger(__name__)
        """
        # Create logger with module name
        logger = logging.getLogger(name)
        logger.setLevel(self.logger_config['level'])
        
        # Remove existing handlers to avoid duplicates
        logger.handlers.clear()
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(self.logger_config['level'])
        console_formatter = logging.Formatter(
            self.logger_config['format'],
            datefmt=self.logger_config['datefmt']
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
        
        # File handler with rotation
        if self.config_override.get('enable_file_logging', True):
            from logging.handlers import RotatingFileHandler
            file_handler = RotatingFileHandler(
                self.log_file,
                maxBytes=self.max_log_size,
                backupCount=self.log_backup_count
            )
            file_handler.setLevel(self.logger_config['level'])
            file_handler.setFormatter(console_formatter)
            logger.addHandler(file_handler)
        
        return logger
    
    def to_dict(self) -> Dict[str, Any]:
        """
        [FUNCTION SUMMARY]
        Purpose: Export configuration as dictionary for debugging/inspection
        Returns: dict - All configuration values except sensitive data
        Example: config_dict = config.to_dict()
        """
        # Create dictionary with all non-sensitive configuration
        return {
            'api_settings': {
                'base_url': self.base_url,
                'api_version': self.api_version,
                'subscription_tier': self.subscription_tier,
                'timeout': self.request_timeout,
                'max_retries': self.max_retries
            },
            'storage_settings': {
                'cache_enabled': self.cache_enabled,
                'cache_ttl_minutes': self.cache_ttl_minutes,
                'historical_cache_days': self.historical_cache_days,
                'use_compression': self.use_compression,
                'compression_type': self.compression_type,
                'paths': {
                    'data_dir': str(self.data_dir),
                    'cache_dir': str(self.cache_dir),
                    'parquet_dir': str(self.parquet_dir)
                }
            },
            'rate_limits': {
                'requests_per_minute': self.requests_per_minute,
                'requests_per_day': self.requests_per_day,
                'max_symbols_per_request': self.max_symbols_per_request,
                'max_days_per_request': self.max_days_per_request
            },
            'market_config': {
                'timezone': 'UTC',  # Always UTC to match Polygon API
                'market_hours': {k: v.strftime('%H:%M UTC') for k, v in self.market_hours.items()},
                'market_hours_dst': {k: v.strftime('%H:%M UTC') for k, v in self.market_hours_dst.items()},
                'dst_aware': self.dst_aware,
                'trading_days': self.trading_days,
                'valid_timespans': self.valid_timespans,
                'use_utc_timestamps': self.use_utc_timestamps,
                'timestamp_unit': self.timestamp_unit
            },
            'logging': {
                'level': logging.getLevelName(self.logger_config['level']),
                'log_file': str(self.log_file) if self.config_override.get('enable_file_logging', True) else None
            }
        }
    
    def save_to_file(self, filepath: Optional[Path] = None):
        """
        [FUNCTION SUMMARY]
        Purpose: Save current configuration to JSON file for reference
        Parameters:
            - filepath (Path, optional): Where to save config, defaults to data_dir
        Example: config.save_to_file()
        """
        # Default to saving in data directory
        if filepath is None:
            filepath = self.data_dir / 'config_snapshot.json'
        
        # Convert to dictionary and save
        config_dict = self.to_dict()
        config_dict['snapshot_timestamp'] = os.environ.get('BUILD_TIMESTAMP', 'development')
        
        # Write to file with pretty formatting
        with open(filepath, 'w') as f:
            json.dump(config_dict, f, indent=2)
            
        # Log the save
        logger = self.get_logger(__name__)
        logger.info(f"Configuration saved to {filepath}")


# Module-level constants that don't require instantiation
DEFAULT_MULTIPLIER = 1
DEFAULT_TIMESPAN = 'minute'
DEFAULT_LIMIT = 1000

# Data quality thresholds
MIN_VOLUME_THRESHOLD = 0  # Minimum volume to consider valid
MAX_PRICE_CHANGE_PERCENT = 50  # Maximum % change to consider valid
MAX_SPREAD_PERCENT = 10  # Maximum bid-ask spread as % of price

# Convenience function for getting config instance
_config_instance = None

def get_config(reset: bool = False, **overrides) -> PolygonConfig:
    """
    [FUNCTION SUMMARY]
    Purpose: Get or create singleton configuration instance
    Parameters:
        - reset (bool): Force create new instance
        - **overrides: Configuration overrides
    Returns: PolygonConfig - Configuration instance
    Example: config = get_config(cache_enabled=False)
    """
    global _config_instance
    
    # Create new instance if needed
    if _config_instance is None or reset or overrides:
        _config_instance = PolygonConfig(overrides)
    
    return _config_instance