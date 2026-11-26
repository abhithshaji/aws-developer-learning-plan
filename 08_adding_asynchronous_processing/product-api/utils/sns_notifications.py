import boto3
import json
from typing import Dict, List


def create_notification_topics():
    """Create SNS topics for different notification types."""
    sns = boto3.client('sns')
    
    # Customer notification topic
    customer_topic = sns.create_topic(
        Name='customer-notifications',
        Attributes={
            'DisplayName': 'Customer Notifications',
            'DeliveryPolicy': json.dumps({
                'http': {
                    'defaultHealthyRetryPolicy': {
                        'minDelayTarget': 20,
                        'maxDelayTarget': 20,
                        'numRetries': 3,
                        'numMaxDelayRetries': 0,
                        'backoffFunction': 'linear'
                    }
                }
            })
        }
    )
    
    # System alert topic
    system_topic = sns.create_topic(
        Name='system-alerts',
        Attributes={
            'DisplayName': 'System Alerts',
            'DeliveryPolicy': json.dumps({
                'http': {
                    'defaultHealthyRetryPolicy': {
                        'minDelayTarget': 20,
                        'maxDelayTarget': 20,
                        'numRetries': 5,
                        'numMaxDelayRetries': 0,
                        'backoffFunction': 'exponential'
                    }
                }
            })
        }
    )
    
    # Inventory alert topic
    inventory_topic = sns.create_topic(
        Name='inventory-alerts',
        Attributes={
            'DisplayName': 'Inventory Alerts'
        }
    )
    
    return {
        'customer_topic_arn': customer_topic['TopicArn'],
        'system_topic_arn': system_topic['TopicArn'],
        'inventory_topic_arn': inventory_topic['TopicArn']
    }


def subscribe_to_notifications(topic_arn: str, subscription_type: str, endpoint: str):
    """Subscribe endpoints to SNS topics."""
    sns = boto3.client('sns')
    
    subscription = sns.subscribe(
        TopicArn=topic_arn,
        Protocol=subscription_type,  # 'email', 'sms', 'http', 'https', 'sqs'
        Endpoint=endpoint
    )
    
    return subscription['SubscriptionArn']


def send_order_confirmation(order_data: Dict, topic_arn: str):
    """Send order confirmation notification to customers."""
    sns = boto3.client('sns')
    
    # Create notification message
    message = {
        'default': f"Order {order_data['order_id']} confirmed. Total: ${order_data['total_amount']:.2f}",
        'email': create_email_message(order_data),
        'sms': create_sms_message(order_data)
    }
    
    # Message attributes for filtering
    message_attributes = {
        'order_type': {
            'DataType': 'String',
            'StringValue': order_data.get('order_type', 'standard')
        },
        'customer_tier': {
            'DataType': 'String',
            'StringValue': order_data.get('customer_tier', 'regular')
        },
        'notification_preference': {
            'DataType': 'String',
            'StringValue': order_data.get('notification_preference', 'all')
        }
    }
    
    response = sns.publish(
        TopicArn=topic_arn,
        Message=json.dumps(message),
        MessageStructure='json',
        Subject=f"Order Confirmation - {order_data['order_id']}",
        MessageAttributes=message_attributes
    )
    
    return response['MessageId']


def create_email_message(order_data: Dict) -> str:
    """Create formatted email message for order confirmation."""
    items_list = '\n'.join([
        f"- {item['title']} (Qty: {item['quantity']}) - ${item['price']:.2f}"
        for item in order_data['items']
    ])
    
    email_template = f"""
    Dear {order_data['customer_name']},
    
    Thank you for your order! Here are the details:
    
    Order ID: {order_data['order_id']}
    Order Date: {order_data['order_date']}
    
    Items Ordered:
    {items_list}
    
    Total Amount: ${order_data['total_amount']:.2f}
    
    Estimated Delivery: {order_data.get('estimated_delivery', 'TBD')}
    
    You can track your order at: https://store.example.com/orders/{order_data['order_id']}
    
    Thank you for shopping with us!
    """
    
    return email_template.strip()


def create_sms_message(order_data: Dict) -> str:
    """Create concise SMS message for order confirmation."""
    return f"Order {order_data['order_id']} confirmed! Total: ${order_data['total_amount']:.2f}. Track at: https://store.example.com/track/{order_data['order_id']}"


def setup_filtered_subscriptions(topic_arn: str):
    """Set up SNS subscriptions with message filtering."""
    sns = boto3.client('sns')
    
    # Subscribe premium customers with filter
    premium_sub = sns.subscribe(
        TopicArn=topic_arn,
        Protocol='email',
        Endpoint='premium@example.com'
    )
    
    sns.set_subscription_attributes(
        SubscriptionArn=premium_sub['SubscriptionArn'],
        AttributeName='FilterPolicy',
        AttributeValue=json.dumps({
            'customer_tier': ['premium', 'vip']
        })
    )
    
    # Subscribe to urgent notifications only
    urgent_sub = sns.subscribe(
        TopicArn=topic_arn,
        Protocol='sms',
        Endpoint='+1234567890'
    )
    
    sns.set_subscription_attributes(
        SubscriptionArn=urgent_sub['SubscriptionArn'],
        AttributeName='FilterPolicy',
        AttributeValue=json.dumps({
            'order_type': ['express', 'same_day']
        })
    )


def send_inventory_alert(product_data: Dict, topic_arn: str):
    """Send inventory alert when stock levels are low."""
    sns = boto3.client('sns')
    
    # Build the alert message for each protocol
    alert_message = {
        'default': f"Low stock: {product_data['title']} "
                   f"({product_data['inventory_count']} remaining)",
        'email': f"Inventory alert for {product_data['title']}: "
                 f"{product_data['inventory_count']} units remaining. "
                 f"Reorder level: {product_data.get('reorder_level', 10)}."
    }

    message_attributes = {
        'alert_type': {
            'DataType': 'String',
            'StringValue': 'inventory_low'
        },
        'product_category': {
            'DataType': 'String',
            'StringValue': product_data['category']
        },
        'urgency': {
            'DataType': 'String',
            'StringValue': 'high' if product_data['inventory_count'] == 0 else 'medium'
        }
    }
    
    response = sns.publish(
        TopicArn=topic_arn,
        Message=json.dumps(alert_message),
        MessageStructure='json',
        Subject=f"Inventory Alert: {product_data['title']}",
        MessageAttributes=message_attributes
    )
    
    return response['MessageId']
