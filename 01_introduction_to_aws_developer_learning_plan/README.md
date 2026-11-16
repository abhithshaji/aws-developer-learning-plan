# 📦 Module 01: Introduction to AWS Developer Learning Plan

Welcome to the **AWS Developer Learning Plan** companion repository. This module sets up your local development environment and pre-provisions foundational AWS cloud resources used across all subsequent modules in this course.

---

## 📌 Overview

Throughout this learning plan, you will build, test, secure, and optimize a serverless e-commerce product service. Rather than repeatedly creating and tearing down disparate test databases, this module provisions a shared suite of resources:

- **5 Amazon DynamoDB Tables**: Supports the product catalog, customer records, order tracking, and analytics logs.
- **1 Amazon S3 Bucket**: Stores product media assets and course artifacts.
- **Initial Seed Data**: Populates sample products, customers, and orders so that read and query operations work immediately in later modules.

> [!NOTE]
> **Zero Idle Cost Architecture**: All DynamoDB tables are provisioned with on-demand capacity (`PAY_PER_REQUEST`). When no requests are being processed, idle tables cost **\$0.00**. Similarly, an S3 bucket with a few kilobytes of seed data incurs virtually no cost. You can leave these resources active while working through the learning plan.

---

## 🛠️ Environment Verification

Before provisioning AWS resources, verify that your local development tools and AWS authentication are properly configured.

### 1. Verify AWS CLI Credentials
Ensure your CLI is authenticated against your target AWS account:
```sh
aws sts get-caller-identity
```
*Expected output: A JSON object displaying your `UserId`, `Account`, and `Arn`.*

### 2. Verify AWS CDK CLI
Ensure the AWS Cloud Development Kit (CDK) CLI is installed:
```sh
cdk --version
```
*Expected output: `2.x.x (build ...)` or newer.*

### 3. Verify Python & Pip
Verify that Python (3.11+ recommended) and `pip` are accessible:
```sh
python3 --version
pip --version
```

---

## ⚙️ Regional Configuration

To avoid routing errors and resource fragmentation, pick a single AWS Region for the entire learning plan. Set these environment variables in your terminal session:

```sh
# Set the primary region (change if you prefer another region, e.g., us-west-2, eu-west-1)
export AWS_REGION="us-east-1"
export AWS_DEFAULT_REGION="$AWS_REGION"
```

---

## 🚀 Provisioning Practice Resources

### 1. Create DynamoDB Tables

Run the following commands to create the 5 foundational DynamoDB tables:

```sh
# 1. Product Catalog (Used in Modules 03, 04, 05 and performance modules)
# Includes a Global Secondary Index (GSI) on 'category' to support category filtering
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

# 2. Customer Records (Used in data masking and privacy exercises)
aws dynamodb create-table \
    --table-name Customers \
    --attribute-definitions AttributeName=customer_id,AttributeType=S \
    --key-schema AttributeName=customer_id,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST

# 3. Customer Orders (Used in authorization and transactional workflows)
aws dynamodb create-table \
    --table-name Orders \
    --attribute-definitions AttributeName=customer_id,AttributeType=S AttributeName=order_id,AttributeType=S \
    --key-schema AttributeName=customer_id,KeyType=HASH AttributeName=order_id,KeyType=RANGE \
    --billing-mode PAY_PER_REQUEST

# 4. Analytics Events (Used in event-driven asynchronous architectures)
aws dynamodb create-table \
    --table-name AnalyticsEvents \
    --attribute-definitions AttributeName=event_id,AttributeType=S \
    --key-schema AttributeName=event_id,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST

# 5. Customer Analytics (Used in IAM role assumption and cross-account analytics)
aws dynamodb create-table \
    --table-name CustomerAnalytics \
    --attribute-definitions AttributeName=customer_id,AttributeType=S \
    --key-schema AttributeName=customer_id,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST

# Wait until all tables transition to ACTIVE status
echo "Waiting for tables to become ACTIVE..."
for table in Products Customers Orders AnalyticsEvents CustomerAnalytics; do
    aws dynamodb wait table-exists --table-name $table
done
echo "All DynamoDB tables are ready."
```

#### Table Schema Summary

