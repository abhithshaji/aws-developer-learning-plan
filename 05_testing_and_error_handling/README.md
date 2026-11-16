# 📦 Module 05: Testing, Error Handling & Resilience

In this module, we introduce a complete testing strategy and production-grade resilience patterns to our serverless product API. We implement comprehensive unit tests with **Pytest** and **Moto**, local emulation with the **AWS SAM CLI**, and advanced cloud reliability patterns including **Structured Error Envelopes**, **Dead-Letter Queues (DLQ)**, **Lambda Destinations**, **Exponential Backoff with Jitter**, and the **Circuit Breaker Pattern**.

---

## 📌 Summary of Changes from Module 04

If you are coming from **Module 04**, here is what has been introduced in this module:

1. **Automated Unit Testing & Mocking**:
   - Added `pytest`, `pytest-cov`, and `moto[dynamodb]` to `requirements-dev.txt`.
   - Implemented an `APIGatewayEventFactory` (`tests/event_factory.py`) to generate standardized proxy events with minimal boilerplate.
   - Isolated Lambda handler tests from live AWS calls using Python's `unittest.mock` (`@patch`).
   - Simulated real DynamoDB tables locally without hitting AWS using **Moto**.
   - Added CDK infrastructure assertions in `test_product_api_stack.py` to test CloudFormation resource definitions.

2. **Standardized & Contextual Error Handling (`utils/response_utils.py`)**:
   - Created structured error payloads containing error `type`, `message`, `timestamp`, `request_id`, `details`, and actionable `suggestions`.
   - Built `ContextualErrorHandler` to dynamically enrich 404 responses with recommendations based on user search queries or categories.

3. **Dead-Letter Queues (DLQ)**:
   - Defined an SQS Dead-Letter Queue (`ProductApiDLQ`) in CDK and attached it to asynchronous Lambda invocations (`dead_letter_queue=self.dlq`).
   - Implemented `dlq_processor.py` to parse, classify, and triage failed invocations (`timeout`, `rate_limit`, `validation_error`).

4. **Lambda Destinations (`destinations_setup.py`, `destinations_handlers.py`)**:
   - Demonstrated routing successful and failed asynchronous Lambda executions to target SQS queues without adding custom publishing code in function handlers.
   - Built compensation logic (`inventory_rollback_handler`) for transactional rollbacks.

5. **Retry Strategies (`utils/retry_utils.py`)**:
   - Implemented an `@retry_with_exponential_backoff` decorator featuring full jitter to prevent thundering herd problems.
   - Created `RetryPolicyManager` for operation-specific retry limits and error classifications.

6. **Circuit Breaker Pattern (`utils/circuit_breaker.py`)**:
   - Implemented a 3-state state machine (`CLOSED` → `OPEN` → `HALF_OPEN`) to protect downstream dependencies from cascading failures, with CloudWatch metric reporting.

7. **Local Emulation via AWS SAM CLI (`events/`)**:
   - Configured SAM CLI to consume CDK-synthesized templates (`cdk.out/ProductApiStack.template.json`) for local Lambda invocation and API Gateway HTTP emulation (`localhost:3000`).

---

## 🛠️ Installations & Setup

### 1. Development Dependencies
From the `product-api/` directory, activate your virtual environment and install test dependencies:

```sh
cd product-api
source .venv/bin/activate                 # macOS/Linux
# .venv\Scripts\Activate.ps1             # Windows PowerShell

pip install -r requirements-dev.txt
```

Your `requirements-dev.txt` should contain:
```text
pytest~=8.3
pytest-cov~=5.0
moto[dynamodb]~=5.0
boto3~=1.35
flake8~=7.1
mypy~=1.11
```

### 2. Pydantic Lambda Layer (Prerequisite from Module 04)
If you haven't built the Pydantic layer yet, build it targeting Amazon Linux (Python 3.13):

```sh
mkdir -p layers/pydantic/python

pip install \
  --platform manylinux2014_x86_64 \
  --target layers/pydantic/python \
  --implementation cp \
  --python-version 3.13 \
  --only-binary=:all: \
  --no-cache-dir \
  pydantic
```
---

## 📂 Project Structure

