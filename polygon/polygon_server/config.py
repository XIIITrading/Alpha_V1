"""
Server configuration
"""
import os
from pathlib import Path
from typing import Optional


class ServerConfig:
    """Server configuration settings"""
    
    def __init__(self):
        # Server settings
        self.host = os.getenv("SERVER_HOST", "0.0.0.0")
        self.port = int(os.getenv("SERVER_PORT", "8200"))
        self.workers = int(os.getenv("SERVER_WORKERS", "1"))
        
        # CORS settings
        self.cors_origins = os.getenv("CORS_ORIGINS", "*").split(",")
        
        # Polygon settings
        self.polygon_api_key = os.getenv("POLYGON_API_KEY")
        self.polygon_tier = os.getenv("POLYGON_TIER", "advanced")
        
        # Cache settings
        self.cache_dir = Path(os.getenv("CACHE_DIR", "./polygon_cache"))
        self.cache_ttl = int(os.getenv("CACHE_TTL", "3600"))  # 1 hour
        
        # WebSocket settings
        self.ws_heartbeat_interval = int(os.getenv("WS_HEARTBEAT", "30"))
        self.ws_max_connections = int(os.getenv("WS_MAX_CONNECTIONS", "100"))
        
        # Logging
        self.log_level = os.getenv("LOG_LEVEL", "INFO")
        self.log_file = os.getenv("LOG_FILE", "polygon_server.log")
        
    def validate(self):
        """Validate configuration"""
        if not self.polygon_api_key:
            raise ValueError("POLYGON_API_KEY environment variable is required")
        
        # Create cache directory if needed
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
    def to_dict(self):
        """Convert to dictionary"""
        return {
            "host": self.host,
            "port": self.port,
            "cors_origins": self.cors_origins,
            "polygon_tier": self.polygon_tier,
            "cache_dir": str(self.cache_dir),
            "ws_max_connections": self.ws_max_connections
        }


# Global config instance
config = ServerConfig()