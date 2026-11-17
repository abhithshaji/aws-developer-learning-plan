import unittest
from lambda_code.dlq_processor import analyze_failure

class TestDLQProcessor(unittest.TestCase):

    def test_timeout_is_retryable(self):
        """Test timeout failures are marked as retryable with delay."""
        event = {'errorMessage': 'Task timed out after 3.00 seconds'}
        analysis = analyze_failure(event)

        self.assertTrue(analysis['retryable'])
        self.assertEqual(analysis['reason'], 'timeout')
        self.assertEqual(analysis['delay'], 300)

    def test_rate_limit_is_retryable(self):
        """Test rate limit / throttling is marked as retryable."""
        event = {'errorMessage': 'Rate limit exceeded on DynamoDB table'}
        analysis = analyze_failure(event)

        self.assertTrue(analysis['retryable'])
        self.assertEqual(analysis['reason'], 'rate_limit')
        self.assertEqual(analysis['delay'], 600)

    def test_validation_error_is_not_retryable(self):
        """Test payload validation error is permanently non-retryable."""
        event = {'errorMessage': 'Validation error: title field is required'}
        analysis = analyze_failure(event)

        self.assertFalse(analysis['retryable'])
        self.assertEqual(analysis['reason'], 'validation_error')

    def test_resource_not_found_is_not_retryable(self):
        """Test non-existent resource error is non-retryable."""
        event = {'errorMessage': 'Product not found with id prod_999'}
        analysis = analyze_failure(event)

        self.assertFalse(analysis['retryable'])
        self.assertEqual(analysis['reason'], 'resource_not_found')

    def test_unknown_error_defaults_to_retryable(self):
        """Test unknown error defaults to retryable with backoff."""
        event = {'errorMessage': 'Unrecognized network blip'}
        analysis = analyze_failure(event)

        self.assertTrue(analysis['retryable'])
        self.assertEqual(analysis['reason'], 'unknown')
