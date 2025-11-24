import sqlite3
import os
from datetime import datetime

import os
DATABASE = os.path.join(os.path.dirname(__file__), 'bizdrive.db')
ACCIDENT_PHOTO_FOLDER = 'static/accident_photos'

# Ensure photo folder exists
os.makedirs(ACCIDENT_PHOTO_FOLDER, exist_ok=True)

def init_accident_table():
    """Create accident tables if they do not exist."""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # Main accidents table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS accidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            vehicle_id INTEGER NOT NULL,
            accident_date TEXT NOT NULL,
            accident_time TEXT NOT NULL,
            location TEXT NOT NULL,
            weather_conditions TEXT,
            road_conditions TEXT,
            circumstances TEXT,
            police_report_number TEXT,
            insurance_claim_number TEXT,
            estimated_damage REAL,
            other_driver_name TEXT,
            other_driver_phone TEXT,
            other_driver_license TEXT,
            other_driver_insurance TEXT,
            other_vehicle_registration TEXT,
            other_vehicle_make TEXT,
            other_vehicle_model TEXT,
            witness_name TEXT,
            witness_phone TEXT,
            witness_email TEXT,
            notes TEXT,
            status TEXT DEFAULT 'Open',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (vehicle_id) REFERENCES vehicles(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    # Accident photos table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS accident_photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            accident_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            description TEXT,
            uploaded_at TEXT NOT NULL,
            FOREIGN KEY (accident_id) REFERENCES accidents(id) ON DELETE CASCADE
        )
    ''')
    
    conn.commit()
    conn.close()


def add_accident(user_id, vehicle_id, accident_date, accident_time, location,
                weather_conditions=None, road_conditions=None, circumstances=None,
                police_report_number=None, insurance_claim_number=None, estimated_damage=None,
                other_driver_name=None, other_driver_phone=None, other_driver_license=None,
                other_driver_insurance=None, other_vehicle_registration=None,
                other_vehicle_make=None, other_vehicle_model=None,
                witness_name=None, witness_phone=None, witness_email=None,
                notes=None, status='Open'):
    """Add a new accident record."""
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        timestamp = datetime.utcnow().isoformat()

        cursor.execute("""
            INSERT INTO accidents (
                user_id, vehicle_id, accident_date, accident_time, location,
                weather_conditions, road_conditions, circumstances,
                police_report_number, insurance_claim_number, estimated_damage,
                other_driver_name, other_driver_phone, other_driver_license,
                other_driver_insurance, other_vehicle_registration,
                other_vehicle_make, other_vehicle_model,
                witness_name, witness_phone, witness_email,
                notes, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id, vehicle_id, accident_date, accident_time, location,
            weather_conditions, road_conditions, circumstances,
            police_report_number, insurance_claim_number, estimated_damage,
            other_driver_name, other_driver_phone, other_driver_license,
            other_driver_insurance, other_vehicle_registration,
            other_vehicle_make, other_vehicle_model,
            witness_name, witness_phone, witness_email,
            notes, status, timestamp, timestamp
        ))

        conn.commit()
        accident_id = cursor.lastrowid
        conn.close()
        return True, "Accident record created successfully", accident_id

    except Exception as e:
        return False, str(e), None


def get_user_accidents(user_id, vehicle_id=None, status=None):
    """Get all accidents for a user with optional filters."""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # JOIN with vehicles table to get vehicle registration
    query = """
        SELECT a.*,
               v.registration as vehicle_registration,
               v.make as vehicle_make,
               v.model as vehicle_model,
               (SELECT COUNT(*) FROM accident_photos WHERE accident_id = a.id) as photo_count
        FROM accidents a
        LEFT JOIN vehicles v ON a.vehicle_id = v.id
        WHERE a.user_id = ?
    """
    params = [user_id]
    
    if vehicle_id:
        query += " AND a.vehicle_id = ?"
        params.append(vehicle_id)
    
    if status and status != 'All':
        query += " AND a.status = ?"
        params.append(status)
    
    query += " ORDER BY a.accident_date DESC, a.accident_time DESC"
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    accidents = []
    for row in rows:
        accidents.append({
            "id": row[0],
            "user_id": row[1],
            "vehicle_id": row[2],
            "accident_date": row[3],
            "accident_time": row[4],
            "location": row[5],
            "weather_conditions": row[6],
            "road_conditions": row[7],
            "circumstances": row[8],
            "police_report_number": row[9],
            "insurance_claim_number": row[10],
            "estimated_damage": row[11],
            "other_driver_name": row[12],
            "other_driver_phone": row[13],
            "other_driver_license": row[14],
            "other_driver_insurance": row[15],
            "other_vehicle_registration": row[16],
            "other_vehicle_make": row[17],
            "other_vehicle_model": row[18],
            "witness_name": row[19],
            "witness_phone": row[20],
            "witness_email": row[21],
            "notes": row[22],
            "status": row[23],
            "created_at": row[24],
            "updated_at": row[25],
            "vehicle_registration": row[26] if row[26] else 'N/A',
            "vehicle_make": row[27],
            "vehicle_model": row[28],
            "photo_count": row[29],
        })
    return accidents


def get_accident_by_id(accident_id, user_id):
    """Get a single accident record with photos."""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT a.*, v.registration as vehicle_registration, v.make, v.model
        FROM accidents a
        JOIN vehicles v ON a.vehicle_id = v.id
        WHERE a.id = ? AND a.user_id = ?
    """, (accident_id, user_id))
    
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return None
    
    # Get photos
    cursor.execute("""
        SELECT id, filename, description, uploaded_at
        FROM accident_photos
        WHERE accident_id = ?
        ORDER BY uploaded_at
    """, (accident_id,))
    
    photos = cursor.fetchall()
    conn.close()
    
    photo_list = []
    for photo in photos:
        photo_list.append({
            'id': photo[0],
            'filename': photo[1],
            'description': photo[2],
            'uploaded_at': photo[3]
        })
    
    return {
        "id": row[0],
        "user_id": row[1],
        "vehicle_id": row[2],
        "accident_date": row[3],
        "accident_time": row[4],
        "location": row[5],
        "weather_conditions": row[6],
        "road_conditions": row[7],
        "circumstances": row[8],
        "police_report_number": row[9],
        "insurance_claim_number": row[10],
        "estimated_damage": row[11],
        "other_driver_name": row[12],
        "other_driver_phone": row[13],
        "other_driver_license": row[14],
        "other_driver_insurance": row[15],
        "other_vehicle_registration": row[16],
        "other_vehicle_make": row[17],
        "other_vehicle_model": row[18],
        "witness_name": row[19],
        "witness_phone": row[20],
        "witness_email": row[21],
        "notes": row[22],
        "status": row[23],
        "created_at": row[24],
        "updated_at": row[25],
        "vehicle_registration": row[26],
        "vehicle_make": row[27],
        "vehicle_model": row[28],
        "photos": photo_list
    }


def update_accident(accident_id, user_id, **kwargs):
    """Update an accident record with provided fields."""
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # Build UPDATE query dynamically based on provided kwargs
        set_clauses = []
        params = []
        
        allowed_fields = [
            'vehicle_id', 'accident_date', 'accident_time', 'location',
            'weather_conditions', 'road_conditions', 'circumstances',
            'police_report_number', 'insurance_claim_number', 'estimated_damage',
            'other_driver_name', 'other_driver_phone', 'other_driver_license',
            'other_driver_insurance', 'other_vehicle_registration',
            'other_vehicle_make', 'other_vehicle_model',
            'witness_name', 'witness_phone', 'witness_email',
            'notes', 'status'
        ]
        
        for field in allowed_fields:
            if field in kwargs:
                set_clauses.append(f"{field} = ?")
                params.append(kwargs[field])
        
        if not set_clauses:
            return False, "No fields to update"
        
        # Add updated_at timestamp
        set_clauses.append("updated_at = ?")
        params.append(datetime.utcnow().isoformat())
        
        # Add WHERE clause params
        params.extend([accident_id, user_id])
        
        query = f"""
            UPDATE accidents
            SET {', '.join(set_clauses)}
            WHERE id = ? AND user_id = ?
        """
        
        cursor.execute(query, params)
        conn.commit()
        conn.close()
        
        return True, "Accident updated successfully"
    except Exception as e:
        return False, str(e)


def delete_accident(accident_id, user_id):
    """Delete an accident record and all associated photos."""
    try:
        # Get accident to find photos
        accident = get_accident_by_id(accident_id, user_id)
        
        if not accident:
            return False, "Accident not found"
        
        # Delete photo files
        for photo in accident['photos']:
            photo_path = os.path.join(ACCIDENT_PHOTO_FOLDER, photo['filename'])
            if os.path.exists(photo_path):
                try:
                    os.remove(photo_path)
                except Exception as e:
                    print(f"Warning: Could not delete photo file: {e}")
        
        # Delete from database (cascade will delete photos table entries)
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM accidents WHERE id = ? AND user_id = ?", (accident_id, user_id))
        cursor.execute("DELETE FROM accident_photos WHERE accident_id = ?", (accident_id,))
        conn.commit()
        conn.close()
        
        return True, "Accident deleted successfully"
    except Exception as e:
        return False, str(e)


def add_accident_photo(accident_id, filename, description=None):
    """Add a photo to an accident record."""
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        timestamp = datetime.utcnow().isoformat()
        
        cursor.execute("""
            INSERT INTO accident_photos (accident_id, filename, description, uploaded_at)
            VALUES (?, ?, ?, ?)
        """, (accident_id, filename, description, timestamp))
        
        conn.commit()
        photo_id = cursor.lastrowid
        conn.close()
        return True, "Photo added successfully", photo_id
    except Exception as e:
        return False, str(e), None


def delete_accident_photo(photo_id, accident_id):
    """Delete a photo from an accident record."""
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # Get filename
        cursor.execute("SELECT filename FROM accident_photos WHERE id = ? AND accident_id = ?", 
                      (photo_id, accident_id))
        result = cursor.fetchone()
        
        if not result:
            conn.close()
            return False, "Photo not found"
        
        filename = result[0]
        
        # Delete from database
        cursor.execute("DELETE FROM accident_photos WHERE id = ? AND accident_id = ?", 
                      (photo_id, accident_id))
        conn.commit()
        conn.close()
        
        # Delete file
        photo_path = os.path.join(ACCIDENT_PHOTO_FOLDER, filename)
        if os.path.exists(photo_path):
            try:
                os.remove(photo_path)
            except Exception as e:
                print(f"Warning: Could not delete photo file: {e}")
        
        return True, "Photo deleted successfully"
    except Exception as e:
        return False, str(e)


def get_accident_photos(accident_id):
    """
    Get all photos for a specific accident.
    
    Args:
        accident_id: ID of the accident
        
    Returns:
        List of photo dictionaries
    """
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, accident_id, filename, description, uploaded_at
        FROM accident_photos
        WHERE accident_id = ?
        ORDER BY uploaded_at ASC
    """, (accident_id,))
    
    photos = []
    for row in cursor.fetchall():
        photos.append({
            'id': row[0],
            'accident_id': row[1],
            'filename': row[2],
            'description': row[3],
            'uploaded_at': row[4]
        })
    
    conn.close()
    return photos


def get_accident_count(user_id):
    """Get total count of accidents for a user."""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM accidents WHERE user_id = ?", (user_id,))
    count = cursor.fetchone()[0]
    conn.close()
    return count


# Accident status options
ACCIDENT_STATUSES = ['Open', 'Under Investigation', 'Insurance Claim Filed', 'Resolved', 'Closed']

# Severity levels
SEVERITY_LEVELS = ['Minor', 'Moderate', 'Major', 'Severe']

# Weather conditions options
WEATHER_CONDITIONS = ['Clear', 'Rainy', 'Foggy', 'Snowy', 'Windy', 'Other']

# Road conditions options
ROAD_CONDITIONS = ['Dry', 'Wet', 'Icy', 'Snowy', 'Muddy', 'Other']

# Post-accident checklist
POST_ACCIDENT_CHECKLIST = [
    {
        'step': 1,
        'title': 'Ensure Safety',
        'description': 'Check for injuries and move to a safe location if possible. Turn on hazard lights.',
        'critical': True
    },
    {
        'step': 2,
        'title': 'Call Emergency Services',
        'description': 'Call 000 (Australia) if anyone is injured or if there is significant property damage.',
        'critical': True
    },
    {
        'step': 3,
        'title': 'Exchange Information',
        'description': 'Collect name, phone, license number, insurance details, and vehicle registration from other driver(s).',
        'critical': True
    },
    {
        'step': 4,
        'title': 'Take Photos',
        'description': 'Photograph damage to all vehicles, license plates, accident scene, road conditions, and any relevant signs/signals.',
        'critical': False
    },
    {
        'step': 5,
        'title': 'Record Witnesses',
        'description': 'Get contact information from anyone who witnessed the accident.',
        'critical': False
    },
    {
        'step': 6,
        'title': 'Contact Police',
        'description': 'Report the accident to police if required by law or if there is a dispute about fault.',
        'critical': True
    },
    {
        'step': 7,
        'title': 'Notify Insurance',
        'description': 'Contact your insurance company as soon as possible to report the accident.',
        'critical': True
    },
    {
        'step': 8,
        'title': 'Document Everything',
        'description': 'Write down details while fresh: time, location, weather, road conditions, what happened.',
        'critical': False
    },
    {
        'step': 9,
        'title': 'Do Not Admit Fault',
        'description': 'Be factual but do not admit fault or apologize at the scene.',
        'critical': True
    },
    {
        'step': 10,
        'title': 'Seek Medical Attention',
        'description': 'Even if you feel fine, see a doctor within 24 hours. Some injuries may not be immediately apparent.',
        'critical': False
    }
]