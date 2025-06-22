Polygon.io Data Integration Module - Technical Documentation
Overview
The Polygon module is a comprehensive, self-contained Python package for integrating with Polygon.io's market data APIs. It provides both REST and WebSocket connectivity, intelligent caching, data validation, and includes a standalone server for unified data access across multiple applications.
Key Features

Complete REST API Integration: Historical data fetching with intelligent caching
WebSocket Real-time Streaming: Live market data with automatic reconnection
Unified Data Server: FastAPI server exposing both REST and WebSocket endpoints
Advanced Tier Optimized: Built for Polygon's advanced subscription tier
Self-contained: No external dependencies on other modules
Production Ready: Comprehensive error handling, logging, and validation

Architecture
polygon/
├── __init__.py              # Public API exports
├── config.py                # Configuration management
├── core.py                  # Low-level Polygon client
├── websocket.py             # WebSocket streaming client
├── fetcher.py               # High-level data fetching
├── storage.py               # SQLite + Parquet caching
├── rate_limiter.py          # API rate limit management
├── exceptions.py            # Custom exception types
├── utils.py                 # Utility functions
├── validators/              # Data validation suite
│   ├── symbol.py
│   ├── ohlcv.py
│   ├── gaps.py
│   ├── anomalies.py
│   ├── market_hours.py
│   └── api_features.py
└── polygon_server/          # Standalone data server
    ├── server.py            # FastAPI application
    ├── config.py            # Server configuration
    ├── models.py            # Pydantic models
    ├── endpoints/           # API endpoints
    │   ├── rest.py          # REST endpoints
    │   ├── websocket.py     # WebSocket endpoints
    │   └── health.py        # Health/status endpoints
    ├── requirements.txt     # Server dependencies
    └── start_server.py      # Server startup script
Installation
Prerequisites

Python 3.8 or higher
Polygon.io API key (Advanced tier)
Windows/Linux/macOS

Setup

Clone or copy the polygon module to your project:
your_project/
└── polygon/

Install dependencies:
bashpip install -r polygon/polygon_server/requirements.txt

Configure environment variables:
Create a .env file in your project root:
env# Required
POLYGON_API_KEY=your_polygon_api_key_here

# Optional server configuration
SERVER_HOST=0.0.0.0
SERVER_PORT=8200
LOG_LEVEL=INFO
POLYGON_TIER=advanced


Quick Start
Using the Module Directly
pythonimport polygon

# Initialize (optional - will use env vars)
polygon.initialize(api_key='your_key')

# Fetch historical data
df = polygon.get_bars('AAPL', timeframe='5min', start='2024-01-01', end='2024-01-31')

# Get latest price
price = polygon.get_latest_price('AAPL')

# Stream real-time data
async def handle_trade(data):
    print(f"Trade: {data['symbol']} @ ${data['price']}")

client = await polygon.stream_trades(['AAPL', 'MSFT'], handle_trade)
Using the Data Server

Start the server:
bash# Windows
start_polygon_server.bat

# Or directly
python -m polygon.polygon_server.start_server

Access the API:

REST API: http://localhost:8200/api/v1/
API Docs: http://localhost:8200/docs
WebSocket: ws://localhost:8200/ws/{client_id}



API Documentation
REST API Endpoints
Get Historical Bars
httpPOST /api/v1/bars
Content-Type: application/json

{
    "symbol": "AAPL",
    "timeframe": "5min",
    "start_date": "2024-01-01",
    "end_date": "2024-01-31",
    "use_cache": true,
    "validate": true
}
Response:
json{
    "symbol": "AAPL",
    "timeframe": "5min",
    "start_date": "2024-01-01",
    "end_date": "2024-01-31",
    "bar_count": 7800,
    "data": [
        {
            "timestamp": "2024-01-01T09:30:00",
            "open": 185.50,
            "high": 185.75,
            "low": 185.25,
            "close": 185.60,
            "volume": 125000,
            "vwap": 185.55,
            "transactions": 850
        }
    ],
    "cached": true,
    "validation": {
        "overall_quality": "EXCELLENT",
        "issues": []
    }
}
Get Latest Price
httpGET /api/v1/latest/AAPL
Validate Symbols
httpPOST /api/v1/validate
Content-Type: application/json

