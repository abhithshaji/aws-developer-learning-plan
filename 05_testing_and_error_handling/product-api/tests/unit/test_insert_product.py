import unittest
import json
from unittest.mock import patch
import os

# Ensure boto3 does not fail on import if products_db initializes DynamoDB at module level
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")

class TestInsertProduct(unittest.TestCase):
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