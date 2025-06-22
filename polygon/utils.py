# polygon/utils.py - Utility functions for the Polygon module
"""
Utility functions for data manipulation, validation, and conversion.
Provides common operations used throughout the polygon module.
"""

import re
from datetime import datetime, timedelta, time as dt_time
from typing import Union, Tuple, Optional, List, Dict, Any
import pandas as pd
import pytz
from dateutil import parser as date_parser

from .config import get_config, POLYGON_TIMEZONE
from .exceptions import PolygonDataError, PolygonTimeRangeError


def parse_timeframe(timeframe: str) -> Tuple[int, str]:
    """
    [FUNCTION SUMMARY]
    Purpose: Parse user-friendly timeframe strings into Polygon API format
    Parameters:
        - timeframe (str): Timeframe string (e.g., '5min', '1h', '1d')
    Returns: tuple - (multiplier, timespan) for Polygon API
    Example: parse_timeframe('5min') -> (5, 'minute')
    """
    # Get configuration for mappings
    config = get_config()
    
    # Check if it's a known mapping
    if timeframe.lower() in config.timeframe_mappings:
        return config.timeframe_mappings[timeframe.lower()]
    
    # Try to parse custom format (e.g., "15minute", "2hour")
    pattern = r'^(\d+)\s*([a-zA-Z]+)$'
    match = re.match(pattern, timeframe)
    
    if match:
        multiplier = int(match.group(1))
        unit = match.group(2).lower()
        
        # Map common abbreviations to Polygon timespans
        unit_mappings = {
            's': 'second', 'sec': 'second', 'secs': 'second', 'second': 'second', 'seconds': 'second',
            'm': 'minute', 'min': 'minute', 'mins': 'minute', 'minute': 'minute', 'minutes': 'minute',
            'h': 'hour', 'hr': 'hour', 'hrs': 'hour', 'hour': 'hour', 'hours': 'hour',
            'd': 'day', 'day': 'day', 'days': 'day',
            'w': 'week', 'wk': 'week', 'week': 'week', 'weeks': 'week',
            'mo': 'month', 'month': 'month', 'months': 'month',
            'q': 'quarter', 'qtr': 'quarter', 'quarter': 'quarter', 'quarters': 'quarter',
            'y': 'year', 'yr': 'year', 'year': 'year', 'years': 'year'
        }
        
        if unit in unit_mappings:
            timespan = unit_mappings[unit]
            if timespan in config.valid_timespans:
                return (multiplier, timespan)
    
    # If we can't parse it, raise an error
    raise PolygonDataError(
        f"Invalid timeframe format: {timeframe}",
        field='timeframe',
        value=timeframe,
        valid_formats=['1min', '5min', '1h', '1d', '15minute', '2hour']
    )


def validate_symbol(symbol: str) -> str:
    """
    [FUNCTION SUMMARY]
    Purpose: Validate and normalize stock symbol
    Parameters:
        - symbol (str): Stock ticker symbol
    Returns: str - Normalized uppercase symbol
    Example: validate_symbol('aapl') -> 'AAPL'
    Raises: PolygonDataError if symbol is invalid
    """
    # Strip whitespace and convert to uppercase
    symbol = symbol.strip().upper()
    
    # Check if empty
    if not symbol:
        raise PolygonDataError("Symbol cannot be empty", field='symbol')
    
    # Validate symbol format (letters, dots, and hyphens allowed)
    # Examples: AAPL, BRK.B, SPY-USD
    pattern = r'^[A-Z][A-Z0-9\.\-]{0,15}$'
    if not re.match(pattern, symbol):
        raise PolygonDataError(
            f"Invalid symbol format: {symbol}",
            field='symbol',
            value=symbol,
            valid_pattern='Letters, numbers, dots, and hyphens only'
        )
    
    return symbol


