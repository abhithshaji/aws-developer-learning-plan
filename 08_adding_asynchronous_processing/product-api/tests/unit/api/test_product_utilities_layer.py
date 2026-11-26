import os
import sys
import unittest
from decimal import Decimal

# Ensure layer python directory is in path
LAYER_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'layers', 'product_utilities', 'python'))
if LAYER_PATH not in sys.path:
    sys.path.insert(0, LAYER_PATH)

import product_validator
import response_formatter
import database_helper


class TestProductUtilitiesLayer(unittest.TestCase):
    """Unit tests for modules inside the Product Utilities Lambda Layer."""

    def test_product_validator_valid_input(self):
        """Test ProductInput schema validation with valid attributes."""
        product = product_validator.ProductInput(
            title="Mechanical Keyboard",
            category="Electronics",
            description="RGB mechanical keyboard",
            price=Decimal("99.99")
        )
        self.assertEqual(product.title, "Mechanical Keyboard")
        self.assertEqual(product.category, "Electronics")
        self.assertEqual(product.price, Decimal("99.99"))

    def test_product_validator_invalid_price(self):
        """Test ProductInput validation fails when price is non-positive."""
        with self.assertRaises(ValueError):
            product_validator.ProductInput(
                title="Free Mousepad",
                category="Accessories",
                description="Promotional pad",
                price=Decimal("0.00")
            )

    def test_product_validator_invalid_category(self):
        """Test ProductInput validation fails when category is invalid."""
        with self.assertRaises(ValueError):
            product_validator.ProductInput(
                title="Desk Chair",
                category="Furniture",  # Not in allowed list
                description="Ergonomic office chair",
                price=Decimal("299.99")
            )

    def test_response_formatter_success_response(self):
        """Test standardized success response structure and CORS headers."""
        data = {"id": "prod_123", "price": Decimal("19.99")}
        res = response_formatter.create_success_response(200, data)

        self.assertEqual(res['statusCode'], 200)
        self.assertEqual(res['headers']['Content-Type'], 'application/json')
        self.assertEqual(res['headers']['Access-Control-Allow-Origin'], '*')
        self.assertIn('"price": 19.99', res['body'])

    def test_response_formatter_error_response(self):
        """Test standardized error response structure."""
        res = response_formatter.create_error_response(400, "Invalid payload")
        self.assertEqual(res['statusCode'], 400)
        self.assertIn('"error": "Invalid payload"', res['body'])

    def test_response_formatter_structured_error(self):
        """Test structured error envelopes with suggestions."""
        res = response_formatter.create_structured_error_response(
            status_code=409,
            error_type="conflict",
            message="Item exists",
            suggestions=["Use a unique ID"]
        )
        self.assertEqual(res['statusCode'], 409)
        self.assertIn('"type": "conflict"', res['body'])
        self.assertIn('"suggestions": ["Use a unique ID"]', res['body'])

    def test_contextual_error_handler_not_found(self):
        """Test ContextualErrorHandler generates helpful search/category suggestions."""
        handler = response_formatter.ContextualErrorHandler(
            user_context={'category': 'Audio', 'search_term': 'headphones'}
        )
        res = handler.handle_product_not_found("prod_999")
        self.assertEqual(res['statusCode'], 404)
        self.assertIn('headphones', res['body'])
        self.assertIn('Audio', res['body'])

    def test_database_helper_exports(self):
        """Verify database_helper exports expected CRUD and query callables."""
        self.assertTrue(callable(database_helper.get_product))
        self.assertTrue(callable(database_helper.insert_product))
        self.assertTrue(callable(database_helper.update_product))
        self.assertTrue(callable(database_helper.get_products_by_category))
        self.assertTrue(callable(database_helper.get_all_products))


if __name__ == '__main__':
    unittest.main()
