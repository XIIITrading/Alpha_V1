"""
WebSocket endpoints for real-time data streaming
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, Set, List, Optional
import json
import asyncio
from datetime import datetime
import logging

# Import from parent polygon module
from ... import PolygonWebSocketClient

from ..models import WebSocketSubscription, ChannelEnum
from ..config import config

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])

# Active WebSocket connections
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.client_subscriptions: Dict[str, Set[str]] = {}
        self.polygon_client: Optional[PolygonWebSocketClient] = None
        self.listen_task: Optional[asyncio.Task] = None
        
    async def connect(self, websocket: WebSocket, client_id: str):
        """Accept new WebSocket connection"""
        await websocket.accept()
        self.active_connections[client_id] = websocket
        self.client_subscriptions[client_id] = set()
        logger.info(f"Client {client_id} connected")
        
    def disconnect(self, client_id: str):
        """Remove WebSocket connection"""
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            del self.client_subscriptions[client_id]
            logger.info(f"Client {client_id} disconnected")
            
    async def send_to_client(self, client_id: str, data: dict):
        """Send data to specific client"""
        if client_id in self.active_connections:
            try:
                await self.active_connections[client_id].send_json(data)
            except Exception as e:
                logger.error(f"Error sending to client {client_id}: {e}")
                
    async def broadcast(self, data: dict, symbol: str = None):
        """Broadcast data to all relevant clients"""
        # If symbol specified, only send to clients subscribed to that symbol
        if symbol:
            for client_id, subscriptions in self.client_subscriptions.items():
                if symbol in subscriptions:
                    await self.send_to_client(client_id, data)
        else:
            # Broadcast to all
            for client_id in self.active_connections:
                await self.send_to_client(client_id, data)
                
    async def ensure_polygon_connected(self):
        """Ensure Polygon WebSocket is connected"""
        if not self.polygon_client:
            self.polygon_client = PolygonWebSocketClient()
            await self.polygon_client.connect()
            
            # Start listen task
            self.listen_task = asyncio.create_task(self.polygon_client.listen())
            logger.info("Polygon WebSocket client connected")
            
    async def subscribe_client(self, client_id: str, symbols: List[str], channels: List[str]):
        """Subscribe client to symbols"""
        await self.ensure_polygon_connected()
        
        # Update client subscriptions
        self.client_subscriptions[client_id].update(symbols)
        
        # Create callback for this subscription
        async def data_callback(data):
            # Format data for client
            message = {
                "type": "market_data",
                "data": data,
                "timestamp": datetime.now().isoformat()
            }
            
            # Send to subscribing client
            await self.send_to_client(client_id, message)
        
        # Subscribe to Polygon
        sub_id = f"client_{client_id}"
        await self.polygon_client.subscribe(symbols, channels, data_callback, sub_id)
        
        return sub_id


# Global connection manager
manager = ConnectionManager()


@router.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    """
    WebSocket endpoint for real-time data streaming
    
    Protocol:
    - Connect: ws://localhost:8200/ws/{client_id}
    - Subscribe: {"action": "subscribe", "symbols": ["AAPL"], "channels": ["T", "Q"]}
    - Unsubscribe: {"action": "unsubscribe", "symbols": ["AAPL"]}
    - Ping: {"action": "ping"}
    """
    await manager.connect(websocket, client_id)
    
    try:
        # Send welcome message
        await websocket.send_json({
            "type": "connected",
            "message": "Connected to Polygon data stream",
            "client_id": client_id,
            "timestamp": datetime.now().isoformat()
        })
        
        # Handle incoming messages
        while True:
            # Receive message
            data = await websocket.receive_json()
            action = data.get("action")
            
            if action == "subscribe":
                # Subscribe to symbols
                symbols = data.get("symbols", [])
                channels = data.get("channels", ["T"])  # Default to trades
                
                if symbols:
                    sub_id = await manager.subscribe_client(client_id, symbols, channels)
                    
                    await websocket.send_json({
                        "type": "subscribed",
                        "symbols": symbols,
                        "channels": channels,
                        "subscription_id": sub_id
                    })
                else:
                    await websocket.send_json({
                        "type": "error",
                        "message": "No symbols provided"
                    })
                    
            elif action == "unsubscribe":
                # Handle unsubscribe
                symbols = data.get("symbols", [])
                # TODO: Implement unsubscribe logic
                
                await websocket.send_json({
                    "type": "unsubscribed",
                    "symbols": symbols
                })
                
            elif action == "ping":
                # Respond to ping
                await websocket.send_json({
                    "type": "pong",
                    "timestamp": datetime.now().isoformat()
                })
                
            else:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Unknown action: {action}"
                })
                
    except WebSocketDisconnect:
        manager.disconnect(client_id)
    except Exception as e:
        logger.error(f"WebSocket error for client {client_id}: {e}")
        manager.disconnect(client_id)
        await websocket.close()


@router.get("/ws/status")
async def websocket_status():
    """Get WebSocket connection status"""
    polygon_status = {}
    if manager.polygon_client:
        polygon_status = manager.polygon_client.get_status()
    
    return {
        "active_clients": len(manager.active_connections),
        "client_ids": list(manager.active_connections.keys()),
        "polygon_connected": polygon_status.get("connected", False),
        "polygon_status": polygon_status
    }