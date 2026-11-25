import json
import boto3
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Any

from utils.sns_notifications import send_order_confirmation, send_inventory_alert
from lambda_code.order_processor import OrderProcessingError, update_order_status

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def order_processor_handler(event, context):
    """Main order processing Lambda triggered by SQS messages."""
    sns = boto3.client('sns')
    
    # Environment variables for topic ARNs
    customer_topic_arn = os.environ['CUSTOMER_NOTIFICATION_TOPIC']
    system_topic_arn = os.environ['SYSTEM_ALERT_TOPIC']
    
    for record in event['Records']:
        order_data = {}
        try:
            # Parse order message
            order_data = json.loads(record['body'])
            order_id = order_data['order_id']
            
            logger.info(f"Processing order {order_id}")
            
            # Execute order processing workflow
            processing_result = execute_order_workflow(order_data)
            
            if processing_result['success']:
                # Send customer confirmation
                send_order_confirmation(order_data, customer_topic_arn)
                
                # Update order status
                update_order_status(order_id, 'confirmed')
                
                logger.info(f"Order {order_id} processed successfully")
            else:
                # Send failure notification
                send_processing_failure_alert(order_data, processing_result['error'], system_topic_arn)
                
                # Update order status
                update_order_status(order_id, 'failed')
                
                # Re-raise to trigger SQS retry mechanism
                raise OrderProcessingError(f"Order {order_id} processing failed: {processing_result['error']}")
                
        except Exception as e:
            logger.error(f"Error processing order: {str(e)}")
            
            # Send system alert for processing errors
            send_system_alert({
                'error_type': 'order_processing_error',
                'error_message': str(e),
                'order_id': order_data.get('order_id', 'unknown')
            }, system_topic_arn)
            
            raise e
    
    return {'statusCode': 200, 'body': 'Orders processed successfully'}


def inventory_monitor_handler(event, context):
    """Monitor inventory levels and send alerts when stock is low."""
    dynamodb = boto3.resource('dynamodb')
    sns = boto3.client('sns')
    
    products_table = dynamodb.Table('Products')
    inventory_topic_arn = os.environ['INVENTORY_ALERT_TOPIC']
    
    # Scan for products with low inventory
    response = products_table.scan(
        FilterExpression='inventory_count <= reorder_level'
    )
    
    low_stock_products = response['Items']
    
    for product in low_stock_products:
        # Send inventory alert
        alert_sent = send_inventory_alert(product, inventory_topic_arn)
        
        if alert_sent:
            # Update product with alert timestamp
            products_table.update_item(
                Key={'id': product['id']},
                UpdateExpression='SET last_inventory_alert = :timestamp',
                ExpressionAttributeValues={
                    ':timestamp': datetime.now(timezone.utc).isoformat()
                }
            )
    
    return {
        'statusCode': 200,
        'body': f'Processed {len(low_stock_products)} low stock alerts'
    }


def notification_dispatcher_handler(event, context):
    """Dispatch notifications based on SNS messages."""
    for record in event['Records']:
        # Parse SNS message
        sns_message = json.loads(record['Sns']['Message'])
        message_attributes = record['Sns']['MessageAttributes']
        
        # Determine notification type and route accordingly
        notification_type = message_attributes.get('notification_type', {}).get('Value', 'general')
        
        if notification_type == 'order_confirmation':
            send_order_email(sns_message)
            send_order_sms(sns_message)
        elif notification_type == 'inventory_alert':
            send_inventory_email(sns_message)
            create_reorder_task(sns_message)
        elif notification_type == 'system_alert':
            send_admin_notification(sns_message)
            log_system_event(sns_message)
    
    return {'statusCode': 200, 'body': 'Notifications dispatched'}


