import unittest
import time
from unittest.mock import MagicMock
from utils.circuit_breaker import CircuitBreaker, CircuitState, CircuitBreakerOpenError

class TestCircuitBreaker(unittest.TestCase):

    def test_normal_operation_remains_closed(self):
        """Test successful operations keep the circuit closed."""
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=1)
        mock_func = MagicMock(return_value="OK")

        result = breaker.call(mock_func)

        self.assertEqual(result, "OK")
        self.assertEqual(breaker.state, CircuitState.CLOSED)
        self.assertEqual(breaker.failure_count, 0)

    def test_circuit_trips_to_open_after_failure_threshold(self):
        """Test consecutive failures trip the breaker to OPEN and fail fast."""
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=2)
        failing_func = MagicMock(side_effect=Exception("DB Failure"))

        # 3 failures reach threshold
        for _ in range(3):
            with self.assertRaises(Exception):
                breaker.call(failing_func)

        self.assertEqual(breaker.state, CircuitState.OPEN)

        # 4th call immediately raises CircuitBreakerOpenError without invoking the function
        with self.assertRaises(CircuitBreakerOpenError):
            breaker.call(failing_func)

        self.assertEqual(failing_func.call_count, 3)

    def test_circuit_half_open_and_recovery_to_closed(self):
        """Test circuit transitions from OPEN to HALF_OPEN, then back to CLOSED after successes."""
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=0.05, success_threshold=2)

        # Trip to OPEN
        with self.assertRaises(Exception):
            breaker.call(MagicMock(side_effect=Exception("Failed")))
        self.assertEqual(breaker.state, CircuitState.OPEN)

        # Wait past recovery timeout
        time.sleep(0.08)

        success_func = MagicMock(return_value="Recovered")

        # 1st success puts state into HALF_OPEN
        result1 = breaker.call(success_func)
        self.assertEqual(result1, "Recovered")
        self.assertEqual(breaker.state, CircuitState.HALF_OPEN)

        # 2nd consecutive success reaches success_threshold (2), restoring to CLOSED
        result2 = breaker.call(success_func)
        self.assertEqual(result2, "Recovered")
        self.assertEqual(breaker.state, CircuitState.CLOSED)
        self.assertEqual(breaker.failure_count, 0)

    def test_circuit_breaker_timeout_parameter_support(self):
        """Test CircuitBreaker supports the tutorial 'timeout' parameter."""
        breaker = CircuitBreaker(failure_threshold=5, timeout=15, success_threshold=2)
        self.assertEqual(breaker.timeout, 15)
        self.assertEqual(breaker.recovery_timeout, 15)

    def test_process_payment_success(self):
        """Test process_payment returns success when payment gateway succeeds."""
        from utils.circuit_breaker import process_payment
        mock_gateway = MagicMock()
        mock_charge_result = MagicMock()
        mock_charge_result.id = "txn_12345"
        mock_gateway.charge.return_value = mock_charge_result

        res = process_payment(order_id="order_1", amount=99.99, payment_gateway=mock_gateway)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["transaction_id"], "txn_12345")

    def test_process_payment_gateway_failure_and_circuit_open(self):
        """Test process_payment gracefully fails and opens the circuit after threshold."""
        from utils.circuit_breaker import process_payment, payment_circuit
        payment_circuit.state = CircuitState.CLOSED
        payment_circuit.failure_count = 0

        mock_gateway = MagicMock()
        mock_gateway.charge.side_effect = Exception("Payment Gateway Down")

        # 5 failures trip the breaker
        for _ in range(5):
            res = process_payment(order_id="order_err", amount=50.0, payment_gateway=mock_gateway)
            self.assertEqual(res["status"], "failed")

        self.assertEqual(payment_circuit.state, CircuitState.OPEN)

        # 6th attempt fails fast because circuit is open
        res_open = process_payment(order_id="order_err", amount=50.0, payment_gateway=mock_gateway)
        self.assertEqual(res_open["status"], "failed")
        self.assertIn("Circuit breaker is OPEN", res_open["error"])

        # Reset state for other tests
        payment_circuit.state = CircuitState.CLOSED
        payment_circuit.failure_count = 0

