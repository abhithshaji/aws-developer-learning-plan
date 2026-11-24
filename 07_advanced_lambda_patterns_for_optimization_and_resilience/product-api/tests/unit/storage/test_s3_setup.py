import os

# Set mock AWS credentials before any boto3 import
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_SECURITY_TOKEN"] = "testing"
os.environ["AWS_SESSION_TOKEN"] = "testing"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

import unittest
import boto3
from moto import mock_aws
import utils.s3_setup
from utils.s3_setup import create_product_images_bucket, configure_s3_event_notification


class TestS3Setup(unittest.TestCase):
    """Test suite for S3 bucket creation and configuration utilities."""

    @mock_aws
    def test_create_product_images_bucket_us_east_1(self):
        """Test bucket creation in us-east-1 with versioning and access blocks."""
        os.environ['AWS_REGION'] = 'us-east-1'
        os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'
        client = boto3.client('s3', region_name='us-east-1')
        utils.s3_setup.s3_client = client

        bucket_name = create_product_images_bucket()

        self.assertIsNotNone(bucket_name)
        self.assertTrue(bucket_name.startswith('assets-bucket-'))

        # Verify bucket exists
        buckets = [b['Name'] for b in client.list_buckets().get('Buckets', [])]
        self.assertIn(bucket_name, buckets)

        # Verify versioning is enabled
        versioning = client.get_bucket_versioning(Bucket=bucket_name)
        self.assertEqual(versioning.get('Status'), 'Enabled')

        # Verify public access block configuration
        pab = client.get_public_access_block(Bucket=bucket_name)
        config = pab.get('PublicAccessBlockConfiguration', {})
        self.assertTrue(config.get('BlockPublicAcls'))
        self.assertTrue(config.get('IgnorePublicAcls'))
        self.assertFalse(config.get('BlockPublicPolicy'))
        self.assertFalse(config.get('RestrictPublicBuckets'))

    @mock_aws
    def test_create_product_images_bucket_other_region(self):
        """Test bucket creation in non us-east-1 region (e.g. us-west-2)."""
        os.environ['AWS_REGION'] = 'us-west-2'
        os.environ['AWS_DEFAULT_REGION'] = 'us-west-2'
        client = boto3.client('s3', region_name='us-west-2')
        utils.s3_setup.s3_client = client

        bucket_name = create_product_images_bucket()

        self.assertIsNotNone(bucket_name)
        self.assertTrue(bucket_name.startswith('assets-bucket-'))

        # Verify bucket exists in region
        buckets = [b['Name'] for b in client.list_buckets().get('Buckets', [])]
        self.assertIn(bucket_name, buckets)

    @mock_aws
    def test_configure_s3_event_notification_success(self):
        """Test configuring S3 event notification on object creation."""
        client = boto3.client('s3', region_name='us-east-1')
        bucket_name = "test-event-bucket"
        client.create_bucket(Bucket=bucket_name)

        lambda_arn = "arn:aws:lambda:us-east-1:123456789012:function:process-image"
        
        os.environ['PRODUCT_IMAGE_BUCKET'] = bucket_name
        os.environ['LAMBDA_FUNCTION_ARN'] = lambda_arn

        success = configure_s3_event_notification()
        self.assertTrue(success)

        # Verify notification configuration
        notif = client.get_bucket_notification_configuration(Bucket=bucket_name)
        self.assertIn('LambdaFunctionConfigurations', notif)
        configs = notif['LambdaFunctionConfigurations']
        self.assertEqual(len(configs), 1)
        self.assertEqual(configs[0]['LambdaFunctionArn'], lambda_arn)
        self.assertIn('s3:ObjectCreated:*', configs[0]['Events'])

    def test_configure_s3_event_notification_missing_env(self):
        """Test failure when required environment variables or arguments are missing."""
        old_bucket = os.environ.pop('PRODUCT_IMAGE_BUCKET', None)
        old_arn = os.environ.pop('LAMBDA_FUNCTION_ARN', None)
        try:
            success = configure_s3_event_notification()
            self.assertFalse(success)
        finally:
            if old_bucket:
                os.environ['PRODUCT_IMAGE_BUCKET'] = old_bucket
            if old_arn:
                os.environ['LAMBDA_FUNCTION_ARN'] = old_arn


if __name__ == '__main__':
    unittest.main()
