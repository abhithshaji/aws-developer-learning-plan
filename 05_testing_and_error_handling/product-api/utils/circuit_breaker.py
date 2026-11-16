# utils/circuit_breaker.py
import time
import logging
import boto3
from enum import Enum
from threading import Lock

logger = logging.getLogger()
logger.setLevel(logging.INFO)


class CircuitBreakerOpenError(Exception):
    """Raised when an operation is attempted while the circuit breaker is OPEN."""
    pass


class CircuitState(Enum):
    CLOSED = "closed"        # Normal operation
    OPEN = "open"            # Blocking requests
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitBreaker:
    """Circuit breaker implementation for service protection."""
    
    def __init__(self, failure_threshold=5, recovery_timeout=60, success_threshold=3):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        self.state = CircuitState.CLOSED
        self.lock = Lock()
    
    def call(self, func, *args, **kwargs):
        """Execute function with circuit breaker protection."""
        with self.lock:
            if self.state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self.state = CircuitState.HALF_OPEN
                    self.success_count = 0
                else:
                    raise CircuitBreakerOpenError("Circuit breaker is open")
            
            try:
                result = func(*args, **kwargs)
                self._on_success()
                return result
                
            except Exception as e:
                self._on_failure()
                raise e
    
    def _should_attempt_reset(self):
        """Check if enough time has passed to attempt reset."""
        return (time.time() - self.last_failure_time) >= self.recovery_timeout
    
    def _on_success(self):
        """Handle successful operation."""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.success_threshold:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
        else:
            self.failure_count = 0
    
    def _on_failure(self):
        """Handle failed operation."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN


# Shared Breaker Instances
database_circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30)
payment_circuit_breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=120)


# Metrics & Health Monitoring
def log_circuit_breaker_metrics(service_name, breaker):
    """Log circuit breaker metrics to Amazon CloudWatch."""
    cloudwatch = boto3.client('cloudwatch')
    cloudwatch.put_metric_data(
        Namespace='ProductAPI/CircuitBreakers',
        MetricData=[
            {
                'MetricName': 'CircuitBreakerState',
                'Dimensions': [{'Name': 'Service', 'Value': service_name}],
                'Value': 1 if breaker.state == CircuitState.OPEN else 0,
                'Unit': 'Count'
            },
            {
                'MetricName': 'FailureCount',
                'Dimensions': [{'Name': 'Service', 'Value': service_name}],
                'Value': breaker.failure_count,
                'Unit': 'Count'
            }
        ]
    )


def monitor_circuit_breaker_health():
    """Monitor circuit breaker states and log metrics."""
    circuit_breakers = {
        'database': database_circuit_breaker,
        'payment_service': payment_circuit_breaker
    }
    
    for service_name, breaker in circuit_breakers.items():
        if breaker.state == CircuitState.OPEN:
            logger.error(f"Circuit breaker OPEN for {service_name}")
        elif breaker.state == CircuitState.HALF_OPEN:
            logger.info(f"Circuit breaker testing recovery for {service_name}")
        
        try:
            log_circuit_breaker_metrics(service_name, breaker)
        except Exception as e:
            logger.warning(f"Failed to publish metrics to CloudWatch: {str(e)}")