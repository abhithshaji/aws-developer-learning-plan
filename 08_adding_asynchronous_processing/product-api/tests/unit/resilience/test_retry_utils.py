import unittest
from unittest.mock import patch, MagicMock
from utils.retry_utils import (
    retry_with_exponential_backoff,
    get_shipping_rate,
    get_cached_rate,
    RetryPolicyManager,
    RetryableError,
    PermanentError,
    DatabaseTimeoutError,
    RateLimitError
)

class TestRetryUtils(unittest.TestCase):

    @patch('time.sleep', return_value=None)
    def test_retry_success_after_transient_failure(self, mock_sleep):
        """Test operation succeeds on retry after a transient error."""
        mock_func = MagicMock(side_effect=[DatabaseTimeoutError("Temporary timeout"), "success_result"])

        decorated = retry_with_exponential_backoff(max_retries=2, base_delay=0.1)(mock_func)
        result = decorated()

        self.assertEqual(result, "success_result")
        self.assertEqual(mock_func.call_count, 2)
        mock_sleep.assert_called_once()

    @patch('time.sleep', return_value=None)
    def test_max_retries_exceeded_raises_error(self, mock_sleep):
        """Test operation raises error once max retries are exhausted."""
        mock_func = MagicMock(side_effect=DatabaseTimeoutError("Persistent DB error"))

        decorated = retry_with_exponential_backoff(max_retries=2, base_delay=0.1)(mock_func)

        with self.assertRaises(DatabaseTimeoutError):
            decorated()

        # 1 initial attempt + 2 retries = 3 calls
        self.assertEqual(mock_func.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch('time.sleep', return_value=None)
    def test_permanent_error_fails_immediately_without_retry(self, mock_sleep):
        """Test non-retryable PermanentError aborts immediately."""
        mock_func = MagicMock(side_effect=PermanentError("Resource not found"))

        decorated = retry_with_exponential_backoff(max_retries=3, base_delay=0.1)(mock_func)

        with self.assertRaises(PermanentError):
            decorated()

        self.assertEqual(mock_func.call_count, 1)
        mock_sleep.assert_not_called()

    def test_retry_policy_manager(self):
        """Test RetryPolicyManager decisions for different operations and attempt counts."""
        manager = RetryPolicyManager()

        # product_lookup allows DatabaseTimeoutError on attempt 0
        self.assertTrue(manager.should_retry('product_lookup', DatabaseTimeoutError(), attempt_count=0))

        # product_lookup does not retry after max_retries (max is 2)
        self.assertFalse(manager.should_retry('product_lookup', DatabaseTimeoutError(), attempt_count=2))

        # inventory_update allows RateLimitError
        self.assertTrue(manager.should_retry('inventory_update', RateLimitError(), attempt_count=1))

        # non-retryable error type returns False
        self.assertFalse(manager.should_retry('inventory_update', ValueError("Invalid data"), attempt_count=0))

    @patch('time.sleep', return_value=None)
    def test_direct_runner_retry_with_exponential_backoff(self, mock_sleep):
        """Test invoking retry_with_exponential_backoff directly as a function runner."""
        mock_action = MagicMock(side_effect=[Exception("Transient network blip"), "rate_result"])
        result = retry_with_exponential_backoff(mock_action, max_retries=3, base_delay=0.1, max_delay=5)
        self.assertEqual(result, "rate_result")
        self.assertEqual(mock_action.call_count, 2)
        mock_sleep.assert_called_once()

    @patch('time.sleep', return_value=None)
    def test_get_shipping_rate_success(self, mock_sleep):
        """Test get_shipping_rate succeeds on first attempt."""
        mock_shipping_api = MagicMock()
        mock_resp = MagicMock()
        mock_resp.rate = 12.50
        mock_shipping_api.calculate_rate.return_value = mock_resp

        result = get_shipping_rate(order_id="ord-101", destination="US", shipping_api=mock_shipping_api)
        self.assertEqual(result, {"status": "success", "rate": 12.50})
        self.assertEqual(mock_shipping_api.calculate_rate.call_count, 1)
        mock_sleep.assert_not_called()

    @patch('time.sleep', return_value=None)
    def test_get_shipping_rate_retry_recovery(self, mock_sleep):
        """Test get_shipping_rate recovers on retry after initial failure."""
        mock_shipping_api = MagicMock()
        mock_resp = MagicMock()
        mock_resp.rate = 18.00
        mock_shipping_api.calculate_rate.side_effect = [
            ConnectionResetError("Connection reset"),
            mock_resp
        ]

        result = get_shipping_rate(order_id="ord-102", destination="CA", shipping_api=mock_shipping_api)
        self.assertEqual(result, {"status": "success", "rate": 18.00})
        self.assertEqual(mock_shipping_api.calculate_rate.call_count, 2)
        mock_sleep.assert_called_once()

    @patch('time.sleep', return_value=None)
    def test_get_shipping_rate_fallback_on_max_retries_exceeded(self, mock_sleep):
        """Test get_shipping_rate falls back to cached rate when all retries fail."""
        mock_shipping_api = MagicMock()
        mock_shipping_api.calculate_rate.side_effect = TimeoutError("Shipping API unresponsive")

        result = get_shipping_rate(order_id="ord-103", destination="EU", shipping_api=mock_shipping_api)
        self.assertEqual(result["status"], "fallback")
        self.assertEqual(result["rate"], 19.99)  # Cached fallback rate for EU
        # 1 initial call + 3 retries = 4 total attempts
        self.assertEqual(mock_shipping_api.calculate_rate.call_count, 4)
        self.assertEqual(mock_sleep.call_count, 3)

    def test_get_cached_rate_destinations(self):
        """Test get_cached_rate returns correct regional and fallback rates."""
        self.assertEqual(get_cached_rate("US"), 9.99)
        self.assertEqual(get_cached_rate("CA"), 14.99)
        self.assertEqual(get_cached_rate("EU"), 19.99)
        self.assertEqual(get_cached_rate("APAC"), 24.99)
        self.assertEqual(get_cached_rate("UNKNOWN"), 29.99)

