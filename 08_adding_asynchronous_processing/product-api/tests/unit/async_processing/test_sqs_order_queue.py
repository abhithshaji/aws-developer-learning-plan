import json
import unittest
from unittest.mock import MagicMock, patch

from utils.sqs_order_queue import create_order_processing_queue, send_order_to_queue


class TestSQSOrderQueue(unittest.TestCase):

    @patch("utils.sqs_order_queue.boto3.client")
    def test_create_order_processing_queue(self, mock_boto_client):
        """Test creating main order processing queue and dead-letter queue."""
        mock_sqs = MagicMock()
        mock_sqs.create_queue.side_effect = [
            {"QueueUrl": "https://sqs.us-east-1.amazonaws.com/123456789012/order-processing-queue"},
            {"QueueUrl": "https://sqs.us-east-1.amazonaws.com/123456789012/order-processing-dlq"},
        ]
        mock_boto_client.return_value = mock_sqs

        main_url, dlq_url = create_order_processing_queue()

        self.assertEqual(main_url, "https://sqs.us-east-1.amazonaws.com/123456789012/order-processing-queue")
        self.assertEqual(dlq_url, "https://sqs.us-east-1.amazonaws.com/123456789012/order-processing-dlq")
        self.assertEqual(mock_sqs.create_queue.call_count, 2)

        first_call = mock_sqs.create_queue.call_args_list[0].kwargs
        self.assertEqual(first_call["QueueName"], "order-processing-queue")
        self.assertEqual(first_call["Attributes"]["VisibilityTimeoutSeconds"], "300")
        self.assertEqual(first_call["Attributes"]["ReceiveMessageWaitTimeSeconds"], "20")
        redrive = json.loads(first_call["Attributes"]["RedrivePolicy"])
        self.assertEqual(redrive["maxReceiveCount"], 3)

        second_call = mock_sqs.create_queue.call_args_list[1].kwargs
        self.assertEqual(second_call["QueueName"], "order-processing-dlq")
        self.assertEqual(second_call["Attributes"]["VisibilityTimeoutSeconds"], "60")

    @patch("utils.sqs_order_queue.boto3.client")
    def test_send_order_to_queue_defaults(self, mock_boto_client):
        """Test sending order payload with default priority and customer tier."""
        mock_sqs = MagicMock()
        mock_sqs.send_message.return_value = {"MessageId": "msg-001"}
        mock_boto_client.return_value = mock_sqs

        order_data = {
            "order_id": "ord-123",
            "customer_id": "cust-456",
            "items": [{"id": "prod-1", "quantity": 2}],
            "total_amount": 99.98,
        }
        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789012/order-processing-queue"

        message_id = send_order_to_queue(order_data, queue_url)

        self.assertEqual(message_id, "msg-001")
        call_kwargs = mock_sqs.send_message.call_args.kwargs
        self.assertEqual(call_kwargs["QueueUrl"], queue_url)

        body = json.loads(call_kwargs["MessageBody"])
        self.assertEqual(body["order_id"], "ord-123")
        self.assertEqual(body["customer_id"], "cust-456")
        self.assertEqual(body["total_amount"], 99.98)
        self.assertIn("timestamp", body)
        self.assertEqual(
            body["processing_steps"],
            ["validate_inventory", "process_payment", "create_shipping_label", "send_confirmation"],
        )

        attrs = call_kwargs["MessageAttributes"]
        self.assertEqual(attrs["order_priority"]["StringValue"], "standard")
        self.assertEqual(attrs["customer_tier"]["StringValue"], "regular")

    @patch("utils.sqs_order_queue.boto3.client")
    def test_send_order_to_queue_custom_attributes(self, mock_boto_client):
        """Test sending order payload with custom priority and customer tier."""
        mock_sqs = MagicMock()
        mock_sqs.send_message.return_value = {"MessageId": "msg-002"}
        mock_boto_client.return_value = mock_sqs

        order_data = {
            "order_id": "ord-999",
            "customer_id": "cust-vip",
            "items": [{"id": "prod-2", "quantity": 1}],
            "total_amount": 250.0,
            "priority": "high",
            "customer_tier": "vip",
        }

        message_id = send_order_to_queue(order_data, "https://sqs.example.com/q")
        self.assertEqual(message_id, "msg-002")

        attrs = mock_sqs.send_message.call_args.kwargs["MessageAttributes"]
        self.assertEqual(attrs["order_priority"]["StringValue"], "high")
        self.assertEqual(attrs["customer_tier"]["StringValue"], "vip")


if __name__ == "__main__":
    unittest.main()