| Table Name | Partition Key (HASH) | Sort Key (RANGE) | Secondary Indexes | Primary Purpose |
| :--- | :--- | :--- | :--- | :--- |
| `Products` | `id` (String) | *None* | `category-index` (HASH: `category`) | Product catalog, queries, and mutations |
| `Customers` | `customer_id` (String) | *None* | *None* | Customer PII & data masking |
| `Orders` | `customer_id` (String) | `order_id` (String) | *None* | Multi-attribute query & authorization |
| `AnalyticsEvents` | `event_id` (String) | *None* | *None* | Asynchronous event logging |
| `CustomerAnalytics` | `customer_id` (String) | *None* | *None* | Aggregated metrics & IAM delegation |

---

### 2. Create the Amazon S3 Bucket

S3 bucket names are globally unique across all AWS accounts. We construct a predictable bucket name by appending your 12-digit AWS account ID:

```sh
# Resolve current AWS region and account ID
REGION="${AWS_REGION:-$(aws configure get region)}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export COURSE_BUCKET="online-store-assets-${ACCOUNT_ID}"

# Create bucket (us-east-1 does not require LocationConstraint)
if [ "$REGION" = "us-east-1" ]; then
    aws s3api create-bucket --bucket "$COURSE_BUCKET"
else
    aws s3api create-bucket --bucket "$COURSE_BUCKET" \
        --create-bucket-configuration LocationConstraint="$REGION"
fi

echo "Created course bucket: $COURSE_BUCKET (Region: $REGION)"
```

---

## 📥 Seed Initial Data

Populate the tables with sample records so you can verify queries in later modules:

```sh
# 1. Seed Product Catalog
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

# 2. Seed Customer Record
aws dynamodb put-item --table-name Customers --item '{
  "customer_id": {"S": "cust_001"}, "name": {"S": "Jordan Smith"},
  "email": {"S": "jordan.smith@example.com"}, "phone": {"S": "206-555-0142"},
  "address": {"S": "2021 7th Ave, Seattle, WA 98121"}
}'

# 3. Seed Customer Orders
aws dynamodb put-item --table-name Orders --item '{
  "customer_id": {"S": "cust_001"}, "order_id": {"S": "ord_1001"},
  "status": {"S": "shipped"}, "total_amount": {"N": "212.98"}
}'

aws dynamodb put-item --table-name Orders --item '{
  "customer_id": {"S": "cust_001"}, "order_id": {"S": "ord_1002"},
  "status": {"S": "processing"}, "total_amount": {"N": "8.49"}
}'

# 4. Seed Analytics Summary
aws dynamodb put-item --table-name CustomerAnalytics --item '{
  "customer_id": {"S": "cust_001"}, "orders_placed": {"N": "2"},
  "lifetime_value": {"N": "221.47"}
}'

echo "Sample data successfully seeded."
```

---

## 🔍 Verification

Verify that all tables are active, seeded with records, and the S3 bucket exists:

```sh
# 1. Verify Table Statuses (All must report 'ACTIVE')
for table in Products Customers Orders AnalyticsEvents CustomerAnalytics; do
    echo "$table: $(aws dynamodb describe-table --table-name $table \
        --query 'Table.TableStatus' --output text)"
done

# 2. Verify Product Item Count (Must report 3)
aws dynamodb scan --table-name Products --select COUNT --query Count

# 3. Verify S3 Bucket Presence
aws s3 ls | grep online-store-assets
```

---

## 🧹 Cleanup (When Finished with Course)

> [!IMPORTANT]
> **Do not delete these resources yet** if you intend to continue with subsequent modules. Run this cleanup only when you have completed all modules in the learning plan.

```sh
# 1. Delete all 5 DynamoDB tables
for table in Products Customers Orders AnalyticsEvents CustomerAnalytics; do
    aws dynamodb delete-table --table-name $table
    echo "Deleted DynamoDB table: $table"
done

# 2. Empty and delete the S3 bucket
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
BUCKET="${COURSE_BUCKET:-online-store-assets-${ACCOUNT_ID}}"

aws s3 rm "s3://$BUCKET" --recursive
aws s3api delete-bucket --bucket "$BUCKET"
echo "Emptied and deleted S3 bucket: $BUCKET"
```

---

## ⏭️ Next Step

Proceed to **[Module 02: Introduction to Being an AWS Developer](../02_introduction_to_being_an_aws_developer/README.md)** to learn cloud naming conventions, global vs. regional resource considerations, and multi-developer namespace isolation.
