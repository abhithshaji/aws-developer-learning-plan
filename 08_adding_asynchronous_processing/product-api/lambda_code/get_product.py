# Handler for GET /products/{id}
from utils.response_utils import create_success_response, create_error_response, ContextualErrorHandler
from db.products_db import get_product
import logging
from utils.circuit_breaker import database_circuit_breaker, CircuitBreakerOpenError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handler(event, context):
    try:
        path_parameters = event.get('pathParameters') or {}
        query_params = event.get('queryStringParameters') or {}
        product_id = path_parameters.get('id')
        
        if not product_id:
            return create_error_response(400, 'Product id is required')
        
         # 1. Build context from the request (e.g. search query or category filter)
        user_context = {
            'search_term': query_params.get('search'),
            'category': query_params.get('category')
        }
        error_handler = ContextualErrorHandler(user_context=user_context)

        # Wrap database call in circuit breaker
        product = database_circuit_breaker.call(get_product, product_id)

        if not product:
            return error_handler.handle_product_not_found(product_id)

        return create_success_response(200, product)

    except CircuitBreakerOpenError:
        logger.warning("Database circuit breaker OPEN - failing fast")
        return create_error_response(503, 'Database service temporarily unavailable. Please retry shortly.')
    except Exception as e:
        logger.error(f"Unexpected error processing product {product_id}: {str(e)}")
        return create_error_response(500, 'Internal server error')