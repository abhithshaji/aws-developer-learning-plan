import json
import boto3
import logging
from typing import Dict, List

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, context):
    """Process order messages from SQS queue."""
    sqs = boto3.client('sqs')
    
    # Process each message in the batch
    for record in event['Records']:
        try:
            # Parse message body
            message_body = json.loads(record['body'])
            order_id = message_body['order_id']
            
            logger.info(f"Processing order {order_id}")
            
            # Process order through defined steps
            processing_result = process_order_workflow(message_body)
            
            if processing_result['success']:
                logger.info(f"Order {order_id} processed successfully")
                # Message automatically deleted from queue on successful return
            else:
                # Raise exception to trigger retry mechanism
                raise OrderProcessingError(f"Failed to process order {order_id}: {processing_result['error']}")
                
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            # Message will be retried based on queue configuration
            raise e
    
    return {'statusCode': 200, 'body': 'Orders processed successfully'}


def process_order_workflow(order_data: Dict) -> Dict:
    """Execute order processing workflow steps."""
    try:
        # Step 1: Validate inventory
        inventory_result = validate_inventory(order_data['items'])
        if not inventory_result['available']:
            return {'success': False, 'error': 'Insufficient inventory'}
        
        # Step 2: Process payment
        payment_result = process_payment(
            order_data['customer_id'],
            order_data['total_amount']
        )
        if not payment_result['success']:
            return {'success': False, 'error': 'Payment processing failed'}
        
        # Step 3: Create shipping label
        shipping_result = create_shipping_label(order_data)
        if not shipping_result['success']:
            # Refund payment before failing
            refund_payment(payment_result['transaction_id'])
            return {'success': False, 'error': 'Shipping label creation failed'}
        
        # Step 4: Update order status
        update_order_status(order_data['order_id'], 'processing')
        
        return {
            'success': True,
            'payment_id': payment_result['transaction_id'],
            'shipping_label': shipping_result['label_url']
        }
        
    except Exception as e:
        logger.error(f"Order workflow error: {str(e)}")
        return {'success': False, 'error': str(e)}


def validate_inventory(items: List[Dict]) -> Dict:
    """Check product availability for order items."""
    dynamodb = boto3.resource('dynamodb')
    products_table = dynamodb.Table('Products')
    
    for item in items:
        response = products_table.get_item(
            Key={'id': item['id']}
        )
        
        if 'Item' not in response:
            return {'available': False, 'reason': f"Product {item['id']} not found"}
        
        product = response['Item']
        if product['inventory_count'] < item['quantity']:
            return {
                'available': False,
                'reason': f"Insufficient inventory for {item['id']}"
            }
    
    return {'available': True}


def process_payment(customer_id: str, total_amount: float) -> Dict:
    """Process customer payment for an order."""
    logger.info(f"Processing payment of {total_amount} for customer {customer_id}")
    return {'success': True, 'transaction_id': f"txn_{customer_id}_{int(total_amount * 100)}"}


def create_shipping_label(order_data: Dict) -> Dict:
    """Create shipping label for the order."""
    order_id = order_data['order_id']
    logger.info(f"Creating shipping label for order {order_id}")
    return {'success': True, 'label_url': f"https://shipping.example.com/labels/{order_id}.pdf"}


def refund_payment(transaction_id: str) -> Dict:
    """Refund payment when downstream order step fails."""
    logger.info(f"Refunding payment for transaction {transaction_id}")
    return {'success': True, 'transaction_id': transaction_id}


def update_order_status(order_id: str, status: str) -> Dict:
    """Update order status in persistence layer."""
    logger.info(f"Updating order {order_id} status to {status}")
    return {'order_id': order_id, 'status': status}


class OrderProcessingError(Exception):
    """Custom exception for order processing failures."""
    pass
