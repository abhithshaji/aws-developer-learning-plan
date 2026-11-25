import json
import unittest
from unittest.mock import MagicMock, patch

from utils.sns_notifications import (
    create_email_message,
    create_notification_topics,
    create_sms_message,
    send_inventory_alert,
    send_order_confirmation,
    setup_filtered_subscriptions,
    subscribe_to_notifications,
)


class TestSNSNotifications(unittest.TestCase):

    @patch("utils.sns_notifications.boto3.client")
    def test_create_notification_topics(self, mock_boto_client):
        """Test creating customer, system, and inventory SNS topics."""
        mock_sns = MagicMock()
        mock_sns.create_topic.side_effect = [
            {"TopicArn": "arn:aws:sns:us-east-1:123456789012:customer-notifications"},
            {"TopicArn": "arn:aws:sns:us-east-1:123456789012:system-alerts"},
            {"TopicArn": "arn:aws:sns:us-east-1:123456789012:inventory-alerts"},
        ]
        mock_boto_client.return_value = mock_sns

        arns = create_notification_topics()

        self.assertEqual(
            arns,
            {
                "customer_topic_arn": "arn:aws:sns:us-east-1:123456789012:customer-notifications",
                "system_topic_arn": "arn:aws:sns:us-east-1:123456789012:system-alerts",
                "inventory_topic_arn": "arn:aws:sns:us-east-1:123456789012:inventory-alerts",
            },
        )
        self.assertEqual(mock_sns.create_topic.call_count, 3)

        cust_policy = json.loads(
            mock_sns.create_topic.call_args_list[0].kwargs["Attributes"]["DeliveryPolicy"]
        )
        self.assertEqual(
            cust_policy["http"]["defaultHealthyRetryPolicy"]["backoffFunction"], "linear"
        )

        sys_policy = json.loads(
            mock_sns.create_topic.call_args_list[1].kwargs["Attributes"]["DeliveryPolicy"]
        )
        self.assertEqual(
            sys_policy["http"]["defaultHealthyRetryPolicy"]["backoffFunction"], "exponential"
        )
        self.assertEqual(sys_policy["http"]["defaultHealthyRetryPolicy"]["numRetries"], 5)

    @patch("utils.sns_notifications.boto3.client")
    def test_subscribe_to_notifications(self, mock_boto_client):
        """Test subscribing an endpoint to an SNS topic."""
        mock_sns = MagicMock()
        mock_sns.subscribe.return_value = {
            "SubscriptionArn": "arn:aws:sns:us-east-1:123456789012:customer-notifications:sub-1"
        }
        mock_boto_client.return_value = mock_sns

        sub_arn = subscribe_to_notifications(
            "arn:aws:sns:us-east-1:123456789012:customer-notifications",
            "email",
            "user@example.com",
        )

        self.assertEqual(
            sub_arn, "arn:aws:sns:us-east-1:123456789012:customer-notifications:sub-1"
        )
        mock_sns.subscribe.assert_called_once_with(
            TopicArn="arn:aws:sns:us-east-1:123456789012:customer-notifications",
            Protocol="email",
            Endpoint="user@example.com",
        )

    @patch("utils.sns_notifications.boto3.client")
    def test_send_order_confirmation(self, mock_boto_client):
        """Test publishing multi-protocol JSON order confirmation notification."""
        mock_sns = MagicMock()
        mock_sns.publish.return_value = {"MessageId": "sns-msg-101"}
        mock_boto_client.return_value = mock_sns

        order_data = {
            "order_id": "ord-777",
            "customer_name": "Alex Rivera",
            "order_date": "2026-11-25",
            "items": [{"title": "Mechanical Keyboard", "quantity": 1, "price": 149.99}],
            "total_amount": 149.99,
            "order_type": "express",
            "customer_tier": "vip",
            "notification_preference": "email_and_sms",
        }
        topic_arn = "arn:aws:sns:us-east-1:123456789012:customer-notifications"

        msg_id = send_order_confirmation(order_data, topic_arn)

        self.assertEqual(msg_id, "sns-msg-101")
        kwargs = mock_sns.publish.call_args.kwargs
        self.assertEqual(kwargs["MessageStructure"], "json")
        self.assertEqual(kwargs["Subject"], "Order Confirmation - ord-777")

        payload = json.loads(kwargs["Message"])
        self.assertIn("Order ord-777 confirmed. Total: $149.99", payload["default"])
        self.assertIn("Dear Alex Rivera", payload["email"])
        self.assertIn("Mechanical Keyboard (Qty: 1) - $149.99", payload["email"])
        self.assertIn("https://store.example.com/track/ord-777", payload["sms"])

        attrs = kwargs["MessageAttributes"]
        self.assertEqual(attrs["order_type"]["StringValue"], "express")
        self.assertEqual(attrs["customer_tier"]["StringValue"], "vip")

    def test_create_email_and_sms_messages(self):
        """Test email and SMS message formatters directly."""
        order_data = {
            "order_id": "ord-10",
            "customer_name": "Sam",
            "order_date": "2026-11-25",
            "items": [{"title": "USB-C Hub", "quantity": 2, "price": 25.0}],
            "total_amount": 50.0,
        }
        email = create_email_message(order_data)
        sms = create_sms_message(order_data)

        self.assertIn("Estimated Delivery: TBD", email)
        self.assertIn("USB-C Hub (Qty: 2) - $25.00", email)
        self.assertEqual(
            sms,
            "Order ord-10 confirmed! Total: $50.00. Track at: https://store.example.com/track/ord-10",
        )

    @patch("utils.sns_notifications.boto3.client")
    def test_setup_filtered_subscriptions(self, mock_boto_client):
        """Test creating subscriptions with SNS FilterPolicy attributes."""
        mock_sns = MagicMock()
        mock_sns.subscribe.side_effect = [
            {"SubscriptionArn": "sub-premium"},
            {"SubscriptionArn": "sub-urgent"},
        ]
        mock_boto_client.return_value = mock_sns

        topic_arn = "arn:aws:sns:us-east-1:123456789012:customer-notifications"
        setup_filtered_subscriptions(topic_arn)

        self.assertEqual(mock_sns.subscribe.call_count, 2)
        self.assertEqual(mock_sns.set_subscription_attributes.call_count, 2)

        first_filter = json.loads(
            mock_sns.set_subscription_attributes.call_args_list[0].kwargs["AttributeValue"]
        )
        self.assertEqual(first_filter, {"customer_tier": ["premium", "vip"]})

        second_filter = json.loads(
            mock_sns.set_subscription_attributes.call_args_list[1].kwargs["AttributeValue"]
        )
        self.assertEqual(second_filter, {"order_type": ["express", "same_day"]})

    @patch("utils.sns_notifications.boto3.client")
    def test_send_inventory_alert_urgency_levels(self, mock_boto_client):
        """Test inventory alert publishes medium and high urgency levels."""
        mock_sns = MagicMock()
        mock_sns.publish.side_effect = [{"MessageId": "alert-1"}, {"MessageId": "alert-2"}]
        mock_boto_client.return_value = mock_sns

        topic_arn = "arn:aws:sns:us-east-1:123456789012:inventory-alerts"

        id_med = send_inventory_alert(
            {"title": "Wireless Mouse", "inventory_count": 3, "category": "Electronics"},
            topic_arn,
        )
        id_high = send_inventory_alert(
            {"title": "Wireless Mouse", "inventory_count": 0, "category": "Electronics", "reorder_level": 15},
            topic_arn,
        )

        self.assertEqual(id_med, "alert-1")
        self.assertEqual(id_high, "alert-2")

        med_attrs = mock_sns.publish.call_args_list[0].kwargs["MessageAttributes"]
        self.assertEqual(med_attrs["urgency"]["StringValue"], "medium")
        self.assertEqual(med_attrs["alert_type"]["StringValue"], "inventory_low")

        high_kwargs = mock_sns.publish.call_args_list[1].kwargs
        self.assertEqual(high_kwargs["MessageAttributes"]["urgency"]["StringValue"], "high")
        self.assertIn("Reorder level: 15", json.loads(high_kwargs["Message"])["email"])


if __name__ == "__main__":
    unittest.main()
