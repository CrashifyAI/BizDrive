import sqlite3
import os
from datetime import datetime

DATABASE = os.path.join(os.path.dirname(__file__), 'bizdrive.db')
RECEIPT_FOLDER = 'static/receipts'

# Ensure receipt folder exists
os.makedirs(RECEIPT_FOLDER, exist_ok=True)

def init_expense_table():
    """Create expense table if it does not exist."""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            vehicle_id INTEGER,
            expense_date TEXT NOT NULL,
            expense_type TEXT NOT NULL,
            amount REAL NOT NULL,
            notes TEXT,
            receipt_filename TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (vehicle_id) REFERENCES vehicles(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    conn.commit()
    conn.close()


def add_expense(user_id, vehicle_id, expense_date, expense_type, amount, notes=None, receipt_filename=None):
    """Add a new expense record."""
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        created_at = datetime.utcnow().isoformat()

        cursor.execute("""
            INSERT INTO expenses (user_id, vehicle_id, expense_date, expense_type, amount, notes, receipt_filename, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, vehicle_id, expense_date, expense_type, amount, notes, receipt_filename, created_at))

        conn.commit()
        expense_id = cursor.lastrowid
        conn.close()
        return True, "Expense added successfully", expense_id

    except Exception as e:
        return False, str(e), None


def get_user_expenses(user_id, vehicle_id=None, expense_type=None, start_date=None, end_date=None):
    """Get all expenses for a user with optional filters."""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # JOIN with vehicles table to get vehicle registration
    query = """
        SELECT e.*, v.registration as vehicle_registration
        FROM expenses e
        LEFT JOIN vehicles v ON e.vehicle_id = v.id
        WHERE e.user_id = ?
    """
    params = [user_id]
    
    if vehicle_id:
        query += " AND e.vehicle_id = ?"
        params.append(vehicle_id)
    
    if expense_type and expense_type != 'All':
        query += " AND e.expense_type = ?"
        params.append(expense_type)
    
    if start_date:
        query += " AND e.expense_date >= ?"
        params.append(start_date)
    
    if end_date:
        query += " AND e.expense_date <= ?"
        params.append(end_date)
    
    query += " ORDER BY e.expense_date DESC, e.id DESC"
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    expenses = []
    for row in rows:
        expenses.append({
            "id": row[0],
            "user_id": row[1],
            "vehicle_id": row[2],
            "expense_date": row[3],
            "expense_type": row[4],
            "amount": row[5],
            "notes": row[6],
            "receipt_filename": row[7],
            "created_at": row[8],
            "vehicle_registration": row[9] if row[9] else 'N/A'
        })
    return expenses


def get_expense_by_id(expense_id, user_id):
    """Get a single expense for editing or viewing."""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT e.*
        FROM expenses e
        WHERE e.id = ? AND e.user_id = ?
    """, (expense_id, user_id))
    row = cursor.fetchone()
    conn.close()

    if row:
        return {
            "id": row[0],
            "user_id": row[1],
            "vehicle_id": row[2],
            "expense_date": row[3],
            "expense_type": row[4],
            "amount": row[5],
            "notes": row[6],
            "receipt_filename": row[7],
            "created_at": row[8],
            # Note: vehicle_registration removed - can't JOIN across databases
        }
    return None


def update_expense(expense_id, user_id, vehicle_id, expense_date, expense_type, amount, notes=None, receipt_filename=None):
    """Update an existing expense."""
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        # If receipt_filename is provided, update it; otherwise keep existing
        if receipt_filename is not None:
            cursor.execute("""
                UPDATE expenses
                SET vehicle_id = ?, expense_date = ?, expense_type = ?, amount = ?, notes = ?, receipt_filename = ?
                WHERE id = ? AND user_id = ?
            """, (vehicle_id, expense_date, expense_type, amount, notes, receipt_filename, expense_id, user_id))
        else:
            cursor.execute("""
                UPDATE expenses
                SET vehicle_id = ?, expense_date = ?, expense_type = ?, amount = ?, notes = ?
                WHERE id = ? AND user_id = ?
            """, (vehicle_id, expense_date, expense_type, amount, notes, expense_id, user_id))

        conn.commit()
        conn.close()
        return True, "Expense updated successfully"
    except Exception as e:
        return False, str(e)


def delete_expense(expense_id, user_id):
    """Delete an expense record and its receipt file."""
    try:
        # Get expense to find receipt filename
        expense = get_expense_by_id(expense_id, user_id)
        
        if not expense:
            return False, "Expense not found"
        
        # Delete from database
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM expenses
            WHERE id = ? AND user_id = ?
        """, (expense_id, user_id))
        conn.commit()
        conn.close()
        
        # Delete receipt file if exists
        if expense['receipt_filename']:
            receipt_path = os.path.join(RECEIPT_FOLDER, expense['receipt_filename'])
            if os.path.exists(receipt_path):
                try:
                    os.remove(receipt_path)
                except Exception as e:
                    print(f"Warning: Could not delete receipt file: {e}")
        
        return True, "Expense deleted successfully"
    except Exception as e:
        return False, str(e)


def get_expense_summary(user_id, vehicle_id=None, start_date=None, end_date=None):
    """Get expense summary statistics."""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # Total expenses
    query = "SELECT COUNT(*), SUM(amount) FROM expenses WHERE user_id = ?"
    params = [user_id]
    
    if vehicle_id:
        query += " AND vehicle_id = ?"
        params.append(vehicle_id)
    
    if start_date:
        query += " AND expense_date >= ?"
        params.append(start_date)
    
    if end_date:
        query += " AND expense_date <= ?"
        params.append(end_date)
    
    cursor.execute(query, params)
    total_count, total_amount = cursor.fetchone()
    
    # Expenses by category
    query_cat = """
        SELECT expense_type, COUNT(*), SUM(amount)
        FROM expenses
        WHERE user_id = ?
    """
    params_cat = [user_id]
    
    if vehicle_id:
        query_cat += " AND vehicle_id = ?"
        params_cat.append(vehicle_id)
    
    if start_date:
        query_cat += " AND expense_date >= ?"
        params_cat.append(start_date)
    
    if end_date:
        query_cat += " AND expense_date <= ?"
        params_cat.append(end_date)
    
    query_cat += " GROUP BY expense_type ORDER BY SUM(amount) DESC"
    
    cursor.execute(query_cat, params_cat)
    categories = cursor.fetchall()
    
    # Expenses by vehicle (without vehicle details due to cross-database limitation)
    # Note: We can only get vehicle_id, not registration/make/model
    query_veh = """
        SELECT e.vehicle_id, COUNT(e.id), SUM(e.amount)
        FROM expenses e
        WHERE e.user_id = ? AND e.vehicle_id IS NOT NULL
    """
    params_veh = [user_id]
    
    if vehicle_id:
        query_veh += " AND e.vehicle_id = ?"
        params_veh.append(vehicle_id)
    
    if start_date:
        query_veh += " AND e.expense_date >= ?"
        params_veh.append(start_date)
    
    if end_date:
        query_veh += " AND e.expense_date <= ?"
        params_veh.append(end_date)
    
    query_veh += " GROUP BY e.vehicle_id ORDER BY SUM(e.amount) DESC"
    
    cursor.execute(query_veh, params_veh)
    vehicles = cursor.fetchall()
    
    conn.close()
    
    # Format results
    category_breakdown = []
    for cat in categories:
        category_breakdown.append({
            'type': cat[0],
            'count': cat[1],
            'total': cat[2] or 0
        })
    
    vehicle_breakdown = []
    for veh in vehicles:
        vehicle_breakdown.append({
            'vehicle_id': veh[0],  # Only ID available, template must look up details
            'count': veh[1],
            'total': veh[2] or 0
        })
    
    # Get top category
    top_category = category_breakdown[0]['type'] if category_breakdown else 'N/A'
    
    return {
        'total_count': total_count or 0,
        'total_amount': total_amount or 0,
        'top_category': top_category,
        'category_breakdown': category_breakdown,
        'vehicle_breakdown': vehicle_breakdown
    }


def get_monthly_expenses(user_id, vehicle_id=None):
    """Get monthly expense totals for the current year."""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    query = """
        SELECT strftime('%Y-%m', expense_date) as month, SUM(amount) as total
        FROM expenses
        WHERE user_id = ? AND strftime('%Y', expense_date) = strftime('%Y', 'now')
    """
    params = [user_id]
    
    if vehicle_id:
        query += " AND vehicle_id = ?"
        params.append(vehicle_id)
    
    query += " GROUP BY month ORDER BY month"
    
    cursor.execute(query, params)
    results = cursor.fetchall()
    conn.close()
    
    monthly_data = []
    for row in results:
        monthly_data.append({
            'month': row[0],
            'total': row[1] or 0
        })
    
    return monthly_data


# Expense categories for dropdown
EXPENSE_CATEGORIES = [
    'Fuel',
    'Maintenance',
    'Insurance',
    'Registration',
    'Repairs',
    'Tires',
    'Parking',
    'Tolls',
    'Car Wash',
    'Other'
]