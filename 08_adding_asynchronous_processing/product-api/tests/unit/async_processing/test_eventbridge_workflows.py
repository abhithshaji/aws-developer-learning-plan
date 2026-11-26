import json
import os
import unittest
from unittest.mock import MagicMock, patch

import boto3
from moto import mock_aws

from lambda_code.eventbridge_handlers import (
    analytics_processor_handler,
    inventory_processor_handler,
    notification_processor_handler,
    process_failed_events_handler,
)
from utils.eventbridge_error_handling import (
    create_event_monitoring_dashboard,
    setup_event_error_handling,
)


class TestEventBridgeWorkflows(unittest.TestCase):

    @mock_aws
    def test_inventory_processor_handler_order_placed(self):
        """Test inventory_processor_handler decrements inventory_count in DynamoDB."""
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = dynamodb.create_table(
            TableName="Products",
            KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        table.put_item(Item={"id": "prod-1", "inventory_count": 10})

        event = {
            "detail-type": "Order Placed",
            "detail": {"items": [{"productId": "prod-1", "quantity": 3}]},
        }

        res = inventory_processor_handler(event, None)

        self.assertEqual(res, {"statusCode": 200, "body": "Event processed"})
        updated = table.get_item(Key={"id": "prod-1"})["Item"]
        self.assertEqual(updated["inventory_count"], 7)

    @patch.dict(os.environ, {"ORDER_TOPIC_ARN": "arn:aws:sns:us-east-1:123:order-topic"})
    @patch("lambda_code.eventbridge_handlers.boto3.client")
    def test_notification_processor_handler(self, mock_boto_client):
        """Test notification_processor_handler publishes Order Placed detail to SNS."""
        mock_sns = MagicMock()
        mock_boto_client.return_value = mock_sns

        event = {
            "detail-type": "Order Placed",
            "detail": {"orderId": "ord-123", "orderAmount": 49.99},
        }

        res = notification_processor_handler(event, None)

        self.assertEqual(res, {"statusCode": 200, "body": "Notifications sent"})
        mock_sns.publish.assert_called_once_with(
            TopicArn="arn:aws:sns:us-east-1:123:order-topic",
            Message=json.dumps(event["detail"]),
            Subject="Order Confirmation",
        )

    @mock_aws
    def test_analytics_processor_handler(self):
        """Test analytics_processor_handler writes event record to AnalyticsEvents table."""
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = dynamodb.create_table(
            TableName="AnalyticsEvents",
            KeySchema=[{"AttributeName": "event_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "event_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        context = MagicMock()
        context.aws_request_id = "req-abc-123"
        event = {
            "detail-type": "Order Placed",
            "time": "2026-11-26T13:00:00Z",
            "detail": {"orderId": "ord-123"},
        }

        res = analytics_processor_handler(event, context)

        self.assertEqual(res, {"statusCode": 200, "body": "Analytics processed"})
        saved = table.get_item(Key={"event_id": "req-abc-123"})["Item"]
        self.assertEqual(saved["event_type"], "Order Placed")
        self.assertEqual(json.loads(saved["event_detail"]), {"orderId": "ord-123"})

    @patch("lambda_code.eventbridge_handlers.store_for_investigation")
    @patch("lambda_code.eventbridge_handlers.attempt_recovery")
    @patch("lambda_code.eventbridge_handlers.is_recoverable")
    def test_process_failed_events_handler(self, mock_is_rec, mock_recover, mock_store):
        """Test DLQ failed event handler routes recoverable vs non-recoverable events."""
        mock_is_rec.side_effect = [True, False]
        event = {
            "Records": [
                {"body": json.dumps({"eventId": "e1", "error": "timeout"})},
                {"body": json.dumps({"eventId": "e2", "error": "validation_error"})},
            ]
        }

        process_failed_events_handler(event, None)

        mock_recover.assert_called_once_with({"eventId": "e1", "error": "timeout"})
        mock_store.assert_called_once_with({"eventId": "e2", "error": "validation_error"})

    @patch("utils.eventbridge_error_handling.boto3.client")
    def test_setup_event_error_handling(self, mock_boto_client):
        """Test creating EventBridge DLQ and attaching RetryPolicy + DeadLetterConfig."""
        mock_eb = MagicMock()
        mock_sqs = MagicMock()
        mock_sqs.create_queue.return_value = {
            "QueueUrl": "https://sqs.us-east-1.amazonaws.com/123/eventbridge-failed-events-dlq"
        }
        mock_sqs.get_queue_attributes.return_value = {
            "Attributes": {"QueueArn": "arn:aws:sqs:us-east-1:123:eventbridge-failed-events-dlq"}
        }
        mock_boto_client.side_effect = lambda svc: mock_eb if svc == "events" else mock_sqs

        setup_event_error_handling()

        mock_sqs.create_queue.assert_called_once()
        target = mock_eb.put_targets.call_args.kwargs["Targets"][0]
        self.assertEqual(target["RetryPolicy"]["MaximumRetryAttempts"], 3)
        self.assertEqual(target["RetryPolicy"]["MaximumEventAge"], 3600)
        self.assertEqual(
            target["DeadLetterConfig"]["Arn"],
            "arn:aws:sqs:us-east-1:123:eventbridge-failed-events-dlq",
        )

    @patch("utils.eventbridge_error_handling.boto3.client")
    def test_create_event_monitoring_dashboard(self, mock_boto_client):
        """Test creating CloudWatch dashboard for EventBridge and Lambda metrics."""
        mock_cw = MagicMock()
        mock_boto_client.return_value = mock_cw

        create_event_monitoring_dashboard()

        mock_cw.put_dashboard.assert_called_once()
        kwargs = mock_cw.put_dashboard.call_args.kwargs
        self.assertEqual(kwargs["DashboardName"], "EventDrivenArchitecture-Monitoring")
        body = json.loads(kwargs["DashboardBody"])
        self.assertEqual(len(body["widgets"]), 2)


if __name__ == "__main__":
    unittest.main()
