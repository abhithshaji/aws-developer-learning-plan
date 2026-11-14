import unittest
from db.product_schema import ProductInput
from pydantic import ValidationError

class TestProductValidation(unittest.TestCase):
    def setUp(self):
        """Set up realistic test data."""
        self.valid_products = [
            {
                'title': 'Wireless Headphones',
                'price': 199.99,
                'category': 'Electronics',
                'description': 'High-quality wireless headphones'
            },
            {
                'title': 'Running Shoes',
                'price': 129.99,
                'category': 'Home',
                'description': 'Comfortable running shoes'
            }
        ]
        
        self.invalid_products = [
            {
                'title': '',  # Empty title fails validation
                'price': 99.99,
                'category': 'Electronics',
                'description': 'Valid description'
            },
            {
                'title': 'Valid Product',
                'price': -50,  # Negative price fails validation
                'category': 'Electronics',
                'description': 'Valid description'
            },
            {
                'title': 'Another Product',
                'price': 199.99,
                'category': 'NonexistentCategory',  # Invalid category
                'description': 'Valid description'
            }
        ]

    def test_product_validation_with_valid_data(self):
        """Test validation passes for valid product data."""
        for product in self.valid_products:
            with self.subTest(product=product['title']):
                ProductInput(**product)  # Raises ValidationError if invalid

    def test_product_validation_with_invalid_data(self):
        """Test validation catches invalid product data."""
        for product in self.invalid_products:
            with self.subTest(product=product):
                with self.assertRaises(ValidationError):
                    ProductInput(**product)