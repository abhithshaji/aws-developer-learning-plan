"""Product Schema & Validation Bridge.

Re-exports ProductInput from the shared product-utilities layer
(product_validator module) for backward compatibility.
"""
import sys
import os

try:
    from product_validator import ProductInput
except ImportError:
    _layer_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'layers', 'product_utilities', 'python'))
    if _layer_path not in sys.path:
        sys.path.insert(0, _layer_path)
    from product_validator import ProductInput

__all__ = ['ProductInput']
