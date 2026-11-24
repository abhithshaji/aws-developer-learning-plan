"""API Gateway Response Formatting Module (Shared Lambda Layer).

Standardizes HTTP success/error envelopes, CORS headers, JSON Decimal serialization,
and contextual error suggestions across all Lambda functions.
"""
import json
from datetime import datetime, timezone
from decimal import Decimal

# Common CORS and Content headers
DEFAULT_HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*'
}


def decimal_serializer(obj):
    """Handle Decimal objects in JSON serialization."""
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def create_success_response(status_code, data):
    """Create standardized success response for API Gateway."""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps(data, default=decimal_serializer)
    }


def create_error_response(status_code, message):
    """Create standardized error response for API Gateway."""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps({'error': message}, default=decimal_serializer)
    }


def create_structured_error_response(status_code, error_type, message, details=None, suggestions=None, request_id=None):
    """Create comprehensive, actionable error response for API Gateway consumers."""
    error_payload = {
        'error': {
            'type': error_type,
            'message': message,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'request_id': request_id
        }
    }

    if details:
        error_payload['error']['details'] = details

    if suggestions:
        error_payload['error']['suggestions'] = suggestions

    return {
        'statusCode': status_code,
        'headers': DEFAULT_HEADERS,
        'body': json.dumps(error_payload, default=decimal_serializer)
    }


def handle_product_validation_error(validation_errors, request_id=None):
    """Handle product validation failures with detailed feedback (HTTP 400)."""
    return create_structured_error_response(
        status_code=400,
        error_type='validation_error',
        message='Product data validation failed',
        details=validation_errors,
        suggestions=[
            'Check that all required fields (title, category, price, description) are provided',
            'Ensure price is a positive number',
            'Verify category is from the allowed list: Electronics, Audio, Computers, Accessories, Home'
        ],
        request_id=request_id
    )


def handle_inventory_insufficient_error(product_id, requested, available, request_id=None):
    """Handle insufficient inventory with helpful guidance (HTTP 409 or 400)."""
    return create_structured_error_response(
        status_code=409,
        error_type='insufficient_inventory',
        message=f'Not enough inventory for product {product_id}',
        details={
            'product_id': product_id,
            'requested_quantity': requested,
            'available_quantity': available
        },
        suggestions=[
            f'Reduce quantity to {available} or less',
            'Check back later for restocked inventory',
            'Consider similar products in the same category'
        ],
        request_id=request_id
    )


class ContextualErrorHandler:
    """Generate context-aware error messages for better user experience."""

    def __init__(self, user_context=None):
        self.user_context = user_context or {}

    def handle_product_not_found(self, product_id):
        """Generate helpful message for missing products."""
        base_message = f'Product {product_id} is not available'
        suggestions = ['Verify the product ID is correct']

        if self.user_context.get('search_term'):
            suggestions.append(f'Try searching for "{self.user_context["search_term"]}" to find similar products')

        if self.user_context.get('category'):
            suggestions.append(f'Browse other products in {self.user_context["category"]} category')

        return create_structured_error_response(
            status_code=404,
            error_type='product_not_found',
            message=base_message,
            suggestions=suggestions
        )

    def handle_checkout_error(self, error_details):
        """Generate helpful checkout error messages."""
        if error_details.get('payment_failed'):
            return create_structured_error_response(
                status_code=500,
                error_type='payment_error',
                message='Payment processing failed',
                suggestions=[
                    'Verify your payment information is correct',
                    'Check that your card has sufficient funds',
                    'Try a different payment method',
                    'Contact your bank if the problem persists'
                ]
            )

        elif error_details.get('address_invalid'):
            return create_structured_error_response(
                status_code=400,
                error_type='address_error',
                message='Shipping address validation failed',
                details=error_details['address_errors'],
                suggestions=[
                    'Verify your address is complete and accurate',
                    'Check that postal code matches your city/state',
                    'Ensure we deliver to your location'
                ]
            )
