import json
import boto3
import os
from datetime import datetime

# Initialize clients outside handler for reuse
try:
    s3_client = boto3.client('s3')
except Exception:
    s3_client = None

try:
    dynamodb = boto3.resource('dynamodb')
except Exception:
    dynamodb = None


def handler(event, context):
    """Process S3 object creation events and update product records with image metadata."""
    
    product_table = dynamodb.Table(os.environ.get('PRODUCT_TABLE', 'Products'))
    
    records = event.get('Records') or []
    
    # Process each S3 event record
    for record in records:
        s3_info = record.get('s3', {})
        bucket_data = s3_info.get('bucket', {})
        
        # Support both standard S3 event schema ('name') and tutorial snippet ('title')
        bucket_name = bucket_data.get('name') or bucket_data.get('title')
        object_key = s3_info.get('object', {}).get('key')
        
        if not bucket_name or not object_key:
            continue
            
        try:
            # Extract product ID from object key
            # Format: products/prod_123/main.jpg
            parts = object_key.split('/')
            if len(parts) < 2:
                print(f"Key does not match expected structure: {object_key}")
                continue
            product_id = parts[1]
            
            # Get image metadata without downloading the file
            response = s3_client.head_object(Bucket=bucket_name, Key=object_key)
            file_size = response['ContentLength']
            content_type = response.get('ContentType', 'image/jpeg')
            
            # Create image URL
            image_url = f"https://{bucket_name}.s3.amazonaws.com/{object_key}"
            
            # Update product record with image information
            product_table.update_item(
                Key={'id': product_id},
                UpdateExpression='SET image_url = :img, file_size = :size, upload_date = :date',
                ExpressionAttributeValues={
                    ':img': image_url,
                    ':size': file_size,
                    ':date': datetime.now().isoformat()
                }
            )
            
            # TODO: To do this in production, you would choose from the following:
            # 1. Use AWS Lambda layers with image processing libraries such as Pillow
            # 2. Invoke another service like AWS Batch for heavy processing
            # 3. Use Amazon Rekognition for image analysis
            # 4. Start an AWS Step Functions workflow for complex workflows
            
            print(f"Processed image metadata for product {product_id}")
            
        except Exception as e:
            print(f"Error processing {object_key}: {e}")
    
    return {
        'statusCode': 200,
        'body': json.dumps('Image metadata processed successfully')
    }


# Alias matching tutorial naming
process_image_upload = handler
