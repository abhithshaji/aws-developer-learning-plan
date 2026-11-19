# 📦 Module 06: Scaling with Data Storage

In this module, we scale our serverless microservice beyond tabular database records to handle high-throughput unstructured media and low-latency query workloads. We implement:
1. **Unstructured Media Storage**: Direct-to-S3 uploads and secure downloads using **Amazon S3 Presigned URLs**, keeping large binary payloads out of API Gateway and Lambda RAM.
2. **Atomic Metadata Linking**: Linking uploaded media URLs to DynamoDB items using atomic `list_append` update expressions.
3. **Event-Driven Architecture**: Processing uploaded images asynchronously using **S3 Event Notifications** (`s3:ObjectCreated:*`) and Lambda triggers with zero polling.
4. **In-Memory Caching Layer**: Ultra-low latency data access and reduced DynamoDB read costs using **Amazon ElastiCache** with **Valkey / Redis**, implementing the **Cache-Aside Pattern**, **Global Secondary Index (GSI) Search Caching**, **Dual-Tier Cache Invalidation**, and **Data-Type Specific TTLs**.

---

## 📌 Summary of Changes from Module 05

If you are coming from **Module 05**, here is everything that was added and set up in this module:

### 1. Amazon S3 Object Storage & Media Pipeline
- **S3 Bucket Provisioning (`utils/s3_setup.py`, `product_api_stack.py`)**:
  - Provisioned a versioned S3 bucket (`ProductImagesBucket`) with strict modern access controls (`block_public_acls=True`, `ignore_public_acls=True`, while allowing controlled bucket policies).
  - Configured CORS rules allowing browser/client apps to perform direct `GET`, `PUT`, and `POST` calls.
  - Implemented multi-region support with cross-region compatibility (handling the `LocationConstraint` requirement for non-`us-east-1` regions).
- **Secure Direct Uploads via Presigned PUT URLs (`lambda_code/generate_presigned_url.py`)**:
  - Direct client-to-S3 upload URLs signed with SigV4 virtual-host addressing.
  - Partitioned S3 keys predictably: `products/{product_id}/{image_type}.jpg`.
  - Constrained uploads to `image/jpeg` with temporary 1-hour expiration tokens (`ExpiresIn=3600`).
- **Secure Temporary Downloads via Presigned GET URLs (`lambda_code/generate_download_url.py`)**:
  - Temporary download URLs granting secure, time-limited read access without exposing the S3 bucket publicly.
- **Atomic DynamoDB Media Metadata Linking (`lambda_code/update_product_images.py`)**:
  - Direct API endpoint (`POST /products/{id}/images`) to link uploaded images.
  - Utilizes DynamoDB's atomic `list_append(if_not_exists(image_urls, :empty_list), :new_image)` update expression to safely append URLs without concurrency conflicts.
- **Asynchronous Event-Driven Processing (`lambda_code/process_image_upload.py`)**:
  - Configured S3 bucket event notifications triggering on `s3:ObjectCreated:*` with prefix `products/` and suffix `.jpg`.
  - Processor uses `s3.head_object()` to inspect headers (`ContentLength`, `ContentType`) without downloading binary payloads into Lambda execution RAM.
  - Updates the corresponding DynamoDB record with `image_url`, `file_size`, and `upload_date`.

### 2. In-Memory Caching with Amazon ElastiCache (Valkey / Redis)
- **ElastiCache Cluster Provisioning (`utils/elasticache_setup.py`)**:
  - Automated provisioning of `cache.t3.micro` single-node clusters supporting **Valkey** (port 6379), **Redis** (port 6379), and **Memcached** (port 11211).
  - Subnet group and security group assignment for secure VPC deployment.
- **Cache-Aside Data Retrieval (`db/cache_db.py:get_product_with_cache`)**:
  - Inspects Valkey/Redis first using key `product:{product_id}`.
  - On **Cache Hit**: Deserializes JSON and returns immediately with sub-millisecond latency.
  - On **Cache Miss**: Queries DynamoDB, populates Valkey with a 1-hour TTL (3600s), and returns the record.
  - **Fail-Open Architecture**: Gracefully falls back to DynamoDB if the cache is unreachable or cold.
