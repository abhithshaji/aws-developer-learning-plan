# Installtions & Configurations
```sh
# Activate the project's virtual environment
source .venv/bin/activate                 # macOS/Linux
# .venv\Scripts\Activate.ps1             # Windows PowerShell

# Install Pydantic for schema validation
pip install pydantic

# Add Pydantic to requirements.txt
pydantic>=2.0.0

# package Pydantic into a lambda layer
mkdir -p layers/pydantic/python

pip install \
  --platform manylinux2014_x86_64 \
  --target layers/pydantic/python \
  --implementation cp \
  --python-version 3.13 \
  --only-binary=:all: \
  --no-cache-dir \
  pydantic

# Add to .gitignore
layers/
```

# Lambda Function Deployment
## Prerequsites
```sh
# Check AWS credentials, and confirm the Account field is the account you intend to deploy to
aws sts get-caller-identity

# If not logged in to aws
aws login

# Verify you are in the project directory
ls cdk.json
```

## Deploy the API stack
```sh
# Deploy the stack
cdk deploy ProductApiStack
```

# Testing
```sh
# Replace with your actual API URL from deployment output
API_URL="https://<api-id>.execute-api.<region>.amazonaws.com/dev"

# Test 1: Insert (create) product
curl -X POST "$API_URL/products" -H "Content-Type: application/json" -d '{"title": "Speaker", "price": 99.99, "category":"Electronics","description":"Simple speaker of JBL"}'

# Test 2: List all products
curl "$API_URL/products"

# Test 3: Get specific product
curl "$API_URL/products/92b16f7b-a24c-4464-ad8a-06b2b8c5cb0a"

# Test 4: Filter by category 
curl "$API_URL/products?category=Electronics"

# Test 5: Update product
curl -X PUT "$API_URL/products/92b16f7b-a24c-4464-ad8a-06b2b8c5cb0a" \
-H "Content-Type: application/json" \
-d '{"title": "Speaker", "price": 2000, "category":"Electronics","description":"Simple speaker of JBL"}'
```

# Clean up
```sh
# Check existing stacks
cdk list

# Delete stack
cdk destroy ProductApiStack

# Confirm deletion 
aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE UPDATE_ROLLBACK_COMPLETE
```