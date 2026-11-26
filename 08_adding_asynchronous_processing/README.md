# ⚡ Module 08: Adding Asynchronous Processing

In this module, you learn how to address the responsiveness challenges that prevent your API from handling real-world e-commerce demands. You implement asynchronous messaging patterns that decouple services, handle failures gracefully, and process complex workflows in the background while maintaining responsive customer interactions. These patterns transform your API from synchronous operations to event-driven architecture.

---

## 📌 Summary of Changes from Module 07

If you are coming from **Module 07**, here is what has been introduced in this module:

### 1. SQS Order Processing Queue & Dead-Letter Queue (`utils/sqs_order_queue.py`)
- **`create_order_processing_queue()`**: Creates `order-processing-queue` (5-minute `VisibilityTimeoutSeconds`, 14-day `MessageRetentionPeriod`, 20-second long polling `ReceiveMessageWaitTimeSeconds`, and a `RedrivePolicy` with `maxReceiveCount: 3`) alongside `order-processing-dlq` for failed messages.
- **`send_order_to_queue(order_data, queue_url)`**: Enqueues order payloads with UTC timestamps, `processing_steps` metadata, and `order_priority` / `customer_tier` message attributes.

### 2. SQS Order Processor Lambda (`lambda_code/order_processor.py`)
- **`handler(event, context)`**: Consumes SQS batch `Records`, executes the multi-step `process_order_workflow`, and raises `OrderProcessingError` on failure so SQS automatically retries and routes persistent failures to the DLQ.
- **`validate_inventory(items)`**: Checks `Products` DynamoDB table stock availability before payment/shipping execution, with compensating `refund_payment` on downstream label creation failures.

### 3. SQS Monitoring & Scaling (`utils/sqs_monitoring.py`)
- **`monitor_queue_metrics(queue_url)`**: Combines real-time SQS attributes (`ApproximateNumberOfMessages`, `ApproximateNumberOfMessagesNotVisible`) with CloudWatch `AWS/SQS` `ApproximateNumberOfVisibleMessages` statistics.
- **`scale_processing_capacity(queue_metrics)`**: Generates `scale_up` (when `visible_messages > 100`, capped at 50) and `scale_down` (when `max_queue_depth < 5` and `visible_messages < 10`) recommendations.

### 4. Amazon SNS Topics, Publishing & Filtering (`utils/sns_notifications.py`)
- **`create_notification_topics()` & `subscribe_to_notifications()`**: Provisions `customer-notifications` (linear retry policy), `system-alerts` (exponential retry policy), and `inventory-alerts` topics.
- **`send_order_confirmation()`**: Publishes `MessageStructure='json'` payloads tailored for `default`, `email` (`create_email_message`), and `sms` (`create_sms_message`) channels with filtering attributes.
- **`setup_filtered_subscriptions()` & `send_inventory_alert()`**: Configures `FilterPolicy` rules (`customer_tier`, `order_type`) and publishes stock alerts with `medium`/`high` urgency.

### 5. Event-Driven Lambda Integration & Rollback (`lambda_code/async_workflow_handlers.py`)
- **`order_processor_handler`**, **`inventory_monitor_handler`**, and **`notification_dispatcher_handler`**: Orchestrate SQS consumption, DynamoDB low-stock scans, and SNS attribute-based notification routing using `CUSTOMER_NOTIFICATION_TOPIC`, `SYSTEM_ALERT_TOPIC`, and `INVENTORY_ALERT_TOPIC` environment variables.
- **`execute_order_workflow()` & `rollback_completed_steps()`**: Executes workflow steps sequentially and rolls back completed steps in reverse order on failure.
- **`configure_lambda_triggers()`**: Wires SQS `create_event_source_mapping` (`BatchSize=10`, `MaximumBatchingWindowInSeconds=5`) and SNS `add_permission`.