- **GSI Search Query Optimization & Caching (`db/cache_db.py:search_products_with_cache`)**:
  - Category searches query DynamoDB's `category-index` Global Secondary Index (avoiding expensive full table scans).
  - Search results cached under `search:{query}:{category}:{page}:{limit}` with a 30-minute TTL (1800s).
- **Dual-Tier Cache Invalidation (`db/cache_db.py:invalidate_product_cache`, `update_product_with_cache_invalidation`)**:
  - Whenever product data is updated in DynamoDB, the cache is automatically purged:
    1. Removes the exact item key: `product:{product_id}`.
    2. Uses cursor-based scanning (`scan_iter`) to purge category-specific searches (`search:*:{category}:*`) and broad searches (`search:*`).
- **Data-Type Specific TTL Strategies (`db/cache_db.py:CACHE_TTL`, `cache_with_appropriate_ttl`)**:
  - Tiered expiration times based on data volatility:
    - `product_details`: 3600s (1 hour)
    - `search_results`: 1800s (30 minutes)
    - `category_lists`: 7200s (2 hours)
    - `inventory_counts`: 300s (5 minutes)
    - `user_sessions`: 86400s (24 hours)
    - `popular_products`: 3600s (1 hour)
- **Cache Telemetry & Hit-Rate Analytics (`db/cache_db.py:get_comprehensive_cache_stats`, `analyze_cache_performance`)**:
  - Tracks keyspace hits, misses, hit rate percentage, memory utilization, connected clients, operations per second, and evictions.

### 3. CDK Infrastructure Expansion (`product_api/product_api_stack.py`)
- Provisioned `aws_s3.Bucket` with versioning, auto-delete, and CORS.
- Wired S3 event notifications directly to `aws_s3_notifications.LambdaDestination`.
- Provisioned 4 new Lambda functions with fine-grained IAM grants (`grant_put`, `grant_read`, `grant_read_write_data`).
- Added REST API routes:
  - `GET /products/{id}/image-upload-url`
  - `GET /products/{id}/image-download-url`
  - `POST /products/{id}/images`

---

## 🏛️ System Architecture

### 1. Direct-to-S3 Media Upload & Event-Driven Processing Flow

```text
                                DIRECT CLIENT-TO-S3 FLOW
                                
   1. GET /products/{id}/image-upload-url
  ┌─────────────────────────────────────────────────────────────┐
  │                                                             │
  ▼                                                             ▼
┌──────────────┐         2. Presigned PUT URL           ┌──────────────┐
│    Client    │ ◄───────────────────────────────────── │ API Gateway  │
└──────┬───────┘                                        └──────┬───────┘
       │                                                       │
       │ 3. Direct HTTP PUT (image binary)                     ▼
       │    [Bypasses API Gateway/Lambda limits]        ┌──────────────┐
       ▼                                                │    Lambda    │
┌──────────────┐                                        │(GenerateURL) │
│  Amazon S3   │                                        └──────────────┘
│ ProductImages│
└──────┬───────┘
       │
       │ 4. s3:ObjectCreated:* (prefix: products/, suffix: .jpg)
       ▼
┌──────────────┐         5. s3.head_object()            ┌──────────────┐
│  S3 Trigger  │ ─────────────────────────────────────► │  Amazon S3   │
│  (Event Notif│                                        └──────────────┘
│   Processor) │
└──────┬───────┘
       │ 6. Update item: image_url, file_size, upload_date
       ▼
┌──────────────┐
│AmazonDynamoDB│
│ (Products)   │
└──────────────┘
```

### 2. In-Memory Caching (Cache-Aside & Invalidation Flow)

