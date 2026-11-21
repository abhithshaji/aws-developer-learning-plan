import boto3
import json
import os
from utils.response_utils import create_error_response, create_success_response

# Initialize clients outside handler for reuse
try:
    dynamodb = boto3.resource('dynamodb')
except Exception:
    dynamodb = None


def handler(event, context):
    """Update a product's record in DynamoDB with a newly uploaded S3 image URL."""
    
    product_table = dynamodb.Table(os.environ.get('PRODUCT_TABLE', 'Products'))
    
    product_id = event.get('pathParameters').get('id')
    if not product_id:
        return create_error_response(400, 'Product id is required')

    # Parse request body (supports both API Gateway string or direct dict)
    raw_body = event.get('body') or {}
    if isinstance(raw_body, str):
        try:
            body = json.loads(raw_body)
        except json.JSONDecodeError:
            return create_error_response(400, 'Invalid JSON body')
    elif isinstance(raw_body, dict):
        body = raw_body
    else:
        body = {}

    image_key = body.get('image_key')
    if not image_key:
        return create_error_response(400, 'image_key is required in request body')

    # Construct the public URL for the image
    bucket_name = os.environ.get('PRODUCT_IMAGE_BUCKET', '')
    region = (
        boto3.session.Session().region_name
        or os.environ.get('AWS_REGION')
        or os.environ.get('AWS_DEFAULT_REGION')
        or 'us-east-1'
    )
    image_url = f"https://{bucket_name}.s3.{region}.amazonaws.com/{image_key}"
    
    
    try:
        # Update the product with the new image URL
        response = product_table.update_item(
            Key={'id': product_id},
            UpdateExpression='SET image_urls = list_append(if_not_exists(image_urls, :empty_list), :new_image)',
            ExpressionAttributeValues={
                ':empty_list': [],
                ':new_image': [image_url]
            },
            ReturnValues='UPDATED_NEW'
        )
        
        return create_success_response(
            200,
            {
                'message': 'Product image updated successfully',
                'image_url': image_url
            }
        )
        
    except Exception as e:
        return create_error_response(
            500,
            f"Failed to update product: {str(e)}"
        )


# Alias matching tutorial naming
update_product_images = handler