### 6. Amazon EventBridge Custom Buses & Event Routing (`utils/eventbridge_routing.py`)
- **`create_event_buses()`**: Provisions dedicated domain buses (`online-store-orders`, `online-store-inventory`, `online-store-customers`).
- **`publish_order_event()` & `publish_inventory_event()`**: Publishes structured domain events (`store.orders`, `store.inventory`) and raises `EventPublishError` when `FailedEntryCount > 0`.
- **`create_order_processing_rules()` & `create_inventory_alert_rules()`**: Configures routing rules with `InputTransformer` payloads targeting Lambda, SNS, and FIFO SQS (`MessageGroupId`).
- **`create_advanced_event_patterns()` & `create_content_based_routing_rule()`**: Implements numeric (`>= 500`, `<= 5`), nested (`shippingAddress.state`), and existence (`exists: True`) pattern matching.

### 7. EventBridge Workflows, DLQ Error Handling & Dashboards (`lambda_code/eventbridge_handlers.py`, `utils/eventbridge_error_handling.py`)
- **`inventory_processor_handler`**, **`notification_processor_handler`**, and **`analytics_processor_handler`**: Process EventBridge `Order Placed` events to atomically decrement `Products` inventory, publish to `ORDER_TOPIC_ARN`, and persist records in `AnalyticsEvents`.
- **`setup_event_error_handling()` & `process_failed_events_handler()`**: Creates `eventbridge-failed-events-dlq`, attaches target `RetryPolicy` (`MaximumRetryAttempts=3`, `MaximumEventAge=3600`) + `DeadLetterConfig`, and triages failed events (`is_recoverable` / `attempt_recovery` / `store_for_investigation`).
- **`create_event_monitoring_dashboard()`**: Creates the `EventDrivenArchitecture-Monitoring` CloudWatch dashboard for `AWS/Events` and `AWS/Lambda` metrics.

---

## 🏛️ Event-Driven Asynchronous Architecture

```text
  ┌──────────────┐      send_message      ┌──────────────────────────┐
  │  Client/API  │ ─────────────────────▶ │  order-processing-queue  │
  └──────┬───────┘                        └────────────┬─────────────┘
         │                                             │ (maxReceiveCount=3)
         │ put_events                     ┌────────────┴────────────┐
         ▼                                ▼                         ▼
  ┌──────────────────────────┐   ┌──────────────────┐    ┌─────────────────────┐
  │ EventBridge Custom Buses │   │  order_processor │    │ order-processing-dlq│
  │ (orders / inv / cust)    │   └────────┬─────────┘    └─────────────────────┘
  └──────┬───────────────────┘            │ publish
         │ Rules & InputTransformer       ▼
         ├───────────────────▶ ┌──────────────────────────────┐
         │                     │   SNS Topics & FilterPolicy  │
         ▼                     │ (customer / system / inv)    │
  ┌──────────────────────────┐ └──────────────┬───────────────┘
  │ Lambda Targets + EB DLQ  │                │
  │ (inventory/notify/stats) │        ┌───────┴───────┐
  └──────────────────────────┘        ▼               ▼
                                 Email (VIP)     SMS (Express)
```

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

## 🛡️ Resilience Flow Architecture (`ResilientExternalService`)

```text
                                  ┌─────────────────────────────┐
                                  │   ResilientExternalService  │
                                  └──────────────┬──────────────┘
                                                 │
                                     Is Circuit CLOSED/HALF-OPEN?
                                                 │
                        ┌────────────────────────┴────────────────────────┐
                        │ YES                                             │ NO (Circuit is OPEN)
                        ▼                                                 ▼
        ┌───────────────────────────────┐                       ┌───────────────────┐
        │ retry_with_exponential_backoff│                       │     Fail Fast     │
        │       (Attempts 1 .. N)       │                       │     (< 1 ms)      │
        └───────────────┬───────────────┘                       └─────────┬─────────┘
                        │                                                 │
             Did call succeed?                                            │
           ┌────────────┴────────────┐                                    │
           │ YES                     │ NO (All retries exhausted)         │
           ▼                         ▼                                    │
   {"status": "success"}     Trip failure count / OPEN                    │
                             Does a fallback exist?                       │
                                     │                                    │
                        ┌────────────┴────────────┐                       │
                        │ YES                     │ NO                    │
                        ▼                         ▼                       │
               {"status": "fallback"}     {"status": "failed"}            │
                        ▲                                                 │
                        └─────────────────────────────────────────────────┘
```