```text
                               CACHE-ASIDE READ PATH
                         
                       1. Read Request (e.g. GET /products/{id})
                      ┌────────────────────────────────────────┐
                      ▼                                        │
               ┌──────────────┐                                │
               │ API / Lambda │                                │
               └──────┬───────┘                                │
                      │                                        │
           2. Check   │                                        │
           Valkey     ▼                                        │
      ┌────────────────────────────────┐                       │
      │ Amazon ElastiCache (Valkey)    │                       │
      └───────┬────────────────┬───────┘                       │
              │                │                               │
       Hit    │                │ Miss                          │
   ┌──────────┘                └──────────┐                    │
   ▼                                      ▼                    │
Return Cached                      3. Query DynamoDB           │
Data (sub-ms)                      ┌──────────────┐            │
                                   │AmazonDynamoDB│            │
                                   └──────┬───────┘            │
                                          │ 4. Return Item     │
                                          ▼                    │
                                   5. Populate Cache           │
                                      (TTL=3600s) & Return     │
                                                               │
                                                               │
                               WRITE / INVALIDATION PATH       │
                                                               │
                       1. Update Request (e.g. PUT /products)  │
                      ┌────────────────────────────────────────┘
                      ▼
               ┌──────────────┐
               │ API / Lambda │
               └──────┬───────┘
                      │ 2. Update Record
                      ▼
               ┌──────────────┐
               │AmazonDynamoDB│
               └──────┬───────┘
                      │ 3. On DB Success: Invalidate Cache
                      ▼
               ┌────────────────────────────────┐
               │ Amazon ElastiCache (Valkey)    │
               │  - DEL product:{id}            │
               │  - SCAN & DEL search:*         │
               └────────────────────────────────┘
```

---

## 📂 Project Structure

```text
06_scaling_with_data_storage/product-api/
├── cdk.json                           # CDK application configuration
├── requirements.txt                   # Production dependencies (aws-cdk, pydantic, redis>=5.0.0)
├── requirements-dev.txt               # Testing dependencies (pytest, moto[s3,dynamodb])
├── layers/                            # Binary layer assets
│   └── pydantic/python/               # Compiled Pydantic C-extensions for Python 3.13
├── product_api/                       # CDK Infrastructure Stack
│   ├── __init__.py
│   └── product_api_stack.py           # S3 Bucket, DynamoDB, SQS DLQ, Lambdas & API Gateway
├── db/                                # Persistence & Data Layer
│   ├── __init__.py
│   ├── product_schema.py              # Pydantic request validation models
│   ├── products_db.py                 # DynamoDB CRUD operations with exponential backoff
│   └── cache_db.py                    # Valkey / Redis caching layer (Cache-Aside, GSI caching, invalidation)
├── utils/                             # Shared Resilience & Infrastructure Helpers
│   ├── __init__.py
│   ├── response_utils.py              # Standardized API Gateway JSON response helpers
│   ├── retry_utils.py                 # Exponential backoff decorator with full jitter
│   ├── circuit_breaker.py             # Circuit breaker state machine & CloudWatch reporting
│   ├── dlq_setup.py                   # SQS Dead-Letter Queue helper
│   ├── destinations_setup.py          # Lambda Destinations helper
│   ├── s3_setup.py                    # S3 bucket provisioning & event notification setup
│   └── elasticache_setup.py           # Amazon ElastiCache / Valkey cluster provisioning helper
├── lambda_code/                       # Lambda Function Handlers
│   ├── __init__.py
│   ├── get_product.py                 # GET /products/{id}
│   ├── insert_product.py              # POST /products (DLQ-attached)
│   ├── query_products.py              # GET /products (Category GSI query)
│   ├── update_product.py              # PUT /products/{id}
│   ├── options.py                     # CORS preflight handler
│   ├── dlq_processor.py               # DLQ failure classifier & processor
│   ├── destinations_handlers.py       # Asynchronous success/failure destination handlers
│   ├── generate_presigned_url.py      # GET /products/{id}/image-upload-url (S3 PUT url)
│   ├── generate_download_url.py       # GET /products/{id}/image-download-url (S3 GET url)
│   ├── update_product_images.py       # POST /products/{id}/images (DynamoDB list_append)
│   └── process_image_upload.py        # S3 ObjectCreated event consumer (head_object metadata)
├── events/                            # Mock Event Payloads for Local SAM Testing
│   ├── get-product-event.json
│   ├── insert-product-event.json
│   ├── query-products-event.json
│   ├── image-upload-url-event.json    # GET /products/prod_001/image-upload-url event
│   ├── image-download-url-event.json  # GET /products/prod_001/image-download-url event
│   ├── update-product-images-event.json # POST /products/prod_001/images event
│   └── s3-image-upload-event.json     # S3 ObjectCreated mock event
├── scripts/
│   └── init.sh
└── tests/                             # Comprehensive Unit Test Suite
    ├── __init__.py
    ├── event_factory.py               # Standardized APIGatewayEventFactory
    └── unit/                          # Domain-Categorized Unit Tests
        ├── __init__.py
        ├── api/                       # Core API & DynamoDB tests
        │   ├── __init__.py
        │   ├── test_product_api_stack.py
        │   ├── test_products_db.py
        │   ├── test_product_validation.py
        │   ├── test_get_product.py
        │   ├── test_insert_product.py
        │   └── test_error_handling.py
        ├── storage/                   # S3 Storage & Image Processing tests
        │   ├── __init__.py
        │   ├── test_s3_setup.py
        │   ├── test_generate_presigned_url.py
        │   ├── test_generate_download_url.py
        │   ├── test_update_product_images.py
        │   └── test_process_image_upload.py
        ├── cache/                     # ElastiCache / Valkey Caching tests
        │   ├── __init__.py
        │   ├── test_elasticache_setup.py
        │   └── test_cache_db.py
        └── resilience/                # Fault Tolerance & Resilience tests
            ├── __init__.py
            ├── test_circuit_breaker.py
            ├── test_retry_utils.py
            └── test_dlq_processor.py
```