{
    "symbols": ["AAPL", "MSFT", "INVALID"],
    "detailed": true
}
Search Symbols
httpGET /api/v1/search?query=apple&active_only=true
Cache Management
httpGET /api/v1/cache/stats
DELETE /api/v1/cache?symbol=AAPL&older_than_days=30
Rate Limit Status
httpGET /api/v1/rate-limit
WebSocket API
Connection
javascriptconst ws = new WebSocket('ws://localhost:8200/ws/my-client-id');

ws.onopen = () => {
    console.log('Connected to Polygon data stream');
};

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log('Received:', data);
};
Subscribe to Data
javascript// Subscribe to trades and quotes
ws.send(JSON.stringify({
    action: 'subscribe',
    symbols: ['AAPL', 'MSFT'],
    channels: ['T', 'Q']  // T=Trades, Q=Quotes, A=Aggregates
}));
Data Format
javascript// Trade data
{
    "type": "market_data",
    "data": {
        "event_type": "trade",
        "symbol": "AAPL",
        "timestamp": 1706284800000,
        "price": 185.50,
        "size": 100,
        "conditions": [14, 37],
        "exchange": 4,
        "trade_id": "12345"
    },
    "timestamp": "2024-01-26T09:30:00"
}

// Quote data
{
    "type": "market_data",
    "data": {
        "event_type": "quote",
        "symbol": "AAPL",
        "timestamp": 1706284800000,
        "bid_price": 185.48,
        "bid_size": 300,
        "ask_price": 185.52,
        "ask_size": 500,
        "exchange": 4
    },
    "timestamp": "2024-01-26T09:30:00"
}
Module API Reference
Simple Functions
python# Get historical data
polygon.get_bars(symbol, timeframe, start, end, use_cache=True, validate=True)

# Get latest price
polygon.get_latest_price(symbol)

# Validate ticker
polygon.validate_ticker(symbol)

# Clear cache
polygon.clear_cache(symbol=None, older_than_days=None)

# Get statistics
polygon.get_storage_statistics()
polygon.get_rate_limit_status()
Advanced Usage
pythonfrom polygon import PolygonDataManager

manager = PolygonDataManager()

# Fetch multiple symbols in parallel
data = manager.fetch_multiple_symbols(
    symbols=['AAPL', 'GOOGL', 'MSFT'],
    timeframe='1day',
    start_date='2024-01-01',
    end_date='2024-01-31'
)

# Validate data quality
validation = manager.validate_data(df, 'AAPL', '5min')

# Search symbols
results = manager.search_symbols('Tesla')
WebSocket Client
pythonfrom polygon import PolygonWebSocketClient

async def stream_data():
    client = PolygonWebSocketClient()
    
    async def handle_data(data):
        print(f"{data['event_type']}: {data['symbol']} @ ${data['price']}")
    
    await client.connect()
    await client.subscribe(['AAPL', 'TSLA'], ['T', 'Q'], handle_data)
    await client.listen()
Integration Examples
Electron/JavaScript Integration
javascript// Using REST API
async function fetchHistoricalData(symbol, timeframe) {
    const response = await fetch('http://localhost:8200/api/v1/bars', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            symbol,
            timeframe,
            start_date: '2024-01-01',
            end_date: '2024-01-31'
        })
    });
    
    return await response.json();
}

// Using WebSocket
class PolygonStream {
    constructor(clientId) {
        this.ws = new WebSocket(`ws://localhost:8200/ws/${clientId}`);
        this.setupHandlers();
    }
    
    setupHandlers() {
        this.ws.onmessage = (event) => {
            const message = JSON.parse(event.data);
            if (message.type === 'market_data') {
                this.handleMarketData(message.data);
            }
        };
    }
    
    subscribe(symbols, channels = ['T']) {
        this.ws.send(JSON.stringify({
            action: 'subscribe',
            symbols,
            channels
        }));
    }
    