def parse_date(date_input: Union[str, datetime, pd.Timestamp], 
               timezone: Optional[pytz.timezone] = None) -> datetime:
    """
    [FUNCTION SUMMARY]
    Purpose: Parse various date formats into UTC datetime
    Parameters:
        - date_input: Date in various formats
        - timezone (pytz.timezone, optional): Source timezone if not specified
    Returns: datetime - UTC datetime object
    Example: parse_date('2023-01-01') -> datetime(2023, 1, 1, 0, 0, 0, tzinfo=UTC)
    """
    # Default to UTC if no timezone specified
    if timezone is None:
        timezone = POLYGON_TIMEZONE
    
    # Handle different input types
    if isinstance(date_input, datetime):
        dt = date_input
    elif isinstance(date_input, pd.Timestamp):
        dt = date_input.to_pydatetime()
    elif isinstance(date_input, str):
        # Try to parse string
        try:
            dt = date_parser.parse(date_input)
        except (ValueError, TypeError) as e:
            raise PolygonDataError(
                f"Cannot parse date: {date_input}",
                field='date',
                value=date_input,
                error=str(e)
            )
    else:
        raise PolygonDataError(
            f"Unsupported date type: {type(date_input)}",
            field='date',
            value=str(date_input)
        )
    
    # Ensure timezone awareness
    if dt.tzinfo is None:
        # Assume the provided timezone if naive
        dt = timezone.localize(dt)
    else:
        # Convert to UTC if already timezone-aware
        dt = dt.astimezone(POLYGON_TIMEZONE)
    
    return dt


def format_date_for_api(date: Union[str, datetime, pd.Timestamp]) -> str:
    """
    [FUNCTION SUMMARY]
    Purpose: Format date for Polygon API (YYYY-MM-DD)
    Parameters:
        - date: Date in various formats
    Returns: str - Date string in YYYY-MM-DD format
    Example: format_date_for_api(datetime.now()) -> '2023-12-25'
    """
    # Parse to datetime first
    dt = parse_date(date)
    
    # Format as YYYY-MM-DD
    return dt.strftime('%Y-%m-%d')


def timestamp_to_datetime(timestamp: Union[int, float], unit: str = 'ms') -> datetime:
    """
    [FUNCTION SUMMARY]
    Purpose: Convert Unix timestamp to UTC datetime
    Parameters:
        - timestamp: Unix timestamp
        - unit (str): Timestamp unit ('s', 'ms', 'us', 'ns')
    Returns: datetime - UTC datetime object
    Example: timestamp_to_datetime(1640995200000) -> datetime(2022, 1, 1, 0, 0, 0, tzinfo=UTC)
    """
    # Convert to seconds based on unit
    unit_multipliers = {
        's': 1,
        'ms': 1000,
        'us': 1000000,
        'ns': 1000000000
    }
    
    if unit not in unit_multipliers:
        raise PolygonDataError(f"Invalid timestamp unit: {unit}", field='unit', value=unit)
    
    # Convert to seconds
    timestamp_seconds = timestamp / unit_multipliers[unit]
    
    # Create UTC datetime
    try:
        dt = datetime.fromtimestamp(timestamp_seconds, tz=POLYGON_TIMEZONE)
        return dt
    except (ValueError, OSError) as e:
        raise PolygonDataError(
            f"Invalid timestamp: {timestamp}",
            field='timestamp',
            value=timestamp,
            error=str(e)
        )


def datetime_to_timestamp(dt: datetime, unit: str = 'ms') -> int:
    """
    [FUNCTION SUMMARY]
    Purpose: Convert datetime to Unix timestamp
    Parameters:
        - dt (datetime): Datetime object
        - unit (str): Desired timestamp unit
    Returns: int - Unix timestamp
    Example: datetime_to_timestamp(datetime(2022, 1, 1, tzinfo=UTC)) -> 1640995200000
    """
    # Ensure UTC
    if dt.tzinfo is None:
        dt = POLYGON_TIMEZONE.localize(dt)
    else:
        dt = dt.astimezone(POLYGON_TIMEZONE)
    
    # Get timestamp in seconds
    timestamp_seconds = dt.timestamp()
    
    # Convert to desired unit
    unit_multipliers = {
        's': 1,
        'ms': 1000,
        'us': 1000000,
        'ns': 1000000000
    }
    
    if unit not in unit_multipliers:
        raise PolygonDataError(f"Invalid timestamp unit: {unit}", field='unit', value=unit)
    
    return int(timestamp_seconds * unit_multipliers[unit])


