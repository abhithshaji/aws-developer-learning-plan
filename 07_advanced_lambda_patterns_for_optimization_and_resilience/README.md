# ⚡ Module 07: Advanced Lambda Patterns for Optimization and Resilience

> [!NOTE]
> **Module In Progress**: This guide documents the architectural enhancements and patterns introduced in **Module 07: Advanced Lambda Patterns for Optimization and Resilience**. The current milestone establishes **Custom Lambda Layers for Shared Utilities & Domain Logic**, modular packaging, safe layer versioning, and rollback procedures.

In this module, we optimize our serverless microservice architecture for performance, maintainability, and operational resilience. We reduce Lambda bundle sizes, eliminate redundant boilerplate across microservices, and decouple business logic into immutable, versioned **AWS Lambda Layers**.

---

## 📌 Summary of Changes from Module 06

If you are coming from **Module 06**, here is what has been introduced in this module:

### 1. Creation of the Shared `product-utilities` Lambda Layer
- **Candidate Identification**:
  - **Data Validation**: Centralized Pydantic schemas and boundary rules into `product_validator.py`.
  - **Database Helpers**: Consolidated DynamoDB connection management, CRUD operations, GSI category querying, and optimistic locking into `database_helper.py`.
  - **Response Formatting**: Standardized API Gateway JSON response envelopes, CORS headers, Decimal serialization, and contextual error suggestion builders into `response_formatter.py`.
- **Packaging Structure (`layers/product_utilities/`)**:
  ```text
  product-utilities-layer/
  ├── python/
  │   ├── __init__.py
  │   ├── product_validator.py       # Pydantic schemas & field-level validation
  │   ├── database_helper.py         # DynamoDB CRUD, queries & audit attributes
  │   └── response_formatter.py      # Standardized APIGW headers & JSON envelopes
  └── requirements.txt               # Layer runtime dependency specifications
  ```
- **AWS Runtime Mounting**:
  - AWS Lambda extracts layer archives into `/opt`.
  - In Python runtimes, `/opt/python` is pre-configured in `sys.path`.
  - Functions can import layer modules directly (`import product_validator`, `import database_helper`, `import response_formatter`) with zero local file path coupling.

### 2. Backward-Compatible Project Architecture
- The existing microservice modules (`db/product_schema.py`, `db/products_db.py`, and `utils/response_utils.py`) act as clean bridges that re-export from the shared layer.
- Existing Lambda handlers and test suites continue to function with zero regressions.

### 3. CDK Infrastructure Integration (`product_api_stack.py`)
- Provisioned `ProductUtilitiesLayer` alongside `PydanticLayer` via `aws_lambda.LayerVersion`:
  ```python
  self.product_utils_layer = aws_lambda.LayerVersion(
      self, "ProductUtilitiesLayer",
      code=aws_lambda.Code.from_asset("layers/product_utilities"),
      compatible_runtimes=[lambda_runtime],
      description="v1.0.0 - Shared validation, database helpers, and response formatting"
  )
  ```
- Attached the layer to all core REST and Media Lambda functions.

---

## 🏛️ Layer Architecture & Lambda Runtime Mounts

```text
                           LAMBDA EXECUTION ENVIRONMENT
                     ┌───────────────────────────────────────┐
                     │                                       │
                     │  /var/task/  (Function Deployment)   │
                     │  ├── handler.py                       │
                     │                                       │
                     │  /opt/python/  (Mounted Layers)       │
                     │  ├── pydantic/                        │
                     │  ├── product_validator.py             │
                     │  ├── database_helper.py               │
                     │  └── response_formatter.py            │
                     │                                       │
                     │  sys.path automatically resolves:     │
                     │  ["/var/task", "/opt/python", ...]    │
                     └───────────────────────────────────────┘
```

---

## 📂 Project Structure

```text
07_advanced_lambda_patterns_for_optimization_and_resilience/product-api/
├── cdk.json                           # CDK application configuration
├── requirements.txt                   # Production dependencies (aws-cdk, pydantic, redis>=5.0.0)
├── requirements-dev.txt               # Testing dependencies (pytest, moto[s3,dynamodb])
├── layers/                            # Lambda Layers
│   ├── pydantic/                      # External dependency layer (C-extensions)
│   └── product_utilities/             # Custom shared business utilities layer
│       ├── requirements.txt
│       └── python/
│           ├── __init__.py
│           ├── product_validator.py   # Validation models & constraints
│           ├── database_helper.py     # DynamoDB operations & retries
│           └── response_formatter.py  # Response & error envelopes
├── product_api/                       # CDK Infrastructure Stack
│   ├── __init__.py
│   └── product_api_stack.py           # LayerVersion, S3 Bucket, DynamoDB, DLQ, Lambdas & APIGW
├── db/                                # Persistence & Data Bridges
│   ├── __init__.py
│   ├── product_schema.py              # Bridges to product_validator
│   ├── products_db.py                 # Bridges to database_helper
│   └── cache_db.py                    # Valkey caching layer
├── utils/                             # Resilience & Infrastructure Helpers
│   ├── __init__.py
│   ├── response_utils.py              # Bridges to response_formatter
│   ├── retry_utils.py                 # Exponential backoff with full jitter
│   ├── circuit_breaker.py             # Circuit breaker state machine
│   ├── dlq_setup.py                   # SQS DLQ helper
│   ├── destinations_setup.py          # Lambda Destinations helper
│   ├── s3_setup.py                    # S3 bucket & notification setup
│   └── elasticache_setup.py           # ElastiCache / Valkey helper
├── lambda_code/                       # Lambda Function Handlers
│   ├── __init__.py
│   ├── get_product.py                 # GET /products/{id}
│   ├── insert_product.py              # POST /products
│   ├── query_products.py              # GET /products
│   ├── update_product.py              # PUT /products/{id}
│   ├── options.py                     # CORS preflight handler
│   ├── dlq_processor.py               # DLQ failure triage
│   ├── destinations_handlers.py       # Asynchronous destination handlers
│   ├── generate_presigned_url.py      # S3 PUT presigned URLs
│   ├── generate_download_url.py       # S3 GET presigned URLs
│   ├── update_product_images.py       # Atomic image URL appending
│   └── process_image_upload.py        # S3 ObjectCreated metadata consumer
└── tests/                             # Comprehensive Unit Test Suite
    ├── __init__.py
    ├── event_factory.py               # Standardized APIGatewayEventFactory
    └── unit/
        ├── api/
        │   ├── test_product_utilities_layer.py # Direct tests for layer modules
        │   ├── test_product_api_stack.py       # CDK assertions (LayerVersion properties)
        │   ├── test_products_db.py
        │   ├── test_product_validation.py
        │   ├── test_get_product.py
        │   ├── test_insert_product.py
        │   └── test_error_handling.py
        ├── storage/                           # S3 & image processing tests
        ├── cache/                             # ElastiCache & Valkey tests
        └── resilience/                        # Circuit breaker, retry & DLQ tests
```

