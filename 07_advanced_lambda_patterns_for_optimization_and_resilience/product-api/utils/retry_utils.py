import time
import random
import logging
from functools import wraps

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Base and custom error classifications
class RetryableError(Exception):
    """Base error for transient failures that can be safely retried."""
    pass

class PermanentError(Exception):
    """Base error for non-recoverable failures that should not be retried."""
    pass

class DatabaseTimeoutError(RetryableError):
    pass

class RateLimitError(RetryableError):
    pass

class NetworkTimeoutError(RetryableError):
    pass

class SearchServiceUnavailableError(RetryableError):
    pass

class ProductNotFoundError(PermanentError):
    pass

class InsufficientInventoryError(PermanentError):
    pass


# 1. Exponential Backoff with Jitter
def _execute_with_retry(func, max_retries=3, base_delay=0.1, max_delay=10, func_name=None):
    """Internal runner to execute a callable with exponential backoff and jitter."""
    if func_name is None:
        func_name = getattr(func, '__name__', str(func))

    for attempt in range(max_retries + 1):
        try:
            return func()
        except PermanentError as e:
            logger.error(f"Permanent error in {func_name}: {str(e)}")
            raise e
        except Exception as e:
            if attempt == max_retries:
                # Final attempt failed, raise exception
                logger.error(f"Max retries ({max_retries}) exceeded for {func_name}: {str(e)}")
                raise e

            # Calculate exponential backoff with jitter
            exponential_delay = base_delay * (2 ** attempt)
            jitter = random.uniform(0, exponential_delay * 0.1)  # 10% jitter
            wait_time = min(exponential_delay + jitter, max_delay)

            msg = f"Attempt {attempt + 1} failed for {func_name}. Retrying in {wait_time:.2f}s."
            logger.warning(msg)
            print(msg)
            time.sleep(wait_time)


def retry_with_exponential_backoff(func=None, max_retries=3, base_delay=0.1, max_delay=10):
    """Retry a function with exponential backoff and jitter.

    Can be invoked directly as a runner:
        rate = retry_with_exponential_backoff(call_shipping_api, max_retries=3, base_delay=0.1, max_delay=5)

    Or as a decorator:
        @retry_with_exponential_backoff(max_retries=2, base_delay=0.5, max_delay=3)
        def get_product(product_id): ...
    """
    if func is not None and not callable(func):
        max_retries = func
        func = None

    if func is not None and callable(func):
        return _execute_with_retry(
            func,
            max_retries=max_retries,
            base_delay=base_delay,
            max_delay=max_delay
        )

    def decorator(target_func):
        target_name = getattr(target_func, '__name__', str(target_func))

        @wraps(target_func)
        def wrapper(*args, **kwargs):
            return _execute_with_retry(
                lambda: target_func(*args, **kwargs),
                max_retries=max_retries,
                base_delay=base_delay,
                max_delay=max_delay,
                func_name=target_name
            )
        return wrapper

    return decorator


# 2. Shipping Rate Resilience Example (with cached fallback)
def get_cached_rate(destination):
    """Fallback rate lookup when live shipping services fail."""
    fallback_rates = {
        "US": 9.99,
        "CA": 14.99,
        "EU": 19.99,
        "APAC": 24.99,
        "GLOBAL": 29.99,
    }
    return fallback_rates.get(destination, fallback_rates["GLOBAL"])


def get_shipping_rate(order_id, destination, shipping_api=None):
    """Calculate shipping rate with exponential backoff and cached fallback."""
    if shipping_api is None:
        raise ValueError("Shipping API client is required")

    def call_shipping_api():
        response = shipping_api.calculate_rate(
            order_id=order_id,
            destination=destination
        )
        return response.rate

    try:
        rate = retry_with_exponential_backoff(
            call_shipping_api,
            max_retries=3,
            base_delay=0.1,
            max_delay=5
        )
        return {"status": "success", "rate": rate}
    except Exception as e:
        # All retries failed, return cached rate
        logger.warning(f"All retries failed for order {order_id} to {destination}: {e}. Falling back to cached rate.")
        return {"status": "fallback", "rate": get_cached_rate(destination)}


# 3. Operation-Specific Retry Policies
class RetryPolicyManager:
    """Manage retry policies for different operation types."""
    
    def __init__(self):
        self.policies = {
            'product_lookup': {
                'max_retries': 2,
                'base_delay': 0.5,
                'max_delay': 5,
                'retryable_errors': [DatabaseTimeoutError, ConnectionError]
            },
            'inventory_update': {
                'max_retries': 3,
                'base_delay': 1,
                'max_delay': 30,
                'retryable_errors': [DatabaseTimeoutError, RateLimitError]
            },
            'payment_processing': {
                'max_retries': 1,  # Limited retries for financial operations
                'base_delay': 2,
                'max_delay': 10,
                'retryable_errors': [NetworkTimeoutError]
            },
            'search_index_update': {
                'max_retries': 5,  # Search can tolerate more retries
                'base_delay': 1,
                'max_delay': 60,
                'retryable_errors': [SearchServiceUnavailableError, RateLimitError]
            }
        }
    
    def get_policy(self, operation_type):
        """Get retry policy for specific operation type."""
        return self.policies.get(operation_type, self.policies['product_lookup'])
    
    def should_retry(self, operation_type, error, attempt_count):
        """Determine if operation should be retried."""
        policy = self.get_policy(operation_type)
        
        if attempt_count >= policy['max_retries']:
            return False
        
        return any(isinstance(error, error_type) for error_type in policy['retryable_errors'])