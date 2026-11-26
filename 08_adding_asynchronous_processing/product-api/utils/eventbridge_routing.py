import boto3
import json
from datetime import datetime, timezone
from typing import Dict, List


class EventPublishError(Exception):
    """Custom exception for event publishing failures."""
    pass


def create_event_buses():
    """Create custom event buses for different business domains."""
    eventbridge = boto3.client('events')
    
    # Create order processing event bus
    order_bus = eventbridge.create_event_bus(
        Name='online-store-orders'
    )
    
    # Create inventory management event bus
    inventory_bus = eventbridge.create_event_bus(
        Name='online-store-inventory'
    )
    
    # Create customer management event bus
    customer_bus = eventbridge.create_event_bus(
        Name='online-store-customers'
    )
    
    return {
        'order_bus_arn': order_bus['EventBusArn'],
        'inventory_bus_arn': inventory_bus['EventBusArn'],
        'customer_bus_arn': customer_bus['EventBusArn']
    }


def publish_order_event(order_data: Dict, event_bus_name: str):
    """Publish order-related events to EventBridge."""
    eventbridge = boto3.client('events')
    
    # Create event entry
    event_entry = {
        'Source': 'store.orders',
        'DetailType': 'Order Placed',
        'Detail': json.dumps({
            'orderId': order_data['order_id'],
            'customerId': order_data['customer_id'],
            'orderAmount': order_data['total_amount'],
            'items': order_data['items'],
            'timestamp': order_data['timestamp'],
            'customerTier': order_data.get('customer_tier', 'regular'),
            'orderType': order_data.get('order_type', 'standard'),
            'shippingAddress': order_data.get('shipping_address', {}),
            'paymentMethod': order_data.get('payment_method', 'credit_card')
        }),
        'EventBusName': event_bus_name
    }
    
    # Publish event
    response = eventbridge.put_events(
        Entries=[event_entry]
    )
    
    if response['FailedEntryCount'] > 0:
        raise EventPublishError(f"Failed to publish event: {response['Entries'][0]['ErrorMessage']}")
    
    return response['Entries'][0]['EventId']


def publish_inventory_event(product_data: Dict, event_type: str, event_bus_name: str):
    """Publish inventory-related events to EventBridge."""
    eventbridge = boto3.client('events')
    
    event_entry = {
        'Source': 'store.inventory',
        'DetailType': event_type,  # 'Inventory Updated', 'Stock Low', 'Product Added'
        'Detail': json.dumps({
            'productId': product_data['id'],
            'productName': product_data['title'],
            'category': product_data['category'],
            'currentStock': product_data['inventory_count'],
            'reorderLevel': product_data.get('reorder_level', 10),
            'price': product_data['price'],
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'changeReason': product_data.get('change_reason', 'manual_update')
        }),
        'EventBusName': event_bus_name
    }
    
    response = eventbridge.put_events(
        Entries=[event_entry]
    )
    
    return response['Entries'][0]['EventId']


def create_order_processing_rules(event_bus_name: str):
    """Create EventBridge rules for order processing workflows."""
    eventbridge = boto3.client('events')
    
    # Rule for inventory updates on order placement
    inventory_rule = eventbridge.put_rule(
        Name='order-inventory-update',
        EventPattern=json.dumps({
            'source': ['store.orders'],
            'detail-type': ['Order Placed'],
            'detail': {
                'orderType': ['standard', 'express']
            }
        }),
        State='ENABLED',
        Description='Route order events to inventory service',
        EventBusName=event_bus_name
    )
    
    # Add Lambda target for inventory processing
    eventbridge.put_targets(
        Rule='order-inventory-update',
        EventBusName=event_bus_name,
        Targets=[
            {
                'Id': '1',
                'Arn': 'arn:aws:lambda:region:account:function:inventory-processor',
                'InputTransformer': {
                    'InputPathsMap': {
                        'orderId': '$.detail.orderId',
                        'items': '$.detail.items'
                    },
                    'InputTemplate': '{"orderId": "<orderId>", "items": <items>}'
                }
            }
        ]
    )
    
    # Rule for customer notifications
    notification_rule = eventbridge.put_rule(
        Name='order-customer-notification',
        EventPattern=json.dumps({
            'source': ['store.orders'],
            'detail-type': ['Order Placed', 'Order Shipped', 'Order Delivered'],
            'detail': {
                'customerId': [{'exists': True}]
            }
        }),
        State='ENABLED',
        Description='Route order events to notification service',
        EventBusName=event_bus_name
    )
    
    # Add SNS target for notifications
    eventbridge.put_targets(
        Rule='order-customer-notification',
        EventBusName=event_bus_name,
        Targets=[
            {
                'Id': '1',
                'Arn': 'arn:aws:sns:region:account:customer-notifications',
                'InputTransformer': {
                    'InputPathsMap': {
                        'customerId': '$.detail.customerId',
                        'orderId': '$.detail.orderId',
                        'eventType': '$.detail-type'
                    },
                    'InputTemplate': '{"customerId": "<customerId>", "orderId": "<orderId>", "eventType": "<eventType>"}'
                }
            }
        ]
    )
    
    # Rule for analytics processing
    analytics_rule = eventbridge.put_rule(
        Name='order-analytics-processing',
        EventPattern=json.dumps({
            'source': ['store.orders', 'store.inventory', 'store.customers'],
            'detail-type': ['Order Placed', 'Inventory Updated', 'Customer Registered']
        }),
        State='ENABLED',
        Description='Route events to analytics service',
        EventBusName=event_bus_name
    )
    
    # Add SQS target for analytics processing
    eventbridge.put_targets(
        Rule='order-analytics-processing',
        EventBusName=event_bus_name,
        Targets=[
            {
                'Id': '1',
                'Arn': 'arn:aws:sqs:region:account:analytics-processing-queue.fifo',  # Message groups require a FIFO queue
                'SqsParameters': {
                    'MessageGroupId': 'analytics-events'
                }
            }
        ]
    )
    
    return {
        'inventory_rule_arn': inventory_rule['RuleArn'],
        'notification_rule_arn': notification_rule['RuleArn'],
        'analytics_rule_arn': analytics_rule['RuleArn']
    }