---

## 📂 Project Structure

```text
08_adding_asynchronous_processing/product-api/
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
├── utils/                             # Asynchronous Messaging, Resilience & Infrastructure Helpers
│   ├── __init__.py
│   ├── sqs_order_queue.py             # Order processing SQS queue & DLQ setup + producer
│   ├── sqs_monitoring.py              # SQS CloudWatch metrics & capacity scaling
│   ├── sns_notifications.py           # SNS topics, multi-format messages & FilterPolicy setup
│   ├── eventbridge_routing.py         # EventBridge custom buses, rules & content-based patterns
│   ├── eventbridge_error_handling.py  # EventBridge RetryPolicy, DLQ & CloudWatch dashboard
│   ├── response_utils.py              # Bridges to response_formatter
│   ├── retry_utils.py                 # Exponential backoff with full jitter & shipping rates
│   ├── circuit_breaker.py             # Circuit breaker state machine & payment processing
│   ├── graceful_degradation.py        # Critical aborts, shipping fallbacks & async queues
│   ├── resilient_service.py           # ResilientExternalService composite orchestrator & handler
│   ├── dlq_setup.py                   # SQS DLQ helper
│   ├── destinations_setup.py          # Lambda Destinations helper
│   ├── s3_setup.py                    # S3 bucket & notification setup
│   └── elasticache_setup.py           # ElastiCache / Valkey helper
├── lambda_code/                       # Lambda Function Handlers
│   ├── __init__.py
│   ├── order_processor.py             # SQS order processing consumer & inventory validation
│   ├── async_workflow_handlers.py     # SQS/SNS workflow handlers, reverse rollback & triggers
│   ├── eventbridge_handlers.py        # EventBridge inventory, notification, analytics & DLQ handlers
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
        ├── api/                       # API, DynamoDB & layer tests
        ├── async_processing/          # Module 08 SQS, SNS, EventBridge & workflow tests
        │   ├── test_sqs_order_queue.py
        │   ├── test_order_processor.py
        │   ├── test_sqs_monitoring.py
        │   ├── test_sns_notifications.py
        │   ├── test_async_workflow_handlers.py
        │   ├── test_eventbridge_routing.py
        │   └── test_eventbridge_workflows.py
        ├── storage/                   # S3 & image processing tests
        ├── cache/                     # ElastiCache & Valkey tests
        └── resilience/                # Circuit breaker, retry & DLQ tests
```

---

## 🛠️ Installations & Setup

### 1. Development Dependencies
Activate the virtual environment and install project dependencies:

```sh
cd 08_adding_asynchronous_processing/product-api
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

### 3. Product Utilities Lambda Layer
The source code for `ProductUtilitiesLayer` is located under `layers/product_utilities/python/`. Because `pydantic` is provided by `PydanticLayer` and `boto3` is pre-installed in the AWS Lambda runtime, no C-extension compilation is required—CDK packages this directory automatically on deploy:

```text
layers/product_utilities/
├── python/
│   ├── __init__.py
│   ├── product_validator.py
│   ├── database_helper.py
│   └── response_formatter.py
└── requirements.txt
```


---

## 🧪 Testing & Verification Guide

### 1. Local Testing & Verification

You can verify all layers, handlers, resilience patterns, and infrastructure templates locally without incurring AWS charges:

#### A. Run the Entire Test Suite (138 Passing Tests)
```sh
cd 08_adding_asynchronous_processing/product-api
source .venv/bin/activate
pytest tests/unit/ -v
```

#### B. Test Module 08 Asynchronous Processing Patterns Locally
```sh
# Run all SQS, SNS, EventBridge, and async workflow tests (43 tests):
pytest tests/unit/async_processing/ -v

