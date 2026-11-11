import json
import uuid
from db.products_db import insert_product
from utils.response_utils import create_success_response, create_error_response
from pydantic import ValidationError
from db.product_schema import ProductInput

def handler(event, context):
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

    except ValidationError as e:
        # Pydantic validation errors provide detailed field-level feedback
        errors = e.errors()
        error_messages = [f"{err['loc'][0]}: {err['msg']}" for err in errors]
        return create_error_response(400, f'Validation failed: {", ".join(error_messages)}')
    except ValueError as e:
        return create_error_response(409, str(e))
    except json.JSONDecodeError as e:
        return create_error_response(400, f'Invalid JSON: {str(e)}')
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return create_error_response(500, f'Internal server error - {str(e)}')