```text
product-api/
├── cdk.json
├── requirements.txt                   # Production dependencies (aws-cdk, pydantic)
├── requirements-dev.txt               # Testing dependencies (pytest, moto, boto3)
├── .gitignore
├── layers/                            # (Git-ignored) Lambda layer binary assets
│   └── pydantic/python/
├── product_api/                       # CDK Infrastructure Stack
│   ├── __init__.py
│   └── product_api_stack.py           # DynamoDB, DLQ, Lambdas, and API Gateway
├── db/                                # Data Layer
│   ├── __init__.py
│   ├── product_schema.py              # Pydantic validation schemas
│   └── products_db.py                 # DynamoDB Boto3 operations
├── utils/                             # Shared Resilience & Utility Helpers
│   ├── __init__.py
│   ├── response_utils.py              # Success, error, & contextual error responses
│   ├── retry_utils.py                 # Exponential backoff + RetryPolicyManager
│   ├── circuit_breaker.py             # CircuitBreaker state machine & CloudWatch metrics
│   ├── dlq_setup.py                   # SQS DLQ configuration helper
│   └── destinations_setup.py          # Lambda Destinations configuration helper
├── lambda_code/                       # Lambda Handlers
│   ├── __init__.py
│   ├── get_product.py                 # GET /products/{id} (Contextual error handling)
│   ├── insert_product.py              # POST /products (Pydantic validation)
│   ├── query_products.py              # GET /products (Category query via GSI)
│   ├── update_product.py              # PUT /products/{id}
│   ├── options.py                     # CORS preflight handler
│   ├── dlq_processor.py               # DLQ SQS message consumer & failure analyzer
│   └── destinations_handlers.py       # Success/failure destinations & rollback handler
├── events/                            # SAM Local Mock Events
│   ├── get-product-event.json         # Mock event for GET /products/{id}
│   ├── insert-product-event.json       # Mock event for POST /products
│   └── query-products-event.json      # Mock event for GET /products?category=...
└── tests/                             # Comprehensive Test Suite
    ├── __init__.py
    ├── event_factory.py               # APIGatewayEventFactory helper
    └── unit/
        ├── __init__.py
        ├── test_get_product.py        # GET endpoint unit tests
        ├── test_insert_product.py     # POST endpoint unit tests
        ├── test_product_validation.py # Pydantic schema validation tests
        ├── test_products_db.py        # DynamoDB CRUD tests (Moto mock)
        ├── test_error_handling.py     # Error responses & 400/404/500 validation
        ├── test_retry_utils.py        # Backoff, jitter, & policy manager tests
        ├── test_circuit_breaker.py    # Circuit breaker CLOSED/OPEN/HALF_OPEN tests
        ├── test_dlq_processor.py      # Failure classification & retryability tests
        └── test_product_api_stack.py  # CDK SQS assertions test
```

---

## 🧪 Running the Unit Tests

> [!TIP]
> When running tests that touch `boto3`, pass dummy AWS environment variables so `boto3` does not attempt to contact AWS STS or look for active SSO credentials.

### Run All Unit Tests
```sh
AWS_DEFAULT_REGION=us-east-1 AWS_ACCESS_KEY_ID=testing AWS_SECRET_ACCESS_KEY=testing \
pytest tests/unit -v
```

### Run Tests by Category
```sh
# 1. Endpoint & Handler Tests
pytest tests/unit/test_get_product.py tests/unit/test_insert_product.py -v

# 2. Pydantic Schema Validation Tests
pytest tests/unit/test_product_validation.py -v

# 3. Mock Database (Moto) Tests
pytest tests/unit/test_products_db.py -v

# 4. Error Handling & Structured Response Tests
pytest tests/unit/test_error_handling.py -v

# 5. Resilience Pattern Tests (Retries & Circuit Breaker)
pytest tests/unit/test_retry_utils.py tests/unit/test_circuit_breaker.py -v

# 6. DLQ Analyzer Tests
pytest tests/unit/test_dlq_processor.py -v

# 7. CDK Infrastructure Stack Assertions
pytest tests/unit/test_product_api_stack.py -v
```

### Run with Code Coverage
```sh
AWS_DEFAULT_REGION=us-east-1 AWS_ACCESS_KEY_ID=testing AWS_SECRET_ACCESS_KEY=testing \
pytest --cov=lambda_code --cov=utils --cov=db tests/unit/
```

---

## 🛡️ Resilience & Error Handling Architecture