def validate_date_range(start_date: Union[str, datetime], 
                       end_date: Union[str, datetime],
                       max_days: Optional[int] = None) -> Tuple[datetime, datetime]:
    """
    [FUNCTION SUMMARY]
    Purpose: Validate date range for API requests
    Parameters:
        - start_date: Start date
        - end_date: End date
        - max_days (int, optional): Maximum allowed days in range
    Returns: tuple - (start_datetime, end_datetime) in UTC
    Example: validate_date_range('2023-01-01', '2023-01-31') -> (datetime, datetime)
    Raises: PolygonTimeRangeError if range is invalid
    """
    # Parse dates
    start_dt = parse_date(start_date)
    end_dt = parse_date(end_date)
    
    # Check if start is before end
    if start_dt >= end_dt:
        raise PolygonTimeRangeError(
            "Start date must be before end date",
            start_date=start_dt,
            end_date=end_dt
        )
    
    # Check if end date is in the future
    now = datetime.now(POLYGON_TIMEZONE)
    if end_dt > now:
        raise PolygonTimeRangeError(
            "End date cannot be in the future",
            start_date=start_dt,
            end_date=end_dt,
            current_time=now
        )
    
    # Check maximum range if specified
    if max_days:
        days_diff = (end_dt - start_dt).days
        if days_diff > max_days:
            raise PolygonTimeRangeError(
                f"Date range exceeds maximum of {max_days} days",
                start_date=start_dt,
                end_date=end_dt,
                max_range=f"{max_days} days",
                actual_days=days_diff
            )
    
    return start_dt, end_dt


def is_market_open(check_time: Optional[datetime] = None) -> bool:
    """
    [FUNCTION SUMMARY]
    Purpose: Check if US stock market is open at given time
    Parameters:
        - check_time (datetime, optional): Time to check (defaults to now)
    Returns: bool - True if market is open
    Example: is_market_open() -> True
    Note: Checks regular trading hours only, not extended hours
    """
    # Get configuration
    config = get_config()
    
    # Use current time if not specified
    if check_time is None:
        check_time = datetime.now(POLYGON_TIMEZONE)
    else:
        # Ensure UTC
        check_time = parse_date(check_time)
    
    # Check if it's a weekday (Monday=0, Sunday=6)
    if check_time.weekday() not in config.trading_days:
        return False
    
    # Get time component
    current_time = check_time.time()
    
    # Check against market hours (accounting for DST if needed)
    # Note: This is simplified and doesn't account for holidays
    market_start = config.market_hours['regular_start']
    market_end = config.market_hours['regular_end']
    
    return market_start <= current_time <= market_end


def is_extended_hours(check_time: Optional[datetime] = None) -> bool:
    """
    [FUNCTION SUMMARY]
    Purpose: Check if time falls within extended trading hours
    Parameters:
        - check_time (datetime, optional): Time to check
    Returns: bool - True if in pre-market or after-hours
    Example: is_extended_hours() -> False
    """
    config = get_config()
    
    if check_time is None:
        check_time = datetime.now(POLYGON_TIMEZONE)
    else:
        check_time = parse_date(check_time)
    
    # Not extended hours on weekends
    if check_time.weekday() not in config.trading_days:
        return False
    
    current_time = check_time.time()
    
    # Check pre-market
    if config.market_hours['pre_market_start'] <= current_time < config.market_hours['regular_start']:
        return True
    
    # Check after-hours
    if config.market_hours['regular_end'] < current_time <= config.market_hours['post_market_end']:
        return True
    
    return False


def calculate_bars_in_range(start_date: Union[str, datetime], 
                           end_date: Union[str, datetime],
                           timeframe: str) -> int:
    """
    [FUNCTION SUMMARY]
    Purpose: Estimate number of bars in a date range for given timeframe
    Parameters:
        - start_date: Start date
        - end_date: End date
        - timeframe (str): Timeframe (e.g., '5min', '1d')
    Returns: int - Estimated number of bars
    Example: calculate_bars_in_range('2023-01-01', '2023-01-31', '1d') -> 22
    Note: This is an estimate, actual bars depend on market hours and holidays
    """
    # Parse dates
    start_dt, end_dt = validate_date_range(start_date, end_date)
    
    # Parse timeframe
    multiplier, timespan = parse_timeframe(timeframe)
    
    # Calculate based on timespan
    total_seconds = (end_dt - start_dt).total_seconds()
    
    # Avoid division by zero
    if total_seconds <= 0:
        return 0
    
    # Seconds per unit
    seconds_per_unit = {
        'second': 1,
        'minute': 60,
        'hour': 3600,
        'day': 86400,
        'week': 604800,
        'month': 2592000,  # Approximate (30 days)
        'quarter': 7776000,  # Approximate (90 days)
        'year': 31536000  # Approximate (365 days)
    }
    
    if timespan not in seconds_per_unit:
        raise PolygonDataError(f"Unknown timespan: {timespan}", field='timespan', value=timespan)
    
    # Calculate approximate bars
    seconds_per_bar = seconds_per_unit[timespan] * multiplier
    estimated_bars = int(total_seconds / seconds_per_bar)
    
    # Adjust for market hours if intraday
    if timespan in ['second', 'minute', 'hour']:
        # Approximate: 6.5 hours per trading day, 252 trading days per year
        market_fraction = (6.5 * 252) / (24 * 365)  # ~0.187
        estimated_bars = int(estimated_bars * market_fraction)
    
    return max(estimated_bars, 1)