---

## 🛠️ Installations & Setup

### 1. Development Dependencies
Activate the virtual environment and install project dependencies:

```sh
cd 06_scaling_with_data_storage/product-api
python3 -m venv .venv
source .venv/bin/activate                 # macOS/Linux
# .venv\Scripts\Activate.ps1             # Windows PowerShell

pip install -r requirements.txt
pip install -r requirements-dev.txt
```

Your `requirements.txt` includes:
```text
aws-cdk-lib>=2.170.0
constructs>=10.0.0
pydantic>=2.0.0
redis>=5.0.0
boto3>=1.35.0
```

### 2. Pydantic Lambda Layer
If the layer binary directory is not yet built, package Pydantic for Amazon Linux / Python 3.13:

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

## 🧪 Running Unit Tests

We use **Pytest** with **Moto** and `unittest.mock` to test DynamoDB, S3, and ElastiCache/Valkey logic locally with zero cloud dependencies. Unit tests are organized into domain-specific subdirectories under `tests/unit/`:

```sh
# Run the entire test suite (64 tests across all domains)
pytest tests/unit/ -v

# Or run tests for a specific domain:
pytest tests/unit/api/ -v          # Core REST API & DynamoDB tests (15 tests)
pytest tests/unit/storage/ -v      # S3 storage & image processing tests (22 tests)
pytest tests/unit/cache/ -v        # ElastiCache / Valkey caching tests (15 tests)
pytest tests/unit/resilience/ -v   # Circuit breaker, retry & DLQ tests (12 tests)
```

### Test Suite Coverage (64 Passing Tests)

| Subfolder | Test Module | Coverage Area | Status |
| :--- | :--- | :--- | :--- |
| **`tests/unit/api/`** | `test_product_api_stack.py` | CDK CloudFormation properties: SQS DLQ & Versioned S3 Bucket | **Passed** |
| | `test_products_db.py` | Mock DynamoDB table CRUD & query operations | **Passed** |
| | `test_product_validation.py` | Pydantic schema validation & boundary constraints | **Passed** |
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

## 💻 Local Testing & Verification

### A. Testing the In-Memory Caching Layer Locally (Docker + Valkey)

To test the Cache-Aside pattern, GSI search caching, invalidation, and metrics without incurring AWS charges or needing VPC access:

#### 1. Start a Local Valkey Container with Docker
```sh
docker run -d --name valkey-local -p 6379:6379 valkey/valkey:latest
```
*(Alternatively, you can run Redis: `docker run -d --name valkey-local -p 6379:6379 redis:7-alpine`)*

Verify that Valkey is accepting connections:
```sh
docker exec -it valkey-local valkey-cli ping
# Output: PONG
```

#### 2. Verify Cache-Aside & Invalidation via Interactive Python
Launch Python within `.venv`:

