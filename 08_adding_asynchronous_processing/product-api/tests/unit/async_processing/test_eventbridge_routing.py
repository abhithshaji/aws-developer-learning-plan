import json
import unittest
from unittest.mock import MagicMock, patch

from utils.eventbridge_routing import (
    EventPublishError,
    create_advanced_event_patterns,
    create_content_based_routing_rule,
    create_event_buses,
    create_inventory_alert_rules,
    create_order_processing_rules,
    publish_inventory_event,
    publish_order_event,
)


class TestEventBridgeRouting(unittest.TestCase):

    @patch("utils.eventbridge_routing.boto3.client")
    def test_create_event_buses(self, mock_boto_client):
        """Test creating orders, inventory, and customers EventBridge buses."""
        mock_eb = MagicMock()
        mock_eb.create_event_bus.side_effect = [
            {"EventBusArn": "arn:aws:events:us-east-1:123:event-bus/online-store-orders"},
            {"EventBusArn": "arn:aws:events:us-east-1:123:event-bus/online-store-inventory"},
            {"EventBusArn": "arn:aws:events:us-east-1:123:event-bus/online-store-customers"},
        ]
        mock_boto_client.return_value = mock_eb

        arns = create_event_buses()

        self.assertEqual(
            arns,
            {
                "order_bus_arn": "arn:aws:events:us-east-1:123:event-bus/online-store-orders",
                "inventory_bus_arn": "arn:aws:events:us-east-1:123:event-bus/online-store-inventory",
                "customer_bus_arn": "arn:aws:events:us-east-1:123:event-bus/online-store-customers",
            },
        )
        created_names = [c.kwargs["Name"] for c in mock_eb.create_event_bus.call_args_list]
        self.assertEqual(
            created_names,
            ["online-store-orders", "online-store-inventory", "online-store-customers"],
        )

    @patch("utils.eventbridge_routing.boto3.client")
    def test_publish_order_event_success(self, mock_boto_client):
        """Test publishing an Order Placed event to custom bus."""
        mock_eb = MagicMock()
        mock_eb.put_events.return_value = {
            "FailedEntryCount": 0,
            "Entries": [{"EventId": "evt-001"}],
        }
        mock_boto_client.return_value = mock_eb

        order_data = {
            "order_id": "ord-101",
            "customer_id": "cust-55",
            "total_amount": 299.99,
            "items": [{"id": "prod-1", "quantity": 1}],
            "timestamp": "2026-11-26T12:00:00Z",
            "customer_tier": "vip",
            "order_type": "express",
        }

        event_id = publish_order_event(order_data, "online-store-orders")

        self.assertEqual(event_id, "evt-001")
        entry = mock_eb.put_events.call_args.kwargs["Entries"][0]
        self.assertEqual(entry["Source"], "store.orders")
        self.assertEqual(entry["DetailType"], "Order Placed")
        self.assertEqual(entry["EventBusName"], "online-store-orders")

        detail = json.loads(entry["Detail"])
        self.assertEqual(detail["orderId"], "ord-101")
        self.assertEqual(detail["customerTier"], "vip")
        self.assertEqual(detail["orderType"], "express")

    @patch("utils.eventbridge_routing.boto3.client")
    def test_publish_order_event_failure_raises_error(self, mock_boto_client):
        """Test FailedEntryCount > 0 raises EventPublishError."""
        mock_eb = MagicMock()
        mock_eb.put_events.return_value = {
            "FailedEntryCount": 1,
            "Entries": [{"ErrorMessage": "EventBus does not exist"}],
        }
        mock_boto_client.return_value = mock_eb

        order_data = {
            "order_id": "ord-102",
            "customer_id": "cust-55",
            "total_amount": 10.0,
            "items": [],
            "timestamp": "2026-11-26T12:00:00Z",
        }

        with self.assertRaises(EventPublishError) as ctx:
            publish_order_event(order_data, "missing-bus")

        self.assertIn("EventBus does not exist", str(ctx.exception))

    @patch("utils.eventbridge_routing.boto3.client")
    def test_publish_inventory_event(self, mock_boto_client):
        """Test publishing inventory Stock Low event."""
        mock_eb = MagicMock()
        mock_eb.put_events.return_value = {"Entries": [{"EventId": "inv-evt-1"}]}
        mock_boto_client.return_value = mock_eb

        product_data = {
            "id": "prod-9",
            "title": "USB-C Dock",
            "category": "Electronics",
            "inventory_count": 3,
            "price": 79.99,
        }

        event_id = publish_inventory_event(product_data, "Stock Low", "online-store-inventory")

        self.assertEqual(event_id, "inv-evt-1")
        entry = mock_eb.put_events.call_args.kwargs["Entries"][0]
        self.assertEqual(entry["Source"], "store.inventory")
        self.assertEqual(entry["DetailType"], "Stock Low")
        detail = json.loads(entry["Detail"])
        self.assertEqual(detail["productId"], "prod-9")
        self.assertEqual(detail["currentStock"], 3)
        self.assertEqual(detail["reorderLevel"], 10)

    @patch("utils.eventbridge_routing.boto3.client")
    def test_create_order_processing_rules(self, mock_boto_client):
        """Test creating order rules with Lambda, SNS, and SQS FIFO targets."""
        mock_eb = MagicMock()
        mock_eb.put_rule.side_effect = [
            {"RuleArn": "arn:aws:events:us-east-1:123:rule/order-inventory-update"},
            {"RuleArn": "arn:aws:events:us-east-1:123:rule/order-customer-notification"},
            {"RuleArn": "arn:aws:events:us-east-1:123:rule/order-analytics-processing"},
        ]
        mock_boto_client.return_value = mock_eb

        arns = create_order_processing_rules("online-store-orders")

        self.assertEqual(len(arns), 3)
        self.assertEqual(mock_eb.put_rule.call_count, 3)
        self.assertEqual(mock_eb.put_targets.call_count, 3)

        # Verify FIFO SqsParameters on analytics target
        analytics_targets = mock_eb.put_targets.call_args_list[2].kwargs["Targets"]
        self.assertEqual(
            analytics_targets[0]["SqsParameters"]["MessageGroupId"], "analytics-events"
        )

    @patch("utils.eventbridge_routing.boto3.client")
    def test_create_inventory_alert_rules(self, mock_boto_client):
        """Test creating inventory low-stock rule with multi-target fan-out."""
        mock_eb = MagicMock()
        mock_eb.put_rule.return_value = {
            "RuleArn": "arn:aws:events:us-east-1:123:rule/inventory-low-stock-alert"
        }
        mock_boto_client.return_value = mock_eb

        rule_arn = create_inventory_alert_rules("online-store-inventory")

        self.assertEqual(rule_arn, "arn:aws:events:us-east-1:123:rule/inventory-low-stock-alert")
        targets = mock_eb.put_targets.call_args.kwargs["Targets"]
        self.assertEqual(len(targets), 2)
        self.assertIn("sns", targets[0]["Arn"])
        self.assertIn("lambda", targets[1]["Arn"])

    def test_create_advanced_event_patterns(self):
        """Test advanced EventBridge pattern definitions."""
        patterns = create_advanced_event_patterns()

        self.assertEqual(
            set(patterns.keys()),
            {"premium_customer", "express_shipping", "critical_inventory", "customer_lifecycle"},
        )
        self.assertEqual(
            patterns["premium_customer"]["detail"]["orderAmount"], [{"numeric": [">=", 500]}]
        )
        self.assertEqual(
            patterns["express_shipping"]["detail"]["shippingAddress"]["state"],
            ["WA", "OR", "CA"],
        )
        self.assertEqual(
            patterns["critical_inventory"]["detail"]["category"],
            ["Electronics", "Best Sellers"],
        )

    @patch("utils.eventbridge_routing.boto3.client")
    def test_create_content_based_routing_rule(self, mock_boto_client):
        """Test creating a generic content-based routing rule with InputTransformer."""
        mock_eb = MagicMock()
        mock_eb.put_rule.return_value = {
            "RuleArn": "arn:aws:events:us-east-1:123:rule/content-routing-premium_customer"
        }
        mock_boto_client.return_value = mock_eb

        patterns = create_advanced_event_patterns()
        rule_arn = create_content_based_routing_rule(
            "premium_customer",
            patterns["premium_customer"],
            "arn:aws:lambda:us-east-1:123:function:vip-handler",
            "online-store-orders",
        )

        self.assertIn("content-routing-premium_customer", rule_arn)
        put_rule_kwargs = mock_eb.put_rule.call_args.kwargs
        self.assertEqual(put_rule_kwargs["Name"], "content-routing-premium_customer")
        target = mock_eb.put_targets.call_args.kwargs["Targets"][0]
        self.assertEqual(target["Arn"], "arn:aws:lambda:us-east-1:123:function:vip-handler")
        self.assertIn("routingPattern", target["InputTransformer"]["InputTemplate"])


if __name__ == "__main__":
    unittest.main()
