"""
Simplified report generation - minimal code, maximum functionality
Following .cursorrules: minimal code, modular functions, production ready
"""
import os
import csv
import time
import logging
from datetime import datetime
from io import StringIO
from flask import current_app
from models import db, GlobalPreference
from api.biotrack import get_auth_token, get_inventory_info, get_room_info, get_inventory_qa_check
from utils.inventory_types import get_product_display_name

logger = logging.getLogger('utils.rpt_generation')

def generate_inventory_report_simple():
    """Generate full inventory report - simple and clean"""
    logger.info("Starting inventory report generation")
    
    # Ensure Flask app context
    from app import app
    with app.app_context():
        try:
            # Update status to generating
            _update_report_status('inventory', 'generating')
            
            # Get BioTrack data
            logger.info("Authenticating with BioTrack")
            token = get_auth_token()
            if not token:
                raise Exception("Failed to authenticate with BioTrack API")
            
            logger.info("Fetching inventory data")
            inventory_data = get_inventory_info(token)
            if not inventory_data:
                raise Exception("Failed to retrieve inventory data from BioTrack")
            
            logger.info("Fetching room data")
            room_data = get_room_info(token)
            room_lookup = {}
            if room_data:
                room_lookup = {room_id: room_info['name'] for room_id, room_info in room_data.items()}
            
            # Generate CSV
            logger.info(f"Processing {len(inventory_data)} inventory items")
            csv_content = _create_inventory_csv(inventory_data, room_lookup, token)
            
            # Save file
            filename = f"inventory_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.csv"
            file_path = _save_report_file('inventory', filename, csv_content)
            
            # Update status to ready
            _update_report_status('inventory', 'ready', filename, file_path)
            logger.info(f"Inventory report completed: {file_path}")
            
        except Exception as e:
            logger.error(f"Error generating inventory report: {str(e)}", exc_info=True)
            _update_report_status('inventory', 'error', error=str(e))
            raise

def generate_finished_goods_report_simple():
    """Generate finished goods report with room filtering"""
    logger.info("Starting finished goods report generation")
    
    # Ensure Flask app context
    from app import app
    with app.app_context():
        try:
            # Update status to generating
            _update_report_status('finished_goods', 'generating')
            
            # Get room selection
            selected_rooms = _get_selected_rooms()
            logger.info(f"Selected rooms: {selected_rooms}")
            
            # Get BioTrack data
            logger.info("Authenticating with BioTrack")
            token = get_auth_token()
            if not token:
                raise Exception("Failed to authenticate with BioTrack API")
            
            logger.info("Fetching inventory data")
            inventory_data = get_inventory_info(token)
            if not inventory_data:
                raise Exception("Failed to retrieve inventory data from BioTrack")
            
            logger.info("Fetching room data")
            room_data = get_room_info(token)
            room_lookup = {}
            if room_data:
                room_lookup = {room_id: room_info['name'] for room_id, room_info in room_data.items()}
            
            # Generate filtered CSV
            logger.info(f"Processing {len(inventory_data)} inventory items with filtering")
            csv_content = _create_finished_goods_csv(inventory_data, room_lookup, selected_rooms, token)
            
            # Save file
            filename = f"finished_goods_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.csv"
            file_path = _save_report_file('finished_goods', filename, csv_content)
            
            # Update status to ready
            _update_report_status('finished_goods', 'ready', filename, file_path)
            logger.info(f"Finished goods report completed: {file_path}")
            
        except Exception as e:
            logger.error(f"Error generating finished goods report: {str(e)}", exc_info=True)
            _update_report_status('finished_goods', 'error', error=str(e))
            raise

