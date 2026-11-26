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
    product_image_bucket = os.environ.get('PRODUCT_IMAGE_BUCKET', '')
    
    # Extract product ID and image type safely
    path_parameters = event.get('pathParameters') or {}
    query_parameters = event.get('queryStringParameters') or {}
    
    product_id = path_parameters.get('id')
    if not product_id:
        return create_error_response(400, 'Product id is required')
        
    image_type = query_parameters.get('type', 'main')
    
    # Generate unique object key
    object_key = f"products/{product_id}/{image_type}.jpg"
    
    client = s3_client or boto3.client(
        's3',
        config=Config(signature_version='s3v4', s3={'addressing_style': 'virtual'})
    )
    
    try:
        # Generate presigned URL for PUT operation
        presigned_url = client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': product_image_bucket,
                'Key': object_key,
                'ContentType': 'image/jpeg'
            },
            ExpiresIn=3600  # URL expires in 1 hour
        )
        
        return create_success_response(
            200,
            {
                'upload_url': presigned_url,
                'object_key': object_key,
                'expires_in': 3600
            }
        )
        
    except ClientError as e:
        return create_error_response(
            500,
            f"Failed to generate upload URL: {str(e)}"
        )
