# 📦 Module 06: Scaling with Data Storage

> [!NOTE]
> **Module In Progress**: This module is actively being developed. This guide documents everything implemented and verified through the **Amazon S3 Object Storage**, **Presigned URLs**, **Atomic DynamoDB Media Linking**, and **Event-Driven Lambda Processing** milestones.

In this module, we scale our serverless microservice beyond tabular database records to handle unstructured media storage using **Amazon Simple Storage Service (Amazon S3)**. We implement secure client-to-storage upload and download patterns using **S3 Presigned URLs**, link media metadata to DynamoDB records using atomic update expressions, and establish asynchronous, event-driven workflows using **S3 Event Notifications** and **AWS Lambda triggers**.

---

## 📌 Summary of Changes from Module 05

If you are coming from **Module 05**, here is what has been introduced in this module:

1. **Amazon S3 Bucket Provisioning (`utils/s3_setup.py`, `product_api_stack.py`)**:
   - Provisioned an S3 bucket (`ProductImagesBucket`) with **Object Versioning** enabled to safeguard against accidental overwrites.
   - Enforced modern security best practices with **Public Access Block** (`BlockPublicAcls`, `IgnorePublicAcls`, while allowing controlled bucket policies).
   - Added **CORS Rules** to allow browser and client applications to execute direct `GET`, `PUT`, and `POST` operations against S3.
   - Handled regional endpoint nuances (e.g., omitting `LocationConstraint` for `us-east-1` while applying it to regional endpoints like `ap-southeast-2`).

2. **Secure Direct Uploads via Presigned PUT URLs (`lambda_code/generate_presigned_url.py`)**:
   - Enabled clients to upload media directly to S3 without routing heavy binary payloads through API Gateway or Lambda execution memory (bypassing Lambda payload and timeout limits).
   - Configured SigV4 virtual-host addressing and partitioned object keys predictably: `products/{product_id}/{image_type}.jpg`.
   - Constrained uploads to `image/jpeg` with temporary 1-hour expiration tokens (`ExpiresIn=3600`).

3. **Secure Temporary Downloads via Presigned GET URLs (`lambda_code/generate_download_url.py`)**:
   - Implemented temporary download URL generation for private product images, granting time-limited read access without exposing the bucket publicly.

4. **Atomic DynamoDB Media Metadata Linking (`lambda_code/update_product_images.py`)**:
   - Exposed an endpoint for clients to explicitly register uploaded image keys.
   - Leveraged DynamoDB's `list_append(if_not_exists(image_urls, :empty_list), :new_image)` update expression to atomically append URLs to the `image_urls` list attribute without overwriting existing entries or item attributes.

5. **Asynchronous Event-Driven Processing via S3 Event Notifications (`lambda_code/process_image_upload.py`, `utils/s3_setup.py`)**:
   - Configured S3 bucket event notifications for `s3:ObjectCreated:*` filtered to prefix `products/` and suffix `.jpg`.
   - Created an event-driven Lambda processor that reacts immediately to image creations.
   - Used `s3.head_object()` to read file size and content type metadata directly from S3 headers without pulling the binary image file into Lambda RAM.
   - Updated the corresponding DynamoDB record with `image_url`, `file_size`, and `upload_date`.

6. **AWS CDK Infrastructure Expansion (`product_api/product_api_stack.py`)**:
   - Integrated `aws_s3.Bucket` and `aws_s3_notifications.LambdaDestination`.
   - Wired 4 new Lambda functions with fine-grained IAM grants (`grant_put`, `grant_read`, `grant_read_write_data`).
   - Added RESTful API Gateway resources and CORS options:
     - `GET /products/{id}/image-upload-url`
     - `GET /products/{id}/image-download-url`
     - `POST /products/{id}/images`

7. **Multi-Faceted Testing Strategy**:
   - **64 Automated Unit Tests** across 4 categorized suites (`api`, `storage`, `cache`, `resilience`) with `pytest`, `moto[s3,dynamodb]`, and mock Valkey clients.
   - **Local AWS SAM CLI Emulation** with active Docker integration (`sam local invoke`, `sam local start-api`).
   - **Live AWS Integration Script** (`scripts/test_live_services.py`) to verify real S3 uploads and DynamoDB updates against live AWS infrastructure.

---

## 🏛️ Architecture & Media Processing Flow

```
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

---

## 📂 Project Structure

```text
06_scaling_with_data_storage/product-api/
├── cdk.json                           # CDK application configuration
├── requirements.txt                   # Production dependencies (aws-cdk, pydantic)
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
│   ├── init.sh
│   └── test_live_services.py          # Integration test runner against real AWS services
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

