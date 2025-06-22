# polygon/validators/symbol.py - Symbol validation functions
"""
Symbol validation functionality for the Polygon module.
Provides detailed validation and classification of trading symbols.
"""

import re
from typing import Dict, Any

from ..exceptions import PolygonSymbolError


def validate_symbol_detailed(symbol: str) -> Dict[str, Any]:
    """
    [FUNCTION SUMMARY]
    Purpose: Perform detailed symbol validation with classification
    Parameters:
        - symbol (str): Stock ticker symbol
    Returns: dict - Validation results with symbol type and characteristics
    Example: result = validate_symbol_detailed('AAPL') -> {'valid': True, 'type': 'equity', ...}
    """
    result = {
        'valid': False,
        'normalized': None,
        'type': None,
        'characteristics': [],
        'warnings': []
    }
    
    # Basic validation
    if not symbol or not isinstance(symbol, str):
        result['error'] = 'Symbol must be a non-empty string'
        return result
    
    # Normalize
    normalized = symbol.strip().upper()
    result['normalized'] = normalized
    
    # Length check
    if len(normalized) > 16:
        result['error'] = 'Symbol too long (max 16 characters)'
        return result
    
    # Empty check
    if not normalized:
        result['error'] = 'Symbol cannot be empty'
        return result
    
    # Pattern matching for different symbol types
    patterns = {
        # Standard equity (1-5 letters)
        'equity': r'^[A-Z]{1,5}$',
        # Equity with share class (e.g., BRK.A, BRK.B)
        'equity_class': r'^[A-Z]{1,5}\.[A-Z]$',
        # Preferred stock (e.g., BAC-PD)
        'preferred': r'^[A-Z]{1,5}-P[A-Z]$',
        # Warrant (e.g., NKLA.WS)
        'warrant': r'^[A-Z]{1,5}\.WS$',
        # When issued (e.g., AAPL.WI)
        'when_issued': r'^[A-Z]{1,5}\.WI$',
        # Rights (e.g., AAPL.RT)
        'rights': r'^[A-Z]{1,5}\.RT$',
        # Units (e.g., IPOF.U)
        'units': r'^[A-Z]{1,5}\.U$',
        # Test symbols (e.g., ZVZZT)
        'test': r'^Z[A-Z]{3,}$',
    }
    
    # Check each pattern
    for symbol_type, pattern in patterns.items():
        if re.match(pattern, normalized):
            result['valid'] = True
            result['type'] = symbol_type
            break
    
    # If no pattern matched, check if it could be valid but unusual
    if not result['valid']:
        # More restrictive fallback patterns
        fallback_patterns = [
            # Standard equity with numbers at end (e.g., ABCD1, ABC23)
            (r'^[A-Z]{1,5}[0-9]{1,2}$', 'equity_numbered'),
            # ETF or special with single dot suffix (e.g., SPY.X)
            (r'^[A-Z]{1,5}\.[A-Z0-9]{1,2}$', 'special_suffix'),
            # Preferred with hyphen and letter/number (e.g., ABC-A, XYZ-1)
            (r'^[A-Z]{1,5}-[A-Z0-9]{1,2}$', 'special_class'),
        ]
        
        for pattern, symbol_type in fallback_patterns:
            if re.match(pattern, normalized):
                result['valid'] = True
                result['type'] = symbol_type
                result['warnings'].append('Non-standard symbol format')
                break
        
        if not result['valid']:
            result['valid'] = False
            result['error'] = f'Invalid symbol format: {normalized}'
    
    # Add characteristics
    if result['valid']:
        # Check for special characteristics
        if '.' in normalized:
            result['characteristics'].append('has_suffix')
        if '-' in normalized:
            result['characteristics'].append('has_hyphen')
        if any(c.isdigit() for c in normalized):
            result['characteristics'].append('has_numbers')
        if len(normalized) == 1:
            result['characteristics'].append('single_letter')
        if len(normalized) > 5:
            result['characteristics'].append('extended_length')
        if normalized.startswith('Z'):
            result['warnings'].append('Possible test symbol')
            
        # Add type-specific warnings
        if result['type'] == 'test':
            result['warnings'].append('Test symbol - may not have real market data')
        elif result['type'] in ['warrant', 'when_issued', 'rights', 'units']:
            result['warnings'].append(f'Special security type: {result["type"]}')
    
    return result