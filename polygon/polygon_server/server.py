"""
Main FastAPI application for Polygon data server
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from typing import Any
import orjson
import logging
import sys

# Import from parent polygon module
from .. import (
    PolygonDataManager, 
    get_storage_statistics, 
    get_rate_limit_status,
    initialize,
    __version__
)

from .endpoints import rest, websocket, health
from .config import config
from .models import ErrorResponse
from .utils.json_encoder import PolygonJSONEncoder, polygon_json_dumps

# Configure logging
logging.basicConfig(
    level=config.log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.log_file),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# Custom ORJSONResponse that uses our encoder
class PolygonORJSONResponse(ORJSONResponse):
    def render(self, content: Any) -> bytes:
        try:
            # First use our custom encoder to handle numpy/datetime types
            json_str = polygon_json_dumps(content)
            # Parse back to dict for orjson
            json_compatible = orjson.loads(json_str)
            # Then use orjson for fast serialization
            return orjson.dumps(json_compatible)
        except Exception as e:
            logger.error(f"JSON serialization error: {type(e).__name__}: {str(e)}")
            logger.error(f"Content type: {type(content)}")
            logger.error(f"Content sample: {str(content)[:200]}...")
            raise

# Create FastAPI app
app = FastAPI(
    title="Polygon Data Server",
    description="Unified server for Polygon.io market data - REST and WebSocket APIs",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    default_response_class=PolygonORJSONResponse  # Use custom response class
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router)
app.include_router(rest.router)
app.include_router(websocket.router)

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global exception: {exc}", exc_info=True)
    return PolygonORJSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="internal_error",
            message=str(exc)
        ).dict()
    )

# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize on startup"""
    logger.info("Starting Polygon Data Server...")
    
    # Validate configuration
    try:
        config.validate()
        logger.info("Configuration validated")
    except Exception as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    
    # Initialize polygon module
    initialize(api_key=config.polygon_api_key)
    logger.info("Polygon module initialized")
    
    logger.info(f"Server ready at http://{config.host}:{config.port}")

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down Polygon Data Server...")
    
    # Close WebSocket connections
    from .endpoints.websocket import manager
    if manager.polygon_client:
        await manager.polygon_client.disconnect()
    
    logger.info("Server shutdown complete")

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": "Polygon Data Server",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "status": "/status"
    }