```python
import os
import boto3
from moto import mock_aws

# Point cache client to local Valkey container
os.environ['ELASTICACHE_ENDPOINT'] = 'localhost'
os.environ['ELASTICACHE_PORT'] = '6379'
os.environ['PRODUCT_TABLE'] = 'Products'

# Run with Moto to mock DynamoDB
with mock_aws():
    # 1. Create mock DynamoDB table with GSI
    dynamodb = boto3.resource('dynamodb', region_name='ap-southeast-2')
    table = dynamodb.create_table(
        TableName='Products',
        KeySchema=[{'AttributeName': 'id', 'KeyType': 'HASH'}],
        AttributeDefinitions=[
            {'AttributeName': 'id', 'AttributeType': 'S'},
            {'AttributeName': 'category', 'AttributeType': 'S'}
        ],
        GlobalSecondaryIndexes=[{
            'IndexName': 'category-index',
            'KeySchema': [{'AttributeName': 'category', 'KeyType': 'HASH'}],
            'Projection': {'ProjectionType': 'ALL'}
        }],
        BillingMode='PAY_PER_REQUEST'
    )
    table.put_item(Item={
        'id': 'prod_test',
        'title': 'Mechanical Keyboard',
        'price': 99.99,
        'category': 'Electronics',
        'description': 'RGB Mechanical Keyboard'
    })

    from db.cache_db import (
        get_product_with_cache,
        search_products_with_cache,
        update_product_with_cache_invalidation,
        get_comprehensive_cache_stats,
        analyze_cache_performance,
        valkey_client
    )

    # 2. First call -> Cache Miss (queries DynamoDB and populates Valkey)
    item_miss = get_product_with_cache('prod_test')
    print("Call 1 Result:", item_miss['title'])

    # 3. Second call -> Cache Hit (reads directly from Valkey in < 1ms)
    item_hit = get_product_with_cache('prod_test')
    print("Call 2 Result (from cache):", item_hit['title'])

    # 4. Search caching -> Cache Miss, then Cache Hit
    search_miss = search_products_with_cache(category='Electronics')
    search_hit = search_products_with_cache(category='Electronics')
    print(f"Search found {len(search_hit)} items from cache")

    # 5. Invalidate on update
    update_product_with_cache_invalidation('prod_test', {
        'title': 'Wireless Mechanical Keyboard',
        'price': 129.99,
        'description': 'Updated wireless keyboard',
        'category': 'Electronics'
    })

    # Verify Valkey product key was deleted on write
    print("Product key in Valkey after update:", valkey_client.get("product:prod_test")) # None

    # 6. Analyze cache telemetry
    stats = analyze_cache_performance()
```

#### 3. Inspect Valkey Directly Using CLI
While the above is running, open a terminal to inspect keys and TTLs inside the container:
```sh
# View all keys
docker exec -it valkey-local valkey-cli keys "*"

# Check TTL of a product key (should be ~3600s)
docker exec -it valkey-local valkey-cli ttl "product:prod_test"

# Inspect the stored JSON payload
docker exec -it valkey-local valkey-cli get "product:prod_test"
```

---

### B. Local Testing with AWS SAM CLI

With Docker running, you can use the **AWS SAM CLI** to execute Lambda functions in local container environments matching production.

#### 1. Synthesize the CloudFormation Template
Before running SAM commands, synthesize the CDK stack into `cdk.out/`:

```sh
cdk synth ProductApiStack
```

---

#### 2. Invoke Individual Lambdas Locally
Pass the synthesized template (`-t`) and a mock event payload (`-e`):

```sh
# 1. Test generating a presigned upload URL
sam local invoke GeneratePresignedUrl \
  -t cdk.out/ProductApiStack.template.json \
  -e events/image-upload-url-event.json

# 2. Test generating a presigned download URL
sam local invoke GenerateDownloadUrl \
  -t cdk.out/ProductApiStack.template.json \
  -e events/image-download-url-event.json

# 3. Test linking an image URL to DynamoDB
sam local invoke UpdateProductImages \
  -t cdk.out/ProductApiStack.template.json \
  -e events/update-product-images-event.json

# 4. Test S3 event notification processor
sam local invoke ProcessImageUpload \
  -t cdk.out/ProductApiStack.template.json \
  -e events/s3-image-upload-event.json
```

---