def execute_order_workflow(order_data: Dict) -> Dict:
    """Execute order processing with error handling."""
    workflow_steps = [
        ('validate_inventory', validate_inventory_step),
        ('process_payment', process_payment_step),
        ('create_shipping', create_shipping_step),
        ('update_analytics', update_analytics_step)
    ]
    
    completed_steps = []
    
    try:
        for step_name, step_function in workflow_steps:
            logger.info(f"Executing step: {step_name}")
            
            step_result = step_function(order_data)
            
            if not step_result['success']:
                # Rollback completed steps
                rollback_completed_steps(completed_steps, order_data)
                return {
                    'success': False,
                    'error': f"Step {step_name} failed: {step_result['error']}",
                    'failed_step': step_name
                }
            
            completed_steps.append({
                'step': step_name,
                'result': step_result,
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
        
        return {
            'success': True,
            'completed_steps': completed_steps,
            'total_processing_time': calculate_processing_time(completed_steps)
        }
        
    except Exception as e:
        # Rollback any completed steps
        rollback_completed_steps(completed_steps, order_data)
        
        return {
            'success': False,
            'error': f"Workflow exception: {str(e)}",
            'completed_steps': completed_steps
        }


def rollback_completed_steps(completed_steps: List[Dict], order_data: Dict):
    """Rollback completed workflow steps in reverse order."""
    rollback_functions = {
        'validate_inventory': rollback_inventory_reservation,
        'process_payment': rollback_payment_charge,
        'create_shipping': rollback_shipping_label,
        'update_analytics': rollback_analytics_update
    }
    
    # Rollback in reverse order
    for step in reversed(completed_steps):
        step_name = step['step']
        rollback_function = rollback_functions.get(step_name)
        
        if rollback_function:
            try:
                rollback_result = rollback_function(order_data, step['result'])
                logger.info(f"Rolled back step: {step_name}")
            except Exception as e:
                logger.error(f"Failed to rollback step {step_name}: {str(e)}")
                # Continue with other rollbacks even if one fails


def configure_lambda_triggers():
    """Configure Lambda function triggers for SQS and SNS."""
    lambda_client = boto3.client('lambda')
    
    # Configure SQS trigger for order processing
    lambda_client.create_event_source_mapping(
        EventSourceArn='arn:aws:sqs:region:account:order-processing-queue',
        FunctionName='order-processor',
        BatchSize=10,  # Process up to 10 messages at once
        MaximumBatchingWindowInSeconds=5,  # Wait up to 5 seconds to batch messages
    )
    
    # Configure SNS trigger for notification dispatch
    lambda_client.add_permission(
        FunctionName='notification-dispatcher',
        StatementId='sns-trigger',
        Action='lambda:InvokeFunction',
        Principal='sns.amazonaws.com',
        SourceArn='arn:aws:sns:region:account:customer-notifications'
    )


# --- Business logic helper stubs (stand-ins for domain implementations) ---

def send_processing_failure_alert(order_data: Dict, error: str, system_topic_arn: str):
    sns = boto3.client('sns')
    return sns.publish(
        TopicArn=system_topic_arn,
        Subject=f"Order Processing Failed - {order_data.get('order_id', 'unknown')}",
        Message=json.dumps({'order_id': order_data.get('order_id'), 'error': error})
    )


def send_system_alert(alert_data: Dict[str, Any], system_topic_arn: str):
    sns = boto3.client('sns')
    return sns.publish(
        TopicArn=system_topic_arn,
        Subject=f"System Alert - {alert_data.get('error_type', 'unknown')}",
        Message=json.dumps(alert_data)
    )


def send_order_email(sns_message: Dict):
    logger.info(f"Sending order confirmation email: {sns_message}")


def send_order_sms(sns_message: Dict):
    logger.info(f"Sending order confirmation SMS: {sns_message}")


def send_inventory_email(sns_message: Dict):
    logger.info(f"Sending inventory alert email: {sns_message}")


def create_reorder_task(sns_message: Dict):
    logger.info(f"Creating reorder task: {sns_message}")


def send_admin_notification(sns_message: Dict):
    logger.info(f"Sending admin notification: {sns_message}")


def log_system_event(sns_message: Dict):
    logger.info(f"Logging system event: {sns_message}")


def validate_inventory_step(order_data: Dict) -> Dict:
    return {'success': True, 'reserved_items': order_data.get('items', [])}


def process_payment_step(order_data: Dict) -> Dict:
    return {'success': True, 'transaction_id': f"txn_{order_data.get('order_id', 'mock')}"}


def create_shipping_step(order_data: Dict) -> Dict:
    return {'success': True, 'label_url': f"https://shipping.example.com/{order_data.get('order_id', 'mock')}.pdf"}


def update_analytics_step(order_data: Dict) -> Dict:
    return {'success': True}


def rollback_inventory_reservation(order_data: Dict, step_result: Dict) -> Dict:
    return {'rolled_back': True}


def rollback_payment_charge(order_data: Dict, step_result: Dict) -> Dict:
    return {'rolled_back': True}


def rollback_shipping_label(order_data: Dict, step_result: Dict) -> Dict:
    return {'rolled_back': True}


def rollback_analytics_update(order_data: Dict, step_result: Dict) -> Dict:
    return {'rolled_back': True}


def calculate_processing_time(completed_steps: List[Dict]) -> float:
    if len(completed_steps) < 2:
        return 0.0
    start = datetime.fromisoformat(completed_steps[0]['timestamp'])
    end = datetime.fromisoformat(completed_steps[-1]['timestamp'])
    return (end - start).total_seconds()