    handleMarketData(data) {
        // Process incoming data
        console.log(`${data.symbol}: $${data.price}`);
    }
}
Python Integration
pythonimport requests
import asyncio
import websockets
import json

# REST API client
class PolygonAPIClient:
    def __init__(self, base_url='http://localhost:8200'):
        self.base_url = base_url
    
    def get_bars(self, symbol, timeframe, start_date, end_date):
        response = requests.post(
            f'{self.base_url}/api/v1/bars',
            json={
                'symbol': symbol,
                'timeframe': timeframe,
                'start_date': start_date,
                'end_date': end_date
            }
        )
        return response.json()

# WebSocket client
async def stream_market_data():
    uri = 'ws://localhost:8200/ws/python-client'
    
    async with websockets.connect(uri) as websocket:
        # Subscribe
        await websocket.send(json.dumps({
            'action': 'subscribe',
            'symbols': ['AAPL', 'MSFT'],
            'channels': ['T', 'Q']
        }))
        
        # Listen for data
        async for message in websocket:
            data = json.loads(message)
            if data.get('type') == 'market_data':
                print(f"Received: {data['data']}")
Configuration
Environment Variables
VariableDescriptionDefaultRequiredPOLYGON_API_KEYYour Polygon.io API key-YesSERVER_HOSTServer bind address0.0.0.0NoSERVER_PORTServer port8200NoLOG_LEVELLogging levelINFONoPOLYGON_TIERSubscription tieradvancedNoCACHE_DIRCache directory./polygon_cacheNoWS_MAX_CONNECTIONSMax WebSocket clients100No
Cache Configuration
The module uses SQLite for metadata and Parquet files for data storage:
polygon/data/
├── cache/
│   └── polygon_cache.db      # Metadata
└── parquet/
    └── symbols/
        ├── AAPL/
        │   ├── AAPL_1min.parquet
        │   └── AAPL_1day.parquet
        └── MSFT/
            └── ...
Troubleshooting
Common Issues
1. "POLYGON_API_KEY not found"

Ensure .env file exists in project root
Set environment variable: set POLYGON_API_KEY=your_key

2. "No data returned"

Check if markets are open (WebSocket data)
Verify date range is valid
Ensure symbol is valid US equity

3. "Rate limit exceeded"

Check current usage: /api/v1/rate-limit
Advanced tier has high limits (10,000/min)
Use caching to reduce API calls

4. WebSocket connection drops

Module has automatic reconnection
Check network connectivity
Verify API key is valid

Debug Mode
Enable debug logging:
python# In .env
LOG_LEVEL=DEBUG

# Or in code
import logging
logging.getLogger('polygon').setLevel(logging.DEBUG)
Performance Considerations
Caching Strategy

Historical data is cached locally in Parquet format
Cache is checked before API calls
Use use_cache=False to force fresh data

Rate Limits (Advanced Tier)

10,000 requests per minute
Unlimited daily requests
Up to 1,000 concurrent symbol subscriptions

Memory Usage

Large date ranges are automatically chunked
WebSocket buffers are managed automatically
Cache files are compressed

Development
Running Tests
bash# Run WebSocket test
python polygon/tests/test_websocket_live.py

# Test server endpoints
python polygon/polygon_server/start_server.py --test
Adding New Endpoints

Add endpoint to polygon/polygon_server/endpoints/rest.py:

python@router.get("/api/v1/my-endpoint")
async def my_endpoint():
    return {"status": "ok"}

Add model to polygon/polygon_server/models.py if needed
Restart server to load changes

Security Notes

Never commit .env files
API keys are masked in logs
Server uses CORS protection
Input validation on all endpoints
Rate limiting prevents abuse

Support
Polygon.io Resources

API Documentation: https://polygon.io/docs
Status Page: https://status.polygon.io
Support: https://polygon.io/support

Module Information

Version: 1.0.0
Python: 3.8+
License: Proprietary
Author: AlphaXIII


This module provides a complete, production-ready integration with Polygon.io's market data services, suitable for high-frequency trading, market analysis, and real-time data applications.