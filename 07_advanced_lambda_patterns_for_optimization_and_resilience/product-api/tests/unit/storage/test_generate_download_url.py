import os

# Set mock AWS credentials before any boto3 import
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_SECURITY_TOKEN"] = "testing"
os.environ["AWS_SESSION_TOKEN"] = "testing"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["PRODUCT_IMAGE_BUCKET"] = "test-product-images"

import json
import unittest
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError
from moto import mock_aws
import boto3
from lambda_code.generate_download_url import handler


class TestGenerateDownloadUrl(unittest.TestCase):
    """Test suite for the generate_download_url Lambda handler."""

    def setUp(self):
        self.bucket_name = "test-product-images"
        os.environ["PRODUCT_IMAGE_BUCKET"] = self.bucket_name

    @mock_aws
    def test_generate_download_url_success_default_type(self):
        """Test generating presigned download GET URL with default 'main' image type."""
        s3 = boto3.client('s3', region_name='us-east-1')
        s3.create_bucket(Bucket=self.bucket_name)

        event = {
            'pathParameters': {'id': 'prod_001'},
            'queryStringParameters': None
        }

        response = handler(event, None)
        self.assertEqual(response['statusCode'], 200)

        body = json.loads(response['body'])
        self.assertIn('download_url', body)
        self.assertEqual(body['object_key'], 'products/prod_001/main.jpg')
        self.assertEqual(body['expires_in'], 3600)
        self.assertIn('https://', body['download_url'])
        self.assertIn(self.bucket_name, body['download_url'])

    @mock_aws
    def test_generate_download_url_custom_type(self):
        """Test generating presigned download GET URL with custom image type."""
        s3 = boto3.client('s3', region_name='us-east-1')
        s3.create_bucket(Bucket=self.bucket_name)

        event = {
            'pathParameters': {'id': 'prod_002'},
            'queryStringParameters': {'type': 'gallery'}
        }

        response = handler(event, None)
        self.assertEqual(response['statusCode'], 200)

        body = json.loads(response['body'])
        self.assertEqual(body['object_key'], 'products/prod_002/gallery.jpg')

    def test_generate_download_url_missing_product_id(self):
        """Test 400 Bad Request when product ID is missing."""
        event = {
            'pathParameters': {},
            'queryStringParameters': None
        }

        response = handler(event, None)
        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertIn('error', body)

    @patch('boto3.client')
    def test_generate_download_url_client_error(self, mock_boto_client):
        """Test 404 response when S3 ClientError occurs."""
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.side_effect = ClientError(
            {'Error': {'Code': 'NoSuchKey', 'Message': 'The specified key does not exist'}},
            'generate_presigned_url'
        )
        mock_boto_client.return_value = mock_s3

        with patch('lambda_code.generate_download_url.s3_client', mock_s3):
            event = {
                'pathParameters': {'id': 'prod_001'},
                'queryStringParameters': {'type': 'main'}
            }
            response = handler(event, None)
            self.assertEqual(response['statusCode'], 404)
            body = json.loads(response['body'])
            self.assertIn('Image not found', body['error'])


if __name__ == '__main__':
    unittest.main()