---

## 🧪 Running Unit Tests

We use **Pytest** with **Moto** and `unittest.mock` to test all layers, handlers, and cloud constructs:

```sh
# Run the entire test suite (73 passing tests)
pytest tests/unit/ -v

# Run layer unit tests directly:
pytest tests/unit/api/test_product_utilities_layer.py -v

# Run CDK CloudFormation synthesis assertions:
pytest tests/unit/api/test_product_api_stack.py -v
```

### Test Suite Coverage (73 Passing Tests)

| Subfolder | Test Module | Coverage Area | Status |
| :--- | :--- | :--- | :--- |
| **`tests/unit/api/`** | `test_product_utilities_layer.py` | Direct validation of `product_validator`, `database_helper`, and `response_formatter` | **Passed** |
| | `test_product_api_stack.py` | CDK assertions for `ProductUtilitiesLayer`, `PydanticLayer`, SQS DLQ, S3 Bucket | **Passed** |
| | `test_products_db.py` | DynamoDB mock CRUD & query operations | **Passed** |
| | `test_product_validation.py` | Pydantic model validation & boundary constraints | **Passed** |
| | `test_get_product.py` | Retrieval endpoints with mock factory events | **Passed** |
| | `test_insert_product.py` | Product creation with Pydantic layer validation | **Passed** |
| | `test_error_handling.py` | Structured error envelopes, HTTP 400/404/500 validation, contextual recommendations | **Passed** |
| **`tests/unit/storage/`** | `test_s3_setup.py` | Bucket creation, Versioning, Public Access Blocks, Multi-Region, S3 Notifications | **Passed** |
| | `test_generate_presigned_url.py` | Presigned PUT URL generation, SigV4 virtual addressing, key partitioning | **Passed** |
| | `test_generate_download_url.py` | Presigned GET URL generation, 1-hour expiration, error handling | **Passed** |
| | `test_update_product_images.py` | Atomic DynamoDB `list_append` expressions, URL resolution, validation | **Passed** |
| | `test_process_image_upload.py` | S3 event notification parsing, `head_object` metadata extraction, DynamoDB updates | **Passed** |
| **`tests/unit/cache/`** | `test_elasticache_setup.py` | ElastiCache cluster provisioning (Valkey & Memcached) & error handling | **Passed** |
| | `test_cache_db.py` | Cache-Aside retrieval, GSI query caching, cache invalidation, TTL strategies, metrics | **Passed** |
| **`tests/unit/resilience/`** | `test_circuit_breaker.py` | Circuit breaker 3-state state machine (`CLOSED` → `OPEN` → `HALF_OPEN`) | **Passed** |
| | `test_retry_utils.py` | Exponential backoff, full jitter, `RetryPolicyManager` rules | **Passed** |
| | `test_dlq_processor.py` | Asynchronous DLQ message triage, timeout/rate-limit classification | **Passed** |

---

## 🔄 Layer Versioning & Rollback Strategies

Lambda layers are immutable resources identified by version numbers (`:1`, `:2`, etc.).

### 1. Publishing a New Layer Version via AWS CLI
```sh
# 1. Package the layer code
cd layers/product_utilities
zip -r product-utilities-layer.zip python/

# 2. Publish new version to AWS Lambda
aws lambda publish-layer-version \
    --layer-name product-utilities \
    --description "v1.1.0 - Updated validation rules" \
    --zip-file fileb://product-utilities-layer.zip \
    --compatible-runtimes python3.13
```

### 2. Instant Rollback Without Function Redeployment
If an update causes issues, functions can instantly be rolled back to a previous known-good layer version:

```sh
# Roll back a single function to Layer Version 1
aws lambda update-function-configuration \
    --function-name GetProduct \
    --layers arn:aws:lambda:ap-southeast-2:189053741578:layer:ProductUtilitiesLayer:1

# Batch rollback multiple functions
for func in GetProduct QueryProducts InsertProduct UpdateProduct; do
    aws lambda update-function-configuration \
        --function-name $func \
        --layers arn:aws:lambda:ap-southeast-2:189053741578:layer:ProductUtilitiesLayer:1
done
```
