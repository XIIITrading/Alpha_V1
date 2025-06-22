"""
Custom JSON encoder for Polygon data
Handles numpy types, datetime objects, and other non-JSON serializable types
"""
import json
import numpy as np
from datetime import datetime, date, time
from decimal import Decimal
from typing import Any


class PolygonJSONEncoder(json.JSONEncoder):
    """
    Custom JSON encoder that handles:
    - Numpy data types (int64, float64, arrays, etc.)
    - Datetime objects
    - Decimal types
    - Any other types that might come from financial data
    """
    
    def default(self, obj: Any) -> Any:
        # Handle numpy integer types
        if isinstance(obj, (np.integer, np.int_)):
            return int(obj)
        
        # Handle numpy floating types
        elif isinstance(obj, (np.floating, np.float64)):
            return float(obj)
        
        # Handle numpy arrays
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        
        # Handle numpy booleans
        elif isinstance(obj, np.bool_):
            return bool(obj)
        
        # Handle datetime types
        elif isinstance(obj, datetime):
            return obj.isoformat()
        
        elif isinstance(obj, date):
            return obj.isoformat()
        
        elif isinstance(obj, time):
            return obj.isoformat()
        
        # Handle Decimal (often used for financial data)
        elif isinstance(obj, Decimal):
            return float(obj)
        
        # Handle pandas Timestamp (if pandas is used)
        elif hasattr(obj, 'isoformat'):
            return obj.isoformat()
        
        # Handle pandas NA/NaN
        elif hasattr(obj, '__module__') and obj.__module__ == 'pandas._libs.missing':
            return None
        
        # Let the default encoder handle or raise TypeError
        return super().default(obj)


def polygon_json_dumps(obj: Any, **kwargs) -> str:
    """
    Convenience function to dump JSON using PolygonJSONEncoder
    """
    return json.dumps(obj, cls=PolygonJSONEncoder, **kwargs)


def polygon_json_response(content: Any, **kwargs) -> dict:
    """
    Prepare content for JSON response, handling all special types
    """
    # Convert to JSON and back to ensure all types are handled
    json_str = polygon_json_dumps(content)
    return json.loads(json_str)