#### 3. Emulate API Gateway Locally
Spin up a local HTTP API server on port `3000`:

```sh
sam local start-api -t cdk.out/ProductApiStack.template.json -p 3000
```

In a separate terminal, test the image routes:

```sh
# Request upload URL
curl -s "http://127.0.0.1:3000/products/prod_001/image-upload-url" | jq .

# Request download URL
curl -s "http://127.0.0.1:3000/products/prod_001/image-download-url" | jq .

# Link image to product
curl -X POST "http://127.0.0.1:3000/products/prod_001/images" \
  -H "Content-Type: application/json" \
  -d '{"image_key": "products/prod_001/main.jpg"}' | jq .
```

---

## 🚀 Cloud Deployment & Verification (`cdk deploy`)

### 1. Deploy Stack to AWS
Deploy all resources to your AWS account:

```sh
cdk deploy ProductApiStack
```

Upon completion, capture the output values and export both `API_URL` and `BUCKET_NAME`:
```sh
# Export API Gateway URL and S3 Bucket Name from stack outputs
export API_URL=$(aws cloudformation describe-stacks \
  --stack-name ProductApiStack \
  --query "Stacks[0].Outputs[?OutputKey=='ProductsApiUrl'].OutputValue" \
  --output text)

export BUCKET_NAME=$(aws cloudformation describe-stacks \
  --stack-name ProductApiStack \
  --query "Stacks[0].Outputs[?OutputKey=='ProductImageBucketName'].OutputValue" \
  --output text)

echo "API_URL: $API_URL"
echo "BUCKET_NAME: $BUCKET_NAME"
```

---

### 2. End-to-End Live API Testing

#### Step 1: Create a Product (Auto-Assigned ID)
Create a new product with `title`, `price`, `category`, and `description`:
```sh
CREATE_RESP=$(curl -s -X POST "$API_URL/products" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Cloud Mechanical Keyboard",
    "price": 149.99,
    "category": "Electronics",
    "description": "High performance mechanical keyboard"
  }')

echo "$CREATE_RESP" | jq .

# Export the auto-assigned product ID
export PRODUCT_ID=$(echo "$CREATE_RESP" | jq -r '.product.id')
echo "Created Product ID: $PRODUCT_ID"
```

#### Step 2: Request a Presigned Upload URL
```sh
UPLOAD_RESP=$(curl -s "$API_URL/products/$PRODUCT_ID/image-upload-url")
echo "$UPLOAD_RESP" | jq .

export UPLOAD_URL=$(echo "$UPLOAD_RESP" | jq -r .upload_url)
```
*Response returns `"upload_url"` and `"object_key": "products/<PRODUCT_ID>/main.jpg"`.*

#### Step 3: Upload Image Directly to Amazon S3
Use the existing test image (`test.jpg`) located in the repository:
```sh
# Execute direct S3 PUT upload
curl -X PUT -T test.jpg -H "Content-Type: image/jpeg" "$UPLOAD_URL" -v
```
*(HTTP status should return `200 OK`)*

#### Step 4: Verify Asynchronous S3 Event Trigger
Because S3 is configured to trigger `ProcessImageUpload` on `.jpg` creations under `products/`, S3 automatically invokes the Lambda function. Verify that metadata was saved to DynamoDB:
```sh
curl -s "$API_URL/products/$PRODUCT_ID" | jq .
```
*Verify that `image_url`, `file_size`, and `upload_date` are now populated on the item.*

#### Step 5: Explicitly Link Image Key via API Gateway
```sh
curl -X POST "$API_URL/products/$PRODUCT_ID/images" \
  -H "Content-Type: application/json" \
  -d "{\"image_key\": \"products/$PRODUCT_ID/main.jpg\"}" | jq .
```
*Verify that the `image_urls` list attribute in DynamoDB contains the new URL.*

#### Step 6: Request a Presigned Download URL
```sh
DOWNLOAD_RESP=$(curl -s "$API_URL/products/$PRODUCT_ID/image-download-url")
echo "$DOWNLOAD_RESP" | jq .

export DOWNLOAD_URL=$(echo "$DOWNLOAD_RESP" | jq -r .download_url)

echo "Copy and open the download URL in your web browser to view the image:"
echo "$DOWNLOAD_URL"
```

