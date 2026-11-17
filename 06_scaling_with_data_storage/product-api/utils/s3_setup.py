import os
import uuid
import boto3
from typing import Optional

# Initialize S3 client outside handler for reuse
try:
    s3_client = boto3.client('s3')
except Exception:
    s3_client = None


def create_product_images_bucket():
    bucket_name = f'assets-bucket-{uuid.uuid4()}'

    # Use Region-specific endpoint, fallback to environment or us-east-1
    region = (
        boto3.session.Session().region_name
        or os.environ.get('AWS_REGION')
        or os.environ.get('AWS_DEFAULT_REGION')
        or 'us-east-1'
    )

    try:
        # Create bucket (us-east-1 must omit CreateBucketConfiguration)
        if region == 'us-east-1':
            s3_client.create_bucket(Bucket=bucket_name)
        else:
            s3_client.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={
                    'LocationConstraint': region
                }
            )

        # Enable versioning for data protection
        s3_client.put_bucket_versioning(
            Bucket=bucket_name,
            VersioningConfiguration={
                'Status': 'Enabled'
            }
        )

        # Configure public access block for security
        s3_client.put_public_access_block(
            Bucket=bucket_name,
            PublicAccessBlockConfiguration={
                'BlockPublicAcls': True,
                'IgnorePublicAcls': True,
                'BlockPublicPolicy': False,  # Allow bucket policies
                'RestrictPublicBuckets': False
            }
        )

        print(f"Bucket {bucket_name} created with versioning and access controls")
        return bucket_name
    except Exception as e:
        print(f"Error creating bucket: {e}")
        return None


def configure_s3_event_notification() -> bool:
    """Configure S3 bucket to trigger Lambda function on object creation.
    
    Filters events to only trigger for 'products/' prefix and '.jpg' suffix.
    """
    
    product_image_bucket = os.environ.get('PRODUCT_IMAGE_BUCKET')
    lambda_function_arn  = os.environ.get('LAMBDA_FUNCTION_ARN')
    
    if not product_image_bucket or not lambda_function_arn:
        print("Missing PRODUCT_IMAGE_BUCKET or LAMBDA_FUNCTION_ARN")
        return False

    try:
        # Configure S3 to trigger Lambda on object creation
        s3_client.put_bucket_notification_configuration(
            Bucket=product_image_bucket,
            NotificationConfiguration={
                'LambdaFunctionConfigurations': [
                    {
                        'Id': 'ProcessProductImageUpload',
                        'LambdaFunctionArn': lambda_function_arn,
                        'Events': ['s3:ObjectCreated:*'],
                        'Filter': {
                            'Key': {
                                'FilterRules': [
                                    {
                                        'Name': 'prefix',
                                        'Value': 'products/'
                                    },
                                    {
                                        'Name': 'suffix',
                                        'Value': '.jpg'
                                    }
                                ]
                            }
                        }
                    }
                ]
            }
        )
        print("S3 event notification configured successfully")
        return True
        
    except Exception as e:
        print(f"Error configuring S3 events: {e}")
        return False
