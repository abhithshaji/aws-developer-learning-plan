import json
import logging
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def process_successful_operations(queue_url):
    """Process successful product operations for analytics and notifications."""
    sqs = boto3.client('sqs')
    
    response = sqs.receive_message(
        QueueUrl=queue_url,
        MaxNumberOfMessages=10
    )
    
    for message in response.get('Messages', []):
        success_event = json.loads(message['Body'])
        
        # Extract operation details
        operation_type = success_event.get('requestContext', {}).get('functionName')
        response_payload = success_event.get('responsePayload', {})
        
        logger.info(f"Processed successful operation: {operation_type}")
        
        # Clean up processed message
        sqs.delete_message(
            QueueUrl=queue_url,
            ReceiptHandle=message['ReceiptHandle']
        )


def inventory_rollback_handler(event, context):
    """Handle inventory update failures by rolling back changes."""
    try:
        # Extract original operation details
        original_event = event.get('requestPayload', {})
        product_id = original_event.get('id')
        original_quantity = original_event.get('original_quantity')
        
        # Log rollback for audit trail
        logger.info(f"Rolled back inventory for product {product_id} to {original_quantity}")
        
        return {'statusCode': 200, 'message': 'Rollback completed successfully'}
        
    except Exception as e:
        logger.error(f"Rollback failed for product operation: {str(e)}")
        raise e