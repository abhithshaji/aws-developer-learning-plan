"""DynamoDB Database Helper Module (Shared Lambda Layer).

Manages connection, table interactions, CRUD operations, GSI category queries,
conditional writes, optimistic locking, and audit attributes.
"""
import os
import boto3
import boto3.dynamodb.conditions
from datetime import datetime, timezone
from botocore.exceptions import ClientError, BotoCoreError

try:
    from utils.retry_utils import retry_with_exponential_backoff, RetryableError
except ImportError:
    try:
        from retry_utils import retry_with_exponential_backoff, RetryableError
    except ImportError:
        def retry_with_exponential_backoff(*args, **kwargs):
            def decorator(func):
                return func
            return decorator
        class RetryableError(Exception):
            pass


table_name = os.environ.get('PRODUCT_TABLE', 'Products')
table = boto3.resource('dynamodb').Table(table_name)


@retry_with_exponential_backoff(max_retries=2, base_delay=0.5, max_delay=3)
def get_product(product_id):
    """Retrieve a single product by ID with retry logic."""
    try:
        return table.get_item(Key={'id': product_id}).get('Item')
    except (ClientError, BotoCoreError) as e:
        raise RetryableError(f"DynamoDB error reading product: {str(e)}")


def get_all_products():
    """Retrieve all products from the table."""
    return table.scan()['Items']


def get_products_by_category(category):
    """Retrieve products filtered by category using GSI."""
    return table.query(
        IndexName='category-index',
        KeyConditionExpression=boto3.dynamodb.conditions.Key('category').eq(category)
    ).get('Items')


def insert_product(item, user_arn):
    """Insert a new product into DynamoDB. Fails if product ID already exists."""
    timestamp = datetime.now(timezone.utc).isoformat()

    item['created_at'] = timestamp
    item['created_by'] = user_arn
    item['updated_at'] = timestamp
    item['updated_by'] = user_arn

    try:
        table.put_item(
            Item=item,
            ConditionExpression='attribute_not_exists(id)'
        )
        return item
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            raise ValueError(f"Product with id {item['id']} already exists")
        raise


def update_product(product_id, fields, user_arn):
    """Update an existing product. Fails if product doesn't exist."""
    timestamp = datetime.now(timezone.utc).isoformat()

    update_expression = """SET category = :category,
        title = :title,
        description = :description,
        price = :price,
        updated_at = :updated_at,
        updated_by = :updated_by"""

    expression_attribute_values = {
        ':category': fields['category'],
        ':title': fields['title'],
        ':description': fields['description'],
        ':price': fields['price'],
        ':updated_at': timestamp,
        ':updated_by': user_arn
    }

    try:
        response = table.update_item(
            Key={'id': product_id},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_attribute_values,
            ConditionExpression='attribute_exists(id)',
            ReturnValues='ALL_NEW'
        )
        return response['Attributes']
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            raise ValueError(f"Product with id {product_id} does not exist")
        raise


def update_product_with_version(product_id, fields, user_arn, expected_version):
    """Update product with optimistic locking using version number."""
    timestamp = datetime.now(timezone.utc).isoformat()
    new_version = expected_version + 1

    update_expression = """SET category = :category,
        title = :title,
        description = :description,
        price = :price,
        updated_at = :updated_at,
        updated_by = :updated_by,
        version = :new_version"""

    expression_attribute_values = {
        ':category': fields['category'],
        ':title': fields['title'],
        ':description': fields['description'],
        ':price': fields['price'],
        ':updated_at': timestamp,
        ':updated_by': user_arn,
        ':new_version': new_version,
        ':expected_version': expected_version
    }

    try:
        response = table.update_item(
            Key={'id': product_id},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_attribute_values,
            ConditionExpression='attribute_exists(id) AND version = :expected_version',
            ReturnValues='ALL_NEW'
        )
        return response['Attributes']
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            raise ValueError("Product was modified by another user. Please refresh and try again.")
        raise
