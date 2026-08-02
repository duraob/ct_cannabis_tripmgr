from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, UTC
from utils.timezone import get_est_now_naive

db = SQLAlchemy()

class User(UserMixin, db.Model):
    """User model for authentication"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='user')  # admin, user
    created_at = db.Column(db.DateTime, default=get_est_now_naive)
    is_active = db.Column(db.Boolean, default=True)

class Trip(db.Model):
    """Trip model representing a delivery trip"""
    id = db.Column(db.Integer, primary_key=True)
    status = db.Column(db.String(20), default='pending')  # pending, completed
    date_created = db.Column(db.DateTime, default=get_est_now_naive)
    date_transacted = db.Column(db.DateTime)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    # Trip execution details
    driver1_id = db.Column(db.Integer, db.ForeignKey('driver.id'))
    driver2_id = db.Column(db.Integer, db.ForeignKey('driver.id'))
    vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicle.id'))
    departure_time = db.Column(db.DateTime)
    estimated_completion_time = db.Column(db.DateTime)
    route_data = db.Column(db.Text)  # JSON data from Google Maps route optimization (renamed from route_instructions)
    
    # Trip scheduling details
    approximate_start_time = db.Column(db.DateTime, nullable=True)
    delivery_date = db.Column(db.Date, nullable=True)
    
    # Background execution status
    execution_status = db.Column(db.String(20), default='pending')  # pending, processing, completed, failed
    
    # Relationships
    orders = db.relationship('Order', backref='trip', lazy=True)
    trip_orders = db.relationship('TripOrder', backref='trip', lazy=True)
    driver1 = db.relationship('Driver', foreign_keys=[driver1_id])
    driver2 = db.relationship('Driver', foreign_keys=[driver2_id])
    vehicle = db.relationship('Vehicle', backref='trips', lazy=True)
    execution = db.relationship('TripExecution', backref='trip', uselist=False)

    # Declared so autogenerate does not try to drop them - they were created directly
    # in revision a1b2c3d4e5f6 and exist in the database already.
    __table_args__ = (
        db.Index('idx_trip_date_created', 'date_created'),
        db.Index('idx_trip_execution_status', 'execution_status'),
    )

class Order(db.Model):
    """Order model representing orders from LeafTrade"""
    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey('trip.id'), nullable=True)
    leaftrade_order_id = db.Column(db.String(100), unique=True, nullable=False)
    invoice_id = db.Column(db.String(100))
    biotrack_manifest_id = db.Column(db.String(100))
    delivery_date = db.Column(db.Date)
    customer_name = db.Column(db.String(200))
    customer_contact = db.Column(db.String(200))
    customer_location = db.Column(db.String(500))
    order_status = db.Column(db.String(50), default='pending')
    created_at = db.Column(db.DateTime, default=get_est_now_naive)
    updated_at = db.Column(db.DateTime, default=get_est_now_naive, onupdate=get_est_now_naive)

class TripOrder(db.Model):
    """Trip orders junction table with sequence and room override"""
    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey('trip.id'), nullable=False)
    order_id = db.Column(db.String(255), nullable=False)  # LeafTrade order ID
    sequence_order = db.Column(db.Integer, nullable=False)
    room_override = db.Column(db.String(255))  # BioTrack room override
    manifest_id = db.Column(db.String(255))  # BioTrack manifest ID
    created_at = db.Column(db.DateTime, default=get_est_now_naive)
    address = db.Column(db.String(500)) # Address of the dispensary
    
    # Vendor relationship for BioTrack integration
    vendor_id = db.Column(db.Integer, db.ForeignKey('vendor.id'), nullable=True)
    vendor = db.relationship('Vendor', backref='trip_orders')

    # Exact dispensary mapping this stop resolved to. A BioTrack license can be shared by
    # more than one LeafTrade location, so the vendor alone does not identify the store's
    # phone number or its manifest email contacts.
    location_mapping_id = db.Column(db.Integer, db.ForeignKey('location_mapping.id'), nullable=True)
    location_mapping = db.relationship('LocationMapping', backref='trip_orders')
    
    # Execution status tracking
    status = db.Column(db.String(20), default='pending')  # pending, sublotted, inventory_moved, manifested
    error_message = db.Column(db.Text, nullable=True)  # Order-specific error messages

    # Manifest email audit. Records the most recent send so a stop cannot be re-sent
    # unknowingly; recipients are snapshotted because contacts can change afterwards.
    manifest_sent_at = db.Column(db.DateTime, nullable=True)
    manifest_sent_to = db.Column(db.Text, nullable=True)  # comma separated To + CC
    manifest_send_count = db.Column(db.Integer, default=0)

    # Declared so autogenerate does not try to drop them - they were created directly
    # in revision a1b2c3d4e5f6 and exist in the database already.
    __table_args__ = (
        db.Index('idx_trip_order_trip_id', 'trip_id'),
        db.Index('idx_trip_order_vendor_id', 'vendor_id'),
        db.Index('idx_trip_order_order_id', 'order_id'),
        db.Index('idx_trip_order_status', 'status'),
    )

class TripOrderItem(db.Model):
    """LeafTrade line item captured at execution, paired with the BioTrack sublot created for it.

    Written by trip execution after a successful inventory_split, by zipping the filtered
    request list against the returned barcode IDs (BioTrack returns them in input order).
    The sublot barcode is what prints as 'Batch / Lot ID' on the manifest.
    """
    id = db.Column(db.Integer, primary_key=True)
    trip_order_id = db.Column(db.Integer, db.ForeignKey('trip_order.id'), nullable=False)
    product_name = db.Column(db.String(300))
    quantity = db.Column(db.Integer)
    line_total = db.Column(db.Numeric(12, 2))  # LeafTrade net line total at execution time
    parent_barcode_id = db.Column(db.String(50))  # BioTrack parent lot (LeafTrade batch_ref)
    sublot_barcode_id = db.Column(db.String(50), nullable=True)  # BioTrack sublot UID
    created_at = db.Column(db.DateTime, default=get_est_now_naive)

    trip_order = db.relationship('TripOrder', backref='items')

class Driver(db.Model):
    """Driver model representing drivers from BioTrack"""
    id = db.Column(db.Integer, primary_key=True)
    biotrack_id = db.Column(db.String(100), unique=True)
    name = db.Column(db.String(200), nullable=False)
    dob = db.Column(db.String(10))  # MM/DD/YYYY as printed on the manifest
    is_active = db.Column(db.Boolean, default=True)

class Vehicle(db.Model):
    """Vehicle model representing vehicles from BioTrack"""
    id = db.Column(db.Integer, primary_key=True)
    biotrack_id = db.Column(db.String(100), unique=True)
    name = db.Column(db.String(200), nullable=False)
    vin = db.Column(db.String(50))
    color = db.Column(db.String(50))
    make = db.Column(db.String(100))
    model = db.Column(db.String(100))
    plate = db.Column(db.String(50))
    year = db.Column(db.String(10))
    is_active = db.Column(db.Boolean, default=True)

class Vendor(db.Model):
    """Vendor model representing BioTrack vendors"""
    id = db.Column(db.Integer, primary_key=True)
    biotrack_vendor_id = db.Column(db.String(100), unique=True)  # Location (license)
    name = db.Column(db.String(200), nullable=False)
    license_info = db.Column(db.String(500))
    ubi = db.Column(db.String(100))  # UBI for manifest creation
    # Registered licensed premises, printed as the manifest destination address
    address1 = db.Column(db.String(300))
    address2 = db.Column(db.String(300))
    city = db.Column(db.String(100))
    state = db.Column(db.String(50))
    zip = db.Column(db.String(20))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=get_est_now_naive)
    updated_at = db.Column(db.DateTime, default=get_est_now_naive, onupdate=get_est_now_naive)

class Room(db.Model):
    """Room model representing BioTrack rooms"""
    id = db.Column(db.Integer, primary_key=True)
    biotrack_room_id = db.Column(db.String(100), unique=True)
    name = db.Column(db.String(200), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=get_est_now_naive)
    updated_at = db.Column(db.DateTime, default=get_est_now_naive, onupdate=get_est_now_naive)

class Customer(db.Model):
    """Customer model representing LeafTrade customers"""
    id = db.Column(db.Integer, primary_key=True)
    leaftrade_customer_id = db.Column(db.String(100), unique=True)  # LeafTrade customer ID
    customer_name = db.Column(db.String(200), nullable=False)
    name = db.Column(db.String(200), nullable=False)  # Location name
    address = db.Column(db.String(500))
    city = db.Column(db.String(100))
    state = db.Column(db.String(50))
    zip = db.Column(db.String(20))
    country = db.Column(db.String(100))
    phone = db.Column(db.String(50))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=get_est_now_naive)
    updated_at = db.Column(db.DateTime, default=get_est_now_naive, onupdate=get_est_now_naive)

class LocationMapping(db.Model):
    """Mapping between LeafTrade dispensary locations and BioTrack vendors/rooms"""
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    leaftrade_dispensary_location_id = db.Column(db.Integer, nullable=False)  # LeafTrade dispensary location ID
    biotrack_vendor_id = db.Column(db.String(100), nullable=False)
    default_biotrack_room_id = db.Column(db.String(100))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=get_est_now_naive)
    updated_at = db.Column(db.DateTime, default=get_est_now_naive, onupdate=get_est_now_naive)
    
    # Relationships
    customer = db.relationship('Customer', backref='location_mappings')
    
    # The two indexes were created directly in revision a1b2c3d4e5f6 and exist in the
    # database already; they are declared here so autogenerate does not try to drop them.
    __table_args__ = (
        db.UniqueConstraint('leaftrade_dispensary_location_id', 'biotrack_vendor_id', name='unique_location_mapping'),
        db.Index('idx_location_mapping_dispensary_id', 'leaftrade_dispensary_location_id'),
        db.Index('idx_location_mapping_vendor_id', 'biotrack_vendor_id'),
    )

class EmailContact(db.Model):
    """Manifest email recipients.

    location_mapping_id set  -> 'To' recipient for that dispensary location.
    location_mapping_id NULL -> internal staff CC'd on every manifest send.
    """
    id = db.Column(db.Integer, primary_key=True)
    location_mapping_id = db.Column(db.Integer, db.ForeignKey('location_mapping.id'), nullable=True)
    name = db.Column(db.String(200))
    email = db.Column(db.String(200), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=get_est_now_naive)

    location_mapping = db.relationship('LocationMapping', backref='email_contacts')

class APIRefreshLog(db.Model):
    """Track when API data was last refreshed"""
    id = db.Column(db.Integer, primary_key=True)
    api_name = db.Column(db.String(50), nullable=False)  # 'drivers', 'vehicles', 'orders'
    last_refresh = db.Column(db.DateTime, default=get_est_now_naive)
    records_count = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='success')  # 'success', 'error'
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=get_est_now_naive)
    
    __table_args__ = (db.UniqueConstraint('api_name', name='unique_api_name'),)

# Junction table for many-to-many relationship between trips and drivers
trip_drivers = db.Table('trip_drivers',
    db.Column('trip_id', db.Integer, db.ForeignKey('trip.id'), primary_key=True),
    db.Column('driver_id', db.Integer, db.ForeignKey('driver.id'), primary_key=True)
)

class TripExecution(db.Model):
    """Trip execution tracking model"""
    __tablename__ = 'trip_executions'
    
    trip_id = db.Column(db.Integer, db.ForeignKey('trip.id'), primary_key=True)
    status = db.Column(db.String(20), default='pending')  # pending, processing, completed, failed
    progress_message = db.Column(db.Text)
    job_id = db.Column(db.String(100))  # RQ job ID
    created_at = db.Column(db.DateTime, default=get_est_now_naive)
    updated_at = db.Column(db.DateTime, default=get_est_now_naive, onupdate=get_est_now_naive)
    started_at = db.Column(db.DateTime, nullable=True)  # When execute button was clicked
    completed_at = db.Column(db.DateTime, nullable=True)  # When execution finished
    general_error = db.Column(db.Text, nullable=True)  # General trip-level errors

class GlobalPreference(db.Model):
    """Global preferences model for system-wide settings"""
    id = db.Column(db.Integer, primary_key=True)
    preference_key = db.Column(db.String(255), unique=True, nullable=False)
    preference_value = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=get_est_now_naive)
    updated_at = db.Column(db.DateTime, default=get_est_now_naive, onupdate=get_est_now_naive)
