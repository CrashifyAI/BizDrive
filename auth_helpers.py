"""
Authentication Helper Functions for BizDrive
This module contains utility functions for user authentication and password management.
"""

import bcrypt
import os
import secrets
import re
import sqlite3
from datetime import datetime, timedelta

# ===============================================
# Database Setup
# ===============================================

def get_db_connection():
    """Create and return a database connection."""
    conn = sqlite3.connect(os.path.join(os.path.dirname(__file__), 'bizdrive.db'))
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """Initialize the database with required tables."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            email TEXT,
            role TEXT DEFAULT 'driver',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        )
    ''')
    
    # Create default admin user if not exists
    cursor.execute('SELECT id FROM users WHERE username = ?', ('admin',))
    if not cursor.fetchone():
        admin_password = hash_password('Admin123!')
        cursor.execute('''
            INSERT INTO users (username, password_hash, email, role)
            VALUES (?, ?, ?, ?)
        ''', ('admin', admin_password, 'admin@bizdrive.com', 'admin'))
    
    conn.commit()
    conn.close()
    
    # Create password reset tokens table
    create_reset_token_table()


# ===============================================
# Password Hashing Functions (Secure with bcrypt)
# ===============================================

def hash_password(password):
    """
    Hash a password using bcrypt with salt.
    
    Args:
        password (str): Plain text password
        
    Returns:
        str: Hashed password
    """
    salt = bcrypt.gensalt()
    password_hash = bcrypt.hashpw(password.encode('utf-8'), salt)
    return password_hash.decode('utf-8')


def verify_password(stored_password_hash, provided_password):
    """
    Verify a provided password against a stored bcrypt hash.
    
    Args:
        stored_password_hash (str): The stored hashed password
        provided_password (str): The plain text password to verify
        
    Returns:
        bool: True if passwords match, False otherwise
    """
    try:
        return bcrypt.checkpw(
            provided_password.encode('utf-8'),
            stored_password_hash.encode('utf-8')
        )
    except Exception:
        return False


# ===============================================
# User Validation Functions
# ===============================================

def validate_username(username):
    """
    Validate username format.
    
    Args:
        username (str): Username to validate
        
    Returns:
        tuple: (is_valid, error_message)
    """
    if not username:
        return False, "Username is required."
    
    if len(username) < 3:
        return False, "Username must be at least 3 characters long."
    
    if len(username) > 20:
        return False, "Username must be less than 20 characters."
    
    if not username.isalnum():
        return False, "Username can only contain letters and numbers."
    
    return True, ""


def validate_password(password):
    """
    Validate password strength according to project requirements:
    - Minimum 8 characters
    - At least 1 uppercase letter
    - At least 1 special character (!@#$%^&*(),.?":{}|<>)
    
    Args:
        password (str): Password to validate
        
    Returns:
        tuple: (is_valid, error_message)
    """
    if not password:
        return False, "Password is required."
    
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
    
    if len(password) > 50:
        return False, "Password must be less than 50 characters."
    
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least 1 uppercase letter."
    
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False, "Password must contain at least 1 special character (!@#$%^&*(),.?\":{}|<>)."
    
    return True, ""


def validate_registration(username, password, confirm_password, email):
    """
    Validate all registration fields.
    Email is now REQUIRED for password reset functionality.
    
    Args:
        username (str): Username to validate
        password (str): Password to validate
        confirm_password (str): Password confirmation
        email (str): Email to validate (REQUIRED)
        
    Returns:
        tuple: (is_valid, error_message)
    """
    # Validate username
    username_valid, username_error = validate_username(username)
    if not username_valid:
        return False, username_error
    
    # Validate password
    password_valid, password_error = validate_password(password)
    if not password_valid:
        return False, password_error
    
    # Check if passwords match
    if password != confirm_password:
        return False, "Passwords do not match."
    
    # Email is now REQUIRED (not optional)
    if not email:
        return False, "Email is required for account recovery."
    
    # Validate email format
    if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email):
        return False, "Invalid email format."
    
    return True, ""


# ===============================================
# Password Reset Token Functions
# ===============================================

def generate_reset_token():
    """Generate a secure password reset token."""
    return secrets.token_urlsafe(32)


def create_reset_token_table():
    """Create password reset tokens table."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            used BOOLEAN DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    
    conn.commit()
    conn.close()


def store_reset_token(user_id):
    """
    Generate and store a password reset token.
    Token expires in 1 hour.
    
    Args:
        user_id (int): User ID
        
    Returns:
        str: Reset token
    """
    token = generate_reset_token()
    expires_at = datetime.now() + timedelta(hours=1)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Delete any existing unused tokens for this user
    cursor.execute('DELETE FROM password_reset_tokens WHERE user_id = ? AND used = 0', (user_id,))
    
    # Store new token
    cursor.execute('''
        INSERT INTO password_reset_tokens (user_id, token, expires_at)
        VALUES (?, ?, ?)
    ''', (user_id, token, expires_at))
    
    conn.commit()
    conn.close()
    
    return token


def verify_reset_token(token):
    """
    Verify if a reset token is valid and not expired.
    
    Args:
        token (str): Reset token to verify
        
    Returns:
        tuple: (is_valid, user_id or error_message)
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT user_id, expires_at, used 
        FROM password_reset_tokens 
        WHERE token = ?
    ''', (token,))
    
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        return False, "Invalid reset token."
    
    user_id = result['user_id']
    expires_at = datetime.fromisoformat(result['expires_at'])
    used = result['used']
    
    if used:
        return False, "This reset token has already been used."
    
    if datetime.now() > expires_at:
        return False, "This reset token has expired. Please request a new one."
    
    return True, user_id


def mark_token_as_used(token):
    """Mark a reset token as used."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE password_reset_tokens 
        SET used = 1 
        WHERE token = ?
    ''', (token,))
    
    conn.commit()
    conn.close()


def get_user_by_email(email):
    """
    Get user by email address.
    
    Args:
        email (str): Email address
        
    Returns:
        dict or None: User information or None if not found
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
    user = cursor.fetchone()
    conn.close()
    
    if user:
        return {
            'id': user['id'],
            'username': user['username'],
            'email': user['email'],
            'role': user['role']
        }
    return None


def reset_user_password(user_id, new_password):
    """
    Reset user password.
    
    Args:
        user_id (int): User ID
        new_password (str): New password (plain text, will be hashed)
        
    Returns:
        tuple: (success, message)
    """
    # Validate password
    is_valid, error_msg = validate_password(new_password)
    if not is_valid:
        return False, error_msg
    
    # Hash password
    password_hash = hash_password(new_password)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            UPDATE users 
            SET password_hash = ? 
            WHERE id = ?
        ''', (password_hash, user_id))
        
        conn.commit()
        conn.close()
        return True, "Password reset successfully!"
        
    except Exception as e:
        conn.close()
        return False, f"Error resetting password: {str(e)}"


