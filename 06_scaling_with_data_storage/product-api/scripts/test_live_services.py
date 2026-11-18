"""Live Integration Test Script for Module 06.

Executes the Lambda handlers locally using real AWS credentials against
live Amazon S3 and Amazon DynamoDB services.
"""
import os
import json
import urllib.request
import boto3

# 1. Resolve environment variables
region = (
    boto3.session.Session().region_name
    or os.environ.get('AWS_REGION')
    or os.environ.get('AWS_DEFAULT_REGION')
    or 'ap-southeast-2'
)
os.environ['AWS_DEFAULT_REGION'] = region
os.environ['AWS_REGION'] = region
os.environ['PRODUCT_TABLE'] = os.environ.get('PRODUCT_TABLE', 'Products')

from utils.s3_setup import create_product_images_bucket
from lambda_code.generate_presigned_url import handler as upload_url_handler
from lambda_code.generate_download_url import handler as download_url_handler
from lambda_code.update_product_images import handler as update_images_handler
from lambda_code.process_image_upload import handler as process_upload_handler

def run_live_test():
    print(f"🚀 Starting Live AWS Integration Test in Region: {region}")
    
    # Step 1: Ensure S3 Bucket Exists
    bucket_name = os.environ.get('PRODUCT_IMAGE_BUCKET')
    if not bucket_name:
        print("📦 Creating live S3 bucket for product images...")
        bucket_name = create_product_images_bucket()
        if not bucket_name:
            print("❌ Failed to create S3 bucket.")
            return
        os.environ['PRODUCT_IMAGE_BUCKET'] = bucket_name
    print(f"✅ Using S3 Bucket: {bucket_name}")

    # Ensure sample product exists in DynamoDB
    dynamodb = boto3.resource('dynamodb', region_name=region)
    table = dynamodb.Table(os.environ['PRODUCT_TABLE'])
    test_product_id = 'prod_001'
    print(f"📋 Verifying product '{test_product_id}' in DynamoDB table '{table.table_name}'...")
    table.update_item(
        Key={'id': test_product_id},
        UpdateExpression='SET title = if_not_exists(title, :title)',
        ExpressionAttributeValues={':title': 'Live Test Product'}
    )
    print(f"✅ Product '{test_product_id}' ready in DynamoDB.")

    # Step 2: Test Presigned Upload URL Handler
    print("\n🔑 Step 2: Generating Presigned Upload URL...")
    upload_event = {
        'pathParameters': {'id': test_product_id},
        'queryStringParameters': {'type': 'main'}
    }
    upload_response = upload_url_handler(upload_event, None)
    assert upload_response['statusCode'] == 200, f"Failed: {upload_response}"
    upload_body = json.loads(upload_response['body'])
    upload_url = upload_body['upload_url']
    object_key = upload_body['object_key']
    print(f"✅ Generated Upload URL for key: {object_key}")

    # Step 3: Upload Sample Image using Presigned URL
    print("\n📤 Step 3: Uploading test image to S3 via Presigned URL...")
    # Minimal 1x1 JPEG byte stream
    sample_jpeg = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\' \",#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9'
    
    req = urllib.request.Request(
        upload_url,
        data=sample_jpeg,
        headers={'Content-Type': 'image/jpeg'},
        method='PUT'
    )
    with urllib.request.urlopen(req) as resp:
        print(f"✅ S3 PUT Upload Response Code: {resp.status}")

    # Step 4: Test Presigned Download URL Handler
    print("\n📥 Step 4: Generating Presigned Download URL...")
    download_event = {
        'pathParameters': {'id': test_product_id},
        'queryStringParameters': {'type': 'main'}
    }
    download_response = download_url_handler(download_event, None)
    assert download_response['statusCode'] == 200, f"Failed: {download_response}"
    download_body = json.loads(download_response['body'])
    download_url = download_body['download_url']
    print(f"✅ Generated Download URL: {download_url[:60]}...")

    # Step 5: Test Linking Image URL in DynamoDB
    print("\n🔗 Step 5: Updating DynamoDB Product Image URLs...")
    update_event = {
        'pathParameters': {'id': test_product_id},
        'body': json.dumps({'image_key': object_key})
    }
    update_response = update_images_handler(update_event, None)
    assert update_response['statusCode'] == 200, f"Failed: {update_response}"
    print(f"✅ DynamoDB record updated with image list: {update_response['body']}")

    # Step 6: Test S3 Event-Driven Metadata Processing
    print("\n⚡ Step 6: Testing Event-Driven Image Metadata Processor...")
    s3_event = {
        'Records': [{
            's3': {
                'bucket': {'name': bucket_name},
                'object': {'key': object_key}
            }
        }]
    }
    process_response = process_upload_handler(s3_event, None)
    assert process_response['statusCode'] == 200, f"Failed: {process_response}"
    print(f"✅ Metadata processor succeeded: {process_response['body']}")

    # Step 7: Final Verification from DynamoDB
    print("\n🔍 Step 7: Inspecting updated record in DynamoDB...")
    final_item = table.get_item(Key={'id': test_product_id}).get('Item')
    print("Final DynamoDB Item State:")
    print(json.dumps(final_item, indent=2, default=str))
    print("\n🎉 ALL LIVE AWS INTEGRATION TESTS PASSED SUCCESSFULLY!")

if __name__ == '__main__':
    run_live_test()
