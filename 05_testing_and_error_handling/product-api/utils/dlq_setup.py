import boto3

def setup_dead_letter_queue():
    """Create and configure dead-letter queue for failed Lambda invocations."""
    sqs = boto3.client('sqs')
    
    # Create dead-letter queue
    dlq_response = sqs.create_queue(
        QueueName='product-api-dlq',
        Attributes={
            'MessageRetentionPeriod': '1209600',  # 14 days
            'VisibilityTimeoutSeconds': '300',    # 5 minutes
            'ReceiveMessageWaitTimeSeconds': '20' # Long polling
        }
    )
    
    dlq_url = dlq_response['QueueUrl']
    
    # Get queue attributes for Lambda configuration
    dlq_attributes = sqs.get_queue_attributes(
        QueueUrl=dlq_url,
        AttributeNames=['QueueArn']
    )
    
    return dlq_attributes['Attributes']['QueueArn']


def configure_lambda_with_dlq(function_name, dlq_arn):
    """Configure Lambda function to use dead-letter queue."""
    lambda_client = boto3.client('lambda')
    
    lambda_client.update_function_configuration(
        FunctionName=function_name,
        DeadLetterConfig={
            'TargetArn': dlq_arn
        }
    )