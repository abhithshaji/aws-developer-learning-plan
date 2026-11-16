import boto3

def configure_lambda_destinations(function_name, success_queue_arn=None, failure_queue_arn=None):
    """Configure Lambda Destinations for success and failure routing."""
    lambda_client = boto3.client('lambda')
    
    destination_config = {}
    if success_queue_arn:
        destination_config['OnSuccess'] = {'Destination': success_queue_arn}
    if failure_queue_arn:
        destination_config['OnFailure'] = {'Destination': failure_queue_arn}
        
    lambda_client.put_function_event_invoke_config(
        FunctionName=function_name,
        DestinationConfig=destination_config,
        MaximumRetryAttempts=2,
        MaximumEventAge=3600  # 1 hour
    )


def create_resilient_product_workflow():
    """Create workflow that handles product operations with automatic recovery."""
    workflow_config = {
        'validate_product': {
            'on_success': 'update_inventory_function',
            'on_failure': 'validation_error_handler',
            'retry_attempts': 0  # Validation errors shouldn't be retried
        },
        'update_inventory': {
            'on_success': 'update_search_index_function',
            'on_failure': 'inventory_rollback_function',
            'retry_attempts': 2
        },
        'update_search_index': {
            'on_success': 'completion_notification_function',
            'on_failure': 'search_reindex_queue',
            'retry_attempts': 3
        }
    }
    
    return workflow_config