# 📦 Module 03: Building Your First Serverless API

In this module, you build and deploy your first serverless microservice using the **AWS Cloud Development Kit (CDK)** with Python. You will create a RESTful API with **Amazon API Gateway** backed by **AWS Lambda** functions running Python 3.13.

---

## 📌 Overview

To establish clean architectural boundaries, this module focuses strictly on API contract design, request routing, path parameters, query string handling, CORS headers, and Infrastructure as Code (IaC) deployment workflows. 

At this stage, data is managed by an in-memory mock catalog (`catalog.py`). This allows you to verify API Gateway integrations and Lambda handlers before introducing database connectivity and request validation in **Module 04**.

---

## 🏛️ Architecture & Routing

```
                          Client (curl / browser)
                                     │
                                     ▼
                     Amazon API Gateway (REST API)
                             Stage: /dev
                                     │
        ┌────────────────────────────┼────────────────────────────┐
        │                            │                            │
   GET /products               POST /products               OPTIONS *
   (QueryProducts)             (InsertProduct)              (Options)
        │                            │                            │
        │ [200 OK]                   │ [501 Not Implemented]      │ [CORS Headers]
        │                            │                            │
        ▼                            ▼                            ▼
  ┌───────────┐                ┌───────────┐                ┌───────────┐
  │  Lambda   │                │  Lambda   │                │  Lambda   │
  └─────┬─────┘                └─────┬─────┘                └─────┬─────┘
        │                            │                            │
        └────────────────────────────┼────────────────────────────┘
                                     │
                                     ▼
        ┌─────────────────────────────────────────────────────────┐
        │        In-Memory Mock Catalog (catalog.py)              │
        │  • prod_001: Wireless Headphones ($199.99, Electronics) │
        │  • prod_002: USB-C Cable ($12.99, Electronics)          │
        │  • prod_003: Ceramic Mug ($8.49, Home Goods)            │
        └─────────────────────────────────────────────────────────┘
```

### Route Matrix

| HTTP Method | Resource Path | Lambda Handler | Status in Module 03 |
| :--- | :--- | :--- | :--- |
| `GET` | `/products` | `query_products.handler` | **Active**: Returns all products or filters by `?category=...` |
| `POST` | `/products` | `insert_product.handler` | **Stub**: Returns `501 NotImplementedError` (implemented in Mod 04) |
| `OPTIONS` | `/products` | `options.handler` | **Active**: Returns CORS headers (`Allow-Origin: *`, Methods, Headers) |
| `GET` | `/products/{id}` | `get_product.handler` | **Active**: Returns product by ID or `404 Not Found` |
| `PUT` | `/products/{id}` | `update_product.handler` | **Stub**: Returns `501 NotImplementedError` (implemented in Mod 04) |
| `OPTIONS` | `/products/{id}` | `options.handler` | **Active**: Returns CORS headers |

---

## 📂 Project Directory Structure

```text
03_building_your_first_serverless_api/
└── product-api/
    ├── app.py                         # CDK application entry point
    ├── cdk.json                       # CDK execution configuration
    ├── requirements.txt               # CDK framework dependencies
    ├── requirements-dev.txt           # Test runner dependencies (pytest)
    ├── product_api/
    │   ├── __init__.py
    │   └── product_api_stack.py       # CloudFormation stack: Lambda & API Gateway
    ├── lambda_code/
    │   ├── catalog.py                 # In-memory mock data store & response helpers
    │   ├── get_product.py             # GET /products/{id} handler
    │   ├── query_products.py          # GET /products handler (with category filtering)
    │   ├── insert_product.py          # POST /products handler (501 stub)
    │   ├── update_product.py          # PUT /products/{id} handler (501 stub)
    │   └── options.py                 # OPTIONS handler for CORS preflight
    └── tests/
        └── unit/
            └── test_product_api_stack.py # CDK assertion tests
```

---

## 🛠️ Installations & Setup

### 1. Initialize Virtual Environment & Install Dependencies
Navigate into the `product-api` directory:

```sh
cd 03_building_your_first_serverless_api/product-api

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate                 # macOS/Linux
# .venv\Scripts\Activate.ps1             # Windows PowerShell

# Install dependencies
pip install -r requirements.txt
```

Your `requirements.txt` should contain:
```text
aws-cdk-lib>=2.275.0,<3.0.0
constructs>=10.5.0,<11.0.0
```

---

## 🚀 Deployment Workflow

### 1. Verify Prerequisites
Confirm your AWS CLI identity and CDK CLI version:
```sh
# Check caller identity
aws sts get-caller-identity

# Check CDK version
cdk --version

# Confirm you are in the directory containing cdk.json
ls cdk.json
```