def split_large_date_range(start_date: Union[str, datetime], 
                          end_date: Union[str, datetime],
                          max_days: int) -> List[Tuple[datetime, datetime]]:
    """
    [FUNCTION SUMMARY]
    Purpose: Split large date range into smaller chunks
    Parameters:
        - start_date: Start date
        - end_date: End date
        - max_days (int): Maximum days per chunk
    Returns: list - List of (start, end) datetime tuples
    Example: split_large_date_range('2023-01-01', '2023-12-31', 30) -> [(start1, end1), ...]
    """
    # Parse and validate dates
    start_dt, end_dt = validate_date_range(start_date, end_date)
    
    # Handle very large max_days values
    if max_days > 36500:  # More than 100 years
        max_days = 36500
    
    # Create chunks
    chunks = []
    current_start = start_dt
    
    while current_start < end_dt:
        # Calculate chunk end
        chunk_end = min(
            current_start + timedelta(days=max_days),
            end_dt
        )
        
        # Add chunk
        chunks.append((current_start, chunk_end))
        
        # Move to next chunk (add 1 second to avoid overlap)
        current_start = chunk_end + timedelta(seconds=1)
    
    return chunks


def normalize_ohlcv_data(data: List[Dict[str, Any]]) -> pd.DataFrame:
    """
    [FUNCTION SUMMARY]
    Purpose: Normalize OHLCV data from Polygon API into DataFrame
    Parameters:
        - data (list): List of bar dictionaries from API
    Returns: DataFrame - Normalized OHLCV data with UTC timestamps
    Example: df = normalize_ohlcv_data(api_response['results'])
    """
    if not data:
        # Return empty DataFrame with correct structure
        return pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume', 'vwap', 'transactions'])
    
    # Create DataFrame
    df = pd.DataFrame(data)
    
    # Rename columns to standard names
    column_mapping = {
        'o': 'open',
        'h': 'high',
        'l': 'low',
        'c': 'close',
        'v': 'volume',
        't': 'timestamp',
        'vw': 'vwap',  # Volume weighted average price
        'n': 'transactions'  # Number of transactions
    }
    
    df = df.rename(columns=column_mapping)
    
    # Convert timestamp to datetime index
    if 'timestamp' in df.columns:
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
        df = df.set_index('datetime')
        df = df.drop(columns=['timestamp'])
    
    # Ensure numeric types
    numeric_columns = ['open', 'high', 'low', 'close', 'volume', 'vwap', 'transactions']
    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Sort by time
    df = df.sort_index()
    
    # Remove any duplicates
    df = df[~df.index.duplicated(keep='last')]
    
    return df


