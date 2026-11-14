# 📦 Module 05: Testing and Error Handling

## Installations
Add to requirements-dev.txt
```sh
pytest~=8.3
pytest-cov~=5.0
moto[dynamodb]~=5.0
boto3~=1.35
flake8~=7.1
mypy~=1.11
```

Install requirements-dev file
```sh
source .venv/bin/activate
pip install -r requirements-dev.txt
```

Pydantic Layers:
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

## Folder file creation
```sh

#create test files
mkdir -p tests/unit
touch tests/unit/test_get_product.py tests/unit/test_insert_product.py tests/unit/test_products_db.py 
touch tests/event_factory.py

#create event files
mkdir -p events
touch events/get-product-event.json events/insert-product-event.json
```

## Testing
### Unit
testing get_products:
```sh
pytest tests/unit/test_get_product.py -v

# run test with code coverage
pytest --cov=lambda_code --cov=db tests/unit/test_get_product.py
```

testing error_handling:
```sh
pytest tests/unit/test_error_handling.py -v
```

testing product_validation:
```sh
pytest tests/unit/test_product_validation.py -v
```

testing products_db:
```sh
pytest tests/unit/test_products_db.py -v
```

running all unit tests :
```sh
pytest tests/unit -v
```

## Testing with SAM CLI
### installation
use this doc - https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html

### testing
```sh
#synthesise
cdk synth # this creates the template.yaml file in cdk.out

#if you want local lambda to communicate with real dynamodb then login to aws
aws login

sam local invoke InsertProduct \
  -t cdk.out/ProductApiStack.template.json \
  -e events/insert-product-event.json

sam local invoke GetProduct -t cdk.out/ProductApiStack.template.json -e events/get-product-event.json

#else if testing all locally then use dummy data
AWS_DEFAULT_REGION=us-east-1 AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test \
sam local invoke GetProduct -t cdk.out/ProductApiStack.template.json -e events/get-product-event.json
```

testing with Start a Local API Gateway Server
```sh
#SAM can spin up a local HTTP server emulating API Gateway on localhost:3000
sam local start-api -t cdk.out/ProductApiStack.template.json

# in seperate terminal
curl http://127.0.0.1:3000/products/prod_001

curl -X POST http://127.0.0.1:3000/products \
  -H "Content-Type: application/json" \
  -d '{"title": "Mechanical Keyboard", "price": 129.99, "category": "Electronics", "description": "Hot-swappable keyboard"}'
```