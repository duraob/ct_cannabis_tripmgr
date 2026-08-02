"""
LeafTrade API Integration Module

This module handles all interactions with the LeafTrade API including:
- Order retrieval and filtering
- Customer information extraction
- Order status synchronization
- Invoice management

Production-ready features:
- Comprehensive error handling and logging
- Retry mechanisms with exponential backoff
- Input validation and sanitization
- Rate limiting (see below)
- Proper exception handling
- Type hints and documentation
- Pagination handling for large datasets

Rate limiting (LeafTrade API docs):
- Burst: 100 requests per minute. Exceeding returns 429.
- Sustained: 1000 requests per hour. Exceeding returns 429.
All outbound requests MUST go through _make_api_request(), which enforces the
burst limit and retries once on 429. Future enhancements that call LeafTrade
should use this module's public functions (or _make_api_request) so rate limits
are respected; do not add new direct HTTP calls that bypass this throttle.
"""

import os
import logging
import time
import json
import threading
from collections import deque
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, date
from functools import wraps
import requests
from requests.exceptions import RequestException, Timeout, ConnectionError
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

# Configuration constants
MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds
REQUEST_TIMEOUT = 30  # seconds

# LeafTrade rate limits (from API docs). Enforced in _make_api_request().
LEAFTRADE_RATE_LIMIT_BURST = 100   # requests per minute
LEAFTRADE_RATE_LIMIT_WINDOW = 60   # seconds
LEAFTRADE_429_RETRY_AFTER = 61     # seconds before retry after 429
_rate_limit_timestamps = deque(maxlen=LEAFTRADE_RATE_LIMIT_BURST)
_rate_limit_lock = threading.Lock()

# Environment variables
LEAFTRADE_API_URL = os.getenv("LEAFTRADE_API_URL")
LEAFTRADE_API_KEY = os.getenv("LEAFTRADE_API_KEY")


def validate_config() -> bool:
    """Validate that all required environment variables are set."""
    required_vars = {
        "LEAFTRADE_API_URL": LEAFTRADE_API_URL,
        "LEAFTRADE_API_KEY": LEAFTRADE_API_KEY,
    }
    
    missing_vars = [var for var, value in required_vars.items() if not value]
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        return False
    
    return True


