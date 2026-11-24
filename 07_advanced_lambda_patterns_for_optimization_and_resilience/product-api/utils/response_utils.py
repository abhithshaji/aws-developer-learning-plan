"""Response Utilities Bridge.

Re-exports response formatting and error handling helpers from the shared
product-utilities layer (response_formatter module) for backward compatibility.
"""
import sys
import os

try:
    from response_formatter import (
        DEFAULT_HEADERS,
        decimal_serializer,
        create_success_response,
        create_error_response,
        create_structured_error_response,
        handle_product_validation_error,
        handle_inventory_insufficient_error,
        ContextualErrorHandler
    )
except ImportError:
    _layer_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'layers', 'product_utilities', 'python'))
    if _layer_path not in sys.path:
        sys.path.insert(0, _layer_path)
    from response_formatter import (
        DEFAULT_HEADERS,
        decimal_serializer,
        create_success_response,
        create_error_response,
        create_structured_error_response,
        handle_product_validation_error,
        handle_inventory_insufficient_error,
        ContextualErrorHandler
    )

__all__ = [
    'DEFAULT_HEADERS',
    'decimal_serializer',
    'create_success_response',
    'create_error_response',
    'create_structured_error_response',
    'handle_product_validation_error',
    'handle_inventory_insufficient_error',
    'ContextualErrorHandler'
]