Your `requirements-dev.txt` includes:
```text
pytest~=8.3
pytest-cov~=5.0
moto[dynamodb]~=5.0
boto3~=1.35
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
pytest tests/unit/api/ -v          # Core REST API & DynamoDB tests
pytest tests/unit/storage/ -v      # S3 storage & image processing tests
pytest tests/unit/cache/ -v        # ElastiCache / Valkey caching tests
pytest tests/unit/resilience/ -v   # Circuit breaker, retry & DLQ tests
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

## 💻 Local Testing with AWS SAM CLI

With Docker running, you can use the **AWS SAM CLI** (`v1.172.1`) to execute Lambda functions in local container environments matching production.

### 1. Synthesize the CloudFormation Template
Before running SAM commands, synthesize the CDK stack into `cdk.out/`:

```sh
cdk synth ProductApiStack
```

---

### 2. Invoke Individual Lambdas Locally
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

### 3. Emulate API Gateway Locally
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

## ⚡ Direct Integration Script (Live AWS Services)

To verify the complete image pipeline directly against your live AWS S3 bucket and DynamoDB table (without needing API Gateway or Docker), run:

```sh
python3 scripts/test_live_services.py
```

**Automated Workflow Executed by Script:**
1. Connects to your configured AWS Region (`ap-southeast-2`) and verifies the `Products` table.
2. Creates or resolves your live S3 bucket (`create_product_images_bucket()`).
3. Executes `generate_presigned_url` to obtain an authorized S3 PUT URL.
4. Uploads a sample binary JPEG to S3 using standard HTTP PUT.
5. Executes `generate_download_url` to obtain an authorized S3 GET URL.
6. Executes `update_product_images` to atomically append the S3 URL to DynamoDB.
7. Executes `process_image_upload` with a mock S3 event, verifying `head_object` metadata extraction.
8. Queries DynamoDB and displays the updated product item with full image attributes.

---

## 🚀 Cloud Deployment & Verification (`cdk deploy`)

### 1. Deploy Stack to AWS
Deploy all resources to your AWS account:

```sh
cdk deploy ProductApiStack
```

Upon completion, capture the output URLs:
```text
Outputs:
ProductApiStack.ProductsApiUrl = https://<api-id>.execute-api.ap-southeast-2.amazonaws.com/dev/
ProductApiStack.ProductImageBucketName = productapistack-productimagesbucket-...
```

Export the API URL:
```sh
export API_URL="https://<api-id>.execute-api.ap-southeast-2.amazonaws.com/dev"
```

---

### 2. End-to-End Live API Testing

#### Step 1: Request a Presigned Upload URL
```sh
curl -s "$API_URL/products/prod_001/image-upload-url" | jq .
```
*Response returns `"upload_url"` and `"object_key": "products/prod_001/main.jpg"`.*

#### Step 2: Upload Image Directly to Amazon S3
Export the returned URL and upload a binary image:
```sh
UPLOAD_URL="<paste upload_url here>"

# Create or select a test image
echo "sample-jpeg-binary-payload" > test_image.jpg

# Execute direct S3 PUT upload
curl -X PUT -T test_image.jpg -H "Content-Type: image/jpeg" "$UPLOAD_URL" -v
```

#### Step 3: Verify Asynchronous S3 Event Trigger
Because S3 is configured to trigger `ProcessImageUpload` on `.jpg` creations under `products/`, S3 automatically invokes the Lambda function. Verify that metadata was saved to DynamoDB:
```sh
curl -s "$API_URL/products/prod_001" | jq .
```
*Verify that `image_url`, `file_size`, and `upload_date` are now populated.*

#### Step 4: Explicitly Link Image Key via API Gateway
```sh
curl -X POST "$API_URL/products/prod_001/images" \
  -H "Content-Type: application/json" \
  -d '{"image_key": "products/prod_001/main.jpg"}' | jq .
```
*Verify that `image_urls` list attribute in DynamoDB contains the new URL.*

#### Step 5: Request a Presigned Download URL
```sh
curl -s "$API_URL/products/prod_001/image-download-url" | jq .
```
*Open the resulting `"download_url"` in your web browser to view or download the uploaded image.*

---

## 🧹 Clean Up

To tear down all resources provisioned by this stack:

```sh
# Destroy the CloudFormation stack
cdk destroy ProductApiStack

# If objects were uploaded to S3, empty and delete bucket manually if needed
BUCKET_NAME=$(aws s3 ls | grep productimagesbucket | awk '{print $3}')
if [ -n "$BUCKET_NAME" ]; then
    aws s3 rm "s3://$BUCKET_NAME" --recursive
    aws s3api delete-bucket --bucket "$BUCKET_NAME"
fi
```
