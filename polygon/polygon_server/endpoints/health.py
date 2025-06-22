"""
Health and status endpoints
"""
from fastapi import APIRouter
from datetime import datetime
import psutil
import os

from ..models import ServerStatus
from ..config import config

# Import from parent polygon module
from ... import get_storage_statistics, get_rate_limit_status, __version__

router = APIRouter(tags=["health"])

# Server start time
SERVER_START_TIME = datetime.now()


@router.get("/health")
async def health_check():
    """Basic health check"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@router.get("/status", response_model=ServerStatus)
async def server_status():
    """Detailed server status"""
    uptime = (datetime.now() - SERVER_START_TIME).total_seconds()
    
    # Get system metrics
    process = psutil.Process(os.getpid())
    memory_info = process.memory_info()
    
    try:
        cache_stats = get_storage_statistics()
    except:
        cache_stats = {"error": "Unable to get cache stats"}
        
    try:
        rate_limit = get_rate_limit_status()
    except:
        rate_limit = {"error": "Unable to get rate limit status"}
    
    # Check WebSocket status
    from .websocket import manager
    ws_clients = len(manager.active_connections)
    polygon_connected = False
    if manager.polygon_client:
        status = manager.polygon_client.get_status()
        polygon_connected = status.get("connected", False)
    
    return ServerStatus(
        status="healthy",
        version=__version__,
        uptime_seconds=uptime,
        polygon_connected=polygon_connected,
        websocket_clients=ws_clients,
        cache_stats=cache_stats,
        rate_limit_status=rate_limit,
        system_metrics={
            "memory_mb": memory_info.rss / 1024 / 1024,
            "cpu_percent": process.cpu_percent(),
            "threads": process.num_threads()
        }
    )


@router.get("/config")
async def get_config():
    """Get server configuration (non-sensitive)"""
    return config.to_dict()