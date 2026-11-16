import json
import logging
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def analyze_failure(failed_event):
    """Analyze failed event to determine if retry is appropriate."""
    error_message = failed_event.get('errorMessage', '')
    
    # Classify error types
    if 'timeout' in error_message.lower() or 'timed out' in error_message.lower():
        return {'retryable': True, 'reason': 'timeout', 'delay': 300}
    
    elif 'rate limit' in error_message.lower():
        return {'retryable': True, 'reason': 'rate_limit', 'delay': 600}
    
    elif 'validation' in error_message.lower():
        return {'retryable': False, 'reason': 'validation_error'}
    
    elif 'not found' in error_message.lower():
        return {'retryable': False, 'reason': 'resource_not_found'}
    
    else:
        return {'retryable': True, 'reason': 'unknown', 'delay': 900}


def process_dead_letter_queue_messages(dlq_url):
    """Process and analyze messages from dead-letter queue."""
    sqs = boto3.client('sqs')
    
    while True:
        # Receive messages from DLQ
        response = sqs.receive_message(
            QueueUrl=dlq_url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=20,
            MessageAttributeNames=['All']
        )
        
        messages = response.get('Messages', [])
        if not messages:
            break
        
        for message in messages:
            try:
                # Parse failed Lambda invocation
                failed_event = json.loads(message['Body'])
                
                # Analyze failure reason
                failure_analysis = analyze_failure(failed_event)
                
                # Log analysis for investigation
                logger.info(f"Analyzed failure: {failure_analysis}")
                
                # If retryable, process retry or delete
                if failure_analysis['retryable']:
                    logger.info("Message is retryable")
                else:
                    logger.warning(f"Non-retryable failure: {failure_analysis['reason']}")
                
                # Delete message from DLQ once handled
                sqs.delete_message(
                    QueueUrl=dlq_url,
                    ReceiptHandle=message['ReceiptHandle']
                )
                
            except Exception as e:
                logger.error(f"Error processing DLQ message: {str(e)}")