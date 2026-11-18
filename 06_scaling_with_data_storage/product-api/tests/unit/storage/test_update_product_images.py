import os

# Set mock AWS credentials before any boto3 import
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_SECURITY_TOKEN"] = "testing"
os.environ["AWS_SESSION_TOKEN"] = "testing"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["PRODUCT_TABLE"] = "Products"
os.environ["PRODUCT_IMAGE_BUCKET"] = "test-product-images"

import json
import unittest
from moto import mock_aws
import boto3
from lambda_code.update_product_images import handler


class TestUpdateProductImages(unittest.TestCase):
    """Test suite for update_product_images Lambda handler."""

    def setUp(self):
        self.table_name = "Products"
        self.bucket_name = "test-product-images"
        os.environ["PRODUCT_TABLE"] = self.table_name
        os.environ["PRODUCT_IMAGE_BUCKET"] = self.bucket_name

    @mock_aws
    def _create_mock_table(self):
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = dynamodb.create_table(
            TableName=self.table_name,
            KeySchema=[{'AttributeName': 'id', 'KeyType': 'HASH'}],
            AttributeDefinitions=[{'AttributeName': 'id', 'AttributeType': 'S'}],
            BillingMode='PAY_PER_REQUEST'
        )
        return dynamodb, table

    @mock_aws
    def test_update_product_images_success(self):
        """Test linking a new image URL to an existing product."""
        dynamodb, table = self._create_mock_table()
        table.put_item(Item={'id': 'prod_001', 'title': 'Wireless Headphones'})

        event = {
            'pathParameters': {'id': 'prod_001'},
            'body': json.dumps({'image_key': 'products/prod_001/main.jpg'})
        }

        response = handler(event, None)
        self.assertEqual(response['statusCode'], 200)

        body = json.loads(response['body'])
        expected_url = f"https://{self.bucket_name}.s3.us-east-1.amazonaws.com/products/prod_001/main.jpg"
        self.assertEqual(body['image_url'], expected_url)
        self.assertEqual(body['message'], 'Product image updated successfully')

        # Verify DynamoDB record was updated with image_urls list
        item = table.get_item(Key={'id': 'prod_001'}).get('Item')
        self.assertIn('image_urls', item)
        self.assertEqual(item['image_urls'], [expected_url])

    @mock_aws
    def test_update_product_images_append_multiple(self):
        """Test appending multiple image URLs to the image_urls list."""
        dynamodb, table = self._create_mock_table()
        table.put_item(Item={'id': 'prod_001', 'title': 'Wireless Headphones'})

        # First image
        handler({
            'pathParameters': {'id': 'prod_001'},
            'body': json.dumps({'image_key': 'products/prod_001/main.jpg'})
        }, None)

        # Second image
        event2 = {
            'pathParameters': {'id': 'prod_001'},
            'body': {'image_key': 'products/prod_001/side.jpg'}  # Test direct dict body
        }
        response2 = handler(event2, None)
        self.assertEqual(response2['statusCode'], 200)

        item = table.get_item(Key={'id': 'prod_001'}).get('Item')
        self.assertEqual(len(item['image_urls']), 2)
        self.assertIn('products/prod_001/main.jpg', item['image_urls'][0])
        self.assertIn('products/prod_001/side.jpg', item['image_urls'][1])

    def test_update_product_images_missing_product_id(self):
        """Test 400 Bad Request when product id is missing."""
        event = {
            'pathParameters': {},
            'body': json.dumps({'image_key': 'products/prod_001/main.jpg'})
        }
        response = handler(event, None)
        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertIn('error', body)

    def test_update_product_images_missing_image_key(self):
        """Test 400 Bad Request when image_key is missing from body."""
        event = {
            'pathParameters': {'id': 'prod_001'},
            'body': json.dumps({})
        }
        response = handler(event, None)
        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertIn('image_key is required', body['error'])

    def test_update_product_images_invalid_json(self):
        """Test 400 Bad Request when body is malformed JSON."""
        event = {
            'pathParameters': {'id': 'prod_001'},
            'body': '{malformed:json'
        }
        response = handler(event, None)
        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertIn('Invalid JSON body', body['error'])

    @mock_aws
    def test_update_product_images_table_error(self):
        """Test 500 error when DynamoDB operation fails (e.g. table doesn't exist)."""
        # Note: Do not create the table so update_item fails
        event = {
            'pathParameters': {'id': 'prod_001'},
            'body': json.dumps({'image_key': 'products/prod_001/main.jpg'})
        }
        response = handler(event, None)
        self.assertEqual(response['statusCode'], 500)
        body = json.loads(response['body'])
        self.assertIn('error', body)


if __name__ == '__main__':
    unittest.main()
