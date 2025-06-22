"""
REST API endpoints for historical data
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional, List
import pandas as pd
from datetime import datetime, timedelta
import json
from ..utils.json_encoder import polygon_json_dumps

# Import from parent polygon module
from ... import (
    PolygonDataManager,
    get_storage_statistics,
    get_rate_limit_status,
    get_latest_price,
    validate_ticker,
    validate_symbol_detailed,
    clear_cache
)

from ..models import (
    BarsRequest, BarsResponse, MultipleBarsRequest,
    SymbolValidationRequest, ErrorResponse
)
from ..config import config

router = APIRouter(prefix="/api/v1", tags=["market-data"])

# Initialize data manager
data_manager = PolygonDataManager()


@router.post("/bars")  # Removed response_model=BarsResponse to use custom JSON encoder
async def get_bars(request: BarsRequest):
    """
    Get historical OHLCV bars for a symbol
    
    Returns pandas DataFrame converted to JSON format
    """
    try:
        # Set default dates if not provided
        end_date = request.end_date or datetime.now().strftime("%Y-%m-%d")
        if not request.start_date:
            # Default to 30 days of data
            start = datetime.now() - timedelta(days=30)
            start_date = start.strftime("%Y-%m-%d")
        else:
            start_date = request.start_date
        
        # Fetch data
        df = data_manager.fetch_data(
            symbol=request.symbol,
            timeframe=request.timeframe.value,
            start_date=start_date,
            end_date=end_date,
            use_cache=request.use_cache,
            validate=request.validate
        )
        
        if df.empty:
            raise HTTPException(404, f"No data found for {request.symbol}")
        
        # Apply limit if specified
        if request.limit and len(df) > request.limit:
            df = df.tail(request.limit)
        
        # Convert to response format
        data_records = []
        for idx, row in df.iterrows():
            data_records.append({
                "timestamp": idx.isoformat(),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": int(row["volume"]),
                "vwap": float(row.get("vwap", 0)),
                "transactions": int(row.get("transactions", 0))
            })
        
        # Get validation results if requested
        validation = None
        if request.validate:
            validation = data_manager.validate_data(df, request.symbol, request.timeframe.value)
            # Convert validation to ensure no numpy types
            if validation:
                validation = json.loads(polygon_json_dumps(validation))
        
        return {
            "symbol": request.symbol,
            "timeframe": request.timeframe.value,
            "start_date": df.index[0].strftime("%Y-%m-%d"),
            "end_date": df.index[-1].strftime("%Y-%m-%d"),
            "bar_count": len(df),
            "data": data_records,
            "cached": request.use_cache,
            "validation": validation
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error fetching data: {str(e)}")


@router.post("/bars/multiple")
async def get_multiple_bars(request: MultipleBarsRequest):
    """
    Get bars for multiple symbols
    """
    try:
        # Set default dates
        end_date = request.end_date or datetime.now()
        start_date = request.start_date or (datetime.now() - timedelta(days=30))
        
        if request.parallel:
            # Fetch in parallel
            results = data_manager.fetch_multiple_symbols(
                symbols=request.symbols,
                timeframe=request.timeframe.value,
                start_date=start_date,
                end_date=end_date
            )
        else:
            # Fetch sequentially
            results = {}
            for symbol in request.symbols:
                try:
                    df = data_manager.fetch_data(
                        symbol=symbol,
                        timeframe=request.timeframe.value,
                        start_date=start_date,
                        end_date=end_date
                    )
                    results[symbol] = df
                except Exception as e:
                    results[symbol] = {"error": str(e)}
        
        # Format response
        response = {}
        for symbol, data in results.items():
            if isinstance(data, pd.DataFrame) and not data.empty:
                response[symbol] = {
                    "success": True,
                    "bar_count": len(data),
                    "first_bar": data.index[0].isoformat(),
                    "last_bar": data.index[-1].isoformat()
                }
            else:
                response[symbol] = {
                    "success": False,
                    "error": data.get("error", "No data") if isinstance(data, dict) else "No data"
                }
        
        return response
        
    except Exception as e:
        raise HTTPException(500, f"Error fetching multiple symbols: {str(e)}")


@router.get("/latest/{symbol}")
async def get_latest_price_endpoint(symbol: str):  # Renamed to avoid conflict with imported function
    """Get latest price for a symbol"""
    try:
        price = get_latest_price(symbol.upper())
        if price is None:
            raise HTTPException(404, f"No price data for {symbol}")
            
        return {
            "symbol": symbol.upper(),
            "price": price,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(500, f"Error getting latest price: {str(e)}")


@router.post("/validate")
async def validate_symbols(request: SymbolValidationRequest):
    """Validate if symbols are valid"""
    results = {}
    
    for symbol in request.symbols:
        try:
            if request.detailed:
                # Detailed validation
                validation = validate_symbol_detailed(symbol)
                results[symbol] = validation
            else:
                # Simple validation
                is_valid = validate_ticker(symbol)
                results[symbol] = {"valid": is_valid}
        except Exception as e:
            results[symbol] = {"valid": False, "error": str(e)}
    
    return results


@router.get("/search")
async def search_symbols(
    query: str = Query(..., description="Search query"),
    active_only: bool = Query(True, description="Only active symbols")
):
    """Search for symbols by name or ticker"""
    try:
        results = data_manager.search_symbols(query, active_only)
        return {"query": query, "count": len(results), "results": results}
    except Exception as e:
        raise HTTPException(500, f"Search error: {str(e)}")


@router.get("/cache/stats")
async def get_cache_statistics():
    """Get cache statistics"""
    try:
        stats = get_storage_statistics()
        return stats
    except Exception as e:
        raise HTTPException(500, f"Error getting cache stats: {str(e)}")


@router.delete("/cache")
async def clear_cache_endpoint(  # Renamed to avoid conflict with imported function
    symbol: Optional[str] = Query(None, description="Clear specific symbol"),
    older_than_days: Optional[int] = Query(None, description="Clear data older than N days")
):
    """Clear cache data"""
    try:
        result = clear_cache(symbol=symbol, older_than_days=older_than_days)
        return result
    except Exception as e:
        raise HTTPException(500, f"Error clearing cache: {str(e)}")


@router.get("/rate-limit")
async def get_rate_limit():
    """Get current rate limit status"""
    try:
        status = get_rate_limit_status()
        return status
    except Exception as e:
        raise HTTPException(500, f"Error getting rate limit: {str(e)}")