# Individual test suites:
pytest tests/unit/async_processing/test_sqs_order_queue.py -v
pytest tests/unit/async_processing/test_order_processor.py -v
pytest tests/unit/async_processing/test_sqs_monitoring.py -v
pytest tests/unit/async_processing/test_sns_notifications.py -v
pytest tests/unit/async_processing/test_async_workflow_handlers.py -v
pytest tests/unit/async_processing/test_eventbridge_routing.py -v
pytest tests/unit/async_processing/test_eventbridge_workflows.py -v
```

#### C. Test Shared Lambda Layer Modules Locally
Verify that layer modules (`product_validator`, `database_helper`, `response_formatter`) function identically both in direct imports and via backward-compatible bridges:
```sh
pytest tests/unit/api/test_product_utilities_layer.py -v
```

#### D. Verify CloudFormation Synthesis & Layer Bindings
Synthesize the CDK stack to confirm all Lambda functions have both `PydanticLayer` and `ProductUtilitiesLayer` attached in the synthesized CloudFormation template:
```sh
pytest tests/unit/api/test_product_api_stack.py -v
cdk synth ProductApiStack > /dev/null
```

#### E. Test Locally with AWS SAM CLI (Optional)
If Docker is running on your development machine, invoke API Gateway and Lambda functions locally with layers mounted:
```sh
# Generate CloudFormation template
cdk synth --no-staging > template.yaml

# Start local API Gateway emulator
sam local start-api -t template.yaml

# In a separate terminal, test the local endpoint:
curl -s http://127.0.0.1:3000/products | jq .
```

---

### Test Suite Coverage (138 Passing Tests)

| Subfolder | Test Module | Coverage Area | Status |
| :--- | :--- | :--- | :--- |
| **`tests/unit/async_processing/`** | `test_sqs_order_queue.py` | Order queue & DLQ creation, redrive policy, SQS producer attributes | **Passed** |
| | `test_order_processor.py` | SQS batch handler, 4-step workflow, compensating refunds, Moto DynamoDB inventory | **Passed** |
| | `test_sqs_monitoring.py` | SQS queue attributes, CloudWatch queue depth metrics, scale up/down recommendations | **Passed** |
| | `test_sns_notifications.py` | Topic delivery policies, multi-protocol JSON confirmations, `FilterPolicy`, alerts | **Passed** |
| | `test_async_workflow_handlers.py` | SQS/SNS Lambda handlers, reverse-order rollback, event source mappings | **Passed** |
| | `test_eventbridge_routing.py` | Custom event buses, `put_events`, FIFO targets, numeric/nested/exists pattern matching | **Passed** |
| | `test_eventbridge_workflows.py` | EventBridge inventory/SNS/analytics handlers, `RetryPolicy`, DLQ triage & dashboard | **Passed** |
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
| **`tests/unit/resilience/`** | `test_circuit_breaker.py` | Circuit breaker 3-state state machine, timeout alias, `process_payment` integration | **Passed** |
| | `test_retry_utils.py` | Exponential backoff, jitter, direct runner, `get_shipping_rate`, `RetryPolicyManager` | **Passed** |
| | `test_graceful_degradation.py` | Order processing resilience, critical payment abort, degraded fallbacks & SQS triage | **Passed** |
| | `test_resilient_service.py` | `ResilientExternalService` unified orchestration, fast fail, fallbacks, Lambda handler | **Passed** |
| | `test_dlq_processor.py` | Asynchronous DLQ message triage, timeout/rate-limit classification | **Passed** |

---

### 2. Real AWS Cloud Testing & Verification

Follow these steps to deploy and test the layers, functions, and resilience behavior on your real AWS account:

#### Step 1: Deploy the CDK Stack & Configure Lambda Environment Variables
```sh
cd 08_adding_asynchronous_processing/product-api
source .venv/bin/activate