def retry_on_failure(max_retries: int = MAX_RETRIES, delay: float = RETRY_DELAY):
    """Decorator to retry API calls with exponential backoff."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except (RequestException, Timeout, ConnectionError) as e:
                    last_exception = e
                    if attempt < max_retries:
                        wait_time = delay * (2 ** attempt)  # Exponential backoff
                        logger.warning(
                            f"API call failed (attempt {attempt + 1}/{max_retries + 1}): "
                            f"{func.__name__} - {str(e)}. Retrying in {wait_time}s..."
                        )
                        time.sleep(wait_time)
                    else:
                        logger.error(
                            f"API call failed after {max_retries + 1} attempts: "
                            f"{func.__name__} - {str(e)}"
                        )
                        raise last_exception
            
            return None
        return wrapper
    return decorator


def validate_api_key(api_key: str) -> bool:
    """Validate that an API key is provided and not empty."""
    if not api_key or not isinstance(api_key, str):
        logger.error("Invalid or missing LeafTrade API key")
        return False
    return True


def validate_status(status: str) -> str:
    """Validate and normalize order status parameter."""
    valid_statuses = ["new", "approved", "processing", "completed", "cancelled"]
    if status not in valid_statuses:
        logger.warning(f"Invalid status '{status}', defaulting to 'approved'")
        return "approved"
    return status


def _wait_for_rate_limit() -> None:
    """Sleep if needed so we stay under LeafTrade burst limit (100 requests per minute)."""
    while True:
        with _rate_limit_lock:
            now = time.monotonic()
            while _rate_limit_timestamps and _rate_limit_timestamps[0] < now - LEAFTRADE_RATE_LIMIT_WINDOW:
                _rate_limit_timestamps.popleft()
            if len(_rate_limit_timestamps) < LEAFTRADE_RATE_LIMIT_BURST:
                return
            wait = LEAFTRADE_RATE_LIMIT_WINDOW - (now - _rate_limit_timestamps[0])
        if wait > 0:
            logger.debug("LeafTrade rate limit: sleeping %.1fs (burst %d/min)", wait, LEAFTRADE_RATE_LIMIT_BURST)
            time.sleep(wait)


def _record_request_time() -> None:
    """Record that a LeafTrade request was made (for burst throttling)."""
    with _rate_limit_lock:
        _rate_limit_timestamps.append(time.monotonic())


@retry_on_failure()
def _make_api_request(url: str, headers: Dict[str, str], params: Optional[Dict[str, Any]] = None, action: str = "API request") -> Optional[Dict[str, Any]]:
    """
    Make a standardized API request to LeafTrade with proper error handling.
    Enforces LeafTrade rate limits (100/min burst; retries once on 429).
    All LeafTrade HTTP calls must go through this function.
    """
    if not validate_config():
        raise ValueError("LeafTrade configuration is invalid")
    try:
        logger.debug(f"Making LeafTrade API request: {action}")
        logger.debug(f"Request URL: {url}")
        logger.debug(f"Request headers: {headers}")
        logger.debug(f"Request params: {params}")
        _wait_for_rate_limit()
        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=REQUEST_TIMEOUT
        )
        _record_request_time()
        if response.status_code == 429:
            logger.warning("LeafTrade rate limit (429); retrying once after %ds", LEAFTRADE_429_RETRY_AFTER)
            time.sleep(LEAFTRADE_429_RETRY_AFTER)
            _wait_for_rate_limit()
            response = requests.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
            _record_request_time()
        response.raise_for_status()
        try:
            json_data = response.json()
            logger.debug(f"LeafTrade API response for {action}: {json_data}")
            return json_data
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response for {action}: {e}")
            logger.error(f"Response content: {response.text[:500]}...")
            if response.text.startswith('<!doctype') or response.text.startswith('<html'):
                logger.error(f"Received HTML response instead of JSON for {action}")
                raise ValueError(f"API returned HTML instead of JSON for {action}")
            raise
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error for {action}: {e.response.status_code} - {e.response.text}")
        raise
    except Timeout:
        logger.error(f"Request timeout for {action}")
        raise
    except ConnectionError as e:
        logger.error(f"Connection error for {action}: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error for {action}: {e}")
        raise


def _handle_pagination(base_url: str, headers: Dict[str, str], params: Dict[str, Any], action: str) -> List[Dict[str, Any]]:
    """
    Handle pagination for LeafTrade API responses.
    
    Args:
        base_url: Base API URL
        headers: Request headers
        params: Query parameters
        action: Action description for logging
    
    Returns:
        List of all results from all pages
    """
    all_results = []
    next_url = base_url
    
    while next_url:
        try:
            logger.debug(f"Fetching page for {action}: {next_url}")
            response_data = _make_api_request(next_url, headers, params, f"{action} - page")
            
            if response_data and "results" in response_data:
                page_results = response_data["results"]
                all_results.extend(page_results)
                logger.debug(f"Retrieved {len(page_results)} items from current page")
                
                # Check for next page
                next_url = response_data.get("next")
                if next_url:
                    logger.debug(f"Next page available: {next_url}")
                else:
                    logger.debug("No more pages available")
            else:
                logger.error(f"Invalid response structure for {action}: missing 'results' field")
                break
                
        except Exception as e:
            logger.error(f"Failed to fetch page for {action}: {e}")
            break
    
    logger.info(f"Retrieved total of {len(all_results)} items for {action}")
    return all_results


def get_dispensary_info() -> Optional[Dict[str, Dict[str, Any]]]:
    """
    Retrieve dispensary information from LeafTrade with pagination support.
    
    Returns:
        Dictionary mapping dispensary_id to dispensary details or None if failed
    """
    if not validate_config():
        return None
    
    if not validate_api_key(LEAFTRADE_API_KEY):
        return None
    
    endpoint = LEAFTRADE_API_URL + "dispensaries/"
    headers = {
        "Authorization": f"Token {LEAFTRADE_API_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        # Handle pagination for dispensaries
        dispensaries = _handle_pagination(endpoint, headers, {}, "dispensary_info")
        
        if not dispensaries:
            logger.warning("No dispensaries found")
            return {}
        
        dispensary_dict = {}
        
        for dispensary in dispensaries:
            try:
                customer_id = dispensary.get("id")
                customer_name = dispensary.get("name", "Unknown")
                
                if not customer_id:
                    logger.warning("Dispensary missing ID, skipping")
                    continue
                
                # Process dispensary locations
                locations = dispensary.get("locations", [])
                for dispensary_location in locations:
                    try:
                        dispensary_id = dispensary_location.get("id")
                        dispensary_name = dispensary_location.get("name", "Unknown")
                        
                        # Safely access address information
                        address = dispensary_location.get("address", {})
                        dispensary_address = address.get("street_address_1", "")
                        dispensary_city = address.get("city", "")
                        dispensary_state = address.get("state", "")
                        dispensary_zip = address.get("postal_code", "")
                        dispensary_country = dispensary_location.get("country", "")
                        dispensary_phone = dispensary_location.get("phone", "")
                        
                        if dispensary_id:
                            dispensary_dict[dispensary_id] = {
                                "customer_id": customer_id,
                                "customer_name": customer_name,
                                "name": dispensary_name,
                                "address": dispensary_address,
                                "city": dispensary_city,
                                "state": dispensary_state,
                                "zip": dispensary_zip,
                                "country": dispensary_country,
                                "phone": dispensary_phone
                            }
                    except KeyError as e:
                        logger.warning(f"Dispensary location data missing required field: {e}")
                        continue
                        
            except KeyError as e:
                logger.warning(f"Dispensary data missing required field: {e}")
                continue
        
        logger.info(f"Successfully retrieved {len(dispensary_dict)} dispensary locations")
        return dispensary_dict
        
    except Exception as e:
        logger.error(f"Failed to get dispensary info: {e}")
        return None


def get_customers() -> Optional[List[Dict[str, Any]]]:
    """
    Retrieve customer information from LeafTrade.
    
    Returns:
        List of customer dictionaries or None if failed
    """
    try:
        dispensary_dict = get_dispensary_info()
        
        if dispensary_dict is None:
            logger.error("Failed to get dispensary info")
            return None
        
        # Convert dictionary to list format for consistency
        customers_list = []
        for dispensary_id, dispensary_info in dispensary_dict.items():
            customers_list.append({
                'id': str(dispensary_id),  # Convert to string for database consistency
                'customer_id': dispensary_info['customer_id'],
                'customer_name': dispensary_info['customer_name'],
                'name': dispensary_info['name'],
                'address': dispensary_info['address'],
                'city': dispensary_info['city'],
                'state': dispensary_info['state'],
                'zip': dispensary_info['zip'],
                'country': dispensary_info['country'],
                'phone': dispensary_info['phone']
            })
        
        logger.info(f"Successfully retrieved {len(customers_list)} customers")
        return customers_list
        
    except Exception as e:
        logger.error(f"Failed to get customers: {e}")
        return None


def get_orders(status: str = "approved") -> Optional[Dict[str, Dict[str, Any]]]:
    """
    Retrieve orders from LeafTrade API with pagination support.
    
    Args:
        status: Order status filter ("approved", "new", "completed", "revised")
    
    Returns:
        Dictionary mapping order_id to order details or None if failed
    """
    if not validate_config():
        return None
    
    headers = {
        "Authorization": f"Token {LEAFTRADE_API_KEY}",
        "Content-Type": "application/json"
    }
    
    params = {
        "status": status
    }
    
    try:
        logger.info(f"Fetching orders with status: {status}")
        orders_data = _handle_pagination(
            f"{LEAFTRADE_API_URL}/orders/",
            headers,
            params,
            "get_orders"
        )
        
        if orders_data:
            # Convert list to dictionary format
            orders_dict = {}
            for order in orders_data:
                try:
                    order_id = order.get("id")
                    if order_id:
                        # Extract dispensary location information (this is the customer)
                        dispensary_location = order.get("dispensary_location", {})
                        dispensary = dispensary_location.get("dispensary", {})
                        customer_name = f'{dispensary.get("name", "Unknown Customer")} - {dispensary_location.get("name", "Unknown Location")}'
                        
                        # Extract address information from dispensary location
                        address_info = dispensary_location.get("address", {})
                        address = address_info.get("street_address_1", "Unknown Address")
                        city = address_info.get("city", "")
                        state = address_info.get("state", "")
                        zip_code = address_info.get("postal_code", "")
                        
                        # Format address
                        full_address = f"{address}, {city}, {state} {zip_code}".strip()
                        if full_address.endswith(","):
                            full_address = full_address[:-1]
                        
                        orders_dict[str(order_id)] = {
                            "order_id": str(order_id),
                            "invoice_id": order.get("invoice_id", ""),
                            "delivery_date": order.get("delivery_date"),
                            "customer_name": customer_name,
                            "customer_location": full_address,
                            "total_amount": order.get("total_gross", 0),
                            "created_at": order.get("created_at"),
                            "updated_at": order.get("updated_at")
                        }
                except KeyError as e:
                    logger.warning(f"Order data missing required field: {e}")
                    continue
            
            logger.info(f"Successfully retrieved {len(orders_dict)} orders from LeafTrade")
            return orders_dict
        else:
            logger.error("Failed to retrieve orders from LeafTrade")
            return None
            
    except Exception as e:
        logger.error(f"Error fetching orders: {e}")
        return None


def get_order_details(order_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve complete order details including line items from LeafTrade API.
    Uses simple in-memory cache with 5-minute TTL.
    
    Args:
        order_id: LeafTrade order ID
    
    Returns:
        Complete order details dictionary or None if failed
    """
    if not validate_config():
        return None
    
    if not order_id:
        logger.error("Order ID is required")
        return None
    
    # Check cache first
    from utils.cache import get as cache_get, set as cache_set
    cache_key = f"leaftrade_order_{order_id}"
    cached_data = cache_get(cache_key)
    if cached_data is not None:
        logger.debug(f"Returning cached order details for order {order_id}")
        return cached_data
    
    headers = {
        "Authorization": f"Token {LEAFTRADE_API_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        logger.info(f"Fetching complete details for order: {order_id}")
        
        # Get order details
        order_url = f"{LEAFTRADE_API_URL}/orders/{order_id}/"
        order_response = _make_api_request(order_url, headers, {}, f"get_order_details_{order_id}")
        
        if not order_response:
            logger.error(f"Failed to retrieve order details for order {order_id}")
            return None
        
        # Extract line items from the order response
        line_items = []
        items_data = order_response.get("items", [])
        
        for item in items_data:
            try:
                # Extract product information from the item structure
                product_name = item.get("product_name", "Unknown Product")
                product_sku = item.get("product_sku", "")
                
                # Extract inventory information
                pull_number = item.get("pull_number", "")
                raw_barcode_id = item.get("batch_ref", "")  # Using batch_ref as barcode_id
                
                # Normalize barcode_id: remove spaces to match BioTrack format
                barcode_id = raw_barcode_id.replace(" ", "") if raw_barcode_id else ""
                
                # Ensure quantity is consistently typed as integer
                quantity = item.get("units", 0)
                if quantity is not None:
                    try:
                        quantity = int(quantity)
                    except (ValueError, TypeError):
                        quantity = 0
                else:
                    quantity = 0
                
                # LeafTrade returns prices as strings ("256.00"), so they are converted
                # before use - multiplying the raw value by the quantity repeats the
                # string instead of computing a total.
                try:
                    unit_price = float(item.get("unit_price_net") or 0)
                except (ValueError, TypeError):
                    logger.warning(f"Unparseable unit price on line item {item.get('id')}: {item.get('unit_price_net')!r}")
                    unit_price = 0.0

                line_item = {
                    "id": item.get("id"),
                    "product_name": product_name,
                    "product_sku": product_sku,
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "total_price": round(unit_price * quantity, 2),
                    "pull_number": pull_number,
                    "barcode_id": barcode_id,
                    "inventory_id": item.get("stock_id"),
                    "notes": ""
                }
                line_items.append(line_item)
            except KeyError as e:
                logger.warning(f"Line item data missing required field: {e}")
                continue
        
        # Combine order and line items
        order_details = {
            "order": order_response,
            "line_items": line_items
        }
        
        # Cache the result for 5 minutes (300 seconds)
        cache_set(cache_key, order_details, ttl_seconds=300)
        
        logger.info(f"Successfully retrieved complete details for order {order_id}")
        return order_details
        
    except Exception as e:
        logger.error(f"Error fetching order details for order {order_id}: {e}")
        return None

