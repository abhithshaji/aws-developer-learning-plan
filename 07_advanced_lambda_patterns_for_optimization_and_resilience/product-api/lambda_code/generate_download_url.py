import boto3
import json
import os
from botocore.exceptions import ClientError
from botocore.config import Config
from utils.response_utils import create_error_response, create_success_response

# Initialize S3 client outside handler for reuse. The Config below signs presigned
# URLs with your Region's endpoint, which every Region except us-east-1 requires.
try:
    s3_client = boto3.client(
        's3',
        config=Config(signature_version='s3v4', s3={'addressing_style': 'virtual'})
    )
except Exception:
    s3_client = None


def handler(event, context):
    """Generate a presigned GET URL for secure product image downloads."""
    product_image_bucket = os.environ.get('PRODUCT_IMAGE_BUCKET', '')
    
    # Safely extract path and query parameters
    path_parameters = event.get('pathParameters') or {}
    query_parameters = event.get('queryStringParameters') or {}
    
    product_id = path_parameters.get('id')
    if not product_id:
        return create_error_response(400, 'Product id is required')
        
    image_type = query_parameters.get('type', 'main')
    object_key = f"products/{product_id}/{image_type}.jpg"
    
    client = s3_client or boto3.client(
        's3',
        config=Config(signature_version='s3v4', s3={'addressing_style': 'virtual'})
    )
    
    try:
        # Generate presigned URL for GET operation
        download_url = client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': product_image_bucket,
                'Key': object_key
            },
            ExpiresIn=3600  # URL expires in 1 hour
        )
        
        return create_success_response(
            200,
            {
                'download_url': download_url,
                'object_key': object_key,
                'expires_in': 3600
            }
        )
        
    except ClientError as e:
        return create_error_response(
            404,
            f"Image not found: {str(e)}"
        )


# Alias matching tutorial naming
generate_download_url = handler
