import json
import uuid
from db.products_db import insert_product
from utils.response_utils import create_success_response, create_error_response, handle_product_validation_error,create_structured_error_response
from pydantic import ValidationError
from db.product_schema import ProductInput
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handler(event, context):
    request_id = context.aws_request_id if context else None
    body = event.get('body') or ''
    try:
        # Parse JSON body
        raw_data = json.loads(body)
        
        # Prevent clients from specifying their own ID
        if 'id' in raw_data:
            return create_error_response(400, 'Product id is not allowed')

        # Validate input using Pydantic
        product_input = ProductInput(**raw_data)

        # Convert validated model to dict for database storage
        validated_data = product_input.model_dump()
        
        # Generate unique ID
        product_id = str(uuid.uuid4())
        validated_data['id'] = product_id
        
        # Extract user Amazon Resource Name (ARN) from request context
        user_arn = event.get('requestContext', {}).get('identity', {}).get('userArn', 'unknown')
        
        # Store in DynamoDB
        inserted = insert_product(validated_data, user_arn)
        
        # Return created product
        return create_success_response(201, inserted)

    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON payload: {str(e)}")
        return create_error_response(400, f'Invalid JSON: {str(e)}')

    except ValidationError as e:
        # Pydantic validation errors provide detailed field-level feedback
        error_messages = [f"{err['loc'][0]}: {err['msg']}" for err in e.errors()]
        logger.warning(f"Validation failed: {error_messages}", extra={"request_id": request_id})
        return handle_product_validation_error(error_messages, request_id=request_id)

    except ValueError as e:
        # Handles duplicate product or category value errors (409 Conflict)
        logger.warning(f"Conflict error: {str(e)}", extra={"request_id": request_id})
        return create_structured_error_response(
            status_code=409,
            error_type="conflict",
            message=str(e),
            suggestions=["Check if a product with the same key already exists"],
            request_id=request_id
        )

    except Exception as e:
        logger.exception(f"Unexpected error: {str(e)}")
        return create_error_response(500, f'Internal server error - {str(e)}')