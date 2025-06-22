"""
Pydantic models for API requests/responses
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class TimeframeEnum(str, Enum):
    """Valid timeframe values"""
    ONE_MIN = "1min"
    FIVE_MIN = "5min"
    FIFTEEN_MIN = "15min"
    THIRTY_MIN = "30min"
    ONE_HOUR = "1hour"
    FOUR_HOUR = "4hour"
    ONE_DAY = "1day"
    ONE_WEEK = "1week"
    ONE_MONTH = "1month"


class DataSourceEnum(str, Enum):
    """Data source options"""
    POLYGON = "polygon"
    CACHE = "cache"
    AUTO = "auto"


class ChannelEnum(str, Enum):
    """WebSocket channel types"""
    TRADES = "T"
    QUOTES = "Q"
    AGGREGATES = "A"
    AGGREGATE_MINUTE = "AM"


class BarsRequest(BaseModel):
    """Request model for historical bars"""
    symbol: str = Field(..., description="Stock symbol (e.g., AAPL)")
    timeframe: TimeframeEnum = Field(TimeframeEnum.ONE_DAY, description="Bar timeframe")
    start_date: Optional[str] = Field(None, description="Start date (YYYY-MM-DD)")
    end_date: Optional[str] = Field(None, description="End date (YYYY-MM-DD)")
    limit: Optional[int] = Field(None, description="Maximum number of bars")
    use_cache: bool = Field(True, description="Use cached data if available")
    validate: bool = Field(True, description="Validate data quality")
    
    @validator('symbol')
    def uppercase_symbol(cls, v):
        return v.upper()


class BarsResponse(BaseModel):
    """Response model for historical bars"""
    symbol: str
    timeframe: str
    start_date: str
    end_date: str
    bar_count: int
    data: List[Dict[str, Any]]
    cached: bool = False
    validation: Optional[Dict[str, Any]] = None


class MultipleBarsRequest(BaseModel):
    """Request for multiple symbols"""
    symbols: List[str] = Field(..., description="List of symbols")
    timeframe: TimeframeEnum = Field(TimeframeEnum.ONE_DAY)
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    parallel: bool = Field(True, description="Fetch in parallel")
    

class SymbolValidationRequest(BaseModel):
    """Request to validate symbols"""
    symbols: List[str] = Field(..., description="Symbols to validate")
    detailed: bool = Field(False, description="Include detailed validation")


class WebSocketSubscription(BaseModel):
    """WebSocket subscription request"""
    symbols: List[str] = Field(..., description="Symbols to subscribe")
    channels: List[ChannelEnum] = Field([ChannelEnum.TRADES], description="Data channels")
    client_id: Optional[str] = Field(None, description="Client identifier")


class ServerStatus(BaseModel):
    """Server status response"""
    status: str = "healthy"
    version: str
    uptime_seconds: float
    polygon_connected: bool
    websocket_clients: int
    cache_stats: Dict[str, Any]
    rate_limit_status: Dict[str, Any]
    system_metrics: Optional[Dict[str, Any]] = None


class ErrorResponse(BaseModel):
    """Error response model"""
    error: str
    message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.now)