# ===============================================
# Session Token Functions
# ===============================================

def generate_session_token():
    """
    Generate a secure random session token.
    
    Returns:
        str: A secure random token
    """
    return secrets.token_hex(32)


# ===============================================
# User Database Functions
# ===============================================

def check_user_exists(username):
    """
    Check if a user exists in the database.
    
    Args:
        username (str): Username to check
        
    Returns:
        bool: True if user exists, False otherwise
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
    user = cursor.fetchone()
    conn.close()
    return user is not None


def check_email_exists(email):
    """
    Check if an email is already registered.
    
    Args:
        email (str): Email to check
        
    Returns:
        bool: True if email exists, False otherwise
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM users WHERE email = ?', (email,))
    user = cursor.fetchone()
    conn.close()
    return user is not None


def add_user(username, password, email, role='driver'):
    """
    Add a new user to the database.
    Email is now REQUIRED for password reset functionality.
    
    Args:
        username (str): Username
        password (str): Plain text password (will be hashed)
        email (str): User email (REQUIRED)
        role (str): User role (driver, fleet_manager, admin)
        
    Returns:
        bool: True if user was added, False if user already exists
    """
    # Validate email is provided
    if not email:
        return False
    
    # Check if username exists
    if check_user_exists(username):
        return False
    
    # Check if email exists
    if check_email_exists(email):
        return False
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    password_hash = hash_password(password)
    
    try:
        cursor.execute('''
            INSERT INTO users (username, password_hash, email, role)
            VALUES (?, ?, ?, ?)
        ''', (username, password_hash, email, role))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False


def authenticate_user(username, password):
    """
    Authenticate a user with username and password.
    
    Args:
        username (str): Username
        password (str): Plain text password
        
    Returns:
        dict or None: User information if authenticated, None otherwise
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
    user = cursor.fetchone()
    
    if user and verify_password(user['password_hash'], password):
        # Update last login timestamp
        cursor.execute('''
            UPDATE users SET last_login = ? WHERE username = ?
        ''', (datetime.now(), username))
        conn.commit()
        conn.close()
        
        return {
            'id': user['id'],
            'username': user['username'],
            'email': user['email'],
            'role': user['role']
        }
    
    conn.close()
    return None


def get_user_info(username):
    """
    Get user information from database.
    
    Args:
        username (str): Username
        
    Returns:
        dict or None: User information dictionary or None if not found
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id, username, email, role, created_at, last_login FROM users WHERE username = ?', (username,))
    user = cursor.fetchone()
    conn.close()
    
    if user:
        return {
            'id': user['id'],
            'username': user['username'],
            'email': user['email'],
            'role': user['role'],
            'created_at': user['created_at'],
            'last_login': user['last_login']
        }
    return None


def get_user_by_id(user_id):
    """
    Get user information by user ID.
    
    Args:
        user_id (int): User ID
        
    Returns:
        dict or None: User information dictionary or None if not found
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id, username, email, role FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    
    if user:
        return {
            'id': user['id'],
            'username': user['username'],
            'email': user['email'],
            'role': user['role']
        }
    return None