"""
Trip Helper Functions for BizDrive - Sprint 4.5 ENHANCED
Enhanced features: Optional odometer, multiple daily site visits, round trips
Address-based trip tracking with multiple distance entry methods
"""

import sqlite3
from datetime import datetime, date
from decimal import Decimal

# ===============================================
# Database Connection
# ===============================================

def get_db_connection():
    """Create and return a database connection."""
    conn = sqlite3.connect('bizdrive.db')
    conn.row_factory = sqlite3.Row
    return conn


def init_trip_table():
    """Initialize the trips table with enhanced fields - odometer now optional."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            vehicle_id INTEGER NOT NULL,
            trip_date DATE NOT NULL,
            from_address TEXT NOT NULL,
            to_address TEXT NOT NULL,
            start_odometer INTEGER,
            end_odometer INTEGER,
            distance REAL,
            trip_type TEXT NOT NULL CHECK(trip_type IN ('Business', 'Personal')),
            purpose TEXT,
            notes TEXT,
            reimbursement_rate DECIMAL(10,2) DEFAULT 0.88,
            reimbursement_amount DECIMAL(10,2),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE
        )
    ''')
    
    # Create indexes
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_trips_user_vehicle 
        ON trips(user_id, vehicle_id)
    ''')
    
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_trips_date 
        ON trips(trip_date DESC)
    ''')
    
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_trips_type 
        ON trips(trip_type)
    ''')
    
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_trips_daily 
        ON trips(trip_date, user_id)
    ''')
    
    conn.commit()
    conn.close()


# ===============================================
# Reimbursement Rate Management
# ===============================================

def get_default_rate():
    """Get the default reimbursement rate (ATO 2025/2026 rate)."""
    return Decimal('0.88')


def calculate_reimbursement(distance, rate=None):
    """
    Calculate reimbursement amount.
    
    Args:
        distance (int/float): Distance in kilometers (optional)
        rate (Decimal, optional): Rate per km (default: ATO rate)
        
    Returns:
        Decimal: Reimbursement amount (0 if no distance)
    """
    if distance is None or distance == 0:
        return Decimal('0.00')
    
    if rate is None:
        rate = get_default_rate()
    
    return Decimal(str(distance)) * Decimal(str(rate))


# ===============================================
# Trip Validation Functions
# ===============================================

def validate_trip_data(vehicle_id, trip_date, from_address, to_address, trip_type, 
                      start_odometer=None, end_odometer=None, distance=None):
    """
    Validate trip data before adding/updating.
    Supports 3 distance entry methods: odometer, manual distance, or no distance.
    
    Args:
        vehicle_id (int): Vehicle ID
        trip_date (str): Trip date (YYYY-MM-DD)
        from_address (str): Starting address (REQUIRED)
        to_address (str): Destination address (REQUIRED)
        trip_type (str): Trip type (Business/Personal)
        start_odometer (int, optional): Starting odometer reading
        end_odometer (int, optional): Ending odometer reading
        distance (float, optional): Direct distance entry in km
        
    Returns:
        tuple: (is_valid, error_message)
    """
    if not vehicle_id:
        return False, "Vehicle is required."
    
    if not trip_date:
        return False, "Trip date is required."
    
    try:
        trip_date_obj = datetime.strptime(trip_date, '%Y-%m-%d').date()
        if trip_date_obj > date.today():
            return False, "Trip date cannot be in the future."
    except ValueError:
        return False, "Invalid date format. Use YYYY-MM-DD."
    
    if not from_address or not from_address.strip():
        return False, "Starting address is required."
    
    if not to_address or not to_address.strip():
        return False, "Destination address is required."
    
    if trip_type not in ['Business', 'Personal']:
        return False, "Trip type must be 'Business' or 'Personal'."
    
    # Odometer validation (optional)
    if start_odometer is not None or end_odometer is not None:
        if start_odometer is not None and start_odometer < 0:
            return False, "Start odometer reading cannot be negative."
        
        if end_odometer is not None and end_odometer < 0:
            return False, "End odometer reading cannot be negative."
        
        if start_odometer is not None and end_odometer is not None:
            if end_odometer <= start_odometer:
                return False, "End odometer must be greater than start odometer."
            
            calc_distance = end_odometer - start_odometer
            if calc_distance > 2000:
                return False, "Trip distance exceeds 2000 km. Please verify odometer readings."
    
    # Distance validation (optional manual entry)
    if distance is not None:
        if distance < 0:
            return False, "Distance cannot be negative."
        if distance > 5000:
            return False, "Distance exceeds 5000 km. Please verify."
    
    return True, ""


# ===============================================
# Trip CRUD Operations
# ===============================================

def add_trip(user_id, vehicle_id, trip_date, from_address, to_address, trip_type, 
             start_odometer=None, end_odometer=None, purpose=None, notes=None, 
             reimbursement_rate=None, distance=None):
    """
    Add a new trip to the database with optional distance tracking.
    Supports 3 methods: odometer-based, manual distance, or address-only.
    
    Args:
        user_id (int): ID of the user
        vehicle_id (int): ID of the vehicle
        trip_date (str): Trip date (YYYY-MM-DD)
        from_address (str): Starting address (REQUIRED)
        to_address (str): Destination address (REQUIRED)
        trip_type (str): Trip type (Business/Personal)
        start_odometer (int, optional): Starting odometer
        end_odometer (int, optional): Ending odometer
        purpose (str, optional): Trip purpose
        notes (str, optional): Additional notes
        reimbursement_rate (Decimal, optional): Rate per km
        distance (float, optional): Direct distance entry in km
        
    Returns:
        tuple: (success, message, trip_id)
    """
    # Validate data
    is_valid, error_msg = validate_trip_data(vehicle_id, trip_date, from_address, to_address, 
                                             trip_type, start_odometer, end_odometer, distance)
    if not is_valid:
        return False, error_msg, None
    
    # Calculate distance based on available data
    final_distance = None
    
    # Method 1: Calculate from odometer readings
    if start_odometer is not None and end_odometer is not None:
        final_distance = end_odometer - start_odometer
    # Method 2: Use manually entered distance
    elif distance is not None and distance > 0:
        final_distance = distance
    # Method 3: No distance (address-only trip)
    
    if reimbursement_rate is None:
        reimbursement_rate = get_default_rate()
    else:
        reimbursement_rate = Decimal(str(reimbursement_rate))
    
    # Only calculate reimbursement for business trips with distance
    reimbursement_amount = calculate_reimbursement(final_distance, reimbursement_rate) if trip_type == 'Business' else Decimal('0.00')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Verify vehicle belongs to user
        cursor.execute('SELECT id FROM vehicles WHERE id = ? AND user_id = ?', 
                      (vehicle_id, user_id))
        if not cursor.fetchone():
            conn.close()
            return False, "Vehicle not found or you don't have permission.", None
        
        # Insert trip
        cursor.execute('''
            INSERT INTO trips (user_id, vehicle_id, trip_date, from_address, to_address, 
                             start_odometer, end_odometer, distance, trip_type, 
                             purpose, notes, reimbursement_rate, reimbursement_amount)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, vehicle_id, trip_date, from_address.strip(), to_address.strip(), 
              start_odometer, end_odometer, final_distance, trip_type, purpose, notes, 
              float(reimbursement_rate), float(reimbursement_amount)))
        
        trip_id = cursor.lastrowid
        
        # Update vehicle odometer only if end_odometer provided
        if end_odometer is not None:
            cursor.execute('''
                UPDATE vehicles 
                SET odometer = ?, updated_at = ?
                WHERE id = ?
            ''', (end_odometer, datetime.now(), vehicle_id))
        
        conn.commit()
        conn.close()
        return True, "Trip logged successfully!", trip_id
        
    except Exception as e:
        conn.close()
        return False, f"Database error: {str(e)}", None


def get_user_trips(user_id, vehicle_id=None, trip_type=None, start_date=None, 
                   end_date=None, trip_date=None, limit=None):
    """
    Get trips for a user with optional filters.
    
    Args:
        user_id (int): User ID
        vehicle_id (int, optional): Filter by vehicle
        trip_type (str, optional): Filter by type (Business/Personal)
        start_date (str, optional): Filter from date (YYYY-MM-DD)
        end_date (str, optional): Filter to date (YYYY-MM-DD)
        trip_date (str, optional): Filter by exact date (YYYY-MM-DD)
        limit (int, optional): Limit number of results
        
    Returns:
        list: List of trip dictionaries
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = '''
        SELECT t.*, v.registration, v.make, v.model
        FROM trips t
        JOIN vehicles v ON t.vehicle_id = v.id
        WHERE t.user_id = ?
    '''
    params = [user_id]
    
    if vehicle_id:
        query += ' AND t.vehicle_id = ?'
        params.append(vehicle_id)
    
    if trip_type:
        query += ' AND t.trip_type = ?'
        params.append(trip_type)
    
    if trip_date:
        query += ' AND t.trip_date = ?'
        params.append(trip_date)
    
    if start_date:
        query += ' AND t.trip_date >= ?'
        params.append(start_date)
    
    if end_date:
        query += ' AND t.trip_date <= ?'
        params.append(end_date)
    
    query += ' ORDER BY t.trip_date DESC, t.created_at DESC'
    
    if limit:
        query += ' LIMIT ?'
        params.append(limit)
    
    cursor.execute(query, params)
    trips = cursor.fetchall()
    conn.close()
    
    return [dict(trip) for trip in trips]


