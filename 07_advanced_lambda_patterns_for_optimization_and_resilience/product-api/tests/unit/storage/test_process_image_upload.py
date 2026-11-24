import os

# Set mock AWS credentials before any boto3 import
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_SECURITY_TOKEN"] = "testing"
os.environ["AWS_SESSION_TOKEN"] = "testing"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["PRODUCT_TABLE"] = "Products"

import json
import unittest
from moto import mock_aws
import boto3
from lambda_code.process_image_upload import handler


class TestProcessImageUpload(unittest.TestCase):
    """Test suite for process_image_upload Lambda handler."""

    def setUp(self):
        self.table_name = "Products"
        self.bucket_name = "test-product-images"
        os.environ["PRODUCT_TABLE"] = self.table_name

    @mock_aws
    def _setup_resources(self):
        # S3
        s3 = boto3.client('s3', region_name='us-east-1')
        s3.create_bucket(Bucket=self.bucket_name)

        # DynamoDB
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = dynamodb.create_table(
            TableName=self.table_name,
            KeySchema=[{'AttributeName': 'id', 'KeyType': 'HASH'}],
            AttributeDefinitions=[{'AttributeName': 'id', 'AttributeType': 'S'}],
            BillingMode='PAY_PER_REQUEST'
        )
        return s3, dynamodb, table

    @mock_aws
    def test_process_image_upload_success(self):
        """Test processing standard S3 event record and updating DynamoDB metadata."""
        s3, dynamodb, table = self._setup_resources()

        # Seed product
        table.put_item(Item={'id': 'prod_123', 'title': 'Test Product'})

        # Put mock image in S3
        image_content = b'test-image-binary-content-12345'
        s3.put_object(
            Bucket=self.bucket_name,
            Key='products/prod_123/main.jpg',
            Body=image_content,
            ContentType='image/jpeg'
        )

        event = {
            'Records': [
                {
                    's3': {
                        'bucket': {'name': self.bucket_name},
                        'object': {'key': 'products/prod_123/main.jpg'}
                    }
                }
            ]
        }

        response = handler(event, None)
        self.assertEqual(response['statusCode'], 200)

        # Verify DynamoDB record was updated
        item = table.get_item(Key={'id': 'prod_123'}).get('Item')
        self.assertIsNotNone(item)
        self.assertIn('image_url', item)
        self.assertEqual(
            item['image_url'],
            f"https://{self.bucket_name}.s3.amazonaws.com/products/prod_123/main.jpg"
        )
        self.assertEqual(item['file_size'], len(image_content))
        self.assertIn('upload_date', item)

    @mock_aws
    def test_process_image_upload_with_bucket_title(self):
        """Test processing S3 event record using tutorial's 'title' key for bucket."""
        s3, dynamodb, table = self._setup_resources()
        table.put_item(Item={'id': 'prod_456', 'title': 'Another Product'})

        image_content = b'another-image-binary'
        s3.put_object(
            Bucket=self.bucket_name,
            Key='products/prod_456/main.jpg',
            Body=image_content,
            ContentType='image/jpeg'
        )

        event = {
            'Records': [
                {
                    's3': {
                        'bucket': {'title': self.bucket_name},  # Tutorial typo compatibility
                        'object': {'key': 'products/prod_456/main.jpg'}
                    }
                }
            ]
        }

        response = handler(event, None)
        self.assertEqual(response['statusCode'], 200)

        item = table.get_item(Key={'id': 'prod_456'}).get('Item')
        self.assertEqual(item['file_size'], len(image_content))

    @mock_aws
    def test_process_image_upload_invalid_key_format(self):
        """Test graceful skipping when object key format does not include product id."""
        _, _, _ = self._setup_resources()

        event = {
            'Records': [
                {
                    's3': {
                        'bucket': {'name': self.bucket_name},
                        'object': {'key': 'invalid_root_file.jpg'}
                    }
                }
            ]
        }

        response = handler(event, None)
        self.assertEqual(response['statusCode'], 200)

    @mock_aws
    def test_process_image_upload_non_existent_s3_object(self):
        """Test error handling when object is missing from S3 (head_object fails)."""
        _, _, table = self._setup_resources()
        table.put_item(Item={'id': 'prod_789', 'title': 'Missing Image Product'})

        event = {
            'Records': [
                {
                    's3': {
                        'bucket': {'name': self.bucket_name},
                        'object': {'key': 'products/prod_789/nonexistent.jpg'}
                    }
                }
            ]
        }

        # Should log error and still complete without throwing unhandled exception
        response = handler(event, None)
        self.assertEqual(response['statusCode'], 200)


if __name__ == '__main__':
    unittest.main()
