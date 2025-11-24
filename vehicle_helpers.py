"""
Vehicle Helper Functions for BizDrive
This module contains utility functions for vehicle management operations.
"""

import os
import sqlite3
from datetime import datetime

# ===============================================
# Database Connection
# ===============================================

def get_db_connection():
    """Create and return a database connection."""
    conn = sqlite3.connect(os.path.join(os.path.dirname(__file__), 'bizdrive.db'))
    conn.row_factory = sqlite3.Row
    return conn


def init_vehicle_table():
    """Initialize the vehicles table in the database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vehicles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            registration TEXT UNIQUE NOT NULL,
            make TEXT NOT NULL,
            model TEXT NOT NULL,
            year INTEGER,
            color TEXT,
            odometer INTEGER DEFAULT 0,
            status TEXT DEFAULT 'Active',
            purchase_date DATE,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    
    conn.commit()
    conn.close()


# ===============================================
# Vehicle Validation Functions
# ===============================================

def validate_registration(registration):
    """
    Validate Australian vehicle registration format.
    Accepts various formats: ABC123, ABC-123, 1ABC23, etc.
    
    Args:
        registration (str): Registration number to validate
        
    Returns:
        tuple: (is_valid, error_message)
    """
    if not registration:
        return False, "Registration number is required."
    
    # Remove spaces and convert to uppercase
    reg = registration.strip().upper().replace(' ', '').replace('-', '')
    
    if len(reg) < 4 or len(reg) > 7:
        return False, "Registration must be 4-7 characters."
    
    # Allow letters and numbers
    if not reg.isalnum():
        return False, "Registration can only contain letters and numbers."
    
    return True, ""


def validate_vehicle_data(registration, make, model, year=None, odometer=None):
    """
    Validate vehicle data before adding/updating.
    
    Args:
        registration (str): Vehicle registration
        make (str): Vehicle make
        model (str): Vehicle model
        year (int, optional): Year of manufacture
        odometer (int, optional): Odometer reading
        
    Returns:
        tuple: (is_valid, error_message)
    """
    # Validate registration
    reg_valid, reg_error = validate_registration(registration)
    if not reg_valid:
        return False, reg_error
    
    # Validate make
    if not make or len(make.strip()) < 2:
        return False, "Vehicle make is required (minimum 2 characters)."
    
    if len(make) > 50:
        return False, "Vehicle make is too long (maximum 50 characters)."
    
    # Validate model
    if not model or len(model.strip()) < 1:
        return False, "Vehicle model is required."
    
    if len(model) > 50:
        return False, "Vehicle model is too long (maximum 50 characters)."
    
    # Validate year if provided
    if year is not None:
        current_year = datetime.now().year
        if year < 1900 or year > current_year + 1:
            return False, f"Year must be between 1900 and {current_year + 1}."
    
    # Validate odometer if provided
    if odometer is not None:
        if odometer < 0:
            return False, "Odometer reading cannot be negative."
        if odometer > 9999999:
            return False, "Odometer reading is too high."
    
    return True, ""


# ===============================================
# Vehicle CRUD Operations
# ===============================================

def add_vehicle(user_id, registration, make, model, year=None, color=None, 
                odometer=0, status='Active', purchase_date=None, notes=None):
    """
    Add a new vehicle to the database.
    
    Args:
        user_id (int): ID of the user who owns the vehicle
        registration (str): Vehicle registration number
        make (str): Vehicle make
        model (str): Vehicle model
        year (int, optional): Year of manufacture
        color (str, optional): Vehicle color
        odometer (int): Current odometer reading
        status (str): Vehicle status (Active/Inactive)
        purchase_date (str, optional): Date of purchase (YYYY-MM-DD)
        notes (str, optional): Additional notes
        
    Returns:
        tuple: (success, message, vehicle_id)
    """
    # Normalize registration (uppercase, no spaces/dashes)
    registration = registration.strip().upper().replace(' ', '').replace('-', '')
    
    # Validate data
    is_valid, error_msg = validate_vehicle_data(registration, make, model, year, odometer)
    if not is_valid:
        return False, error_msg, None
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO vehicles (user_id, registration, make, model, year, color, 
                                odometer, status, purchase_date, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, registration, make.strip(), model.strip(), year, 
              color, odometer, status, purchase_date, notes))
        
        vehicle_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return True, "Vehicle added successfully!", vehicle_id
        
    except sqlite3.IntegrityError:
        conn.close()
        return False, "This registration number already exists.", None
    except Exception as e:
        conn.close()
        return False, f"Database error: {str(e)}", None


def get_user_vehicles(user_id, status=None):
    """
    Get all vehicles for a specific user.
    
    Args:
        user_id (int): User ID
        status (str, optional): Filter by status (Active/Inactive)
        
    Returns:
        list: List of vehicle dictionaries
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if status:
        cursor.execute('''
            SELECT * FROM vehicles 
            WHERE user_id = ? AND status = ?
            ORDER BY registration
        ''', (user_id, status))
    else:
        cursor.execute('''
            SELECT * FROM vehicles 
            WHERE user_id = ?
            ORDER BY registration
        ''', (user_id,))
    
    vehicles = cursor.fetchall()
    conn.close()
    
    return [dict(vehicle) for vehicle in vehicles]


