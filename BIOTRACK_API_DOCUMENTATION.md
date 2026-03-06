# BioTrack API Integration Documentation

## Overview

The BioTrack API integration module (`api/biotrack.py`) provides a comprehensive interface for interacting with the BioTrack traceability system. This module handles authentication, data synchronization, inventory management, and manifest creation for cannabis compliance tracking.

## Table of Contents

1. [Configuration](#configuration)
2. [Authentication](#authentication)
3. [Inventory Types (Reference)](#inventory-types-reference)
4. [Core Functions](#core-functions)
5. [Usage Patterns](#usage-patterns)
6. [Error Handling](#error-handling)
7. [Best Practices](#best-practices)

---

## Configuration

### Environment Variables

The module requires the following environment variables to be set:

```python
BIOTRACK_API_URL      # BioTrack API endpoint URL
BIOTRACK_USERNAME     # BioTrack API username
BIOTRACK_PASSWORD     # BioTrack API password
BIOTRACK_UBI          # BioTrack license number (UBI)
```

### Training Mode

The module supports a "training mode" that determines whether API calls are made against the production or training environment. This is controlled by the `get_training_mode()` function from the main application, which returns `"0"` for production or `"1"` for training.

### Configuration Validation

The `validate_config()` function checks that all required environment variables are set before making API calls. If any are missing, the function logs an error and returns `False`.

---

## Authentication

### `get_auth_token() -> Optional[str]`

Authenticates with the BioTrack API and retrieves a session token.

**Returns:**
- `str`: Session token string on success
- `None`: If authentication failed

**Example:**
```python
from api.biotrack import get_auth_token

token = get_auth_token()
if not token:
    print("Authentication failed")
    return

# Use token for subsequent API calls
```

**API Request:**
```json
{
    "API": "4.0",
    "action": "login",
    "username": "your_username",
    "password": "your_password",
    "license_number": "your_ubi"
}
```

**API Response:**
```json
{
    "sessionid": "abc123xyz..."
}
```

**Notes:**
- The session token must be used for all subsequent API calls
- Tokens are session-based and may expire
- Always check for `None` return value before using the token

---

## Inventory Types (Reference)

Inventory items from `get_inventory_info` / `sync_inventory` include an `inventorytype` field (numeric id). The application maps these ids to user-friendly names in `utils/inventory_types.py` (e.g. for display when product name is missing: `strain - inventory_type`).

| id | name |
|----|------|
| 6 | Flower |
| 7 | Clone |
| 9 | Other Material |
| 10 | Seed |
| 11 | Plant Tissue |
| 12 | Mature Plant |
| 13 | Flower Lot |
| 14 | Other Material Lot |
| 15 | Bubble Hash |
| 16 | Hash |
| 17 | Hydrocarbon Extract |
| 19 | Food Grade Solvent Extract |
| 20 | Infused Dairy Butter or Fat in Solid Form |
| 21 | Infused Cooking Oil |
| 22 | Solid Marijuana Infused Edible |
| 23 | Liquid Marijuana Infused Edible |
| 24 | Marijuana Extract for Inhalation |
| 25 | Marijuana Infused Topicals |
| 27 | Waste |
| 28 | Usable Marijuana |
| 29 | Wet Flower |
| 30 | Marijuana Mix |
| 31 | Marijuana Mix Packaged |
| 32 | Marijuana Mix Infused |
| 33 | Non-Mandatory QA Sample |
| 34 | Capsule |
| 35 | Tincture |
| 36 | Transdermal Patch |
| 38 | Lozenge |
| 39 | Pill |
| 40 | Non Smokable Infused Extract |
| 42 | Ethanol/Alcohol Extract |
| 45 | Liquid Marijuana RSO |
| 46 | CO2 Extract |
| 62 | Vape Cartridge |

**Usage:** Call `get_product_display_name(item_info)` from `utils.inventory_types` to get the display name (productname if present, otherwise `strain - inventory_type`).

---

## Core Functions

### Data Retrieval Functions

#### `get_driver_info(token: str) -> Optional[Dict[str, Dict[str, Any]]]`

Retrieves driver/employee information from BioTrack.

**Parameters:**
- `token` (str): Authentication token from `get_auth_token()`

**Returns:**
- Dictionary mapping `driver_id` to driver details:
  ```python
  {
      "123": {
          "name": "John Doe",
          "is_active": 1
      },
      "456": {
          "name": "Jane Smith",
          "is_active": 1
      }
  }
  ```
- `None`: If the request failed

**API Action:** `sync_employee`

**Usage in Application:**
- Used in `/api/drivers/refresh` endpoint to sync drivers from BioTrack
- Drivers are cached in the local database for faster access
- Only active drivers (`deleted == 0`) are returned

**Example:**
```python
from api.biotrack import get_auth_token, get_driver_info

token = get_auth_token()
if token:
    drivers = get_driver_info(token)
    for driver_id, driver_info in drivers.items():
        print(f"Driver {driver_id}: {driver_info['name']}")
```

---

#### `get_vehicle_info(token: str) -> Optional[Dict[str, Dict[str, Any]]]`

Retrieves vehicle information from BioTrack.

**Parameters:**
- `token` (str): Authentication token

**Returns:**
- Dictionary mapping `vehicle_id` to vehicle details:
  ```python
  {
      "1": {
          "name": "Van 1",
          "is_active": 1
      },
      "2": {
          "name": "Truck 1",
          "is_active": 1
      }
  }
  ```
- `None`: If the request failed

**API Action:** `sync_vehicle`

**Usage in Application:**
- Used in `/api/vehicles/refresh` endpoint to sync vehicles
- Vehicles are cached in the local database
- BioTrack returns `nickname` field which is mapped to `name`
- Only active vehicles (`deleted == 0`) are returned

**Example:**
```python
from api.biotrack import get_auth_token, get_vehicle_info

token = get_auth_token()
if token:
    vehicles = get_vehicle_info(token)
    for vehicle_id, vehicle_info in vehicles.items():
        print(f"Vehicle {vehicle_id}: {vehicle_info['name']}")
```

---

#### `get_vendor_info(token: str) -> Optional[Dict[str, Dict[str, Any]]]`

Retrieves vendor/dispensary information from BioTrack.

**Parameters:**
- `token` (str): Authentication token

**Returns:**
- Dictionary mapping `location` (license) to vendor details:
  ```python
  {
      "123456789": {
          "name": "Dispensary Name",
          "ubi": "UBI123456",
          "license": "123456789"
      }
  }
  ```
- `None`: If the request failed

**API Action:** `sync_vendor`

**Usage in Application:**
- Used in `/api/biotrack/refresh` endpoint to sync vendors
- Only vendors with `retail == 1` and `deleted == 0` are returned
- Vendors are cached in the local database

**Example:**
```python
from api.biotrack import get_auth_token, get_vendor_info

token = get_auth_token()
if token:
    vendors = get_vendor_info(token)
    for location, vendor_info in vendors.items():
        print(f"Vendor {location}: {vendor_info['name']}")
```

---

#### `get_room_info(token: str) -> Optional[Dict[str, Dict[str, Any]]]`

Retrieves room/location information from BioTrack.

**Parameters:**
- `token` (str): Authentication token

**Returns:**
- Dictionary mapping `room_id` to room details:
  ```python
  {
      "1": {
          "name": "Room A",
          "is_active": 1
      },
      "2": {
          "name": "Room B",
          "is_active": 1
      }
  }
  ```
- `None`: If the request failed

**API Action:** `sync_inventory_room`

**Usage in Application:**
- Used in `/api/rooms/refresh` endpoint to sync rooms
- Rooms are cached in the local database
- Only active rooms (`deleted == 0`) are returned

**Example:**
```python
from api.biotrack import get_auth_token, get_room_info

token = get_auth_token()
if token:
    rooms = get_room_info(token)
    for room_id, room_info in rooms.items():
        print(f"Room {room_id}: {room_info['name']}")
```

---

#### `get_inventory_info(token: str) -> Optional[Dict[str, Dict[str, Any]]]`

Retrieves inventory information from BioTrack.

**Parameters:**
- `token` (str): Authentication token

**Returns:**
- Dictionary mapping `item_id` to full inventory item data
- `None`: If the request failed

**API Action:** `sync_inventory`

**Usage in Application:**
- Used in report generation and inventory lookups
- Returns full item data from BioTrack (not a subset)

**Example:**
```python
from api.biotrack import get_auth_token, get_inventory_info

token = get_auth_token()
if token:
    inventory = get_inventory_info(token)
    for item_id, item_data in inventory.items():
        print(f"Item {item_id}: {item_data}")
```

---

#### `get_inventory_qa_check(token: str, barcode_id: str) -> Optional[Dict[str, Any]]`

Retrieves lab test results (QA check) for a specific inventory item.

**Parameters:**
- `token` (str): Authentication token
- `barcode_id` (str): Barcode ID of the inventory item

**Returns:**
- Dictionary with lab test results:
  ```python
  {
      "total": "25.5",
      "thca": "20.3",
      "thc": "2.1",
      "cbda": "1.2",
      "cbd": "0.5"
  }
  ```
- `None`: If no lab data found or request failed

**API Action:** `inventory_qa_check_all`

**Usage in Application:**
- Used in report generation to include lab test results
- Only returns cannabinoid test results (type 2)
- Returns `None` if no cannabinoid data is available

**Example:**
```python
from api.biotrack import get_auth_token, get_inventory_qa_check

token = get_auth_token()
if token:
    lab_results = get_inventory_qa_check(token, "6853296789574117")
    if lab_results:
        print(f"THC: {lab_results['thc']}%")
        print(f"Total: {lab_results['total']}%")
```

---

### Inventory Management Functions

#### `post_sublot(token: str, sublot_id: str, move_info: List[Dict[str, str]]) -> Optional[List[str]]`

Creates inventory sublot splits in BioTrack. This function splits an inventory item into multiple sublots.

**Parameters:**
- `token` (str): Authentication token
- `sublot_id` (str): ID of the sublot to split
- `move_info` (List[Dict]): List of dictionaries with:
  - `barcodeid` (str): Barcode ID of the item to split
  - `remove_quantity` (str): Quantity to remove from the original item

**Returns:**
- `List[str]`: List of new barcode IDs created
- `Dict`: Error response if failed (contains `success: False`, `error`, `errorcode`)
- `None`: If request failed

**API Action:** `inventory_split`

**Example Input:**
```python
move_info = [
    {
        "barcodeid": "6853296789574117",
        "remove_quantity": "693.00"
    },
    {
        "barcodeid": "6853296789574118",
        "remove_quantity": "252.00"
    }
]

result = post_sublot(token, "sublot_123", move_info)
# Returns: ["6853296789574115", "6853296789574116"]
```

**Example API Response:**
```json
{
    "sessiontime": "1384476925",
    "barcode_id": [
        "6853296789574115",
        "6853296789574116"
    ],
    "success": "1",
    "transactionid": "3312"
}
```

---

#### `post_sublot_bulk_create(token: str, sublot_data: List[Dict[str, str]]) -> Optional[List[str]]`

Creates inventory sublots in bulk. This is a convenience function that uses the same API endpoint as `post_sublot` but with a special `sublot_id` value.

**Parameters:**
- `token` (str): Authentication token
- `sublot_data` (List[Dict]): List of dictionaries with:
  - `barcodeid` (str): Barcode ID of the item to split
  - `remove_quantity` (str): Quantity to remove

**Returns:**
- `List[str]`: List of new barcode IDs created
- `Dict`: Error response if failed
- `None`: If request failed

**Usage in Application:**
- Used in `process_order_sublots()` to create sublots from LeafTrade orders
- Used in trip execution to create sublots for delivery manifests

**Example:**
```python
from api.biotrack import get_auth_token, post_sublot_bulk_create

token = get_auth_token()
sublot_data = [
    {"barcodeid": "6853296789574117", "remove_quantity": "10.00"},
    {"barcodeid": "6853296789574118", "remove_quantity": "5.00"}
]

new_barcodes = post_sublot_bulk_create(token, sublot_data)
if new_barcodes:
    print(f"Created {len(new_barcodes)} new sublots")
```

---

#### `post_sublot_move(token: str, move_info: List[Dict[str, str]]) -> Optional[Dict[str, Any]]`

Moves inventory sublots between rooms in BioTrack.

**Parameters:**
- `token` (str): Authentication token
- `move_info` (List[Dict]): List of dictionaries with:
  - `barcodeid` (str): Barcode ID of the item to move
  - `room` (str): Room ID to move the item to

**Returns:**
- `Dict`: Response data with `success`, `transactionid` on success
- `Dict`: Error response if failed (contains `success: False`, `error`, `errorcode`)
- `None`: If request failed

**API Action:** `inventory_move`

**Example Input:**
```python
move_info = [
    {
        "barcodeid": "6853296789574115",
        "room": "1"
    },
    {
        "barcodeid": "6853296789574152",
        "room": "1"
    }
]

result = post_sublot_move(token, move_info)
```

**Example API Response:**
```json
{
    "sessiontime": "1384476925",
    "success": "1",
    "transactionid": "3278"
}
```

**Usage in Application:**
- Used after creating sublots to move them to the appropriate room
- Used in `process_order_sublots()` to move sublots to the default room for a location

---

#### `post_manifest(token: str, manifest_info: Dict[str, Any], drivers: Union[str, List[str]], vehicle: str, location: str = "ACFB0000681") -> Optional[Dict[str, Any]]`

Creates an inventory manifest in BioTrack. Manifests notify the traceability system of intent to transfer inventory items from one license to another.

**Parameters:**
- `token` (str): Authentication token
- `manifest_info` (Dict): Dictionary with manifest details:
  - `approximate_departure` (int): Unix timestamp
  - `approximate_arrival` (int): Unix timestamp
  - `approximate_route` (str): Route description
  - `stop_number` (str): Stop number (typically "1")
  - `barcodeid` (List[str]): List of barcode IDs to include in manifest
  - `vendor_license` (str): Vendor license number
- `drivers` (Union[str, List[str]]): Driver ID(s) - can be single string or list
- `vehicle` (str): Vehicle ID
- `location` (str): Location ID (default: "ACFB0000681")

**Returns:**
- `str`: Manifest ID (barcode_id from response) on success
- `None`: If request failed

**API Action:** `inventory_manifest`

**Example Input:**
```python
from datetime import datetime
import time

manifest_info = {
    "approximate_departure": int(time.time()),
    "approximate_arrival": int(time.time()) + 3600,
    "approximate_route": "Turn left on Main St.",
    "stop_number": "1",
    "barcodeid": [
        "6853296789574115",
        "6853296789574116"
    ],
    "vendor_license": "25678787644"
}

manifest_id = post_manifest(
    token,
    manifest_info,
    ["23468", "23469"],  # Two drivers
    "2",  # Vehicle ID
    "ACFB0000681"  # Location
)
```

**Example API Response:**
```json
{
    "sessiontime": "1384476925",
    "success": "1",
    "transactionid": "3278",
    "barcode_id": "6853296789574115"
}
```

**Usage in Application:**
- Used in trip execution (`utils/trip_execution.py`) to create manifests for delivery trips
- Manifest ID is stored in the `trip_order.manifest_id` field
- Route information is generated using Google Maps API and included in the manifest

---

#### `post_inventory_adjust(token: str, data: Union[Dict[str, Any], List[Dict[str, Any]]]) -> Optional[Dict[str, Any]]`

Adjusts the quantity of one or more inventory items. The API accepts a single adjustment node or an array of nodes in one request.

**Parameters:**
- `token` (str): Authentication token
- `data` (Dict or List[Dict]): One node (dict) or list of nodes. Each node contains:
  - `barcodeid` (str, required): Inventory barcode identifier
  - `quantity` (str, optional if `remove_quantity` provided): New quantity to set the inventory to (decimal)
  - `remove_quantity` (str, optional if `quantity` provided): Quantity to remove (decimal). Does not need to be the full remaining quantity; can be a partial removal. The API prioritizes `remove_quantity` over `quantity` when both are present.
  - `reason` (str, optional): Text explanation for the adjustment
  - `type` (str, required): Adjustment reason type code (see below)
  - `quantity_uom` / `remove_quantity_uom` (str, optional): Unit of measure — `g`, `mg`, `kg`, `oz`, `lb`, or `each`

**Adjustment type codes:**
- `2` — Theft
- `3` — Seizure by Federal, State, Local or Tribal Law Enforcement
- `4` — Correcting a mistake
- `5` — Moisture loss (e.g. wet other plant material)

**Returns:**
- `Dict`: Response with `sessiontime`, `success`, `transactionid` on success
- `None`: If request failed

**API Action:** `inventory_adjust`

**Request pattern (util):** The helper normalizes input to an array: a single dict is wrapped in a list, then sent as `{"data": nodes}` so the API always receives an array of 1 or more nodes.

**Example — single adjustment (set quantity to 0):**
```python
from biotrack_util import get_auth_token, post_inventory_adjust

token = get_auth_token()
if token:
    node = {
        "barcodeid": "6853296789574115",
        "quantity": "0",
        "reason": "Sublot Error - Order Fulfillment",
        "type": "4"
    }
    r = post_inventory_adjust(token, node)
```

**Example — bulk adjustment (many barcodes, same quantity and reason):**
```python
barcodes = ["4805469011436987", "6992985515974772"]  # e.g. from file
nodes = [
    {"barcodeid": b, "quantity": "0", "reason": "Sublot Error - Order Fulfillment", "type": "4"}
    for b in barcodes
]
r = post_inventory_adjust(token, nodes)
```

**Example API Response:**
```json
{
    "sessiontime": "1384476925",
    "success": "1",
    "transactionid": "3278"
}
```

**Usage in Application:**
- Single-item adjust: use a dict for `data`. CLI: `python app.py adjust --barcode <id> --quantity 0 --reason "..."`.
- Bulk adjust: build a list of nodes (same `quantity`, `reason`, `type` per item). CLI: `python app.py adjust_bulk --file barcodes.md --quantity 0 --reason "Sublot Error - Order Fulfillment"` to adjust all barcodes in the file to 0 with that reason.

---

## Usage Patterns

### Pattern 1: Data Synchronization

The application uses a caching pattern where BioTrack data is fetched and stored in the local database:

```python
from api.biotrack import get_auth_token, get_driver_info

# Authenticate
token = get_auth_token()
if not token:
    return {"error": "Authentication failed"}

# Fetch data from BioTrack
drivers_data = get_driver_info(token)
if not drivers_data:
    return {"error": "Failed to fetch drivers"}

# Update local database
for driver_id, driver_info in drivers_data.items():
    existing_driver = db.session.query(Driver).filter_by(biotrack_id=driver_id).first()
    if existing_driver:
        existing_driver.name = driver_info['name']
        existing_driver.is_active = bool(driver_info['is_active'])
    else:
        new_driver = Driver(
            biotrack_id=driver_id,
            name=driver_info['name'],
            is_active=bool(driver_info['is_active'])
        )
        db.session.add(new_driver)

db.session.commit()
```

### Pattern 2: Order Processing with Sublots

When processing orders, the application:
1. Creates sublots from order line items
2. Moves sublots to the appropriate room
3. Creates a manifest for delivery

```python
from api.biotrack import get_auth_token, post_sublot_bulk_create, post_sublot_move

token = get_auth_token()

# Step 1: Create sublots
sublot_data = [
    {"barcodeid": "6853296789574117", "remove_quantity": "10.00"},
    {"barcodeid": "6853296789574118", "remove_quantity": "5.00"}
]

new_barcodes = post_sublot_bulk_create(token, sublot_data)
if not new_barcodes:
    return {"error": "Failed to create sublots"}

# Step 2: Move sublots to room
move_data = [
    {"barcodeid": barcode_id, "room": target_room_id}
    for barcode_id in new_barcodes
]

move_result = post_sublot_move(token, move_data)
if not move_result or move_result.get('success') != '1':
    return {"error": "Failed to move sublots"}
```

### Pattern 3: Trip Manifest Creation

During trip execution, manifests are created with route information:

```python
from api.biotrack import get_auth_token, post_manifest
from datetime import datetime
import time

token = get_auth_token()

# Prepare manifest data with route information
manifest_info = {
    "approximate_departure": route_segment['departure_time'],
    "approximate_arrival": route_segment['arrival_time'],
    "approximate_route": route_segment['route'],
    "stop_number": str(trip_order.sequence_order),
    "barcodeid": new_barcode_ids,
    "vendor_license": vendor_license
}

# Create manifest
manifest_id = post_manifest(
    token,
    manifest_info,
    [driver1.biotrack_id, driver2.biotrack_id],
    vehicle.biotrack_id
)

if manifest_id:
    trip_order.manifest_id = str(manifest_id)
    trip_order.status = 'manifested'
    db.session.commit()
```

---

## Error Handling

### Retry Mechanism

The module includes a `@retry_on_failure` decorator that automatically retries failed API calls with exponential backoff:

- **Max Retries:** 3 (configurable via `MAX_RETRIES`)
- **Initial Delay:** 1 second (configurable via `RETRY_DELAY`)
- **Backoff:** Exponential (delay * 2^attempt)

### Error Response Format

When API calls fail, functions may return error dictionaries:

```python
{
    'success': False,
    'error': 'Error message from BioTrack',
    'errorcode': 'Error code from BioTrack',
    'details': { /* Full response */ }
}
```

### Common Error Scenarios

1. **Authentication Failure:**
   - `get_auth_token()` returns `None`
   - Check credentials and UBI in environment variables

2. **Invalid Token:**
   - Functions return `None` if token validation fails
   - Re-authenticate to get a new token

3. **API Errors:**
   - Check `success` field in response
   - Review `error` and `errorcode` fields for details
   - Log full response for debugging

4. **Network Errors:**
   - Timeout errors (30 second default)
   - Connection errors
   - Automatically retried with exponential backoff

### Logging

The module uses Python's logging framework. All API calls are logged at DEBUG level, errors at ERROR level, and warnings at WARNING level.

---

## Best Practices

### 1. Always Authenticate First

```python
token = get_auth_token()
if not token:
    # Handle authentication failure
    return
```

### 2. Validate Responses

```python
result = some_biotrack_function(token, ...)
if result is None:
    # Handle failure
    return

# Check for error responses
if isinstance(result, dict) and result.get('success') == False:
    error = result.get('error', 'Unknown error')
    # Handle error
    return
```

### 3. Handle Training Mode

The module automatically uses training mode based on application configuration. Ensure your application's `get_training_mode()` function is properly configured.

### 4. Cache Data When Possible

The application caches BioTrack data (drivers, vehicles, vendors, rooms) in the local database to reduce API calls and improve performance.

### 5. Batch Operations

When creating multiple sublots or moving multiple items, use the bulk functions (`post_sublot_bulk_create`, `post_sublot_move`) rather than making individual API calls.

### 6. Error Recovery

Implement proper error handling and recovery:
- Log errors for debugging
- Provide user-friendly error messages
- Consider retry logic for transient failures
- Store error state in database for later review

### 7. Validate Input Data

Before making API calls, validate:
- Barcode IDs are valid (16-digit numbers for BioTrack UIDs)
- Quantities are positive numbers
- Room IDs exist in your system
- Driver/vehicle IDs are valid

---

## API Request/Response Format

### Standard Request Format

All API requests follow this format:

```json
{
    "API": "4.0",
    "action": "action_name",
    "sessionid": "token_from_get_auth_token",
    "training": "0" or "1",
    // ... action-specific fields
}
```

### Standard Response Format

Successful responses typically include:

```json
{
    "sessiontime": "1384476925",
    "success": "1",
    "transactionid": "3278",
    // ... action-specific data
}
```

Error responses include:

```json
{
    "success": "0",
    "error": "Error message",
    "errorcode": "ERROR_CODE"
}
```

---

## Integration Examples

### Example 1: Complete Order Processing Flow

```python
from api.biotrack import (
    get_auth_token,
    post_sublot_bulk_create,
    post_sublot_move,
    post_manifest
)

def process_order_complete(order_data, target_room_id, drivers, vehicle):
    # Authenticate
    token = get_auth_token()
    if not token:
        return {"error": "Authentication failed"}
    
    # Create sublots
    sublot_data = [
        {"barcodeid": item['barcode_id'], "remove_quantity": str(item['quantity'])}
        for item in order_data['line_items']
    ]
    
    new_barcodes = post_sublot_bulk_create(token, sublot_data)
    if not new_barcodes:
        return {"error": "Failed to create sublots"}
    
    # Move to room
    move_data = [
        {"barcodeid": barcode, "room": target_room_id}
        for barcode in new_barcodes
    ]
    
    move_result = post_sublot_move(token, move_data)
    if not move_result or move_result.get('success') != '1':
        return {"error": "Failed to move sublots"}
    
    # Create manifest
    import time
    manifest_info = {
        "approximate_departure": int(time.time()),
        "approximate_arrival": int(time.time()) + 3600,
        "approximate_route": "Route description",
        "stop_number": "1",
        "barcodeid": new_barcodes,
        "vendor_license": order_data['vendor_license']
    }
    
    manifest_id = post_manifest(token, manifest_info, drivers, vehicle)
    if not manifest_id:
        return {"error": "Failed to create manifest"}
    
    return {
        "success": True,
        "sublots": new_barcodes,
        "manifest_id": manifest_id
    }
```

### Example 2: Data Refresh Endpoint

```python
@app.route('/api/biotrack/refresh', methods=['POST'])
def refresh_biotrack_data():
    from api.biotrack import (
        get_auth_token,
        get_driver_info,
        get_vehicle_info,
        get_vendor_info,
        get_room_info
    )
    
    token = get_auth_token()
    if not token:
        return jsonify({'error': 'Authentication failed'}), 500
    
    # Refresh all data types
    drivers = get_driver_info(token)
    vehicles = get_vehicle_info(token)
    vendors = get_vendor_info(token)
    rooms = get_room_info(token)
    
    # Update database (implementation depends on your ORM)
    # ...
    
    return jsonify({'success': True})
```

---

## Notes for Implementation in Other Applications

1. **Dependencies:**
   - `requests` library for HTTP calls
   - `python-dotenv` for environment variable management
   - Python logging framework

2. **Training Mode:**
   - The module imports `get_training_mode()` from the main application
   - You'll need to implement this function or modify the module to use your own training mode logic

3. **Error Handling:**
   - All functions return `None` on failure
   - Some functions return error dictionaries with `success: False`
   - Always check return values before using them

4. **Token Management:**
   - Tokens are session-based and may expire
   - Re-authenticate if you receive authentication errors
   - Consider implementing token caching with expiration

5. **Rate Limiting:**
   - BioTrack may have rate limits
   - The retry mechanism helps with transient failures
   - Consider implementing additional rate limiting if needed

6. **Data Validation:**
   - Validate barcode IDs (must be 16-digit numbers for BioTrack UIDs)
   - Validate quantities are positive numbers
   - Validate room/driver/vehicle IDs exist before using them

---

## Additional Resources

- BioTrack API Documentation (consult BioTrack's official documentation for the latest API specifications)
- Application code: `api/biotrack.py`
- Usage examples: `app.py`, `utils/trip_execution.py`, `utils/rpt_generation.py`