def _update_report_status(report_type, status, filename=None, file_path=None, error=None):
    """Update report status in GlobalPreference"""
    try:
        # Update status
        _set_preference(f'{report_type}_status', status)
        
        if filename:
            _set_preference(f'{report_type}_file', filename)
        
        if file_path:
            _set_preference(f'{report_type}_file_path', file_path)
        
        if status == 'ready':
            _set_preference(f'{report_type}_timestamp', datetime.now().isoformat())
        
        if error:
            _set_preference(f'{report_type}_error', error)
        
        db.session.commit()
        logger.debug(f"Updated {report_type} status to: {status}")
        
    except Exception as e:
        logger.error(f"Error updating report status: {str(e)}", exc_info=True)
        db.session.rollback()

def _get_report_status(report_type):
    """Get current report status"""
    return _get_preference(f'{report_type}_status', 'none')

def _get_report_file_path(report_type):
    """Get report file path"""
    return _get_preference(f'{report_type}_file_path', '')

def _get_selected_rooms():
    """Get selected rooms from preferences"""
    rooms_str = _get_preference('finished_goods_rooms', '')
    if rooms_str:
        return [room_id.strip() for room_id in rooms_str.split(',') if room_id.strip()]
    return []

def _create_inventory_csv(inventory_data, room_lookup, token):
    """Create inventory CSV content"""
    output = StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'Item ID (Text)', 'Product Name', 'Quantity', 'Current Room ID (Text)', 
        'Current Room Name', 'Lab Data Available', 'Total %', 'THCA %', 
        'THC %', 'CBDA %', 'CBD %'
    ])
    
    # Process inventory items
    for item_id, item_info in inventory_data.items():
        try:
            # Get room name
            current_room_id = item_info.get('currentroom', '')
            current_room_name = room_lookup.get(current_room_id, 'Unknown Room')
            
            # Try to get lab data
            barcode_id = str(item_info.get('barcode_id') or item_info.get('barcode') or item_id)
            lab_results = None
            
            if barcode_id:
                try:
                    lab_results = get_inventory_qa_check(token, barcode_id)
                except Exception:
                    lab_results = None

            # Lab data fields
            if lab_results:
                lab_data_available = 'Yes'
                total_pct = lab_results.get('total', '')
                thca_pct = lab_results.get('thca', '')
                thc_pct = lab_results.get('thc', '')
                cbda_pct = lab_results.get('cbda', '')
                cbd_pct = lab_results.get('cbd', '')
            else:
                lab_data_available = 'No'
                total_pct = thca_pct = thc_pct = cbda_pct = cbd_pct = ''
            
            # Write row
            writer.writerow([
                str(item_id),
                get_product_display_name(item_info),
                item_info.get('remaining_quantity', 0),
                current_room_id,
                current_room_name,
                lab_data_available,
                total_pct,
                thca_pct,
                thc_pct,
                cbda_pct,
                cbd_pct
            ])
            
        except Exception as e:
            logger.warning(f"Error processing inventory item {item_id}: {str(e)}")
            continue
    
    output.seek(0)
    return output.getvalue()

def _calculate_pull_number(product_name):
    """Calculate pull number from product name: C00800 + last 5 characters"""
    if not product_name:
        return 'C00800'
    # Get last 5 characters, pad with zeros if needed
    last_chars = product_name[-5:].zfill(5)
    return f'C00800{last_chars}'

def _calculate_package_unit(inventory_type, product_name):
    """Calculate package unit based on inventory type and product name"""
    if inventory_type == 22:
        return '100.00mg'
    elif inventory_type == 62:
        product_name_lower = product_name.lower() if product_name else ''
        if '.5g' in product_name_lower:
            return '500.00mg'
        elif '1g' in product_name_lower:
            return '1000.00mg'
        else:
            return '1000.00mg'
    else:
        return ''

