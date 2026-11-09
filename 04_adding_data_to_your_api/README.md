# Project Setup
## Initialize project using CDK
```sh
mkdir product-api && cd product-api
cdk init app --language python

# Activate the project's virtual environment
source .venv/bin/activate                 # macOS/Linux
# .venv\Scripts\Activate.ps1             # Windows PowerShell

pip install -r requirements.txt
mkdir lambda_code
```

# Lambda Function Deployment
## Prerequsites
```sh
# Check AWS credentials, and confirm the Account field is the account you intend to deploy to
aws sts get-caller-identity

# If not logged in to aws
aws login

# Check CDK version
cdk --version

# Verify you are in the project directory
ls cdk.json
```

## Bootstrap AWS CDK(first time only)
```sh
# Navigate to project directory
cd product-api

# Bootstrap AWS CDK, naming the account and Region explicitly
cdk bootstrap aws://ACCOUNT-NUMBER/REGION

# For example:
#   cdk bootstrap aws://123456789012/us-east-1

# Expected output:
#   Bootstrapping environment aws://123456789012/us-east-1...
#   Environment aws://123456789012/us-east-1 bootstrapped.
```

## Synthesize the template
```sh
# Generate CloudFormation template
cdk synth ProductApiStack

# This creates a template in cdk.out/ directory
# Review the template to understand what resources will be created
```

## Deploy the API stack
```sh
# Deploy the stack
cdk deploy ProductApiStack

# CDK will display:
# - Resources to be created/updated/deleted
# - IAM policy changes (if any)
# - Estimated costs (if significant)

# Type 'y' to confirm deployment

# Copy the ProductsApiUrl from the output above
API_URL="https://abc123def4.execute-api.us-east-1.amazonaws.com/dev"
```

# Testing
```sh
# Replace with your actual API URL from deployment output
API_URL="https://<api-id>.execute-api.<region>.amazonaws.com/dev"

# Test 1: List all products (should work)
curl "$API_URL/products"

# Test 2: Get specific product (should work)
curl "$API_URL/products/prod_001"

# Test 3: Filter by category (should work)
curl "$API_URL/products?category=Electronics"

# Test 4: CORS preflight (should work)
curl -X OPTIONS "$API_URL/products" -v

# Test 5: Create product (returns NotImplementedError)
curl -X POST "$API_URL/products" \
  -H "Content-Type: application/json" \
  -d '{"name": "New Product", "price": 99.99}'

# Test 6: Update product (returns NotImplementedError)
curl -X PUT "$API_URL/products/prod_001" \
-H "Content-Type: application/json" \
-d '{"name": "Updated Product", "price": 149.99}'
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