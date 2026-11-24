"""Unit Tests for Graceful Degradation in Order Processing."""
import unittest
from unittest.mock import MagicMock, patch

from utils.graceful_degradation import (
    process_order,
    get_estimated_shipping_rate,
    PaymentProcessingError,
    InventoryError,
    NotificationError
)


class TestGracefulDegradation(unittest.TestCase):

    def setUp(self):
        self.valid_order = {
            "order_id": "ord_9901",
            "destination": "US",
            "items": [
                {"product_id": "prod_1", "quantity": 2, "price": 49.99}
            ],
            "customer_email": "alex@example.com",
            "payment": {
                "order_id": "ord_9901",
                "amount": 99.98,
                "token": "tok_visa_4242"
            }
        }

    @patch('time.sleep', return_value=None)
    def test_process_order_all_services_healthy(self, mock_sleep):
        """Test happy path where payment, shipping, inventory, and notifications all succeed synchronously."""
        mock_payment = MagicMock(return_value={"status": "success", "transaction_id": "txn_clean_123"})
        mock_shipping = MagicMock(return_value=12.50)
        mock_inv = MagicMock()
        mock_q_inv = MagicMock()
        mock_email = MagicMock()
        mock_q_email = MagicMock()

        result = process_order(
            self.valid_order,
            process_payment_fn=mock_payment,
            get_shipping_rate_fn=mock_shipping,
            update_inventory_fn=mock_inv,
            queue_inventory_update_fn=mock_q_inv,
            send_confirmation_email_fn=mock_email,
            queue_email_fn=mock_q_email
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["order_id"], "ord_9901")
        self.assertEqual(result["payment_id"], "txn_clean_123")
        self.assertEqual(result["shipping_rate"], 12.50)

        # Sync services called
        mock_payment.assert_called_once()
        mock_shipping.assert_called_once()
        mock_inv.assert_called_once_with(self.valid_order["items"])
        mock_email.assert_called_once_with("alex@example.com", "ord_9901")

        # Async queues should not be triggered
        mock_q_inv.assert_not_called()
        mock_q_email.assert_not_called()

    @patch('time.sleep', return_value=None)
    def test_process_order_payment_critical_failure_aborts(self, mock_sleep):
        """Test critical failure: when payment fails, order processing aborts immediately."""
        mock_payment = MagicMock(side_effect=PaymentProcessingError("Card declined"))
        mock_shipping = MagicMock()
        mock_inv = MagicMock()
        mock_email = MagicMock()

        result = process_order(
            self.valid_order,
            process_payment_fn=mock_payment,
            get_shipping_rate_fn=mock_shipping,
            update_inventory_fn=mock_inv,
            send_confirmation_email_fn=mock_email
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"], "Payment processing failed")
        self.assertEqual(result["order_id"], "ord_9901")

        # 1 initial + 3 retries = 4 attempts
        self.assertEqual(mock_payment.call_count, 4)

        # Downstream operations must never be triggered
        mock_shipping.assert_not_called()
        mock_inv.assert_not_called()
        mock_email.assert_not_called()

    @patch('time.sleep', return_value=None)
    def test_process_order_shipping_rate_degradation_to_cached_estimate(self, mock_sleep):
        """Test shipping carrier outage falls back gracefully to estimated/cached rate."""
        mock_payment = MagicMock(return_value={"status": "success", "transaction_id": "txn_ship_fallback"})
        mock_shipping = MagicMock(side_effect=TimeoutError("Carrier API down"))
        mock_inv = MagicMock()
        mock_email = MagicMock()

        result = process_order(
            self.valid_order,
            process_payment_fn=mock_payment,
            get_shipping_rate_fn=mock_shipping,
            update_inventory_fn=mock_inv,
            send_confirmation_email_fn=mock_email
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["payment_id"], "txn_ship_fallback")
        # US cached estimate is 9.99
        self.assertEqual(result["shipping_rate"], 9.99)

        # 1 initial + 2 retries = 3 shipping attempts
        self.assertEqual(mock_shipping.call_count, 3)
        mock_inv.assert_called_once()
        mock_email.assert_called_once()

    @patch('time.sleep', return_value=None)
    def test_process_order_inventory_async_triage(self, mock_sleep):
        """Test inventory update failure degrades to asynchronous queue message."""
        mock_payment = MagicMock(return_value={"status": "success", "transaction_id": "txn_inv_degraded"})
        mock_shipping = MagicMock(return_value=10.00)
        mock_inv = MagicMock(side_effect=InventoryError("Database lock contention"))
        mock_q_inv = MagicMock()
        mock_email = MagicMock()

        result = process_order(
            self.valid_order,
            process_payment_fn=mock_payment,
            get_shipping_rate_fn=mock_shipping,
            update_inventory_fn=mock_inv,
            queue_inventory_update_fn=mock_q_inv,
            send_confirmation_email_fn=mock_email
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["payment_id"], "txn_inv_degraded")
        mock_inv.assert_called_once()
        mock_q_inv.assert_called_once_with(self.valid_order["items"])
        mock_email.assert_called_once()

    @patch('time.sleep', return_value=None)
    def test_process_order_email_notification_async_triage(self, mock_sleep):
        """Test email dispatch failure degrades to asynchronous queue message."""
        mock_payment = MagicMock(return_value={"status": "success", "transaction_id": "txn_email_degraded"})
        mock_shipping = MagicMock(return_value=15.00)
        mock_inv = MagicMock()
        mock_email = MagicMock(side_effect=NotificationError("SES rate limit exceeded"))
        mock_q_email = MagicMock()

        result = process_order(
            self.valid_order,
            process_payment_fn=mock_payment,
            get_shipping_rate_fn=mock_shipping,
            update_inventory_fn=mock_inv,
            send_confirmation_email_fn=mock_email,
            queue_email_fn=mock_q_email
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["payment_id"], "txn_email_degraded")
        mock_email.assert_called_once()
        mock_q_email.assert_called_once_with("alex@example.com", "ord_9901")

    @patch('time.sleep', return_value=None)
    def test_process_order_combined_multi_service_degradation(self, mock_sleep):
        """Test multi-service failure: shipping falls back, inventory queues, email queues, order still succeeds."""
        mock_payment = MagicMock(return_value={"status": "success", "transaction_id": "txn_all_degraded"})
        mock_shipping = MagicMock(side_effect=Exception("Carrier 503"))
        mock_inv = MagicMock(side_effect=Exception("DynamoDB throttled"))
        mock_q_inv = MagicMock()
        mock_email = MagicMock(side_effect=Exception("SES unavailable"))
        mock_q_email = MagicMock()

        order_ca = dict(self.valid_order)
        order_ca["destination"] = "CA"

        result = process_order(
            order_ca,
            process_payment_fn=mock_payment,
            get_shipping_rate_fn=mock_shipping,
            update_inventory_fn=mock_inv,
            queue_inventory_update_fn=mock_q_inv,
            send_confirmation_email_fn=mock_email,
            queue_email_fn=mock_q_email
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["payment_id"], "txn_all_degraded")
        # CA cached fallback is 14.99
        self.assertEqual(result["shipping_rate"], 14.99)
        mock_q_inv.assert_called_once_with(order_ca["items"])
        mock_q_email.assert_called_once_with("alex@example.com", "ord_9901")


if __name__ == "__main__":
    unittest.main()
