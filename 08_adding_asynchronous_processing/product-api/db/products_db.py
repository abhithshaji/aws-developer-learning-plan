"""Database Operations Bridge.

Re-exports DynamoDB table and helper operations from the shared
product-utilities layer (database_helper module) for backward compatibility.
"""
import sys
import os

try:
    from database_helper import (
        table,
        get_product,
        get_all_products,
        get_products_by_category,
        insert_product,
        update_product,
        update_product_with_version
    )
except ImportError:
    _layer_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'layers', 'product_utilities', 'python'))
    if _layer_path not in sys.path:
        sys.path.insert(0, _layer_path)
    from database_helper import (
        table,
        get_product,
        get_all_products,
        get_products_by_category,
        insert_product,
        update_product,
        update_product_with_version
    )

__all__ = [
    'table',
    'get_product',
    'get_all_products',
    'get_products_by_category',
    'insert_product',
    'update_product',
    'update_product_with_version'
]