def _create_finished_goods_csv(inventory_data, room_lookup, selected_rooms, token):
    """Create finished goods CSV content with filtering"""
    output = StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'Batch Ref', 'Pull Number', 'Product Name', 'Quantity', 'Package Unit', 
        'Current Room Name', 'Total %', 'THCA %', 'THC %', 'CBDA %', 'CBD %'
    ])
    
    # Define finished goods inventory types
    finished_goods_types = [22, 23, 24, 25, 28, 34, 35, 36, 37, 38, 39, 45, 62]
    
    # Process inventory items with filtering
    for item_id, item_info in inventory_data.items():
        try:
            # Filter by selected rooms
            current_room_id = item_info.get('currentroom', '')
            if selected_rooms and str(current_room_id) not in selected_rooms:
                continue
            
            # Filter by inventory type
            inventory_type = item_info.get('inventorytype')
            if inventory_type not in finished_goods_types:
                continue
            
            # Get room name
            current_room_name = room_lookup.get(current_room_id, 'Unknown Room')
            
            # Try to get lab data
            barcode_id = str(item_info.get('barcode_id') or item_info.get('barcode') or item_id)
            lab_results = None
            
            if barcode_id:
                try:
                    lab_results = get_inventory_qa_check(token, barcode_id)
                except Exception:
                    lab_results = None

            # Only include items with lab data (QA passed)
            if not lab_results:
                continue
            
            # Extract lab data
            total_pct = lab_results.get('total', '') if lab_results else ''
            thca_pct = lab_results.get('thca', '') if lab_results else ''
            thc_pct = lab_results.get('thc', '') if lab_results else ''
            cbda_pct = lab_results.get('cbda', '') if lab_results else ''
            cbd_pct = lab_results.get('cbd', '') if lab_results else ''
            
            # Calculate new fields
            product_name = get_product_display_name(item_info)
            pull_number = _calculate_pull_number(product_name)
            package_unit = _calculate_package_unit(inventory_type, product_name)
            
            # Write row
            writer.writerow([
                str(item_id),  # Batch Ref
                pull_number,
                product_name,
                item_info.get('remaining_quantity', 0),
                package_unit,
                current_room_name,
                total_pct,
                thca_pct,
                thc_pct,
                cbda_pct,
                cbd_pct
            ])
            
        except Exception as e:
            logger.warning(f"Error processing inventory item {item_id}: {str(e)}")
            continue
    
    output.seek(0)
    return output.getvalue()

def _save_report_file(report_type, filename, csv_content):
    """Save report file to storage directory"""
    # Create storage directory if it doesn't exist
    storage_dir = os.path.join(current_app.root_path, 'storage', 'reports')
    os.makedirs(storage_dir, exist_ok=True)
    
    # Save file
    file_path = os.path.join(storage_dir, filename)
    with open(file_path, 'w', newline='', encoding='utf-8') as f:
        f.write(csv_content)
    
    # Clean up old reports of the same type
    _cleanup_old_reports(report_type, file_path)
    
    return file_path

def _cleanup_old_reports(report_type, current_file_path):
    """Clean up old reports of the same type"""
    try:
        storage_dir = os.path.join(current_app.root_path, 'storage', 'reports')
        if not os.path.exists(storage_dir):
            return
        
        # Find old files of the same type
        for filename in os.listdir(storage_dir):
            if filename.startswith(report_type) and filename != os.path.basename(current_file_path):
                old_file_path = os.path.join(storage_dir, filename)
                try:
                    os.remove(old_file_path)
                    logger.debug(f"Cleaned up old report: {filename}")
                except Exception as e:
                    logger.warning(f"Error cleaning up {filename}: {str(e)}")
                    
    except Exception as e:
        logger.warning(f"Error during cleanup: {str(e)}")

def _get_preference(key, default_value=''):
    """Get preference value"""
    try:
        pref = GlobalPreference.query.filter_by(preference_key=key).first()
        return pref.preference_value if pref else default_value
    except Exception:
        return default_value

def _set_preference(key, value):
    """Set preference value"""
    try:
        pref = GlobalPreference.query.filter_by(preference_key=key).first()
        if pref:
            pref.preference_value = str(value)
        else:
            pref = GlobalPreference(preference_key=key, preference_value=str(value))
            db.session.add(pref)
    except Exception as e:
        logger.error(f"Error setting preference {key}: {str(e)}", exc_info=True)
        raise