### 2. Bootstrap AWS CDK Environment (One-time setup per Region)
If you have never deployed AWS CDK in this account and Region, provision the CDK bootstrap stack (creates an S3 bucket and ECR repository for deployment assets):

```sh
# Set target region
export AWS_REGION="us-east-1"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Bootstrap CDK
cdk bootstrap aws://${ACCOUNT_ID}/${AWS_REGION}
```

### 3. Synthesize CloudFormation Template
Synthesize the CDK app to compile your Python definitions into a CloudFormation template:

```sh
cdk synth ProductApiStack
```
*This validates your stack definitions and outputs the compiled template to `cdk.out/ProductApiStack.template.json`.*

### 4. Deploy the Stack
Deploy the stack to your AWS account:

```sh
cdk deploy ProductApiStack
```

During deployment:
1. CDK displays the IAM permissions created for the Lambda execution roles.
2. Type `y` when prompted to approve the security changes.
3. Once finished, CDK outputs the live API Gateway endpoint:

```text
Outputs:
ProductApiStack.ProductsApiUrl = https://abc123def4.execute-api.us-east-1.amazonaws.com/dev/
```

Store this endpoint in a shell variable for testing:
```sh
export API_URL="https://<api-id>.execute-api.<region>.amazonaws.com/dev"
```

---

## 🧪 API Verification & Testing

Execute the following `curl` commands to test each route against your live API Gateway deployment:

### 1. List All Products
```sh
curl -s "$API_URL/products" | jq .
```
**Expected Response (`200 OK`):**
```json
[
  {"id": "prod_001", "name": "Wireless Headphones", "price": 199.99, "category": "Electronics"},
  {"id": "prod_002", "name": "USB-C Cable", "price": 12.99, "category": "Electronics"},
  {"id": "prod_003", "name": "Ceramic Mug", "price": 8.49, "category": "Home Goods"}
]
```

### 2. Get Product by ID
```sh
curl -s "$API_URL/products/prod_001" | jq .
```
**Expected Response (`200 OK`):**
```json
{
  "id": "prod_001",
  "name": "Wireless Headphones",
  "price": 199.99,
  "category": "Electronics"
}
```

If you query a non-existent product:
```sh
curl -s -i "$API_URL/products/prod_999"
```
**Expected Response (`404 Not Found`):**
```json
{"error": "Product not found"}
```

### 3. Filter Products by Category
```sh
curl -s "$API_URL/products?category=Electronics" | jq .
```
**Expected Response (`200 OK`):**
```json
[
  {"id": "prod_001", "name": "Wireless Headphones", "price": 199.99, "category": "Electronics"},
  {"id": "prod_002", "name": "USB-C Cable", "price": 12.99, "category": "Electronics"}
]
```

### 4. Test CORS Preflight Request
```sh
curl -X OPTIONS "$API_URL/products" -v
```
**Expected Headers in Response (`200 OK`):**
```text
< HTTP/1.1 200 OK
< access-control-allow-origin: *
< access-control-allow-methods: GET, POST, PUT, DELETE, OPTIONS
< access-control-allow-headers: Content-Type, Authorization
```

### 5. Verify Unimplemented Write Endpoints
```sh
# Attempt to create product (POST)
curl -s -i -X POST "$API_URL/products" \
  -H "Content-Type: application/json" \
  -d '{"name": "New Product", "price": 99.99}'
```
**Expected Response (`501 Not Implemented`):**
```json
{"error": "insert_product is not implemented yet"}
```

```sh
# Attempt to update product (PUT)
curl -s -i -X PUT "$API_URL/products/prod_001" \
  -H "Content-Type: application/json" \
  -d '{"name": "Updated Product", "price": 149.99}'
```
**Expected Response (`501 Not Implemented`):**
```json
{"error": "update_product is not implemented yet"}
```

---

## 🧹 Clean Up

To delete the API Gateway and Lambda functions created by this module:

```sh
# Destroy the CloudFormation stack
cdk destroy ProductApiStack

# Confirm deletion
aws cloudformation describe-stacks --stack-name ProductApiStack
# Output should report ValidationError: Stack with id ProductApiStack does not exist
```

---

## ⏭️ Next Step

Proceed to **[Module 04: Adding Data to Your API](../04_adding_data_to_your_api/README.md)**, where we replace the mock `catalog.py` with real **Amazon DynamoDB** operations, implement payload validation with **Pydantic**, and package dependencies using **Lambda Layers**.
