from moto import mock_aws
import unittest
import json
from unittest.mock import patch
import os
import boto3

# Ensure boto3 does not fail on import if products_db initializes DynamoDB at module level
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")

class TestProductErrorHandling(unittest.TestCase):
    
    @patch('lambda_code.get_product.get_product')
    def test_get_product_not_found(self, mock_get_product):
        """Test handling of non-existent product requests."""
        # Arrange
        mock_get_product.return_value = None
        
        event = {
            'httpMethod': 'GET',
            'pathParameters': {'id': 'nonexistent_product'}
        }
        
        # Act
        from lambda_code.get_product import handler
        response = handler(event, None)
        
        # Assert
        self.assertEqual(response['statusCode'], 404)
        
        body = json.loads(response['body'])
        self.assertIn('error', body)
        self.assertIn('Product not found', body['error'])

    def test_missing_path_parameters(self):
        """Test handling of malformed requests."""
        # Arrange
        invalid_event = {
            'httpMethod': 'GET',
            'pathParameters': None  # Missing required parameters
        }
        
        # Act
        from lambda_code.get_product import handler
        response = handler(invalid_event, None)
        
        # Assert
        self.assertEqual(response['statusCode'], 400)
        
        body = json.loads(response['body'])
        self.assertIn('error', body)
        self.assertIn('Product id is required', body['error'])

    @patch('lambda_code.insert_product.insert_product')
    def test_insert_product_validation_error(self, mock_insert_product):
        """Test product creation with invalid data."""
        # Arrange
        invalid_product = {
            'title': '',  # Empty name should fail validation
            'price': -10,  # Negative price should fail
            'category': 'InvalidCategory' # Invalid category fails validator
        }
        
        create_event = {
            'httpMethod': 'POST',
            'body': json.dumps(invalid_product)
        }
        
        # Act
        from lambda_code.insert_product import handler
        response = handler(create_event, None)
        
        # Assert
        self.assertEqual(response['statusCode'], 400)
        
        body = json.loads(response['body'])
        self.assertIn('error', body)
        self.assertIn('Validation failed', body['error'])

        
        # Verify database was not called with invalid data
        mock_insert_product.assert_not_called()

class TestDatabaseErrorHandling(unittest.TestCase):
    
    @patch('db.products_db.table.get_item')
    def test_dynamodb_connection_error(self, mock_get_item):
        """Test handling of DynamoDB connection failures."""
        # Simulate connection error
        mock_get_item.side_effect = Exception("Unable to connect to DynamoDB")
        
        from db.products_db import get_product
        
        with self.assertRaises(Exception) as context:
            get_product('prod_123')
        
        self.assertIn("Unable to connect", str(context.exception))
    
    @mock_aws
    def test_item_not_found_handling(self):
        """Test graceful handling of missing items."""
        # Set up empty table
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = dynamodb.create_table(
            TableName='Products',
            KeySchema=[{'AttributeName': 'id', 'KeyType': 'HASH'}],
            AttributeDefinitions=[{'AttributeName': 'id', 'AttributeType': 'S'}],
            BillingMode='PAY_PER_REQUEST'
        )
        
        import db.products_db as products_db
        products_db.table = table  #  Bind moto table
        
        # Test that missing item returns None instead of raising exception
        result = products_db.get_product('nonexistent_product')
        self.assertIsNone(result)