### 1. Structured & Contextual Errors (`utils/response_utils.py`)
Instead of plain error strings, errors return structured dictionaries with machine-readable types, timestamps, request IDs, and actionable next steps:

```json
{
  "error": {
    "type": "product_not_found",
    "message": "Product prod_999 is not available",
    "timestamp": "2026-11-16T08:00:00+00:00",
    "request_id": "c6b41d2e-0a56-43d2-8cc6-d61ec958fb00",
    "suggestions": [
      "Verify the product ID is correct",
      "Try searching for 'wireless' to find similar products",
      "Browse other products in Electronics category"
    ]
  }
}
```

### 2. Exponential Backoff with Jitter (`utils/retry_utils.py`)
Transient failures (network blips, DynamoDB throughput throttling) automatically retry with exponentially increasing intervals plus random jitter:

$$\text{delay} = \min(\text{base\_delay} \times 2^{\text{attempt}}, \text{max\_delay}) + \text{jitter}$$

- **`RetryableError`**: Transient exceptions (e.g., `DatabaseTimeoutError`, `RateLimitError`) undergo retries.
- **`PermanentError`**: Fatal exceptions (e.g., `ProductNotFoundError`, invalid data) fail fast without retrying.

### 3. Circuit Breaker Pattern (`utils/circuit_breaker.py`)
Wraps downstream calls to prevent cascading system failures:
- **`CLOSED`**: All traffic passes through normally.
- **`OPEN`**: Tripped when failure threshold is exceeded. All subsequent requests fast-fail immediately with `CircuitBreakerOpenError`, shielding the downstream system.
- **`HALF_OPEN`**: After the recovery timeout, allows trial requests. Successes reset to `CLOSED`; failures trip back to `OPEN`.

### 4. Dead-Letter Queues & Destinations
- **DLQ**: Configured in CDK on `InsertProduct` (`dead_letter_queue=self.dlq`) to capture asynchronous failed invocations.
- **Analyzer**: `dlq_processor.analyze_failure()` parses error messages and classifies whether a failed event is safe to retry.

---

## 💻 Local Testing with AWS SAM CLI

The AWS SAM CLI allows you to execute your Lambda functions and emulate API Gateway locally using Docker.

### Prerequisites
1. **Docker Desktop** installed and running.
2. **AWS SAM CLI** installed: [Installation Guide](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html).

### 1. Synthesize the CDK Template
Before running SAM commands, compile your CDK stack:
```sh
cdk synth
```
This generates `cdk.out/ProductApiStack.template.json`.

---

### 2. Invoke Individual Lambdas Locally
Pass the synthesized template (`-t`) and a mock event (`-e`):

```sh
# If testing against live AWS DynamoDB, ensure you are authenticated:
aws login  # or aws sso login

# Test GET /products/{id}
sam local invoke GetProduct \
  -t cdk.out/ProductApiStack.template.json \
  -e events/get-product-event.json

# Test POST /products
sam local invoke InsertProduct \
  -t cdk.out/ProductApiStack.template.json \
  -e events/insert-product-event.json

# Test GET /products?category=Electronics
sam local invoke QueryProducts \
  -t cdk.out/ProductApiStack.template.json \
  -e events/query-products-event.json
```

*(If testing offline without live AWS credentials, prefix the command with `AWS_DEFAULT_REGION=us-east-1 AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test`).*

---

### 3. Emulate the Full API Gateway Locally
Start the local HTTP emulator on port `3000`:

```sh
sam local start-api -t cdk.out/ProductApiStack.template.json
```

In a separate terminal, test your endpoints with `curl`:

```sh
# 1. Create a product
curl -X POST http://127.0.0.1:3000/products \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Mechanical Keyboard",
    "price": 129.99,
    "category": "Electronics",
    "description": "Hot-swappable mechanical gaming keyboard"
  }'

# 2. Query products by category
curl "http://127.0.0.1:3000/products?category=Electronics"

# 3. Fetch specific product
curl http://127.0.0.1:3000/products/prod_001

# 4 Fetch all products
curl http://127.0.0.1:3000/products
```

---

## 🚀 Cloud Deployment & Cleanup

### Deploy to AWS
```sh
cdk deploy ProductApiStack
```

### Cleanup
When you conclude your practice session, destroy all resources to prevent unexpected costs:
```sh
cdk destroy ProductApiStack

# Confirm stack removal
aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE
```
