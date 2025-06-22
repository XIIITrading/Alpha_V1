# polygon/api_validator.py - Polygon API feature validation
"""
API feature validation module for testing Polygon.io endpoints and capabilities.
This is different from data validation - it tests API access, not data quality.
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import logging

from .config import get_config
from .core import PolygonClient
from .exceptions import PolygonAPIError, PolygonAuthenticationError
# Import your existing validators for symbol validation
from .validators import validate_symbol_detailed

logger = logging.getLogger(__name__)


class PolygonAPIValidator:
    """
    Validates Polygon API features and endpoints for the Stocks Advanced tier.
    Tests API functionality, not data quality.
    """
    
    def __init__(self, client: Optional[PolygonClient] = None):
        """Initialize validator with optional client"""
        self.config = get_config()
        self.client = client or PolygonClient(self.config)
        self.logger = self.config.get_logger(__name__)
        
        # Define all API features to test
        self.features = {
            'authentication': 'API Key Authentication',
            'tickers': 'All US Stocks Tickers',
            'api_calls': 'Unlimited API Calls',
            'historical_data': '10 Years Historical Data',
            'market_coverage': '100% Market Coverage',
            'delayed_data': '15-minute Delayed Data',
            'reference_data': 'Reference Data',
            'fundamentals': 'Fundamentals Data',
            'corporate_actions': 'Corporate Actions',
            'technical_indicators': 'Technical Indicators',
            'minute_aggregates': 'Minute Aggregates',
            'websockets': 'WebSockets',
            'second_aggregates': 'Second Aggregates',
            'trades': 'Trades',
            'snapshot': 'Snapshot'
        }
        
        # Cache for validation results
        self._cache = {}
        self._cache_ttl = 300  # 5 minutes

    async def validate_all_features(self, use_cache: bool = True) -> Dict[str, Any]:
        """
        Run all validation tests
        
        Returns:
            Dictionary with test results for each feature
        """
        # Check cache first
        if use_cache and self._is_cache_valid('all_features'):
            self.logger.info("Returning cached validation results")
            return self._cache['all_features']['result']
        
        self.logger.info("Starting comprehensive Polygon API validation")
        start_time = time.time()
        
        results = {
            'timestamp': datetime.utcnow().isoformat(),
            'tier': self.config.subscription_tier,
            'features': {},
            'summary': {
                'total': len(self.features),
                'passed': 0,
                'failed': 0,
                'warnings': 0
            }
        }
        
        # Test each feature
        for feature_key, feature_name in self.features.items():
            try:
                self.logger.info(f"Testing {feature_name}...")
                
                # Get the validation method
                method_name = f'_validate_{feature_key}'
                if hasattr(self, method_name):
                    result = await getattr(self, method_name)()
                else:
                    result = {
                        'status': 'skipped',
                        'message': 'Test not implemented yet',
                        'details': {}
                    }
                
                results['features'][feature_key] = {
                    'name': feature_name,
                    **result
                }
                
                # Update summary
                if result['status'] == 'success':
                    results['summary']['passed'] += 1
                elif result['status'] == 'failed':
                    results['summary']['failed'] += 1
                elif result['status'] == 'warning':
                    results['summary']['warnings'] += 1
                    
            except Exception as e:
                self.logger.error(f"Error testing {feature_name}: {e}")
                results['features'][feature_key] = {
                    'name': feature_name,
                    'status': 'error',
                    'message': str(e),
                    'details': {}
                }
                results['summary']['failed'] += 1
        
        # Calculate overall status
        if results['summary']['failed'] == 0:
            results['overall_status'] = 'healthy'
        elif results['summary']['passed'] > results['summary']['failed']:
            results['overall_status'] = 'degraded'
        else:
            results['overall_status'] = 'unhealthy'
        
        results['execution_time'] = round(time.time() - start_time, 2)
        
        # Cache results
        self._cache['all_features'] = {
            'result': results,
            'timestamp': time.time()
        }
        
        return results
    
    async def validate_single_feature(self, feature: str) -> Dict[str, Any]:
        """
        Validate a single feature
        
        Args:
            feature: Feature key to validate
            
        Returns:
            Validation result for the feature
        """
        if feature not in self.features:
            raise ValueError(f"Unknown feature: {feature}")
        
        # Check cache
        cache_key = f'feature_{feature}'
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]['result']
        
        # Run validation
        method_name = f'_validate_{feature}'
        if hasattr(self, method_name):
            result = await getattr(self, method_name)()
        else:
            result = {
                'status': 'skipped',
                'message': 'Test not implemented yet',
                'details': {}
            }
        
        # Add metadata
        result['feature'] = feature
        result['name'] = self.features[feature]
        result['timestamp'] = datetime.utcnow().isoformat()
        
        # Cache result
        self._cache[cache_key] = {
            'result': result,
            'timestamp': time.time()
        }
        
        return result
    
    def _is_cache_valid(self, key: str) -> bool:
        """Check if cached result is still valid"""
        if key not in self._cache:
            return False
        
        age = time.time() - self._cache[key]['timestamp']
        return age < self._cache_ttl
    
    # Individual validation methods
    
    async def _validate_authentication(self) -> Dict[str, Any]:
        """Test API key authentication"""
        try:
            # Try to get market status (simple authenticated call)
            response = self.client.get_market_status()
            
            return {
                'status': 'success',
                'message': 'API key is valid and authenticated',
                'details': {
                    'market_status': response.get('market', 'unknown'),
                    'server_time': response.get('serverTime', 'unknown')
                }
            }
        except PolygonAuthenticationError:
            return {
                'status': 'failed',
                'message': 'Invalid API key',
                'details': {'error': 'Authentication failed'}
            }
        except Exception as e:
            return {
                'status': 'failed',
                'message': f'Authentication test failed: {str(e)}',
                'details': {}
            }
    
    async def _validate_tickers(self) -> Dict[str, Any]:
        """Test access to all US stocks tickers"""
        try:
            # Search for common tickers
            test_symbols = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'SPY']
            valid_count = 0
            
            for symbol in test_symbols:
                if self.client.validate_ticker(symbol):
                    valid_count += 1
            
            # Try to search for tickers
            search_result = self.client.search_tickers('Apple', limit=5)
            ticker_count = len(search_result.get('results', []))
            
            return {
                'status': 'success' if valid_count == len(test_symbols) else 'warning',
                'message': f'Validated {valid_count}/{len(test_symbols)} test symbols',
                'details': {
                    'test_symbols_valid': valid_count,
                    'search_results': ticker_count,
                    'access': 'All US Stocks'
                }
            }
        except Exception as e:
            return {
                'status': 'failed',
                'message': f'Ticker validation failed: {str(e)}',
                'details': {}
            }
    
    async def _validate_api_calls(self) -> Dict[str, Any]:
        """Test API rate limits"""
        try:
            # Make several rapid API calls
            start_time = time.time()
            calls_made = 0
            
            for i in range(10):  # Make 10 rapid calls
                self.client.get_market_status()
                calls_made += 1
            
            elapsed = time.time() - start_time
            calls_per_second = calls_made / elapsed
            
            # For advanced tier, should handle high rate
            is_unlimited = calls_per_second > 5  # Should handle at least 5 calls/second
            
            return {
                'status': 'success' if is_unlimited else 'warning',
                'message': f'Made {calls_made} calls in {elapsed:.2f}s ({calls_per_second:.1f} calls/sec)',
                'details': {
                    'rate': f'{calls_per_second:.1f} calls/second',
                    'tier_limit': 'Unlimited' if is_unlimited else 'Limited',
                    'subscription_tier': self.config.subscription_tier
                }
            }
        except Exception as e:
            return {
                'status': 'failed',
                'message': f'Rate limit test failed: {str(e)}',
                'details': {}
            }
    
    async def _validate_historical_data(self) -> Dict[str, Any]:
        """Test 10 years historical data access"""
        try:
            # Test with a known symbol
            symbol = 'AAPL'
            end_date = datetime.now()
            start_date = end_date - timedelta(days=365 * 10)  # 10 years ago
            
            # Try to fetch old data (just 1 day to be quick)
            test_date = start_date.strftime('%Y-%m-%d')
            
            response = self.client.get_aggregates(
                ticker=symbol,
                multiplier=1,
                timespan='day',
                from_date=test_date,
                to_date=test_date,
                limit=1
            )
            
            has_data = len(response.get('results', [])) > 0
            
            return {
                'status': 'success' if has_data else 'warning',
                'message': f'10-year historical data {"available" if has_data else "not found"}',
                'details': {
                    'test_symbol': symbol,
                    'test_date': test_date,
                    'data_found': has_data,
                    'years_available': '10+' if has_data else 'Unknown'
                }
            }
        except Exception as e:
            return {
                'status': 'failed',
                'message': f'Historical data test failed: {str(e)}',
                'details': {}
            }
    
    # Placeholder methods for remaining features
    async def _validate_market_coverage(self) -> Dict[str, Any]:
        """Test 100% market coverage"""
        return {
            'status': 'skipped',
            'message': 'Test not implemented yet',
            'details': {}
        }
    
    async def _validate_delayed_data(self) -> Dict[str, Any]:
        """Test 15-minute delayed data"""
        return {
            'status': 'skipped',
            'message': 'Test not implemented yet',
            'details': {}
        }
    
    # Add more validation methods as we implement them...


# Convenience function
async def validate_polygon_features(use_cache: bool = True) -> Dict[str, Any]:
    """
    Validate all Polygon API features
    
    Returns:
        Dictionary with validation results
    """
    validator = PolygonAPIValidator()
    return await validator.validate_all_features(use_cache=use_cache)