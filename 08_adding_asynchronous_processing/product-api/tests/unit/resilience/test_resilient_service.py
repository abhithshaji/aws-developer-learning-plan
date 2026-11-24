"""Unit Tests for ResilientExternalService and Strategy Combination."""
import json
import unittest
from unittest.mock import MagicMock, patch

from utils.circuit_breaker import CircuitBreaker, CircuitState
from utils.resilient_service import (
    ResilientExternalService,
    get_cached_shipping_rate,
    handler
)


class TestResilientExternalService(unittest.TestCase):

    def setUp(self):
        self.breaker = CircuitBreaker(failure_threshold=3, timeout=10, success_threshold=2)
        self.retry_cfg = {"max_retries": 2, "base_delay": 0.05, "max_delay": 1}
        self.service = ResilientExternalService(
            service_name="test_service",
            circuit_breaker=self.breaker,
            retry_config=self.retry_cfg
        )

    @patch('time.sleep', return_value=None)
    def test_call_success_first_attempt(self, mock_sleep):
        """Test call succeeds directly on first attempt."""
        action = MagicMock(return_value="payload_ok")
        resp = self.service.call(action)

        self.assertEqual(resp, {"status": "success", "data": "payload_ok"})
        self.assertEqual(action.call_count, 1)
        mock_sleep.assert_not_called()
        self.assertEqual(self.breaker.state, CircuitState.CLOSED)

    @patch('time.sleep', return_value=None)
    def test_call_recovers_via_retry(self, mock_sleep):
        """Test call recovers after transient retryable error."""
        action = MagicMock(side_effect=[Exception("Transient glitched network"), "recovered_ok"])
        resp = self.service.call(action)

        self.assertEqual(resp, {"status": "success", "data": "recovered_ok"})
        self.assertEqual(action.call_count, 2)
        mock_sleep.assert_called_once()
        self.assertEqual(self.breaker.state, CircuitState.CLOSED)

    @patch('time.sleep', return_value=None)
    def test_call_fails_with_fallback(self, mock_sleep):
        """Test call executes fallback when all retries are exhausted."""
        action = MagicMock(side_effect=Exception("Hard downstream outage"))
        fallback_fn = MagicMock(return_value="cached_fallback_rate")

        resp = self.service.call(action, fallback=fallback_fn)

        self.assertEqual(resp, {"status": "fallback", "data": "cached_fallback_rate"})
        fallback_fn.assert_called_once()
        # 1 initial + 2 retries = 3 calls
        self.assertEqual(action.call_count, 3)

    @patch('time.sleep', return_value=None)
    def test_call_fails_without_fallback(self, mock_sleep):
        """Test call returns failed envelope when no fallback is configured."""
        action = MagicMock(side_effect=Exception("Service crashed"))
        resp = self.service.call(action)

        self.assertEqual(resp["status"], "failed")
        self.assertIn("Service crashed", resp["error"])

    @patch('time.sleep', return_value=None)
    def test_circuit_trips_to_open_and_fails_fast(self, mock_sleep):
        """Test multiple exhausted retry failures trip breaker to OPEN, failing fast."""
        action = MagicMock(side_effect=Exception("Repeated 500 internal error"))

        # Trip breaker: failure_threshold = 3
        for _ in range(3):
            self.service.call(action)

        self.assertEqual(self.breaker.state, CircuitState.OPEN)

        # Next call should fail fast without running action retries
        action.reset_mock()
        mock_sleep.reset_mock()

        resp = self.service.call(action, fallback=lambda: "fast_fail_fallback")
        self.assertEqual(resp, {"status": "fallback", "data": "fast_fail_fallback"})
        action.assert_not_called()
        mock_sleep.assert_not_called()

    @patch('time.sleep', return_value=None)
    def test_handler_success(self, mock_sleep):
        """Test Lambda handler with healthy payment and shipping services."""
        event = {
            "body": json.dumps({
                "order_id": "ord_1001",
                "destination": "US",
                "payment": {"amount": 50.0}
            })
        }
        res = handler(event, None)
        self.assertEqual(res["statusCode"], 200)

        body = json.loads(res["body"])
        self.assertEqual(body["order_id"], "ord_1001")
        self.assertEqual(body["payment_status"], "success")
        self.assertEqual(body["shipping_rate"], 15.00)

    @patch('time.sleep', return_value=None)
    def test_handler_critical_payment_failure(self, mock_sleep):
        """Test Lambda handler aborts with HTTP 500 when payment fails."""
        mock_pay_svc = MagicMock()
        mock_pay_svc.call.return_value = {"status": "failed", "error": "Gateway timeout"}

        event = {
            "body": json.dumps({
                "order_id": "ord_1002",
                "destination": "EU",
                "payment": {"amount": 75.0}
            })
        }
        res = handler(event, None, payment_svc=mock_pay_svc)
        self.assertEqual(res["statusCode"], 500)

        body = json.loads(res["body"])
        self.assertEqual(body["error"], "Payment processing failed")

    @patch('time.sleep', return_value=None)
    def test_handler_non_critical_shipping_fallback(self, mock_sleep):
        """Test Lambda handler returns 200 with cached shipping when live calculation fails."""
        mock_pay_svc = MagicMock()
        mock_pay_svc.call.return_value = {"status": "success", "data": "txn_ok"}

        mock_ship_svc = ResilientExternalService(
            service_name="shipping_test",
            circuit_breaker=CircuitBreaker(failure_threshold=2, timeout=10),
            retry_config={"max_retries": 1, "base_delay": 0.05, "max_delay": 1}
        )

        def failing_shipping_fn(order_data):
            raise Exception("Carrier API 503")

        event = {
            "body": json.dumps({
                "order_id": "ord_1003",
                "destination": "CA",
                "payment": {"amount": 120.0}
            })
        }

        res = handler(
            event,
            None,
            payment_svc=mock_pay_svc,
            shipping_svc=mock_ship_svc,
            shipping_fn=failing_shipping_fn
        )
        self.assertEqual(res["statusCode"], 200)

        body = json.loads(res["body"])
        self.assertEqual(body["order_id"], "ord_1003")
        self.assertEqual(body["payment_status"], "success")
        # CA cached rate fallback is 14.99
        self.assertEqual(body["shipping_rate"], 14.99)


if __name__ == "__main__":
    unittest.main()
