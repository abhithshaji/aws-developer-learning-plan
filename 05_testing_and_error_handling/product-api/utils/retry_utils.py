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


# 1. Exponential Backoff with Jitter Decorator
def retry_with_exponential_backoff(max_retries=3, base_delay=1, max_delay=60):
    """Decorator for implementing exponential backoff retry logic with jitter."""
    def decorator(func):
        func_name = getattr(func, '__name__', str(func))

        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                
                except RetryableError as e:
                    if attempt == max_retries:
                        logger.error(f"Max retries ({max_retries}) exceeded for {func_name}")
                        raise e
                    
                    # Calculate delay with exponential backoff and jitter (full jitter)
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    jitter = random.uniform(0, delay * 0.1)  # 10% jitter
                    total_delay = delay + jitter
                    
                    logger.warning(
                        f"Attempt {attempt + 1} failed for {func_name}, retrying in {total_delay:.2f}s"
                    )
                    time.sleep(total_delay)
                
                except PermanentError as e:
                    logger.error(f"Permanent error in {func_name}: {str(e)}")
                    raise e
            
        return wrapper
    return decorator


# 2. Operation-Specific Retry Policies
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