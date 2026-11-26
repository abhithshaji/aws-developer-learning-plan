"""Resilient External Service Orchestrator.

Combines Circuit Breaker, Exponential Backoff with Jitter, and Fallback Degradation
into a unified resilience strategy for external dependencies in serverless architectures.
"""
import json
import logging
from utils.circuit_breaker import CircuitBreaker, CircuitState
from utils.retry_utils import retry_with_exponential_backoff, get_cached_rate

logger = logging.getLogger()
logger.setLevel(logging.INFO)


class ResilientExternalService:
    """Manages calls to an external service using circuit breaker and exponential backoff retries."""

    def __init__(self, service_name, circuit_breaker, retry_config):
        self.service_name = service_name
        self.circuit_breaker = circuit_breaker
        self.retry_config = retry_config

    def call(self, func, fallback=None):
        """Call external service with circuit breaker and retry logic."""
        try:
            # Use circuit breaker around retry execution
            result = self.circuit_breaker.call(
                lambda: retry_with_exponential_backoff(
                    func,
                    **self.retry_config
                )
            )
            return {"status": "success", "data": result}
        except Exception as e:
            # Circuit is open or all retries failed
            logger.warning(
                f"ResilientService [{self.service_name}] execution failed or circuit tripped: {str(e)}"
            )
            if fallback:
                logger.info(f"ResilientService [{self.service_name}] using provided fallback.")
                return {"status": "fallback", "data": fallback()}
            else:
                return {"status": "failed", "error": str(e)}


# 1. Standard Service Configurations
payment_service = ResilientExternalService(
    service_name="payment",
    circuit_breaker=CircuitBreaker(failure_threshold=5, timeout=30),
    retry_config={"max_retries": 3, "base_delay": 0.1, "max_delay": 5}
)

shipping_service = ResilientExternalService(
    service_name="shipping",
    circuit_breaker=CircuitBreaker(failure_threshold=10, timeout=60),
    retry_config={"max_retries": 2, "base_delay": 0.2, "max_delay": 3}
)


# 2. Helpers for Handler Execution
def get_cached_shipping_rate(destination):
    """Retrieve fallback shipping rate for destination."""
    return get_cached_rate(destination)


def default_calculate_shipping(order_data, shipping_api=None):
    """Calculate live shipping rate."""
    if shipping_api is not None:
        resp = shipping_api.calculate_rate(
            order_id=order_data.get('order_id'),
            destination=order_data.get('destination')
        )
        return getattr(resp, 'rate', resp)
    return 15.00


def default_process_payment(payment_data, payment_gateway=None):
    """Process customer charge with payment gateway."""
    if payment_gateway is not None:
        res = payment_gateway.charge(payment_data)
        return getattr(res, 'id', str(res))
    if isinstance(payment_data, dict) and payment_data.get('fail'):
        raise Exception("Payment authorization declined")
    return f"txn_{payment_data.get('order_id', 'mock')}"


# 3. Resilient Lambda Handler
def handler(event, context, payment_svc=None, shipping_svc=None, payment_fn=None, shipping_fn=None):
    """Lambda handler demonstrating combined resilience strategies."""
    active_payment_service = payment_svc or payment_service
    active_shipping_service = shipping_svc or shipping_service
    _process_payment = payment_fn or default_process_payment
    _calculate_shipping = shipping_fn or default_calculate_shipping

    try:
        body = event.get('body', '{}')
        order_data = json.loads(body) if isinstance(body, str) else body
    except Exception as e:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": f"Invalid request body: {str(e)}"})
        }

    # Critical: Payment must succeed
    payment_result = active_payment_service.call(
        lambda: _process_payment(order_data.get('payment', {}))
    )

    if payment_result['status'] == 'failed':
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Payment processing failed"})
        }

    # Non-critical: Shipping can use fallback
    shipping_result = active_shipping_service.call(
        lambda: _calculate_shipping(order_data),
        fallback=lambda: get_cached_shipping_rate(order_data.get('destination', 'US'))
    )

    return {
        "statusCode": 200,
        "body": json.dumps({
            "order_id": order_data.get('order_id'),
            "payment_status": payment_result['status'],
            "shipping_rate": shipping_result['data']
        })
    }