def validate_ohlcv_data(df: pd.DataFrame, symbol: str = None) -> pd.DataFrame:
    """
    [FUNCTION SUMMARY]
    Purpose: Validate OHLCV data for common issues
    Parameters:
        - df (DataFrame): OHLCV data to validate
        - symbol (str, optional): Symbol for error context
    Returns: DataFrame - Validated data (may have removed invalid rows)
    Example: clean_df = validate_ohlcv_data(df, 'AAPL')
    Raises: PolygonDataError if critical issues found
    """
    if df.empty:
        return df
    
    original_len = len(df)
    issues = []
    
    # Check for required columns
    required_columns = ['open', 'high', 'low', 'close', 'volume']
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        raise PolygonDataError(
            f"Missing required columns: {missing_columns}",
            data_type='ohlcv',
            symbol=symbol
        )
    
    # Remove rows with any NaN in OHLC
    ohlc_columns = ['open', 'high', 'low', 'close']
    nan_mask = df[ohlc_columns].isna().any(axis=1)
    if nan_mask.any():
        issues.append(f"Removed {nan_mask.sum()} rows with NaN prices")
        df = df[~nan_mask]
    
    # Check for negative prices
    negative_mask = (df[ohlc_columns] < 0).any(axis=1)
    if negative_mask.any():
        issues.append(f"Removed {negative_mask.sum()} rows with negative prices")
        df = df[~negative_mask]
    
    # Check for zero prices (likely bad data)
    zero_mask = (df[ohlc_columns] == 0).any(axis=1)
    if zero_mask.any():
        issues.append(f"Removed {zero_mask.sum()} rows with zero prices")
        df = df[~zero_mask]
    
    # Validate high/low logic
    invalid_hl = df['high'] < df['low']
    if invalid_hl.any():
        issues.append(f"Removed {invalid_hl.sum()} rows where high < low")
        df = df[~invalid_hl]
    
    # Validate OHLC relationships
    invalid_oh = df['open'] > df['high']
    invalid_ol = df['open'] < df['low']
    invalid_ch = df['close'] > df['high']
    invalid_cl = df['close'] < df['low']
    
    invalid_ohlc = invalid_oh | invalid_ol | invalid_ch | invalid_cl
    if invalid_ohlc.any():
        issues.append(f"Removed {invalid_ohlc.sum()} rows with invalid OHLC relationships")
        df = df[~invalid_ohlc]
    
    # Check for extreme price changes (possible data errors)
    if len(df) > 1:
        price_change = df['close'].pct_change().abs()
        extreme_changes = price_change > 0.5  # 50% change
        if extreme_changes.any():
            extreme_count = extreme_changes.sum()
            if extreme_count > len(df) * 0.01:  # More than 1% of data
                issues.append(f"Warning: {extreme_count} rows with >50% price changes")
    
    # Validate volume (allow zero but not negative)
    if 'volume' in df.columns:
        negative_volume = df['volume'] < 0
        if negative_volume.any():
            issues.append(f"Removed {negative_volume.sum()} rows with negative volume")
            df = df[~negative_volume]
    
    # Log issues if any
    if issues:
        config = get_config()
        logger = config.get_logger(__name__)
        symbol_str = f" for {symbol}" if symbol else ""
        logger.warning(f"Data validation issues{symbol_str}: {'; '.join(issues)}")
        logger.info(f"Rows after validation: {len(df)}/{original_len} ({len(df)/original_len*100:.1f}%)")
    
    return df


def resample_ohlcv(df: pd.DataFrame, target_timeframe: str, 
                   label: str = 'right', closed: str = 'right') -> pd.DataFrame:
    """
    [FUNCTION SUMMARY]
    Purpose: Resample OHLCV data to a different timeframe
    Parameters:
        - df (DataFrame): Source OHLCV data
        - target_timeframe (str): Target timeframe (e.g., '5min', '1h')
        - label (str): Which bin edge to label bucket with
        - closed (str): Which side of bin is closed
    Returns: DataFrame - Resampled OHLCV data
    Example: hourly_df = resample_ohlcv(minute_df, '1h')
    """
    # Parse target timeframe
    multiplier, timespan = parse_timeframe(target_timeframe)
    
    # Convert to pandas frequency string
    freq_mapping = {
        'second': 'S',
        'minute': 'min',
        'hour': 'H',
        'day': 'D',
        'week': 'W',
        'month': 'M',
        'quarter': 'Q',
        'year': 'Y'
    }
    
    if timespan not in freq_mapping:
        raise PolygonDataError(f"Cannot resample to timespan: {timespan}")
    
    freq = f"{multiplier}{freq_mapping[timespan]}"
    
    # Define aggregation rules
    agg_rules = {
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }
    
    # Add vwap if present (volume-weighted calculation)
    if 'vwap' in df.columns and 'volume' in df.columns:
        # Calculate dollar volume for proper VWAP resampling
        df['dollar_volume'] = df['vwap'] * df['volume']
        agg_rules['dollar_volume'] = 'sum'
    
    # Add transactions if present
    if 'transactions' in df.columns:
        agg_rules['transactions'] = 'sum'
    
    # Resample
    resampled = df.resample(freq, label=label, closed=closed).agg(agg_rules)
    
    # Recalculate VWAP if we had it
    if 'dollar_volume' in resampled.columns:
        resampled['vwap'] = resampled['dollar_volume'] / resampled['volume']
        resampled = resampled.drop(columns=['dollar_volume'])
        # Handle division by zero
        resampled['vwap'] = resampled['vwap'].fillna(resampled['close'])
    
    # Remove empty bars (where volume is 0 or NaN)
    resampled = resampled[resampled['volume'] > 0]
    
    return resampled


