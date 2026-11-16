import unittest
from unittest.mock import patch, MagicMock
from utils.retry_utils import (
    retry_with_exponential_backoff,
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