def get_daily_trips(user_id, trip_date, vehicle_id=None):
    """
    Get all trips for a specific date (for multiple daily site visits).
    
    Args:
        user_id (int): User ID
        trip_date (str): Trip date (YYYY-MM-DD)
        vehicle_id (int, optional): Filter by vehicle
        
    Returns:
        list: List of trips for that day
    """
    return get_user_trips(user_id, vehicle_id=vehicle_id, trip_date=trip_date)


def get_trip_by_id(trip_id, user_id):
    """Get a specific trip by ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT t.*, v.registration, v.make, v.model
        FROM trips t
        JOIN vehicles v ON t.vehicle_id = v.id
        WHERE t.id = ? AND t.user_id = ?
    ''', (trip_id, user_id))
    
    trip = cursor.fetchone()
    conn.close()
    
    return dict(trip) if trip else None


def update_trip(trip_id, user_id, vehicle_id=None, trip_date=None, 
                from_address=None, to_address=None, start_odometer=None, 
                end_odometer=None, trip_type=None, purpose=None, notes=None,
                reimbursement_rate=None, distance=None):
    """
    Update an existing trip.
    
    Args:
        trip_id (int): Trip ID to update
        user_id (int): User ID (for security check)
        Other args: Fields to update (None = don't update)
        
    Returns:
        tuple: (success, message)
    """
    trip = get_trip_by_id(trip_id, user_id)
    if not trip:
        return False, "Trip not found or you don't have permission to edit it."
    
    # Collect new values or use existing
    new_vehicle_id = vehicle_id if vehicle_id is not None else trip['vehicle_id']
    new_trip_date = trip_date if trip_date is not None else trip['trip_date']
    new_from = from_address if from_address is not None else trip['from_address']
    new_to = to_address if to_address is not None else trip['to_address']
    new_type = trip_type if trip_type is not None else trip['trip_type']
    new_start = start_odometer if start_odometer is not None else trip['start_odometer']
    new_end = end_odometer if end_odometer is not None else trip['end_odometer']
    new_distance = distance if distance is not None else trip['distance']
    
    # Validate the complete trip data
    is_valid, error_msg = validate_trip_data(new_vehicle_id, new_trip_date, 
                                             new_from, new_to, new_type, new_start, new_end, new_distance)
    if not is_valid:
        return False, error_msg
    
    # Build update query
    updates = []
    values = []
    
    if vehicle_id is not None:
        updates.append("vehicle_id = ?")
        values.append(vehicle_id)
    
    if trip_date is not None:
        updates.append("trip_date = ?")
        values.append(trip_date)
    
    if from_address is not None:
        updates.append("from_address = ?")
        values.append(from_address.strip())
    
    if to_address is not None:
        updates.append("to_address = ?")
        values.append(to_address.strip())
    
    if start_odometer is not None:
        updates.append("start_odometer = ?")
        values.append(start_odometer)
    
    if end_odometer is not None:
        updates.append("end_odometer = ?")
        values.append(end_odometer)
    
    if trip_type is not None:
        updates.append("trip_type = ?")
        values.append(trip_type)
    
    if purpose is not None:
        updates.append("purpose = ?")
        values.append(purpose)
    
    if notes is not None:
        updates.append("notes = ?")
        values.append(notes)
    
    if reimbursement_rate is not None:
        updates.append("reimbursement_rate = ?")
        values.append(float(reimbursement_rate))
    
    # Recalculate distance based on what was updated
    calc_distance = None
    if start_odometer is not None or end_odometer is not None:
        calc_start = start_odometer if start_odometer is not None else trip['start_odometer']
        calc_end = end_odometer if end_odometer is not None else trip['end_odometer']
        
        if calc_start is not None and calc_end is not None:
            calc_distance = calc_end - calc_start
    elif distance is not None:
        calc_distance = distance
    else:
        calc_distance = trip['distance']
    
    # Always update distance
    updates.append("distance = ?")
    values.append(calc_distance)
    
    # Recalculate reimbursement
    rate = Decimal(str(reimbursement_rate)) if reimbursement_rate is not None else Decimal(str(trip['reimbursement_rate']))
    reimbursement = calculate_reimbursement(calc_distance, rate) if new_type == 'Business' else Decimal('0.00')
    
    updates.append("reimbursement_amount = ?")
    values.append(float(reimbursement))
    
    if not updates:
        return False, "No fields to update."
    
    updates.append("updated_at = ?")
    values.append(datetime.now())
    
    values.extend([trip_id, user_id])
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        query = f"UPDATE trips SET {', '.join(updates)} WHERE id = ? AND user_id = ?"
        cursor.execute(query, values)
        conn.commit()
        conn.close()
        return True, "Trip updated successfully!"
    except Exception as e:
        conn.close()
        return False, f"Database error: {str(e)}"


def delete_trip(trip_id, user_id):
    """Delete a trip from the database."""
    trip = get_trip_by_id(trip_id, user_id)
    if not trip:
        return False, "Trip not found or you don't have permission to delete it."
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('DELETE FROM trips WHERE id = ? AND user_id = ?', 
                      (trip_id, user_id))
        conn.commit()
        conn.close()
        return True, "Trip deleted successfully!"
    except Exception as e:
        conn.close()
        return False, f"Database error: {str(e)}"


# ===============================================
# Trip Statistics Functions
# ===============================================

def get_vehicle_trip_stats(vehicle_id, user_id, start_date=None, end_date=None):
    """
    Get trip statistics for a specific vehicle.
    
    Returns:
        dict: Trip statistics including reimbursement totals
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = '''
        SELECT 
            COUNT(*) as total_trips,
            COALESCE(SUM(distance), 0) as total_distance,
            COALESCE(SUM(CASE WHEN trip_type = 'Business' AND distance IS NOT NULL THEN distance ELSE 0 END), 0) as business_distance,
            COALESCE(SUM(CASE WHEN trip_type = 'Personal' AND distance IS NOT NULL THEN distance ELSE 0 END), 0) as personal_distance,
            COALESCE(SUM(CASE WHEN trip_type = 'Business' THEN reimbursement_amount ELSE 0 END), 0) as total_reimbursement
        FROM trips
        WHERE vehicle_id = ? AND user_id = ?
    '''
    params = [vehicle_id, user_id]
    
    if start_date:
        query += ' AND trip_date >= ?'
        params.append(start_date)
    
    if end_date:
        query += ' AND trip_date <= ?'
        params.append(end_date)
    
    cursor.execute(query, params)
    result = cursor.fetchone()
    conn.close()
    
    stats = dict(result)
    
    if stats['total_distance'] and stats['total_distance'] > 0:
        stats['business_percentage'] = round(
            (stats['business_distance'] / stats['total_distance']) * 100, 1
        )
    else:
        stats['business_percentage'] = 0.0
    
    return stats


def get_user_trip_stats(user_id, start_date=None, end_date=None):
    """
    Get overall trip statistics for a user.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = '''
        SELECT 
            COUNT(*) as total_trips,
            COALESCE(SUM(distance), 0) as total_distance,
            COALESCE(SUM(CASE WHEN trip_type = 'Business' AND distance IS NOT NULL THEN distance ELSE 0 END), 0) as business_distance,
            COALESCE(SUM(CASE WHEN trip_type = 'Personal' AND distance IS NOT NULL THEN distance ELSE 0 END), 0) as personal_distance,
            COALESCE(SUM(CASE WHEN trip_type = 'Business' THEN reimbursement_amount ELSE 0 END), 0) as total_reimbursement
        FROM trips
        WHERE user_id = ?
    '''
    params = [user_id]
    
    if start_date:
        query += ' AND trip_date >= ?'
        params.append(start_date)
    
    if end_date:
        query += ' AND trip_date <= ?'
        params.append(end_date)
    
    cursor.execute(query, params)
    result = cursor.fetchone()
    conn.close()
    
    stats = dict(result)
    
    if stats['total_distance'] and stats['total_distance'] > 0:
        stats['business_percentage'] = round(
            (stats['business_distance'] / stats['total_distance']) * 100, 1
        )
    else:
        stats['business_percentage'] = 0.0
    
    return stats


def get_monthly_trip_stats(user_id, year, month):
    """Get trip statistics for a specific month."""
    from calendar import monthrange
    
    start_date = f"{year}-{month:02d}-01"
    last_day = monthrange(year, month)[1]
    end_date = f"{year}-{month:02d}-{last_day}"
    
    return get_user_trip_stats(user_id, start_date, end_date)


def get_trip_count(user_id, vehicle_id=None, trip_type=None):
    """Get count of trips with optional filters."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = 'SELECT COUNT(*) FROM trips WHERE user_id = ?'
    params = [user_id]
    
    if vehicle_id:
        query += ' AND vehicle_id = ?'
        params.append(vehicle_id)
    
    if trip_type:
        query += ' AND trip_type = ?'
        params.append(trip_type)
    
    cursor.execute(query, params)
    count = cursor.fetchone()[0]
    conn.close()
    
    return count