def dataframe_to_dict(df: pd.DataFrame, orient: str = 'records') -> Union[List[Dict], Dict]:
    """
    [FUNCTION SUMMARY]
    Purpose: Convert DataFrame to dictionary format with proper datetime handling
    Parameters:
        - df (DataFrame): DataFrame to convert
        - orient (str): Dictionary orientation ('records', 'index', 'columns')
    Returns: dict or list - Converted data
    Example: records = dataframe_to_dict(df)
    """
    # Create a copy to avoid modifying original
    df_copy = df.copy()
    
    # Convert datetime index to string if present
    if isinstance(df_copy.index, pd.DatetimeIndex):
        df_copy.index = df_copy.index.strftime('%Y-%m-%d %H:%M:%S')
    
    # Convert any datetime columns
    for col in df_copy.columns:
        if pd.api.types.is_datetime64_any_dtype(df_copy[col]):
            df_copy[col] = df_copy[col].dt.strftime('%Y-%m-%d %H:%M:%S')
    
    # Convert to dict
    return df_copy.to_dict(orient=orient)


def estimate_data_size(symbol_count: int, days: int, timeframe: str) -> Dict[str, Any]:
    """
    [FUNCTION SUMMARY]
    Purpose: Estimate storage size and API calls for data request
    Parameters:
        - symbol_count (int): Number of symbols
        - days (int): Number of days
        - timeframe (str): Data timeframe
    Returns: dict - Estimates for storage size, API calls, cost
    Example: estimate = estimate_data_size(10, 30, '5min')
    """
    # Parse timeframe
    multiplier, timespan = parse_timeframe(timeframe)
    
    # Estimate bars per day
    bars_per_day = {
        'second': 23400,  # 6.5 hours * 3600
        'minute': 390,    # 6.5 hours * 60
        'hour': 7,        # ~6.5 hours
        'day': 1,
        'week': 0.2,      # 1 per 5 days
        'month': 0.05,    # ~1 per 20 days
        'quarter': 0.016, # ~1 per 60 days
        'year': 0.004     # ~1 per 250 days
    }
    
    # Get bars per day for this timespan
    base_bars_per_day = bars_per_day.get(timespan, 390)
    bars_per_day_adjusted = base_bars_per_day / multiplier
    
    # Calculate total bars
    total_bars = int(symbol_count * days * bars_per_day_adjusted)
    
    # Estimate storage (approximately 100 bytes per bar in parquet)
    bytes_per_bar = 100
    total_bytes = total_bars * bytes_per_bar
    
    # Estimate API calls (50,000 bars per call)
    bars_per_call = 50000
    api_calls = max(1, (total_bars + bars_per_call - 1) // bars_per_call)
    
    # Get rate limits
    config = get_config()
    
    # Estimate time based on rate limits
    calls_per_minute = config.requests_per_minute
    estimated_minutes = api_calls / calls_per_minute
    
    return {
        'total_bars': total_bars,
        'storage_bytes': total_bytes,
        'storage_mb': round(total_bytes / (1024 * 1024), 2),
        'api_calls': api_calls,
        'estimated_minutes': round(estimated_minutes, 2),
        'rate_limit_tier': config.subscription_tier,
        'timeframe': f"{multiplier}{timespan}",
        'daily_bars_per_symbol': int(bars_per_day_adjusted)
    }


# Re-export key functions for convenience
__all__ = [
    'parse_timeframe',
    'validate_symbol',
    'parse_date',
    'format_date_for_api',
    'timestamp_to_datetime',
    'datetime_to_timestamp',
    'validate_date_range',
    'is_market_open',
    'is_extended_hours',
    'calculate_bars_in_range',
    'split_large_date_range',
    'normalize_ohlcv_data',
    'validate_ohlcv_data',
    'resample_ohlcv',
    'dataframe_to_dict',
    'estimate_data_size'
]