import unittest
import json
from unittest.mock import patch
import os

# Ensure boto3 does not fail on import if products_db initializes DynamoDB at module level
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")

class TestGetProduct(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures before each test method."""
        self.sample_product = {
            'id': 'prod_123',
            'title': 'Wireless Headphones',
            'price': 199.99,
            'category': 'Electronics',
            'inventory_count': 50
        }
        
        self.valid_event = {
            'httpMethod': 'GET',
            'pathParameters': {'id': 'prod_123'},
            'queryStringParameters': None,
            'body': None
        }

    @patch('lambda_code.get_product.get_product')
    def test_get_product_success(self, mock_get_product):
        """Test successful product retrieval."""
        # Arrange
        mock_get_product.return_value = self.sample_product
        
        # Act
        from lambda_code.get_product import handler
        response = handler(self.valid_event, None)
        
        # Assert
        self.assertEqual(response['statusCode'], 200)
        
        body = json.loads(response['body'])
        self.assertEqual(body['id'], 'prod_123')
        self.assertEqual(body['title'], 'Wireless Headphones')
        
        # Verify database was called correctly
        mock_get_product.assert_called_once_with('prod_123')

    @patch('lambda_code.insert_product.insert_product')
    def test_insert_product_success(self, mock_insert_product):
        """Test successful product creation."""
        # Arrange
        new_product_data = {
            'title': 'Gaming Mouse',
            'price': 79.99,
            'category': 'Electronics',
            'description': 'Ergonomic gaming mouse'
        }
        
        mock_insert_product.return_value = {
            'id': 'prod_456',
            **new_product_data
        }
        
        create_event = {
            'httpMethod': 'POST',
            'body': json.dumps(new_product_data)
        }
        
        # Act
        from lambda_code.insert_product import handler
        response = handler(create_event, None)
        
        # Assert
        self.assertEqual(response['statusCode'], 201)
        
        body = json.loads(response['body'])
        self.assertEqual(body['title'], 'Gaming Mouse')
        self.assertIn('id', body)


# Testing with event factory
class TestProductAPI(unittest.TestCase):
    def test_get_product_with_factory(self):
        """Test using event factory for cleaner test code."""
        from tests import event_factory

        event = event_factory.APIGatewayEventFactory.create_get_product_event('prod_123')
        
        with patch('lambda_code.get_product.get_product') as mock_get:
            mock_get.return_value = {'id': 'prod_123', 'title': 'Test Product'}
            
            from lambda_code.get_product import handler
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 200)