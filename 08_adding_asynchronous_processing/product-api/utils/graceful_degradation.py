"""Graceful Degradation Module.

Demonstrates resilient service degradation across multi-step order processing:
- Critical Path (Payment): Must succeed; fails fast if retries exhausted.
- Non-Critical with Fallback (Shipping): Falls back to cached/estimated rates.
- Non-Critical with Async Triage (Inventory & Email): Queues to SQS for background
  processing if synchronous calls fail.
"""
import os
import json
import logging
import boto3
from utils.retry_utils import retry_with_exponential_backoff, get_cached_rate

logger = logging.getLogger()
logger.setLevel(logging.INFO)


class PaymentProcessingError(Exception):
    """Raised when payment processing fails."""
    pass


class InventoryError(Exception):
    """Raised when inventory update fails."""
    pass


class NotificationError(Exception):
    """Raised when notification delivery fails."""
    pass


def get_estimated_shipping_rate(destination):
    """Fallback: Return estimated or cached shipping rate for destination."""
    logger.info(f"Using estimated shipping rate fallback for destination: {destination}")
    return get_cached_rate(destination)


def default_process_payment(payment_data, payment_gateway=None):
    """Process payment with payment gateway."""
    if payment_gateway is not None:
        result = payment_gateway.charge(payment_data)
        txn_id = getattr(result, 'id', str(result))
        return {"status": "success", "transaction_id": txn_id}
    
    # Default mock behavior if no gateway provided
    if isinstance(payment_data, dict) and payment_data.get('fail'):
        raise PaymentProcessingError("Card declined or gateway unavailable")
    
    order_id = payment_data.get('order_id', 'ord_mock') if isinstance(payment_data, dict) else 'ord_mock'
    return {
        "status": "success",
        "transaction_id": f"txn_{order_id}_success"
    }


def default_get_shipping_rate(order_id, destination, shipping_api=None):
    """Calculate shipping rate via external shipping carrier."""
    if shipping_api is not None:
        response = shipping_api.calculate_rate(order_id=order_id, destination=destination)
        return response.rate
    return 15.00


def default_update_inventory(items, inventory_service=None):
    """Synchronously update product inventory counts."""
    if inventory_service is not None:
        return inventory_service.deduct_inventory(items)
    logger.info(f"Synchronously updated inventory for items: {items}")
    return True


def default_queue_inventory_update(items, sqs_client=None, queue_url=None):
    """Asynchronously queue inventory update for background reconciliation."""
    logger.warning(f"Degraded: Queuing inventory update for async processing: {items}")
    if sqs_client and queue_url:
        sqs_client.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps({"action": "inventory_deduct", "items": items})
        )
    return True


def default_send_confirmation_email(customer_email, order_id, email_service=None):
    """Synchronously dispatch order confirmation email."""
    if email_service is not None:
        return email_service.send_email(customer_email, order_id)
    logger.info(f"Synchronously sent order confirmation to {customer_email} for order {order_id}")
    return True


def default_queue_email(customer_email, order_id, sqs_client=None, queue_url=None):
    """Asynchronously queue email dispatch for background worker."""
    logger.warning(f"Degraded: Queuing confirmation email for async dispatch: {customer_email}")
    if sqs_client and queue_url:
        sqs_client.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps({"action": "send_email", "email": customer_email, "order_id": order_id})
        )
    return True


def process_order(
    order_data,
    process_payment_fn=None,
    get_shipping_rate_fn=None,
    get_estimated_shipping_rate_fn=None,
    update_inventory_fn=None,
    queue_inventory_update_fn=None,
    send_confirmation_email_fn=None,
    queue_email_fn=None,
):
    """
    Process order with graceful degradation for external services.
    
    Matches tutorial specification:
    - Step 1: Process payment (critical - must succeed)
    - Step 2: Calculate shipping (non-critical - can use fallback)
    - Step 3: Update inventory (non-critical - can process async)
    - Step 4: Send confirmation email (non-critical - can process async)
    """
    # Bind service handlers (defaults or injected)
    _process_payment = process_payment_fn or default_process_payment
    _get_shipping_rate = get_shipping_rate_fn or default_get_shipping_rate
    _get_estimated_shipping_rate = get_estimated_shipping_rate_fn or get_estimated_shipping_rate
    _update_inventory = update_inventory_fn or default_update_inventory
    _queue_inventory_update = queue_inventory_update_fn or default_queue_inventory_update
    _send_confirmation_email = send_confirmation_email_fn or default_send_confirmation_email
    _queue_email = queue_email_fn or default_queue_email

    order_id = order_data['order_id']
    
    # Step 1: Process payment (critical - must succeed)
    try:
        payment_result = retry_with_exponential_backoff(
            lambda: _process_payment(order_data['payment']),
            max_retries=3
        )
    except Exception as e:
        # Payment failed - cannot proceed
        logger.error(f"Critical payment failure for order {order_id}: {str(e)}")
        return {
            "status": "failed",
            "error": "Payment processing failed",
            "order_id": order_id
        }
    
    # Step 2: Calculate shipping (non-critical - can use fallback)
    try:
        shipping_rate = retry_with_exponential_backoff(
            lambda: _get_shipping_rate(order_id, order_data['destination']),
            max_retries=2
        )
    except Exception:
        # Use cached or estimated shipping rate
        logger.warning(f"Shipping API unavailable for order {order_id}. Falling back to estimated rate.")
        shipping_rate = _get_estimated_shipping_rate(order_data['destination'])
    
    # Step 3: Update inventory (non-critical - can process async)
    try:
        _update_inventory(order_data['items'])
    except Exception as e:
        # Queue for async processing
        logger.warning(f"Sync inventory update failed for order {order_id}: {str(e)}. Queuing async.")
        _queue_inventory_update(order_data['items'])
    
    # Step 4: Send confirmation email (non-critical - can process async)
    try:
        _send_confirmation_email(order_data['customer_email'], order_id)
    except Exception as e:
        # Queue for async processing
        logger.warning(f"Sync email notification failed for order {order_id}: {str(e)}. Queuing async.")
        _queue_email(order_data['customer_email'], order_id)
    
    return {
        "status": "success",
        "order_id": order_id,
        "payment_id": payment_result['transaction_id'],
        "shipping_rate": shipping_rate
    }