# Deploy the stack to AWS
cdk deploy ProductApiStack
```
Note the `ProductApiEndpoint` URL output at the end of the deployment. When deploying Lambda functions that consume SNS topic ARNs (`order_processor_handler`, `inventory_monitor_handler`), set their environment variables:
```sh
aws lambda update-function-configuration \
    --function-name <your-function-name> \
    --environment "Variables={CUSTOMER_NOTIFICATION_TOPIC=<topic-arn>,SYSTEM_ALERT_TOPIC=<topic-arn>,INVENTORY_ALERT_TOPIC=<topic-arn>}"
```

#### Step 2: Verify Attached Layers on Deployed Lambda Functions
Confirm via AWS CLI that both `ProductUtilitiesLayer` and `PydanticLayer` are attached to your deployed Lambda functions:
```sh
aws lambda get-function-configuration \
    --function-name $(aws lambda list-functions --query "Functions[?contains(FunctionName, 'GetProduct')].FunctionName" --output text) \
    --query "Layers[*].Arn" \
    --output table
```
You should see ARNs for both layers listed under the function configuration.

#### Step 3: Test API Endpoints & Layer Execution on AWS
Send requests to your API Gateway to verify that the functions execute with layer-provided validation and response formatting:

```sh
# 1. Export API Gateway base URL
export API_URL=$(aws cloudformation describe-stacks \
  --stack-name ProductApiStack \
  --query "Stacks[0].Outputs[?OutputKey=='ProductsApiUrl'].OutputValue" \
  --output text)

echo "API_URL: $API_URL"

# 2. Test POST /products (exercises product_validator & response_formatter from layer)
CREATE_RESP=$(curl -s -X POST "$API_URL/products" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Cloud Resilience Keyboard",
    "price": 179.99,
    "category": "Electronics",
    "description": "Ergonomic mechanical keyboard with resilient switches"
  }')

echo "$CREATE_RESP" | jq .

# Export the auto-assigned product ID (.id is top-level in response)
export PRODUCT_ID=$(echo "$CREATE_RESP" | jq -r '.id')
echo "Created Product ID: $PRODUCT_ID"

# 3. Test GET /products/{id} (exercises database_helper retry logic & layer formatting)
curl -s "$API_URL/products/$PRODUCT_ID" | jq .

# 4. Test validation failure (verifies layer returns HTTP 400 with contextual suggestions)
curl -s -X POST "$API_URL/products" \
  -H "Content-Type: application/json" \
  -d '{"title": "Broken", "price": -10, "category": "InvalidCat"}' | jq .
```

#### Step 4: Verify Resilience & CloudWatch Telemetry
Inspect CloudWatch Logs and custom metrics to observe layer execution, retries, and circuit breaker metrics:
```sh
# View recent execution logs for GetProduct
aws logs tail "/aws/lambda/$(aws lambda list-functions --query "Functions[?contains(FunctionName, 'GetProduct')].FunctionName" --output text)" --follow

# Check CloudWatch custom metrics emitted by Circuit Breakers
aws cloudwatch list-metrics --namespace "ProductAPI/CircuitBreakers"
```

---

## 🔄 Layer Versioning & Rollback Strategies

Lambda layers are immutable resources identified by version numbers (`:1`, `:2`, etc.).

### 1. Publishing a New Layer Version via AWS CLI
```sh
# 1. Package the layer code
cd layers/product_utilities
zip -r product-utilities-layer.zip python/

# 2. Publish new version to AWS Lambda
NEW_LAYER_ARN=$(aws lambda publish-layer-version \
    --layer-name product-utilities \
    --description "v1.1.0 - Updated validation rules" \
    --zip-file fileb://product-utilities-layer.zip \
    --compatible-runtimes python3.13 \
    --query "LayerVersionArn" --output text)

