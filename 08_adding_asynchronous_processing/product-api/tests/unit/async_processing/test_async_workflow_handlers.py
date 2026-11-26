import json
import os
import unittest
from unittest.mock import MagicMock, patch

from lambda_code.async_workflow_handlers import (
    configure_lambda_triggers,
    execute_order_workflow,
    inventory_monitor_handler,
    notification_dispatcher_handler,
    order_processor_handler,
    rollback_completed_steps,
)
from lambda_code.order_processor import OrderProcessingError


class TestAsyncWorkflowHandlers(unittest.TestCase):

    def setUp(self):
        self.sample_order = {
            "order_id": "ord-800",
            "customer_id": "cust-88",
            "items": [{"id": "prod-1", "quantity": 1}],
            "total_amount": 59.99,
        }

    @patch.dict(
        os.environ,
        {
            "CUSTOMER_NOTIFICATION_TOPIC": "arn:aws:sns:us-east-1:123:customer",
            "SYSTEM_ALERT_TOPIC": "arn:aws:sns:us-east-1:123:system",
        },
    )
    @patch("lambda_code.async_workflow_handlers.update_order_status")
    @patch("lambda_code.async_workflow_handlers.send_order_confirmation")
    @patch("lambda_code.async_workflow_handlers.execute_order_workflow")
    @patch("lambda_code.async_workflow_handlers.boto3.client")
    def test_order_processor_handler_success(
        self, mock_boto_client, mock_workflow, mock_confirm, mock_status
    ):
        """Test order_processor_handler confirms order and updates status on success."""
        mock_workflow.return_value = {"success": True}
        event = {"Records": [{"body": json.dumps(self.sample_order)}]}

        res = order_processor_handler(event, None)

        self.assertEqual(res["statusCode"], 200)
        mock_confirm.assert_called_once_with(
            self.sample_order, "arn:aws:sns:us-east-1:123:customer"
        )
        mock_status.assert_called_once_with("ord-800", "confirmed")

    @patch.dict(
        os.environ,
        {
            "CUSTOMER_NOTIFICATION_TOPIC": "arn:aws:sns:us-east-1:123:customer",
            "SYSTEM_ALERT_TOPIC": "arn:aws:sns:us-east-1:123:system",
        },
    )
    @patch("lambda_code.async_workflow_handlers.send_system_alert")
    @patch("lambda_code.async_workflow_handlers.update_order_status")
    @patch("lambda_code.async_workflow_handlers.send_processing_failure_alert")
    @patch("lambda_code.async_workflow_handlers.execute_order_workflow")
    @patch("lambda_code.async_workflow_handlers.boto3.client")
    def test_order_processor_handler_failure_alerts_and_raises(
        self, mock_boto_client, mock_workflow, mock_fail_alert, mock_status, mock_sys_alert
    ):
        """Test order_processor_handler sends alerts, marks failed, and raises for SQS retry."""
        mock_workflow.return_value = {"success": False, "error": "Payment declined"}
        event = {"Records": [{"body": json.dumps(self.sample_order)}]}

        with self.assertRaises(OrderProcessingError):
            order_processor_handler(event, None)

        mock_fail_alert.assert_called_once()
        mock_status.assert_called_once_with("ord-800", "failed")
        mock_sys_alert.assert_called_once()

    @patch.dict(
        os.environ,
        {"INVENTORY_ALERT_TOPIC": "arn:aws:sns:us-east-1:123:inventory"},
    )
    @patch("lambda_code.async_workflow_handlers.send_inventory_alert")
    @patch("lambda_code.async_workflow_handlers.boto3.client")
    @patch("lambda_code.async_workflow_handlers.boto3.resource")
    def test_inventory_monitor_handler(self, mock_resource, mock_client, mock_send_alert):
        """Test inventory_monitor_handler scans low stock and updates alert timestamp."""
        mock_table = MagicMock()
        mock_table.scan.return_value = {
            "Items": [
                {"id": "p1", "title": "Mouse", "inventory_count": 2, "reorder_level": 5, "category": "Tech"}
            ]
        }
        mock_resource.return_value.Table.return_value = mock_table
        mock_send_alert.return_value = "alert-msg-1"

        res = inventory_monitor_handler({}, None)

        self.assertEqual(res["statusCode"], 200)
        self.assertIn("Processed 1 low stock alerts", res["body"])
        mock_send_alert.assert_called_once()
        mock_table.update_item.assert_called_once()

    @patch("lambda_code.async_workflow_handlers.send_admin_notification")
    @patch("lambda_code.async_workflow_handlers.create_reorder_task")
    @patch("lambda_code.async_workflow_handlers.send_inventory_email")
    @patch("lambda_code.async_workflow_handlers.send_order_sms")
    @patch("lambda_code.async_workflow_handlers.send_order_email")
    def test_notification_dispatcher_handler_routing(
        self, mock_order_email, mock_order_sms, mock_inv_email, mock_reorder, mock_admin
    ):
        """Test notification_dispatcher_handler routes by notification_type attribute."""
        event = {
            "Records": [
                {
                    "Sns": {
                        "Message": json.dumps({"order_id": "ord-1"}),
                        "MessageAttributes": {"notification_type": {"Value": "order_confirmation"}},
                    }
                },
                {
                    "Sns": {
                        "Message": json.dumps({"product_id": "p1"}),
                        "MessageAttributes": {"notification_type": {"Value": "inventory_alert"}},
                    }
                },
                {
                    "Sns": {
                        "Message": json.dumps({"error": "timeout"}),
                        "MessageAttributes": {"notification_type": {"Value": "system_alert"}},
                    }
                },
            ]
        }

        res = notification_dispatcher_handler(event, None)

        self.assertEqual(res["statusCode"], 200)
        mock_order_email.assert_called_once()
        mock_order_sms.assert_called_once()
        mock_inv_email.assert_called_once()
        mock_reorder.assert_called_once()
        mock_admin.assert_called_once()

    def test_execute_order_workflow_success(self):
        """Test execute_order_workflow completes all 4 steps."""
        res = execute_order_workflow(self.sample_order)

        self.assertTrue(res["success"])
        self.assertEqual(len(res["completed_steps"]), 4)
        self.assertGreaterEqual(res["total_processing_time"], 0.0)

    @patch("lambda_code.async_workflow_handlers.rollback_payment_charge")
    @patch("lambda_code.async_workflow_handlers.rollback_inventory_reservation")
    @patch("lambda_code.async_workflow_handlers.create_shipping_step")
    def test_execute_order_workflow_rolls_back_on_step_failure(
        self, mock_shipping_step, mock_rb_inv, mock_rb_pay
    ):
        """Test execute_order_workflow rolls back completed steps in reverse order on failure."""
        mock_shipping_step.return_value = {"success": False, "error": "Carrier API offline"}

        res = execute_order_workflow(self.sample_order)

        self.assertFalse(res["success"])
        self.assertEqual(res["failed_step"], "create_shipping")
        self.assertIn("Carrier API offline", res["error"])
        mock_rb_pay.assert_called_once()
        mock_rb_inv.assert_called_once()

    @patch("lambda_code.async_workflow_handlers.rollback_inventory_reservation")
    @patch("lambda_code.async_workflow_handlers.rollback_payment_charge")
    def test_rollback_completed_steps_continues_on_rollback_error(self, mock_rb_pay, mock_rb_inv):
        """Test rollback_completed_steps continues rolling back remaining steps if one fails."""
        mock_rb_pay.side_effect = Exception("Refund API down")
        completed = [
            {"step": "validate_inventory", "result": {}},
            {"step": "process_payment", "result": {}},
        ]

        rollback_completed_steps(completed, self.sample_order)

        mock_rb_pay.assert_called_once()
        mock_rb_inv.assert_called_once()

    @patch("lambda_code.async_workflow_handlers.boto3.client")
    def test_configure_lambda_triggers(self, mock_boto_client):
        """Test configure_lambda_triggers sets up SQS event source mapping and SNS permission."""
        mock_lambda = MagicMock()
        mock_boto_client.return_value = mock_lambda

        configure_lambda_triggers()

        mock_lambda.create_event_source_mapping.assert_called_once()
        esm_kwargs = mock_lambda.create_event_source_mapping.call_args.kwargs
        self.assertEqual(esm_kwargs["FunctionName"], "order-processor")
        self.assertEqual(esm_kwargs["BatchSize"], 10)
        self.assertEqual(esm_kwargs["MaximumBatchingWindowInSeconds"], 5)

        mock_lambda.add_permission.assert_called_once()
        perm_kwargs = mock_lambda.add_permission.call_args.kwargs
        self.assertEqual(perm_kwargs["FunctionName"], "notification-dispatcher")
        self.assertEqual(perm_kwargs["Principal"], "sns.amazonaws.com")


if __name__ == "__main__":
    unittest.main()
