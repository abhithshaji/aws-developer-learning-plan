import unittest
import boto3
from moto import mock_aws
from decimal import Decimal
import os

# Ensure boto3 does not fail on import if products_db initializes DynamoDB at module level
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")

@mock_aws
class TestProductDatabase(unittest.TestCase):
    def setUp(self):
        """Set up mock DynamoDB table for testing."""
        # Create mock DynamoDB resource
        self.dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        
        # Create mock table with same structure as production
        self.table = self.dynamodb.create_table(
            TableName='Products',
            KeySchema=[
                {'AttributeName': 'id', 'KeyType': 'HASH'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'id', 'AttributeType': 'S'}
            ],
            BillingMode='PAY_PER_REQUEST'
        )
        
        # Populate with test data
        self.seed_test_data()
    
    def seed_test_data(self):
        """Add sample products for testing."""
        test_products = [
            {
                'id': 'prod_001',
                'title': 'Wireless Headphones',
                'price': Decimal('199.99'),
                'category': 'Electronics',
                'inventory_count': 50
            },
            {
                'id': 'prod_002',
                'title': 'Running Shoes',
                'price': Decimal('129.99'),
                'category': 'Sports',
                'inventory_count': 25
            }
        ]
        
        for product in test_products:
            self.table.put_item(Item=product)
    
    def test_get_product_from_mock_table(self):
        """Test product retrieval from mocked DynamoDB."""
        from db.products_db import get_product
        
        # Test existing product
        product = get_product('prod_001')
        self.assertIsNotNone(product)
        self.assertEqual(product['title'], 'Wireless Headphones')
        
        # Test non-existent product
        product = get_product('nonexistent')
        self.assertIsNone(product)
    
    def test_insert_product_in_mock_table(self):
        """Test product creation in mocked DynamoDB."""
        from db.products_db import insert_product,  get_product
        
        new_product = {
            'id': 'prod_003',
            'title': 'Gaming Mouse',
            'price': Decimal('79.99'),
            'category': 'Electronics',
            'description': 'High precision gaming mouse'
        }
        
        created_product = insert_product(new_product,"test-arn")
        
        # Verify product was created with generated ID
        self.assertIn('id', created_product)
        self.assertEqual(created_product['title'], 'Gaming Mouse')
        
        # Verify product exists in table
        retrieved = get_product(created_product['id'])
        self.assertEqual(retrieved['title'], 'Gaming Mouse')