import json
import unittest
from unittest.mock import patch

import boto3
from moto import mock_aws

from lambda_code.order_processor import (
    OrderProcessingError,
    handler,
    process_order_workflow,
    validate_inventory,
)


class TestOrderProcessor(unittest.TestCase):

    def setUp(self):
        self.sample_order = {
            "order_id": "ord-500",
            "customer_id": "cust-10",
            "items": [{"id": "prod-1", "quantity": 2}],
            "total_amount": 120.0,
        }

    @patch("lambda_code.order_processor.boto3.client")
    @patch("lambda_code.order_processor.process_order_workflow")
    def test_handler_success(self, mock_workflow, mock_boto_client):
        """Test SQS Lambda handler processes all records cleanly."""
        mock_workflow.return_value = {
            "success": True,
            "payment_id": "txn_1",
            "shipping_label": "https://shipping.example.com/labels/ord-500.pdf",
        }
        event = {"Records": [{"body": json.dumps(self.sample_order)}]}

        res = handler(event, None)

        self.assertEqual(res["statusCode"], 200)
        self.assertEqual(res["body"], "Orders processed successfully")
        mock_workflow.assert_called_once_with(self.sample_order)

    @patch("lambda_code.order_processor.boto3.client")
    @patch("lambda_code.order_processor.process_order_workflow")
    def test_handler_workflow_failure_raises_error(self, mock_workflow, mock_boto_client):
        """Test handler raises OrderProcessingError so SQS retries the message."""
        mock_workflow.return_value = {"success": False, "error": "Insufficient inventory"}
        event = {"Records": [{"body": json.dumps(self.sample_order)}]}

        with self.assertRaises(OrderProcessingError) as ctx:
            handler(event, None)

        self.assertIn("Failed to process order ord-500", str(ctx.exception))

    @patch("lambda_code.order_processor.update_order_status")
    @patch("lambda_code.order_processor.create_shipping_label")
    @patch("lambda_code.order_processor.process_payment")
    @patch("lambda_code.order_processor.validate_inventory")
    def test_process_order_workflow_success(self, mock_inv, mock_pay, mock_ship, mock_status):
        """Test full order workflow succeeds across all 4 steps."""
        mock_inv.return_value = {"available": True}
        mock_pay.return_value = {"success": True, "transaction_id": "txn_abc"}
        mock_ship.return_value = {"success": True, "label_url": "https://labels/ord-500.pdf"}

        result = process_order_workflow(self.sample_order)

        self.assertTrue(result["success"])
        self.assertEqual(result["payment_id"], "txn_abc")
        self.assertEqual(result["shipping_label"], "https://labels/ord-500.pdf")
        mock_status.assert_called_once_with("ord-500", "processing")

    @patch("lambda_code.order_processor.validate_inventory")
    def test_process_order_workflow_insufficient_inventory(self, mock_inv):
        """Test workflow stops at step 1 when inventory is insufficient."""
        mock_inv.return_value = {"available": False, "reason": "Out of stock"}

        result = process_order_workflow(self.sample_order)

        self.assertEqual(result, {"success": False, "error": "Insufficient inventory"})

    @patch("lambda_code.order_processor.process_payment")
    @patch("lambda_code.order_processor.validate_inventory")
    def test_process_order_workflow_payment_failure(self, mock_inv, mock_pay):
        """Test workflow stops at step 2 when payment fails."""
        mock_inv.return_value = {"available": True}
        mock_pay.return_value = {"success": False}

        result = process_order_workflow(self.sample_order)

        self.assertEqual(result, {"success": False, "error": "Payment processing failed"})

    @patch("lambda_code.order_processor.refund_payment")
    @patch("lambda_code.order_processor.create_shipping_label")
    @patch("lambda_code.order_processor.process_payment")
    @patch("lambda_code.order_processor.validate_inventory")
    def test_process_order_workflow_shipping_failure_refunds_payment(
        self, mock_inv, mock_pay, mock_ship, mock_refund
    ):
        """Test shipping label failure triggers compensating payment refund."""
        mock_inv.return_value = {"available": True}
        mock_pay.return_value = {"success": True, "transaction_id": "txn_refund_me"}
        mock_ship.return_value = {"success": False}

        result = process_order_workflow(self.sample_order)

        self.assertEqual(result, {"success": False, "error": "Shipping label creation failed"})
        mock_refund.assert_called_once_with("txn_refund_me")

    @mock_aws
    def test_validate_inventory_with_dynamodb(self):
        """Test validate_inventory against mocked Products DynamoDB table."""
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = dynamodb.create_table(
            TableName="Products",
            KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        table.put_item(Item={"id": "prod-1", "inventory_count": 5})

        self.assertEqual(validate_inventory([{"id": "prod-1", "quantity": 3}]), {"available": True})
        self.assertEqual(
            validate_inventory([{"id": "prod-1", "quantity": 10}]),
            {"available": False, "reason": "Insufficient inventory for prod-1"},
        )
        self.assertEqual(
            validate_inventory([{"id": "missing-id", "quantity": 1}]),
            {"available": False, "reason": "Product missing-id not found"},
        )


if __name__ == "__main__":
    unittest.main()
