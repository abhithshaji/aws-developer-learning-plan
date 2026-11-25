import boto3
import json
from datetime import datetime, timezone


def create_order_processing_queue():
    """Create SQS queue for background order processing."""
    sqs = boto3.client('sqs')
    
    # Create main order processing queue
    queue_response = sqs.create_queue(
        QueueName='order-processing-queue',
        Attributes={
            'VisibilityTimeoutSeconds': '300',  # 5 minutes for processing
            'MessageRetentionPeriod': '1209600',  # 14 days
            'ReceiveMessageWaitTimeSeconds': '20',  # Long polling
            'RedrivePolicy': json.dumps({
                'deadLetterTargetArn': 'arn:aws:sqs:region:account:order-processing-dlq',
                'maxReceiveCount': 3
            })
        }
    )
    
    # Create dead letter queue for failed messages
    dlq_response = sqs.create_queue(
        QueueName='order-processing-dlq',
        Attributes={
            'MessageRetentionPeriod': '1209600',  # 14 days for investigation
            'VisibilityTimeoutSeconds': '60'
        }
    )
    
    return queue_response['QueueUrl'], dlq_response['QueueUrl']


def send_order_to_queue(order_data, queue_url):
    """Send order data to SQS queue for background processing."""
    sqs = boto3.client('sqs')
    
    message_body = {
        'order_id': order_data['order_id'],
        'customer_id': order_data['customer_id'],
        'items': order_data['items'],
        'total_amount': order_data['total_amount'],
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'processing_steps': [
            'validate_inventory',
            'process_payment',
            'create_shipping_label',
            'send_confirmation'
        ]
    }
    
    response = sqs.send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps(message_body),
        MessageAttributes={
            'order_priority': {
                'StringValue': order_data.get('priority', 'standard'),
                'DataType': 'String'
            },
            'customer_tier': {
                'StringValue': order_data.get('customer_tier', 'regular'),
                'DataType': 'String'
            }
        }
    )
    
    return response['MessageId']
