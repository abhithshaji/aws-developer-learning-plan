# Environment verification

1. AWS CLI configuration test:
`aws sts get-caller-identity`
2. AWS CDK test:
`cdk --version`
3. Pip test:
`pip --version`


# Provisioning your practice resources

Every resource here uses on-demand pricing, so an idle table costs nothing while you work through the plan. A cleanup section at the end of this topic removes everything.

## Create the DynamoDB tables
```sh
# Use one Region for the whole learning plan. Run these two lines in each new
# terminal session you use, changing the Region if you prefer another one.
export AWS_REGION="us-east-1"
export AWS_DEFAULT_REGION="$AWS_REGION"

# Product catalog, used from the first API module onward. The category-index
# secondary index supports the category queries in the data and performance modules.
aws dynamodb create-table \
    --table-name Products \
    --attribute-definitions AttributeName=id,AttributeType=S AttributeName=category,AttributeType=S \
    --key-schema AttributeName=id,KeyType=HASH \
    --global-secondary-indexes '[{
        "IndexName": "category-index",
        "KeySchema": [{"AttributeName": "category", "KeyType": "HASH"}],
        "Projection": {"ProjectionType": "ALL"}
    }]' \
    --billing-mode PAY_PER_REQUEST

# Customer records, used by the data masking examples
aws dynamodb create-table \
    --table-name Customers \
    --attribute-definitions AttributeName=customer_id,AttributeType=S \
    --key-schema AttributeName=customer_id,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST

# Customer orders, used by the authorization examples
aws dynamodb create-table \
    --table-name Orders \
    --attribute-definitions AttributeName=customer_id,AttributeType=S AttributeName=order_id,AttributeType=S \
    --key-schema AttributeName=customer_id,KeyType=HASH AttributeName=order_id,KeyType=RANGE \
    --billing-mode PAY_PER_REQUEST

# Event log, used by the event-driven workflow examples
aws dynamodb create-table \
    --table-name AnalyticsEvents \
    --attribute-definitions AttributeName=event_id,AttributeType=S \
    --key-schema AttributeName=event_id,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST

# Per-customer analytics, used by the role assumption examples
aws dynamodb create-table \
    --table-name CustomerAnalytics \
    --attribute-definitions AttributeName=customer_id,AttributeType=S \
    --key-schema AttributeName=customer_id,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST

# Wait until all five tables are ready
for table in Products Customers Orders AnalyticsEvents CustomerAnalytics; do
    aws dynamodb wait table-exists --table-name $table
done
```

## Create the Amazon S3 bucket
```sh
# Use the Region from this session, or fall back to your configured Region
REGION="${AWS_REGION:-$(aws configure get region)}"

# Amazon S3 bucket names are globally unique, so include your account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export COURSE_BUCKET="online-store-assets-${ACCOUNT_ID}"

# The us-east-1 Region must omit the location constraint
if [ "$REGION" = "us-east-1" ]; then
    aws s3api create-bucket --bucket "$COURSE_BUCKET"
else
    aws s3api create-bucket --bucket "$COURSE_BUCKET" \
        --create-bucket-configuration LocationConstraint="$REGION"
fi

echo "Your course bucket: $COURSE_BUCKET (Region: $REGION)"
```

## Add sample data
```sh
# Three products for the catalog examples. The data modules store the display
# name in a title attribute, so the seed data uses title too.
aws dynamodb put-item --table-name Products --item '{
  "id": {"S": "prod_001"}, "title": {"S": "Wireless Headphones"},
  "price": {"N": "199.99"}, "category": {"S": "Electronics"},
  "description": {"S": "Over-ear headphones with active noise cancellation"}
}'

aws dynamodb put-item --table-name Products --item '{
  "id": {"S": "prod_002"}, "title": {"S": "USB-C Cable"},
  "price": {"N": "12.99"}, "category": {"S": "Electronics"},
  "description": {"S": "Two meter braided charging cable"}
}'

aws dynamodb put-item --table-name Products --item '{
  "id": {"S": "prod_003"}, "title": {"S": "Ceramic Mug"},
  "price": {"N": "8.49"}, "category": {"S": "Home Goods"},
  "description": {"S": "Twelve ounce stoneware mug"}
}'

# A customer record for the data masking examples
aws dynamodb put-item --table-name Customers --item '{
  "customer_id": {"S": "cust_001"}, "name": {"S": "Jordan Smith"},
  "email": {"S": "jordan.smith@example.com"}, "phone": {"S": "206-555-0142"},
  "address": {"S": "2021 7th Ave, Seattle, WA 98121"}
}'

# Two orders for that customer
aws dynamodb put-item --table-name Orders --item '{
  "customer_id": {"S": "cust_001"}, "order_id": {"S": "ord_1001"},
  "status": {"S": "shipped"}, "total_amount": {"N": "212.98"}
}'

aws dynamodb put-item --table-name Orders --item '{
  "customer_id": {"S": "cust_001"}, "order_id": {"S": "ord_1002"},
  "status": {"S": "processing"}, "total_amount": {"N": "8.49"}
}'

# An analytics summary for the role assumption examples
aws dynamodb put-item --table-name CustomerAnalytics --item '{
  "customer_id": {"S": "cust_001"}, "orders_placed": {"N": "2"},
  "lifetime_value": {"N": "221.47"}
}'
```

## Verify your resources
```sh
# All five tables should report ACTIVE
for table in Products Customers Orders AnalyticsEvents CustomerAnalytics; do
    echo "$table: $(aws dynamodb describe-table --table-name $table \
        --query 'Table.TableStatus' --output text)"
done

# The product catalog should contain three items
aws dynamodb scan --table-name Products --select COUNT --query Count

# Your bucket should appear in the list
aws s3 ls | grep online-store-assets
```

## Clean Up
```sh
# Delete the five tables
for table in Products Customers Orders AnalyticsEvents CustomerAnalytics; do
    aws dynamodb delete-table --table-name $table
done

# Empty the bucket, then delete it
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
BUCKET="${COURSE_BUCKET:-online-store-assets-${ACCOUNT_ID}}"
aws s3 rm "s3://$BUCKET" --recursive
aws s3api delete-bucket --bucket "$BUCKET"
```
Also delete the stacks and resources each module creates. Every module that deploys infrastructure ends with its own cleanup step.