---

### 3. Deploying & Verifying ElastiCache on AWS Cloud

> [!WARNING]
> **Cost Awareness**: Amazon ElastiCache instances incur continuous hourly charges while running. If you are creating a cluster for educational or testing purposes, delete it when you finish your verification.

> [!IMPORTANT]
> **Valkey Engine Requirement**: In Amazon ElastiCache, the Valkey engine is **not** supported by the legacy `CreateCacheCluster` API. You must use the **`CreateReplicationGroup`** API (`aws elasticache create-replication-group`).

#### Step 1: Provision Valkey Cluster via Python or AWS CLI
You can provision the cluster using our helper script:

```python
import os
from utils.elasticache_setup import create_elasticache_cluster

# Set your VPC Subnet Group and Security Group ID
os.environ['CACHE_SUBNET_GROUP'] = 'store-cache-subnet-group'
os.environ['CACHE_SECURITY_GROUP'] = 'sg-0123456789abcdef0'

endpoint = create_elasticache_cluster(engine='valkey')
print(f"Valkey Cluster Endpoint: {endpoint}")
```

Or via the AWS CLI using `create-replication-group`:
```sh
aws elasticache create-replication-group \
    --replication-group-id online-store-valkey-cache \
    --replication-group-description "Online Store Valkey Cache" \
    --engine valkey \
    --cache-node-type cache.t3.micro \
    --num-cache-clusters 1 \
    --cache-subnet-group-name store-cache-subnet-group \
    --security-group-ids "$SG_ID"
```

Monitor cluster creation until status becomes `available`:
```sh
aws elasticache describe-replication-groups \
    --replication-group-id online-store-valkey-cache \
    --query "ReplicationGroups[0].[Status, NodeGroups[0].PrimaryEndpoint.Address]" \
    --output table
```

#### Step 2: Understand VPC Isolation
By design, **Amazon ElastiCache clusters are isolated within your Amazon VPC** and do not have public IP addresses. To communicate with your live ElastiCache cluster:

1. **Option A: Connect Lambda Functions to VPC**:
   Configure your Lambda functions in `product_api_stack.py` with `vpc=vpc, vpc_subnets=...` and security groups allowing outbound traffic on port 6379. Provide the cluster endpoint via environment variable `ELASTICACHE_ENDPOINT`.
2. **Option B: Connect via EC2 Bastion / Cloud9**:
   Launch an EC2 instance in the same VPC and security group:
   ```sh
   sudo dnf install valkey -y
   valkey-cli -h <primary-endpoint> -p 6379 ping
   # Output: PONG
   ```
3. **Option C: AWS Systems Manager Port Forwarding**:
   If you have an EC2 bastion managed by SSM, forward port 6379 to your local workstation:
   ```sh
   aws ssm start-session \
       --target i-0123456789abcdef0 \
       --document-name AWS-StartPortForwardingSessionToRemoteHost \
       --parameters '{"host":["<primary-endpoint>"],"portNumber":["6379"],"localPortNumber":["6379"]}'
   ```
   Now your local tools and scripts can connect to `localhost:6379`!

#### Step 3: Monitor Cache Metrics in CloudWatch
Amazon ElastiCache publishes real-time metrics to Amazon CloudWatch under namespace `AWS/ElastiCache`:
- `CacheHits` & `CacheMisses`: Used to measure your hit rate `(Hits / (Hits + Misses)) * 100`.
- `BytesUsedForCache`: Monitors memory consumption.
- `Evictions`: Ensures your cache memory size is sufficient. If evictions > 0, consider increasing node size or tuning TTLs.

---

## 🧹 Clean Up

To tear down all resources provisioned by this stack:

```sh
# 1. Delete ElastiCache replication group (if provisioned)
aws elasticache delete-replication-group --replication-group-id online-store-valkey-cache

# 2. Empty S3 Bucket (using exported $BUCKET_NAME)
if [ -n "$BUCKET_NAME" ]; then
    aws s3 rm "s3://$BUCKET_NAME" --recursive
    echo "S3 Bucket emptied."
fi

# 3. Destroy CloudFormation stack
cdk destroy ProductApiStack
```