def get_vehicle_by_id(vehicle_id, user_id):
    """
    Get a specific vehicle by ID (with user validation).
    
    Args:
        vehicle_id (int): Vehicle ID
        user_id (int): User ID (for security check)
        
    Returns:
        dict or None: Vehicle information or None if not found/not authorized
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM vehicles 
        WHERE id = ? AND user_id = ?
    ''', (vehicle_id, user_id))
    
    vehicle = cursor.fetchone()
    conn.close()
    
    return dict(vehicle) if vehicle else None


def get_vehicle_by_registration(registration, user_id):
    """
    Get a vehicle by registration number.
    
    Args:
        registration (str): Vehicle registration
        user_id (int): User ID
        
    Returns:
        dict or None: Vehicle information or None if not found
    """
    registration = registration.strip().upper().replace(' ', '').replace('-', '')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM vehicles 
        WHERE registration = ? AND user_id = ?
    ''', (registration, user_id))
    
    vehicle = cursor.fetchone()
    conn.close()
    
    return dict(vehicle) if vehicle else None


def update_vehicle(vehicle_id, user_id, registration=None, make=None, model=None,
                   year=None, color=None, odometer=None, status=None, 
                   purchase_date=None, notes=None):
    """
    Update an existing vehicle.
    
    Args:
        vehicle_id (int): Vehicle ID to update
        user_id (int): User ID (for security check)
        Other args: Fields to update (None = don't update)
        
    Returns:
        tuple: (success, message)
    """
    # Check if vehicle exists and belongs to user
    vehicle = get_vehicle_by_id(vehicle_id, user_id)
    if not vehicle:
        return False, "Vehicle not found or you don't have permission to edit it."
    
    # Build update query dynamically
    updates = []
    values = []
    
    if registration is not None:
        registration = registration.strip().upper().replace(' ', '').replace('-', '')
        reg_valid, reg_error = validate_registration(registration)
        if not reg_valid:
            return False, reg_error
        updates.append("registration = ?")
        values.append(registration)
    
    if make is not None:
        if len(make.strip()) < 2:
            return False, "Vehicle make must be at least 2 characters."
        updates.append("make = ?")
        values.append(make.strip())
    
    if model is not None:
        if len(model.strip()) < 1:
            return False, "Vehicle model is required."
        updates.append("model = ?")
        values.append(model.strip())
    
    if year is not None:
        current_year = datetime.now().year
        if year < 1900 or year > current_year + 1:
            return False, f"Year must be between 1900 and {current_year + 1}."
        updates.append("year = ?")
        values.append(year)
    
    if color is not None:
        updates.append("color = ?")
        values.append(color)
    
    if odometer is not None:
        if odometer < 0:
            return False, "Odometer reading cannot be negative."
        updates.append("odometer = ?")
        values.append(odometer)
    
    if status is not None:
        if status not in ['Active', 'Inactive']:
            return False, "Status must be 'Active' or 'Inactive'."
        updates.append("status = ?")
        values.append(status)
    
    if purchase_date is not None:
        updates.append("purchase_date = ?")
        values.append(purchase_date)
    
    if notes is not None:
        updates.append("notes = ?")
        values.append(notes)
    
    if not updates:
        return False, "No fields to update."
    
    # Add updated timestamp
    updates.append("updated_at = ?")
    values.append(datetime.now())
    
    # Add WHERE clause values
    values.extend([vehicle_id, user_id])
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        query = f"UPDATE vehicles SET {', '.join(updates)} WHERE id = ? AND user_id = ?"
        cursor.execute(query, values)
        conn.commit()
        conn.close()
        return True, "Vehicle updated successfully!"
        
    except sqlite3.IntegrityError:
        conn.close()
        return False, "This registration number already exists."
    except Exception as e:
        conn.close()
        return False, f"Database error: {str(e)}"


def delete_vehicle(vehicle_id, user_id):
    """
    Delete a vehicle from the database.
    
    Args:
        vehicle_id (int): Vehicle ID to delete
        user_id (int): User ID (for security check)
        
    Returns:
        tuple: (success, message)
    """
    # Check if vehicle exists and belongs to user
    vehicle = get_vehicle_by_id(vehicle_id, user_id)
    if not vehicle:
        return False, "Vehicle not found or you don't have permission to delete it."
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('DELETE FROM vehicles WHERE id = ? AND user_id = ?', 
                      (vehicle_id, user_id))
        conn.commit()
        conn.close()
        return True, f"Vehicle {vehicle['registration']} deleted successfully!"
        
    except Exception as e:
        conn.close()
        return False, f"Database error: {str(e)}"


def get_vehicle_count(user_id, status=None):
    """
    Get count of vehicles for a user.
    
    Args:
        user_id (int): User ID
        status (str, optional): Filter by status
        
    Returns:
        int: Vehicle count
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if status:
        cursor.execute('SELECT COUNT(*) FROM vehicles WHERE user_id = ? AND status = ?',
                      (user_id, status))
    else:
        cursor.execute('SELECT COUNT(*) FROM vehicles WHERE user_id = ?', (user_id,))
    
    count = cursor.fetchone()[0]
    conn.close()
    return count