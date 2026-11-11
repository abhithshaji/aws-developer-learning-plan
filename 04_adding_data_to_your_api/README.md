# 📦 Module 04: Adding Data to Your API

In this module, we transition our API from the temporary in-memory mock catalog (`catalog.py` from Module 03) to persistent data storage using **Amazon DynamoDB**, and introduce request validation with **Pydantic**.

---

## 📌 Summary of Changes from Module 03

If you are coming from **Module 03**, here is what changed in this module:

1. **Persistent Storage (Amazon DynamoDB)**:
   - Added a `Products` table definition in CDK with `id` as partition key and on-demand billing (`PAY_PER_REQUEST`).
   - Added a Global Secondary Index (`category-index`) on `category` to support fast queries by category.
   - Granted read/write IAM permissions to Lambda functions (`grant_read_data`, `grant_read_write_data`).
2. **Modular Architecture**:
   - Replaced `catalog.py` with separate packages:
     - `db/products_db.py`: Boto3 interactions with DynamoDB (get, query, insert, update).
     - `db/product_schema.py`: Pydantic models for request validation (`ProductInput`, `ProductUpdate`).
     - `utils/response_utils.py`: Standardized API Gateway JSON response helpers (`create_success_response`, `create_error_response`) and Decimal serializer.
3. **Lambda Packaging & Asset Root**:
   - Changed Lambda code asset root in CDK from `"lambda_code"` to `"."` (project root) so handlers can import from sibling modules (`db`, `utils`).
   - Updated handler references to dotted module paths (e.g., `lambda_code.get_product.handler`).
4. **Pydantic & Lambda Layer**:
   - Handlers for `insert_product` and `update_product` use Pydantic for strict payload validation.
   - Because AWS Lambda standard runtimes do not bundle third-party packages like Pydantic, a **Lambda Layer** (`layers/pydantic`) is built and attached to functions that require it.

---

## 🛠️ Installations & Configurations

### 1. Activate Virtual Environment & Install Local Dependencies
```sh
# Navigate to the project directory
cd product-api

# Activate the virtual environment
source .venv/bin/activate                 # macOS/Linux
# .venv\Scripts\Activate.ps1             # Windows PowerShell

# Install requirements.txt libs
pip install -r requirements.txt
```

Ensure `pydantic>=2.0.0` is present in your `requirements.txt`:
```text
aws-cdk-lib>=2.275.0,<3.0.0
constructs>=10.5.0,<11.0.0
pydantic>=2.0.0
```

---

### 2. Package Pydantic into a Lambda Layer

> [!IMPORTANT]
> AWS Lambda runs on Amazon Linux with **Python 3.13** (as specified in CDK). Because Pydantic uses compiled C-extensions (`pydantic-core`), you must install wheels specifically compiled for `manylinux` and Python 3.13. Otherwise, Lambda will fail with `Runtime.ImportModuleError`.

Run the following commands inside `product-api/`:

```sh
# Create layer directory structure (Lambda requires packages in a 'python' folder)
mkdir -p layers/pydantic/python

# Install Linux x86_64 compatible wheels for Python 3.13
pip install \
  --platform manylinux2014_x86_64 \
  --target layers/pydantic/python \
  --implementation cp \
  --python-version 3.13 \
  --only-binary=:all: \
  --no-cache-dir \
  pydantic
```

#### Add Layers to `.gitignore`
To prevent committing large third-party binary packages to git, add `layers/` to your `.gitignore`:
```sh
echo "layers/" >> .gitignore
```

---

## 📂 Updated Project Structure

```text
product-api/
├── cdk.json
├── requirements.txt
├── .gitignore
├── layers/                           # (Git-ignored) Lambda layer dependencies
│   └── pydantic/
│       └── python/                   # Pydantic & dependencies for Lambda
├── product_api/
│   ├── __init__.py
│   └── product_api_stack.py          # DynamoDB table, GSI, Lambda layer & routes
├── db/
│   ├── __init__.py
│   ├── product_schema.py             # Pydantic validation schemas
│   └── products_db.py                # Boto3 DynamoDB data access functions
├── utils/
│   ├── __init__.py
│   └── response_utils.py             # Success/error response builders
└── lambda_code/
    ├── __init__.py
    ├── get_product.py                # GET /products/{id}
    ├── query_products.py             # GET /products & GET /products?category=...
    ├── insert_product.py             # POST /products (with Pydantic validation)
    ├── update_product.py             # PUT /products/{id} (with Pydantic validation)
    └── options.py                    # CORS preflight handler
```

---

## 🚀 Deployment

### 1. Prerequisites Check
```sh
# Verify AWS credentials and account
aws sts get-caller-identity

# Ensure you are inside the product-api directory
ls cdk.json
```

### 2. Deploy the Stack
```sh
cdk deploy ProductApiStack
```
*Note the `ProductsApiUrl` printed in the Outputs section upon completion.*

---

## 🧪 Testing the API

Set your deployed API endpoint in your terminal:
```sh
# Replace with your actual API URL from CDK deployment output
API_URL="https://<api-id>.execute-api.<region>.amazonaws.com/dev"
```

### Test 1: Insert (Create) a Product
```sh
curl -X POST "$API_URL/products" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Wireless Earbuds",
    "price": 99.99,
    "category": "Electronics",
    "description": "Noise-cancelling wireless earbuds"
  }'
```
*Copy the `id` returned in the JSON response for subsequent tests.*

### Test 2: List All Products
```sh
curl "$API_URL/products"
```

### Test 3: Get a Specific Product by ID
```sh
# Replace <PRODUCT_ID> with an existing ID
curl "$API_URL/products/<PRODUCT_ID>"
```

### Test 4: Filter Products by Category (GSI Query)
```sh
curl "$API_URL/products?category=Electronics"
```

### Test 5: Update a Product
```sh
curl -X PUT "$API_URL/products/<PRODUCT_ID>" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Wireless Earbuds Pro",
    "price": 129.99,
    "category": "Electronics",
    "description": "Upgraded wireless earbuds with spatial audio"
  }'
```

### Test 6: Verify Schema Validation (Expected 400 Bad Request)
Test that Pydantic rejects invalid input (e.g. negative price or missing fields):
```sh
curl -X POST "$API_URL/products" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Invalid Product",
    "price": -10.00,
    "category": "Electronics"
  }'
```

---

## 🧹 Cleanup

When finished practicing, clean up the resources to avoid any ongoing charges:

```sh
# Destroy all stack resources (API Gateway, Lambdas, DynamoDB table, Layer)
cdk destroy ProductApiStack

# Verify stack deletion status
aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE
```