echo "Published Layer: $NEW_LAYER_ARN"
```

### 2. Instant Rollback Without Function Redeployment
If an update causes issues, functions can instantly be rolled back to a previous known-good layer version:

```sh
# Roll back a single function to Layer Version 1
FUNC_NAME=$(aws lambda list-functions --query "Functions[?contains(FunctionName, 'GetProduct')].FunctionName" --output text)

aws lambda update-function-configuration \
    --function-name "$FUNC_NAME" \
    --layers $(aws lambda list-layer-versions --layer-name product-utilities --query "LayerVersions[-1].LayerVersionArn" --output text)

# Batch rollback multiple functions
for func in GetProduct QueryProducts InsertProduct UpdateProduct; do
    REAL_FUNC=$(aws lambda list-functions --query "Functions[?contains(FunctionName, '$func')].FunctionName" --output text)
    aws lambda update-function-configuration \
        --function-name "$REAL_FUNC" \
        --layers arn:aws:lambda:ap-southeast-2:189053741578:layer:ProductUtilitiesLayer:1
done
```

---

## 🧹 Clean Up

### 1. Empty the S3 Media Bucket
CloudFormation cannot delete an S3 bucket if it contains objects or object versions:

```sh
# Discover and empty the media bucket
BUCKET_NAME=$(aws cloudformation describe-stacks \
  --stack-name ProductApiStack \
  --query "Stacks[0].Outputs[?contains(OutputKey, 'Bucket')].OutputValue" \
  --output text 2>/dev/null)

if [ -n "$BUCKET_NAME" ] && [ "$BUCKET_NAME" != "None" ]; then
    echo "Emptying S3 bucket: $BUCKET_NAME"
    aws s3 rm "s3://$BUCKET_NAME" --recursive
fi
```

### 2. Destroy CloudFormation stack
```sh 
cdk destroy ProductApiStack
```

### 3. Delete Manually Published Layer Versions
If you published manual layer versions via `aws lambda publish-layer-version` during the versioning walkthrough, delete them since they exist outside the CDK CloudFormation stack:

```sh
for version in $(aws lambda list-layer-versions --layer-name product-utilities --query "LayerVersions[*].Version" --output text 2>/dev/null); do
    echo "Deleting manual layer version: $version"
    aws lambda delete-layer-version --layer-name product-utilities --version-number "$version"
done
```

### 4. Delete Standalone SQS Queues, SNS Topics & EventBridge Resources (If Created Manually)
If you ran `create_order_processing_queue()`, `create_notification_topics()`, `create_event_buses()`, `setup_event_error_handling()`, or `create_event_monitoring_dashboard()` directly via `boto3`, clean up those standalone resources:

```sh
# Delete SQS queues
for q_name in order-processing-queue order-processing-dlq eventbridge-failed-events-dlq; do
    Q_URL=$(aws sqs get-queue-url --queue-name "$q_name" --query "QueueUrl" --output text 2>/dev/null)
    if [ -n "$Q_URL" ] && [ "$Q_URL" != "None" ]; then
        aws sqs delete-queue --queue-url "$Q_URL"
    fi
done

# Delete SNS topics
for topic_arn in $(aws sns list-topics --query "Topics[?contains(TopicArn, 'customer-notifications') || contains(TopicArn, 'system-alerts') || contains(TopicArn, 'inventory-alerts')].TopicArn" --output text 2>/dev/null); do
    aws sns delete-topic --topic-arn "$topic_arn"
done

# Delete custom EventBridge event buses (remove rules/targets first if attached)
for bus in online-store-orders online-store-inventory online-store-customers; do
    aws events delete-event-bus --name "$bus" 2>/dev/null || true
done

# Delete CloudWatch monitoring dashboard
aws cloudwatch delete-dashboards --dashboard-names EventDrivenArchitecture-Monitoring 2>/dev/null || true
```

---

## ⏭️ Next Step

Proceed to **[Module 09: ](../09_/README.md)** to learn how to address the responsiveness challenges that prevent your API from handling real-world e-commerce demands.