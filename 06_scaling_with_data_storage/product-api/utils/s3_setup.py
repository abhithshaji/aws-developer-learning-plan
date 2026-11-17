import os
import uuid
import boto3

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