def create_inventory_alert_rules(event_bus_name: str):
    """Create rules for inventory management alerts."""
    eventbridge = boto3.client('events')
    
    # Rule for low stock alerts
    low_stock_rule = eventbridge.put_rule(
        Name='inventory-low-stock-alert',
        EventPattern=json.dumps({
            'source': ['store.inventory'],
            'detail-type': ['Stock Low'],
            'detail': {
                'currentStock': [{'numeric': ['<=', 10]}]
            }
        }),
        State='ENABLED',
        Description='Alert when inventory is low',
        EventBusName=event_bus_name
    )
    
    # Add multiple targets for low stock alerts
    eventbridge.put_targets(
        Rule='inventory-low-stock-alert',
        EventBusName=event_bus_name,
        Targets=[
            {
                'Id': '1',
                'Arn': 'arn:aws:sns:region:account:inventory-alerts',
                'InputTransformer': {
                    'InputPathsMap': {
                        'productName': '$.detail.productName',
                        'currentStock': '$.detail.currentStock',
                        'reorderLevel': '$.detail.reorderLevel'
                    },
                    'InputTemplate': '{"alertType": "low_stock", "productName": "<productName>", "currentStock": <currentStock>, "reorderLevel": <reorderLevel>}'
                }
            },
            {
                'Id': '2',
                'Arn': 'arn:aws:lambda:region:account:function:auto-reorder-processor',
                'InputTransformer': {
                    'InputPathsMap': {
                        'productId': '$.detail.productId',
                        'currentStock': '$.detail.currentStock'
                    },
                    'InputTemplate': '{"productId": "<productId>", "currentStock": <currentStock>, "action": "evaluate_reorder"}'
                }
            }
        ]
    )
    
    return low_stock_rule['RuleArn']


def create_advanced_event_patterns():
    """Create advanced event patterns for complex routing scenarios."""
    
    # Pattern for premium customer orders
    premium_customer_pattern = {
        'source': ['store.orders'],
        'detail-type': ['Order Placed'],
        'detail': {
            'customerTier': ['premium', 'vip'],
            'orderAmount': [{'numeric': ['>=', 500]}]
        }
    }
    
    # Pattern for express shipping orders
    express_shipping_pattern = {
        'source': ['store.orders'],
        'detail-type': ['Order Placed'],
        'detail': {
            'orderType': ['express', 'same_day'],
            'shippingAddress': {
                'state': ['WA', 'OR', 'CA']  # West Coast only
            }
        }
    }
    
    # Pattern for inventory critical alerts
    critical_inventory_pattern = {
        'source': ['store.inventory'],
        'detail-type': ['Stock Low', 'Out of Stock'],
        'detail': {
            'category': ['Electronics', 'Best Sellers'],
            'currentStock': [{'numeric': ['<=', 5]}]
        }
    }
    
    # Pattern for customer lifecycle events
    customer_lifecycle_pattern = {
        'source': ['store.customers'],
        'detail-type': ['Customer Registered', 'Customer Updated', 'Customer Churned'],
        'detail': {
            'customerTier': [{'exists': True}],
            'timestamp': [{'exists': True}]
        }
    }
    
    return {
        'premium_customer': premium_customer_pattern,
        'express_shipping': express_shipping_pattern,
        'critical_inventory': critical_inventory_pattern,
        'customer_lifecycle': customer_lifecycle_pattern
    }


def create_content_based_routing_rule(pattern_name: str, event_pattern: Dict, target_arn: str, event_bus_name: str):
    """Create EventBridge rule with content-based routing."""
    eventbridge = boto3.client('events')
    
    rule = eventbridge.put_rule(
        Name=f'content-routing-{pattern_name}',
        EventPattern=json.dumps(event_pattern),
        State='ENABLED',
        Description=f'Content-based routing for {pattern_name}',
        EventBusName=event_bus_name
    )
    
    # Add target with input transformation
    eventbridge.put_targets(
        Rule=f'content-routing-{pattern_name}',
        EventBusName=event_bus_name,
        Targets=[
            {
                'Id': '1',
                'Arn': target_arn,
                'InputTransformer': {
                    'InputPathsMap': {
                        'source': '$.source',
                        'detailType': '$.detail-type',
                        'timestamp': '$.time',
                        'eventDetail': '$.detail'
                    },
                    'InputTemplate': json.dumps({
                        'routingPattern': pattern_name,
                        'eventSource': '<source>',
                        'eventType': '<detailType>',
                        'eventTime': '<timestamp>',
                        'eventData': '<eventDetail>'
                    })
                }
            }
        ]
    )
    
    return rule['RuleArn']
