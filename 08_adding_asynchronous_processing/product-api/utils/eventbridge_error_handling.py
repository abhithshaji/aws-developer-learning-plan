import boto3
import json


def setup_event_error_handling():
    """Set up error handling for EventBridge targets."""
    eventbridge = boto3.client('events')
    sqs = boto3.client('sqs')
    
    # Create dead letter queue for failed events
    dlq_response = sqs.create_queue(
        QueueName='eventbridge-failed-events-dlq',
        Attributes={
            'MessageRetentionPeriod': '1209600',  # 14 days
            'VisibilityTimeoutSeconds': '300'
        }
    )
    
    dlq_arn = sqs.get_queue_attributes(
        QueueUrl=dlq_response['QueueUrl'],
        AttributeNames=['QueueArn']
    )['Attributes']['QueueArn']
    
    # Configure rule with retry and DLQ
    eventbridge.put_targets(
        Rule='order-inventory-update',
        Targets=[{
            'Id': '1',
            'Arn': 'arn:aws:lambda:region:account:function:inventory-processor',
            'RetryPolicy': {
                'MaximumRetryAttempts': 3,
                'MaximumEventAge': 3600
            },
            'DeadLetterConfig': {'Arn': dlq_arn}
        }]
    )


def create_event_monitoring_dashboard():
    """Create CloudWatch dashboard for event monitoring."""
    cloudwatch = boto3.client('cloudwatch')
    
    dashboard_body = {
        'widgets': [
            {
                'type': 'metric',
                'properties': {
                    'metrics': [
                        ['AWS/Events', 'SuccessfulInvocations', 'RuleName', 'order-inventory-update'],
                        ['AWS/Events', 'FailedInvocations', 'RuleName', 'order-inventory-update'],
                        ['AWS/Events', 'MatchedEvents', 'RuleName', 'order-inventory-update']
                    ],
                    'period': 300,
                    'stat': 'Sum',
                    'region': 'us-east-1',
                    'title': 'EventBridge Rule Performance'
                }
            },
            {
                'type': 'metric',
                'properties': {
                    'metrics': [
                        ['AWS/Lambda', 'Invocations', 'FunctionName', 'inventory-processor'],
                        ['AWS/Lambda', 'Errors', 'FunctionName', 'inventory-processor'],
                        ['AWS/Lambda', 'Duration', 'FunctionName', 'inventory-processor']
                    ],
                    'period': 300,
                    'stat': 'Average',
                    'region': 'us-east-1',
                    'title': 'Lambda Function Performance'
                }
            }
        ]
    }
    
    cloudwatch.put_dashboard(
        DashboardName='EventDrivenArchitecture-Monitoring',
        DashboardBody=json.dumps(dashboard_body)
    )
