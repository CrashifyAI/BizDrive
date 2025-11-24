import os
from flask import Flask, render_template, request, redirect, url_for, flash, session, Response, send_file
from functools import wraps
from datetime import date, datetime
from werkzeug.utils import secure_filename
from io import BytesIO
from auth_helpers import (
    authenticate_user, 
    add_user, 
    validate_registration,
    check_user_exists,
    check_email_exists,
    init_database,
    get_user_by_id,
    get_user_by_email,
    store_reset_token,
    verify_reset_token,
    mark_token_as_used,
    reset_user_password
)
from vehicle_helpers import (
    init_vehicle_table,
    add_vehicle,
    get_user_vehicles,
    get_vehicle_by_id,
    get_vehicle_by_registration,
    update_vehicle,
    delete_vehicle,
    get_vehicle_count
)
from trip_helpers import (
    init_trip_table,
    add_trip,
    get_user_trips,
    get_trip_by_id,
    update_trip,
    delete_trip,
    get_vehicle_trip_stats,
    get_user_trip_stats,
    get_monthly_trip_stats,
    get_trip_count,
    get_daily_trips
)
from expense_helpers import (
    init_expense_table,
    add_expense,
    get_user_expenses,
    get_expense_by_id,
    update_expense,
    delete_expense
)
from accident_helpers import (
    init_accident_table,
    add_accident,
    get_accident_by_id,
    get_user_accidents,
    get_accident_count,
    update_accident,
    delete_accident,
    add_accident_photo,
    get_accident_photos,
    delete_accident_photo,
    SEVERITY_LEVELS,
    WEATHER_CONDITIONS,
    ROAD_CONDITIONS,
    ACCIDENT_STATUSES
)
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter


app = Flask(__name__)

# Load secret key from environment variable or use a secure default for development
app.secret_key = os.environ.get('SECRET_KEY') or os.urandom(24)

# Initialize database on startup
init_database()
init_vehicle_table()
init_trip_table()
init_expense_table()
init_accident_table()  # CRITICAL FIX: Initialize accident tables to prevent 500 errors


# ===============================================
# Authentication Decorator
# ===============================================

def login_required(f):
    """Decorator to require login for protected routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def role_required(*roles):
    """Decorator to require specific role(s) for protected routes."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please log in to access this page.', 'error')
                return redirect(url_for('login'))
            
            user = get_user_by_id(session['user_id'])
            if user and user['role'] in roles:
                return f(*args, **kwargs)
            
            flash('You do not have permission to access this page.', 'error')
            return redirect(url_for('dashboard'))
        return decorated_function
    return decorator


# ===============================================
# Authentication Routes
# ===============================================

@app.route('/')
def home():
    """Home route redirects to dashboard if logged in, else to login."""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page and authentication handler."""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        user = authenticate_user(username, password)
        
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            
            flash(f'Welcome back, {user["username"]}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'error')
    
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    """Registration page and new user handler."""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        email = request.form.get('email', '').strip()

        if not email:
            flash('Email is required for account recovery.', 'error')
            return render_template('register.html')

        is_valid, error_message = validate_registration(username, password, confirm_password, email)
        
        if not is_valid:
            flash(error_message, 'error')
            return render_template('register.html')
        
        if check_user_exists(username):
            flash('Username already exists. Please choose another.', 'error')
            return render_template('register.html')
        
        if check_email_exists(email):
            flash('Email already registered. Please use another or reset your password.', 'error')
            return render_template('register.html')
        
        if add_user(username, password, email, role='driver'):
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
        else:
            flash('Registration failed. Please try again.', 'error')
    
    return render_template('register.html')


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Forgot password page - request reset link."""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        
        if not email:
            flash('Please enter your email address.', 'error')
            return render_template('forgot_password.html')
        
        user = get_user_by_email(email)
        
        if user:
            token = store_reset_token(user['id'])
            reset_link = url_for('reset_password', token=token, _external=True)
            session['reset_link'] = reset_link
            
            flash('Password reset instructions have been sent to your email.', 'success')
            return redirect(url_for('reset_link_display'))
        else:
            flash('If an account exists with this email, you will receive reset instructions.', 'info')
    
    return render_template('forgot_password.html')


@app.route('/reset-link')
def reset_link_display():
    """Display reset link (development only - remove in production)."""
    if 'reset_link' not in session:
        return redirect(url_for('login'))
    
    reset_link = session.pop('reset_link')
    return render_template('reset_link_display.html', reset_link=reset_link)


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Reset password with token."""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    
    is_valid, result = verify_reset_token(token)
    
    if not is_valid:
        flash(result, 'error')
        return redirect(url_for('login'))
    
    user_id = result
    
    if request.method == 'POST':
        new_password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if new_password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('reset_password.html', token=token)
        
        success, message = reset_user_password(user_id, new_password)
        
        if success:
            mark_token_as_used(token)
            flash('Password reset successful! Please log in with your new password.', 'success')
            return redirect(url_for('login'))
        else:
            flash(message, 'error')
    
    return render_template('reset_password.html', token=token)


@app.route('/logout')
@login_required
def logout():
    """Log out the current user."""
    username = session.get('username', 'User')
    session.clear()
    flash(f'Goodbye, {username}! You have been logged out.', 'info')
    return redirect(url_for('login'))


# ===============================================
# Dashboard Route
# ===============================================

@app.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard with summary statistics."""
    user_id = session['user_id']
    user = get_user_by_id(user_id)
    
    # Get vehicle counts
    vehicles = get_user_vehicles(user_id)
    total_vehicles = len(vehicles)
    active_vehicles = len([v for v in vehicles if v.get('status') == 'Active'])
    
    # Get trip statistics
    trip_stats = get_user_trip_stats(user_id)
    
    # Get recent trips (last 5)
    recent_trips = get_user_trips(user_id, limit=5)
    
    today = date.today()
    today_trips = get_daily_trips(user_id, today.strftime('%Y-%m-%d'))
    monthly_stats = get_monthly_trip_stats(user_id, today.year, today.month)
    
    return render_template('dashboard.html',
                         user=user,
                         total_vehicles=total_vehicles,
                         active_vehicles=active_vehicles,
                         trip_stats=trip_stats,
                         recent_trips=recent_trips,
                         today_trips=today_trips,
                         monthly_stats=monthly_stats)


# ===============================================
# Vehicle Routes
# ===============================================

@app.route('/vehicles')
@login_required
def vehicle_list():
    """List all vehicles for the current user."""
    user_id = session['user_id']
    vehicles = get_user_vehicles(user_id)
    user = get_user_by_id(user_id)
    return render_template('vehicle_list.html', vehicles=vehicles, user=user)


@app.route('/vehicles/add', methods=['GET', 'POST'])
@login_required
def add_vehicle_route():
    """Add a new vehicle."""
    if request.method == 'POST':
        user_id = session['user_id']
        
        registration = request.form.get('registration', '').strip().upper()
        make = request.form.get('make', '').strip()
        model = request.form.get('model', '').strip()
        year = request.form.get('year', '').strip()
        color = request.form.get('color', '').strip()
        odometer = request.form.get('odometer', '').strip()
        status = request.form.get('status', 'Active')
        purchase_date = request.form.get('purchase_date', '').strip()
        notes = request.form.get('notes', '').strip()
        
        if not all([registration, make, model, year]):
            flash('Registration, make, model, and year are required.', 'error')
            return render_template('add_vehicle.html', user=get_user_by_id(user_id))
        
        # Convert year and odometer to integers
        try:
            year = int(year) if year else None
            odometer = int(odometer) if odometer else 0
        except ValueError:
            flash('Year and odometer must be valid numbers.', 'error')
            return render_template('add_vehicle.html', user=get_user_by_id(user_id))
        
        if get_vehicle_by_registration(registration, user_id):
            flash('A vehicle with this registration already exists.', 'error')
            return render_template('add_vehicle.html', user=get_user_by_id(user_id))
        
        success, message, _ = add_vehicle(user_id, registration, make, model, year, 
                                         color, odometer, status, purchase_date, notes)
        
        if success:
            flash(message, 'success')
            return redirect(url_for('vehicle_list'))
        else:
            flash(message, 'error')
    
    return render_template('add_vehicle.html', user=get_user_by_id(session['user_id']))


@app.route('/vehicles/<int:vehicle_id>')
@login_required
def view_vehicle(vehicle_id):
    """View details of a specific vehicle."""
    user_id = session['user_id']
    vehicle = get_vehicle_by_id(vehicle_id, user_id)
    
    if not vehicle:
        flash('Vehicle not found or access denied.', 'error')
        return redirect(url_for('vehicle_list'))
    
    trip_stats = get_vehicle_trip_stats(vehicle_id, user_id)
    
    return render_template('view_vehicle.html', 
                         vehicle=vehicle, 
                         trip_stats=trip_stats,
                         user=get_user_by_id(user_id))


@app.route('/vehicles/<int:vehicle_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_vehicle_route(vehicle_id):
    """Edit an existing vehicle."""
    user_id = session['user_id']
    vehicle = get_vehicle_by_id(vehicle_id, user_id)
    
    if not vehicle:
        flash('Vehicle not found or access denied.', 'error')
        return redirect(url_for('vehicle_list'))
    
    if request.method == 'POST':
        registration = request.form.get('registration', '').strip().upper()
        make = request.form.get('make', '').strip()
        model = request.form.get('model', '').strip()
        year = request.form.get('year', '').strip()
        color = request.form.get('color', '').strip()
        odometer = request.form.get('odometer', '').strip()
        status = request.form.get('status', vehicle['status'])
        purchase_date = request.form.get('purchase_date', '').strip()
        notes = request.form.get('notes', '').strip()
        
        # Convert year and odometer to integers
        try:
            year = int(year) if year else None
            odometer = int(odometer) if odometer else 0
        except ValueError:
            flash('Year and odometer must be valid numbers.', 'error')
            return render_template('edit_vehicle.html', vehicle=vehicle, user=get_user_by_id(user_id))
        
        existing_vehicle = get_vehicle_by_registration(registration, user_id)
        if existing_vehicle and existing_vehicle['id'] != vehicle_id:
            flash('Another vehicle with this registration already exists.', 'error')
            return render_template('edit_vehicle.html', vehicle=vehicle, user=get_user_by_id(user_id))
        
        success, message = update_vehicle(vehicle_id, user_id, registration, make, model, 
                                        year, color, odometer, status, purchase_date, notes)
        
        if success:
            flash(message, 'success')
            return redirect(url_for('view_vehicle', vehicle_id=vehicle_id))
        else:
            flash(message, 'error')
    
    return render_template('edit_vehicle.html', vehicle=vehicle, user=get_user_by_id(user_id))


@app.route('/vehicles/<int:vehicle_id>/delete', methods=['POST'])
@login_required
def delete_vehicle_route(vehicle_id):
    """Delete a vehicle."""
    user_id = session['user_id']
    success, message = delete_vehicle(vehicle_id, user_id)
    
    flash(message, 'success' if success else 'error')
    return redirect(url_for('vehicle_list'))


# ===============================================
# Trip Routes
# ===============================================

@app.route('/trips')
@login_required
def trip_list():
    """List all trips for the current user with optional filters."""
    user_id = session['user_id']
    
    filter_vehicle = request.args.get('vehicle', '')
    filter_type = request.args.get('type', '')
    filter_month = request.args.get('month', '')
    
    trips = get_user_trips(user_id)
    
    if filter_vehicle:
        trips = [t for t in trips if str(t.get('vehicle_id')) == filter_vehicle]
    
    if filter_type:
        trips = [t for t in trips if t.get('trip_type') == filter_type]
    
    if filter_month:
        trips = [t for t in trips if t.get('trip_date', '').startswith(filter_month)]
    
    vehicles = get_user_vehicles(user_id)
    user = get_user_by_id(user_id)
    
    return render_template('trip_list.html', 
                         trips=trips, 
                         vehicles=vehicles, 
                         user=user,
                         filter_vehicle=filter_vehicle,
                         filter_type=filter_type,
                         filter_month=filter_month)


@app.route('/trips/add', methods=['GET', 'POST'])
@login_required
def add_trip_route():
    """Add a new trip."""
    user_id = session['user_id']
    
    if request.method == 'POST':
        vehicle_id = request.form.get('vehicle_id', type=int)
        trip_date = request.form.get('trip_date', '').strip()
        trip_type = request.form.get('trip_type', 'Personal')
        reimbursement_rate = request.form.get('reimbursement_rate', '').strip()
        
        # Check if this is a multiple trips submission (array format)
        # The form uses trips[0][from_address], trips[1][from_address], etc.
        trips_data = []
        trip_index = 0
        
        while True:
            from_addr = request.form.get(f'trips[{trip_index}][from_address]', '').strip()
            to_addr = request.form.get(f'trips[{trip_index}][to_address]', '').strip()
            purpose = request.form.get(f'trips[{trip_index}][purpose]', '').strip()
            distance = request.form.get(f'trips[{trip_index}][distance]', '').strip()
            
            # If no from_address, we've reached the end of trips
            if not from_addr:
                break
                
            trips_data.append({
                'from_address': from_addr,
                'to_address': to_addr,
                'purpose': purpose,
                'distance': distance
            })
            trip_index += 1
        
        # Validate that we have at least one trip with required fields
        if not vehicle_id or not trip_date or not trips_data:
            flash('All required fields must be filled.', 'error')
            vehicles = get_user_vehicles(user_id)
            return render_template('add_trip.html', vehicles=vehicles, user=get_user_by_id(user_id))
        
        # Validate each trip has required fields
        for i, trip in enumerate(trips_data):
            if not all([trip['from_address'], trip['to_address'], trip['purpose']]):
                flash(f'Trip {i+1}: All required fields (From, To, Purpose) must be filled.', 'error')
                vehicles = get_user_vehicles(user_id)
                return render_template('add_trip.html', vehicles=vehicles, user=get_user_by_id(user_id))
        
        # Add all trips
        success_count = 0
        error_messages = []
        
        for trip in trips_data:
            # Convert distance to float if provided
            trip_distance = None
            if trip['distance']:
                try:
                    trip_distance = float(trip['distance'])
                except ValueError:
                    error_messages.append(f"Invalid distance value: {trip['distance']}")
                    continue
            
            # Convert reimbursement_rate to float if provided
            trip_rate = None
            if reimbursement_rate:
                try:
                    trip_rate = float(reimbursement_rate)
                except ValueError:
                    error_messages.append(f"Invalid reimbursement rate: {reimbursement_rate}")
                    continue
            
            success, message, _ = add_trip(
                user_id=user_id,
                vehicle_id=vehicle_id,
                trip_date=trip_date,
                from_address=trip['from_address'],
                to_address=trip['to_address'],
                purpose=trip['purpose'],
                distance=trip_distance,
                trip_type=trip_type,
                notes='',
                reimbursement_rate=trip_rate
            )
            
            if success:
                success_count += 1
            else:
                error_messages.append(message)
        
        if success_count > 0:
            flash(f'Successfully added {success_count} trip(s).', 'success')
            if error_messages:
                for err in error_messages:
                    flash(err, 'warning')
            return redirect(url_for('trip_list'))
        else:
            for err in error_messages:
                flash(err, 'error')
    
    vehicles = get_user_vehicles(user_id)
    return render_template('add_trip.html', vehicles=vehicles, user=get_user_by_id(user_id))


@app.route('/trips/<int:trip_id>')
@login_required
def view_trip(trip_id):
    """View details of a specific trip."""
    user_id = session['user_id']
    trip = get_trip_by_id(trip_id, user_id)
    
    if not trip:
        flash('Trip not found or access denied.', 'error')
        return redirect(url_for('trip_list'))
    
    vehicle = get_vehicle_by_id(trip['vehicle_id'], user_id) if trip.get('vehicle_id') else None
    
    return render_template('view_trip.html', 
                         trip=trip, 
                         vehicle=vehicle,
                         user=get_user_by_id(user_id))


@app.route('/trips/<int:trip_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_trip_route(trip_id):
    """Edit an existing trip."""
    user_id = session['user_id']
    trip = get_trip_by_id(trip_id, user_id)
    
    if not trip:
        flash('Trip not found or access denied.', 'error')
        return redirect(url_for('trip_list'))
    
    if request.method == 'POST':
        vehicle_id = request.form.get('vehicle_id', type=int)
        trip_date = request.form.get('trip_date', '').strip()
        from_address = request.form.get('from_address', '').strip()
        to_address = request.form.get('to_address', '').strip()
        purpose = request.form.get('purpose', '').strip()
        distance = request.form.get('distance', '').strip()
        trip_type = request.form.get('trip_type', trip['trip_type'])
        notes = request.form.get('notes', '').strip()
        reimbursement_rate = request.form.get('reimbursement_rate', '').strip()
        
        success, message = update_trip(
            trip_id=trip_id,
            user_id=user_id,
            vehicle_id=vehicle_id,
            trip_date=trip_date,
            from_address=from_address,
            to_address=to_address,
            purpose=purpose,
            distance=distance if distance else None,
            trip_type=trip_type,
            notes=notes,
            reimbursement_rate=reimbursement_rate if reimbursement_rate else None
        )
        
        if success:
            flash(message, 'success')
            return redirect(url_for('view_trip', trip_id=trip_id))
        else:
            flash(message, 'error')
    
    vehicles = get_user_vehicles(user_id)
    return render_template('edit_trip.html', 
                         trip=trip, 
                         vehicles=vehicles,
                         user=get_user_by_id(user_id))


@app.route('/trips/<int:trip_id>/delete', methods=['POST'])
@login_required
def delete_trip_route(trip_id):
    """Delete a trip."""
    user_id = session['user_id']
    success, message = delete_trip(trip_id, user_id)
    
    flash(message, 'success' if success else 'error')
    return redirect(url_for('trip_list'))


# ===============================================
# Expense Routes (Sprint 5 - FIXED & COMPLETE)
# ===============================================

RECEIPT_FOLDER = "static/receipts"
ALLOWED_RECEIPT_EXTENSIONS = {"png", "jpg", "jpeg", "pdf"}
os.makedirs(RECEIPT_FOLDER, exist_ok=True)

def allowed_receipt_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_RECEIPT_EXTENSIONS


@app.route('/expenses')
@login_required
def expense_list():
    """List all expenses for the current user with filters."""
    from expense_helpers import get_user_expenses, get_expense_summary, EXPENSE_CATEGORIES
    from vehicle_helpers import get_user_vehicles
    
    user_id = session['user_id']
    user = get_user_by_id(user_id)
    
    # Get filter parameters
    selected_vehicle = request.args.get('vehicle_id', '', type=int)
    selected_category = request.args.get('category', '')
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    
    # Get all expenses and vehicles
    expenses = get_user_expenses(user_id)
    vehicles = get_user_vehicles(user_id)
    
    # Apply filters
    if selected_vehicle:
        expenses = [e for e in expenses if e.get('vehicle_id') == selected_vehicle]
    
    if selected_category:
        expenses = [e for e in expenses if e.get('expense_type') == selected_category]
    
    if start_date:
        expenses = [e for e in expenses if e.get('expense_date', '') >= start_date]
    
    if end_date:
        expenses = [e for e in expenses if e.get('expense_date', '') <= end_date]
    
    # Get summary with filters applied
    summary = get_expense_summary(user_id, selected_vehicle, start_date, end_date)
    
    return render_template('expense_list.html',
                         expenses=expenses,
                         user=user,
                         summary=summary,
                         vehicles=vehicles,
                         categories=EXPENSE_CATEGORIES,
                         selected_vehicle=selected_vehicle,
                         selected_category=selected_category,
                         start_date=start_date,
                         end_date=end_date)



@app.route('/debug-expense')
@login_required
def debug_expense():
    """Debug route to check vehicle loading"""
    try:
        user_id = session['user_id']
        user = get_user_by_id(user_id)
        vehicles = get_user_vehicles(user_id)
        
        debug_info = {
            'user_id': user_id,
            'user_exists': bool(user),
            'user_email': user.get('email') if user else None,
            'vehicles_count': len(vehicles),
            'vehicles': [
                {
                    'id': v.get('id'),
                    'registration': v.get('registration'),
                    'make': v.get('make'),
                    'model': v.get('model')
                } for v in vehicles
            ]
        }
        
        return {
            'status': 'debug info',
            'data': debug_info
        }
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e)
        }

@app.route('/expenses/add', methods=['GET', 'POST'])
@login_required
def add_expense_route():
    """Add a new expense with optional receipt upload."""
    from expense_helpers import EXPENSE_CATEGORIES
    
    user_id = session['user_id']
    user = get_user_by_id(user_id)
    vehicles = get_user_vehicles(user_id)  # ✅ GET VEHICLES
    
    if request.method == 'POST':
        vehicle_id = request.form.get('vehicle_id', type=int)  # ✅ ADDED
        expense_date = request.form.get('date', '').strip()    # ✅ FIXED
        expense_type = request.form.get('category', '').strip() # ✅ FIXED
        amount = request.form.get('amount', '').strip()        # ✓ Already correct
        notes = request.form.get('description', '').strip()    # ✅ FIXED
        receipt_file = request.files.get('receipt')            # ✓ Already correct
        
        if not all([expense_date, expense_type, amount]):
            flash('Date, category, and amount are required.', 'error')
            return render_template('add_expense.html', user=user, categories=EXPENSE_CATEGORIES, vehicles=vehicles, today=date.today().isoformat())
        
        receipt_filename = None
        
        if receipt_file and receipt_file.filename and allowed_receipt_file(receipt_file.filename):
            filename = secure_filename(receipt_file.filename)
            # Generate unique filename
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            receipt_filename = f"{session['user_id']}_{timestamp}_{filename}"
            receipt_file.save(os.path.join(RECEIPT_FOLDER, receipt_filename))
        
        # Add to database
        success, message, expense_id = add_expense(
            user_id=user_id,
            vehicle_id=vehicle_id,  # ✅ ADDED - now saves vehicle assignment
            expense_date=expense_date,
            expense_type=expense_type,
            amount=amount,
            notes=notes,
            receipt_filename=receipt_filename
        )
        
        if success:
            flash(message, 'success')
            return redirect(url_for('expense_list'))
        else:
            flash(message, 'error')
    
    return render_template('add_expense.html', user=user, categories=EXPENSE_CATEGORIES, vehicles=vehicles, today=date.today().isoformat())


@app.route('/expenses/<int:expense_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_expense_route(expense_id):
    """Edit an existing expense."""
    from expense_helpers import EXPENSE_CATEGORIES
    
    user_id = session['user_id']
    user = get_user_by_id(user_id)
    vehicles = get_user_vehicles(user_id)  # ✅ GET VEHICLES
    expense = get_expense_by_id(expense_id, user_id)
    
    if not expense:
        flash('Expense not found or access denied.', 'error')
        return redirect(url_for('expense_list'))
    
    if request.method == 'POST':
        vehicle_id = request.form.get('vehicle_id', type=int)  # ✅ ADDED
        expense_date = request.form.get('date', '').strip()    # ✅ FIXED
        expense_type = request.form.get('category', '').strip() # ✅ FIXED
        amount = request.form.get('amount', '').strip()        # ✓ Already correct
        notes = request.form.get('description', '').strip()    # ✅ FIXED
        receipt_file = request.files.get('receipt')            # ✓ Already correct
        
        receipt_filename = expense.get('receipt_filename')
        
        if receipt_file and receipt_file.filename and allowed_receipt_file(receipt_file.filename):
            # Delete old receipt if exists
            if receipt_filename:
                old_path = os.path.join(RECEIPT_FOLDER, receipt_filename)
                try:
                    if os.path.exists(old_path):
                        os.remove(old_path)
                except Exception as e:
                    print(f"Warning: Could not delete old receipt: {e}")
            
            # Save new receipt
            filename = secure_filename(receipt_file.filename)
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            receipt_filename = f"{session['user_id']}_{timestamp}_{filename}"
            receipt_file.save(os.path.join(RECEIPT_FOLDER, receipt_filename))

        success, message = update_expense(
            expense_id=expense_id,
            user_id=session['user_id'],
            vehicle_id=vehicle_id,  # ✅ ADDED - now saves vehicle assignment
            expense_date=expense_date,
            expense_type=expense_type,
            amount=amount,
            notes=notes,
            receipt_filename=receipt_filename
        )
        
        if success:
            flash(message, 'success')
            return redirect(url_for('expense_list'))
        else:
            flash(message, 'error')
    
    return render_template('edit_expense.html', expense=expense, user=user, categories=EXPENSE_CATEGORIES, vehicles=vehicles)


@app.route('/expenses/<int:expense_id>/delete', methods=['POST'])
@login_required
def delete_expense_route(expense_id):
    """Delete an expense and its receipt."""
    user_id = session['user_id']
    expense = get_expense_by_id(expense_id, user_id)
    
    if not expense:
        flash('Expense not found or access denied.', 'error')
        return redirect(url_for('expense_list'))
    
    if expense.get('receipt_filename'):
        receipt_path = os.path.join(RECEIPT_FOLDER, expense['receipt_filename'])
        try:
            if os.path.exists(receipt_path):
                os.remove(receipt_path)
        except Exception as e:
            print(f"Warning: Could not delete receipt file: {e}")
    
    success, message = delete_expense(expense_id, user_id)
    flash(message, 'success' if success else 'error')
    return redirect(url_for('expense_list'))


# ===============================================
# Accident Routes (Sprint 6 - NEW)
# ===============================================

ACCIDENT_PHOTO_FOLDER = "static/accident_photos"
ALLOWED_PHOTO_EXTENSIONS = {"png", "jpg", "jpeg"}
MAX_PHOTOS_PER_ACCIDENT = 20
os.makedirs(ACCIDENT_PHOTO_FOLDER, exist_ok=True)

def allowed_photo_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_PHOTO_EXTENSIONS


@app.route('/accidents')
@login_required
def accident_list():
    """List all accidents for the current user."""
    
    user = get_user_by_id(session['user_id'])
    vehicles = get_user_vehicles(session['user_id'])
    
    # Get filter parameters
    vehicle_filter = request.args.get('vehicle_id', None)
    status_filter = request.args.get('status', None)
    
    # Convert vehicle_id to int if provided
    if vehicle_filter:
        try:
            vehicle_filter = int(vehicle_filter)
        except ValueError:
            vehicle_filter = None
    
    accidents = get_user_accidents(session['user_id'], vehicle_id=vehicle_filter, status=status_filter)
    total_count = get_accident_count(session['user_id'])
    
    return render_template('accident_list.html',
                         accidents=accidents,
                         vehicles=vehicles,
                         user=user,
                         statuses=ACCIDENT_STATUSES,
                         total_count=total_count,
                         selected_vehicle=vehicle_filter,
                         selected_status=status_filter)


@app.route('/accidents/add', methods=['GET', 'POST'])
@login_required
def add_accident_route():
    """Add a new accident with optional photos."""
    user_id = session['user_id']
    user = get_user_by_id(user_id)
    vehicles = get_user_vehicles(user_id)
    
    if request.method == 'POST':
        vehicle_id = request.form.get('vehicle_id', type=int)
        accident_date = request.form.get('accident_date', '').strip()
        accident_time = request.form.get('accident_time', '').strip()
        location = request.form.get('location', '').strip()
        description = request.form.get('circumstances', '').strip()
        severity = request.form.get('severity', 'Minor')
        police_report_number = request.form.get('police_report_number', '').strip()
        other_party_name = request.form.get('other_party_name', '').strip()
        other_party_contact = request.form.get('other_party_contact', '').strip()
        insurance_claim_number = request.form.get('insurance_claim_number', '').strip()
        photos = request.files.getlist('photos')
        
        if not all([vehicle_id, accident_date, location, description]):
            flash('Vehicle, date, location, and description are required.', 'error')
            return render_template('add_accident.html', 
                                 vehicles=vehicles, 
                                 user=user, 
                                 severity_levels=SEVERITY_LEVELS,
                                 weather_options=WEATHER_CONDITIONS,
                                 road_options=ROAD_CONDITIONS,
                                 statuses=ACCIDENT_STATUSES,
                                 today=date.today().isoformat())
        
        success, message, accident_id = add_accident(
            user_id=user_id,
            vehicle_id=vehicle_id,
            accident_date=accident_date,
            accident_time=accident_time,
            location=location,
            circumstances=description,
            police_report_number=police_report_number,
            other_driver_name=other_party_name,
            other_driver_phone=other_party_contact,
            insurance_claim_number=insurance_claim_number
        )
        
        if success:
            photo_count = 0
            for photo in photos:
                if photo and photo.filename and allowed_photo_file(photo.filename):
                    if photo_count >= MAX_PHOTOS_PER_ACCIDENT:
                        flash(f'Maximum {MAX_PHOTOS_PER_ACCIDENT} photos allowed per accident.', 'warning')
                        break
                    
                    filename = secure_filename(photo.filename)
                    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')
                    photo_filename = f"accident_{accident_id}_{timestamp}_{filename}"
                    photo.save(os.path.join(ACCIDENT_PHOTO_FOLDER, photo_filename))
                    
                    # Add to database
                    add_accident_photo(accident_id, photo_filename)
                    photo_count += 1
            
            flash(message, 'success')
            return redirect(url_for('accident_list'))
        else:
            flash(message, 'error')
    
    return render_template('add_accident.html', 
                         vehicles=vehicles, 
                         user=user, 
                         severity_levels=SEVERITY_LEVELS,
                         weather_options=WEATHER_CONDITIONS,
                         road_options=ROAD_CONDITIONS,
                         statuses=ACCIDENT_STATUSES,
                         today=date.today().isoformat())


@app.route('/accidents/<int:accident_id>')
@login_required
def view_accident(accident_id):
    """View details of a specific accident."""
    user_id = session['user_id']
    user = get_user_by_id(user_id)
    accident = get_accident_by_id(accident_id, user_id)
    
    if not accident:
        flash('Accident not found or access denied.', 'error')
        return redirect(url_for('accident_list'))
    
    vehicle = get_vehicle_by_id(accident['vehicle_id'], user_id) if accident.get('vehicle_id') else None
    photos = get_accident_photos(accident_id)
    
    return render_template('view_accident.html',
                         accident=accident,
                         vehicle=vehicle,
                         photos=photos,
                         user=user)


@app.route('/accidents/<int:accident_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_accident_route(accident_id):
    """Edit an existing accident."""
    user_id = session['user_id']
    user = get_user_by_id(user_id)
    accident = get_accident_by_id(accident_id, user_id)
    
    if not accident:
        flash('Accident not found or access denied.', 'error')
        return redirect(url_for('accident_list'))
    
    vehicles = get_user_vehicles(user_id)
    photos = get_accident_photos(accident_id)
    current_photo_count = len(photos)
    
    if request.method == 'POST':
        vehicle_id = request.form.get('vehicle_id', type=int)
        accident_date = request.form.get('accident_date', '').strip()
        accident_time = request.form.get('accident_time', '').strip()
        location = request.form.get('location', '').strip()
        description = request.form.get('circumstances', '').strip()
        severity = request.form.get('severity', accident['severity'])
        police_report_number = request.form.get('police_report_number', '').strip()
        other_party_name = request.form.get('other_party_name', '').strip()
        other_party_contact = request.form.get('other_party_contact', '').strip()
        insurance_claim_number = request.form.get('insurance_claim_number', '').strip()
        new_photos = request.files.getlist('photos')
        
        success, message = update_accident(
            accident_id=accident_id,
            user_id=user_id,
            vehicle_id=vehicle_id,
            accident_date=accident_date,
            accident_time=accident_time,
            location=location,
            description=description,
            severity=severity,
            police_report_number=police_report_number,
            other_party_name=other_party_name,
            other_party_contact=other_party_contact,
            insurance_claim_number=insurance_claim_number
        )
        
        if success:
            photo_count = 0
            for photo in new_photos:
                if photo and photo.filename and allowed_photo_file(photo.filename):
                    if current_photo_count + photo_count >= MAX_PHOTOS_PER_ACCIDENT:
                        flash(f'Maximum {MAX_PHOTOS_PER_ACCIDENT} photos allowed per accident.', 'warning')
                        break
                    
                    filename = secure_filename(photo.filename)
                    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')
                    photo_filename = f"accident_{accident_id}_{timestamp}_{filename}"
                    photo.save(os.path.join(ACCIDENT_PHOTO_FOLDER, photo_filename))
                    
                    add_accident_photo(accident_id, photo_filename)
                    photo_count += 1
            
            flash(message, 'success')
            return redirect(url_for('view_accident', accident_id=accident_id))
        else:
            flash(message, 'error')
    
    return render_template('edit_accident.html',
                         accident=accident,
                         vehicles=vehicles,
                         photos=photos,
                         user=user,
                         severity_levels=SEVERITY_LEVELS,
                         weather_options=WEATHER_CONDITIONS,
                         road_options=ROAD_CONDITIONS,
                         statuses=ACCIDENT_STATUSES,
                         max_photos=MAX_PHOTOS_PER_ACCIDENT)


@app.route('/accidents/<int:accident_id>/delete', methods=['POST'])
@login_required
def delete_accident_route(accident_id):
    """Delete an accident and all its photos."""
    user_id = session['user_id']
    accident = get_accident_by_id(accident_id, user_id)
    
    if not accident:
        flash('Accident not found or access denied.', 'error')
        return redirect(url_for('accident_list'))
    
    photos = get_accident_photos(accident_id)
    for photo in photos:
        photo_path = os.path.join(ACCIDENT_PHOTO_FOLDER, photo['filename'])
        try:
            if os.path.exists(photo_path):
                os.remove(photo_path)
        except Exception as e:
            print(f"Warning: Could not delete photo file: {e}")
    
    success, message = delete_accident(accident_id, user_id)
    flash(message, 'success' if success else 'error')
    return redirect(url_for('accident_list'))


@app.route('/accidents/photos/<int:photo_id>/delete', methods=['POST'])
@login_required
def delete_accident_photo_route(photo_id):
    """Delete a single accident photo."""
    user_id = session['user_id']
    accident_id = request.form.get('accident_id')
    
    if not accident_id:
        flash('Invalid request.', 'error')
        return redirect(url_for('accident_list'))
    
    accident = get_accident_by_id(int(accident_id), user_id)
    if not accident:
        flash('Access denied.', 'error')
        return redirect(url_for('accident_list'))
    
    photos = get_accident_photos(int(accident_id))
    photo = next((p for p in photos if p['id'] == photo_id), None)
    
    if photo:
        photo_path = os.path.join(ACCIDENT_PHOTO_FOLDER, photo['filename'])
        try:
            if os.path.exists(photo_path):
                os.remove(photo_path)
        except Exception as e:
            print(f"Warning: Could not delete photo file: {e}")
        
        delete_accident_photo(photo_id)
        flash('Photo deleted successfully.', 'success')
    else:
        flash('Photo not found.', 'error')
    
    return redirect(url_for('edit_accident_route', accident_id=accident_id))


@app.route('/accidents/checklist')
@login_required
def accident_checklist():
    """Display accident response checklist."""
    user = get_user_by_id(session['user_id'])
    return render_template('accident_checklist.html', user=user)


# ===============================================
# Export Routes (CSV & PDF)
# ===============================================

@app.route('/expenses/export/csv')
@login_required
def export_expenses_csv():
    user_id = session['user_id']
    expenses = get_user_expenses(user_id)

    def generate():
        header = ['Date', 'Category', 'Description', 'Amount']
        yield ','.join(header) + '\n'

        for exp in expenses:
            row = [
                exp.get('expense_date', ''),
                exp.get('expense_type', ''),
                exp.get('notes', ''),
                str(exp.get('amount', 0))
            ]
            yield ','.join(row) + '\n'

    # Return CSV response
    return Response(generate(),
                    mimetype='text/csv',
                    headers={"Content-Disposition": "attachment;filename=expenses.csv"})

# ===============================================
# Export PDF Files
# ===============================================

@app.route('/expenses/export/pdf')
@login_required
def export_expenses_pdf():
    user_id = session['user_id']
    expenses = get_user_expenses(user_id)
    user = get_user_by_id(user_id)

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    # Get user information with proper fallback
    username = user.get('username') or user.get('email', 'User').split('@')[0] if user.get('email') else 'User'
    
    # Add BizDrive logo to left top header
    try:
        logo_path = os.path.join(os.path.dirname(__file__), 'static', 'images', 'BizDrive-logo.png')
        if os.path.exists(logo_path):
            pdf.drawImage(logo_path, 40, height - 80, width=60, height=40, preserveAspectRatio=True)
    except:
        pass  # Continue without logo if there's an issue

    # Title with proper positioning
    pdf.setTitle(f"{username}_Expenses_Report")
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(120, height - 60, "BizDrive Fleet Management")
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(120, height - 80, f"Expenses Report for {username}")
    
    # Add generation date
    pdf.setFont("Helvetica", 10)
    pdf.drawString(120, height - 95, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Draw line under header
    pdf.setStrokeColorRGB(0.2, 0.2, 0.2)
    pdf.line(40, height - 110, width - 40, height - 110)

    # Table headers
    pdf.setFont("Helvetica-Bold", 11)
    y = height - 130
    pdf.drawString(50, y, "Date")
    pdf.drawString(130, y, "Vehicle")
    pdf.drawString(220, y, "Category")
    pdf.drawString(320, y, "Description")
    pdf.drawString(470, y, "Amount")
    pdf.setFillColorRGB(0.2, 0.2, 0.2)
    pdf.line(50, y - 5, width - 50, y - 5)
    pdf.setFillColorRGB(0, 0, 0)

    # Data rows
    pdf.setFont("Helvetica", 10)
    y -= 20
    total_amount = 0
    
    for exp in expenses:
        if y < 80:  # New page if needed
            pdf.showPage()
            y = height - 50
            # Redraw headers on new page
            pdf.setFont("Helvetica-Bold", 11)
            pdf.drawString(50, y, "Date")
            pdf.drawString(130, y, "Vehicle")
            pdf.drawString(220, y, "Category")
            pdf.drawString(320, y, "Description")
            pdf.drawString(470, y, "Amount")
            pdf.setFillColorRGB(0.2, 0.2, 0.2)
            pdf.line(50, y - 5, width - 50, y - 5)
            pdf.setFillColorRGB(0, 0, 0)
            pdf.setFont("Helvetica", 10)
            y -= 20

        # Draw row data
        pdf.drawString(50, y, str(exp.get('expense_date', '')))
        pdf.drawString(130, y, str(exp.get('vehicle_registration', 'N/A')))
        pdf.drawString(220, y, str(exp.get('expense_type', '')))
        pdf.drawString(320, y, str(exp.get('notes', ''))[:30])  # Limit description length
        amount = exp.get('amount', 0)
        pdf.drawString(470, y, f"${float(amount):.2f}")
        total_amount += float(amount)
        y -= 15

    # Add total at bottom
    if y > 120:  # Only add total if there's space
        pdf.setFillColorRGB(0.2, 0.2, 0.2)
        pdf.line(50, y - 5, width - 50, y - 5)
        pdf.setFillColorRGB(0, 0, 0)
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(420, y - 20, f"Total: ${total_amount:.2f}")

    pdf.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name="expenses.pdf", mimetype='application/pdf')


# ===============================================
# Export Trips CSV Files
# ===============================================

@app.route('/trips/export/csv')
@login_required
def export_trips_csv():
    user_id = session['user_id']
    trips = get_user_trips(user_id)

    def generate():
        header = ['Date', 'Vehicle', 'From', 'To', 'Purpose', 'Distance', 'Type']
        yield ','.join(header) + '\n'

        for t in trips:
            row = [
                t.get('trip_date', ''),
                t.get('vehicle_registration', ''),  # ensure your helper returns vehicle registration
                t.get('from_address', ''),
                t.get('to_address', ''),
                t.get('purpose', ''),
                str(t.get('distance', '')),
                t.get('trip_type', '')
            ]
            yield ','.join(row) + '\n'

    return Response(generate(),
                    mimetype='text/csv',
                    headers={"Content-Disposition": "attachment;filename=trips.csv"})


# ===============================================
# Export Trips PDF Files
# ===============================================

@app.route('/trips/export/pdf')
@login_required
def export_trips_pdf():
    user_id = session['user_id']
    trips = get_user_trips(user_id)
    user = get_user_by_id(user_id)

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    # Get user information with proper fallback
    username = user.get('username') or user.get('email', 'User').split('@')[0] if user.get('email') else 'User'
    
    # Add BizDrive logo to left top header
    try:
        logo_path = os.path.join(os.path.dirname(__file__), 'static', 'images', 'BizDrive-logo.png')
        if os.path.exists(logo_path):
            pdf.drawImage(logo_path, 40, height - 80, width=60, height=40, preserveAspectRatio=True)
    except:
        pass  # Continue without logo if there's an issue

    # Title with proper positioning
    pdf.setTitle(f"{username}_Trips_Report")
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(120, height - 60, "BizDrive Fleet Management")
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(120, height - 80, f"Trips Report for {username}")
    
    # Add generation date
    pdf.setFont("Helvetica", 10)
    pdf.drawString(120, height - 95, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Draw line under header
    pdf.setStrokeColorRGB(0.2, 0.2, 0.2)
    pdf.line(40, height - 110, width - 40, height - 110)

    # Table headers
    pdf.setFont("Helvetica-Bold", 10)
    y = height - 130
    headers = ["Date", "Vehicle", "From", "To", "Purpose", "Distance", "Type"]
    x_positions = [50, 110, 180, 250, 320, 410, 470]
    for x, h in zip(x_positions, headers):
        pdf.drawString(x, y, h)
    pdf.setFillColorRGB(0.2, 0.2, 0.2)
    pdf.line(50, y - 5, width - 50, y - 5)
    pdf.setFillColorRGB(0, 0, 0)

    # Data rows
    pdf.setFont("Helvetica", 9)
    y -= 20
    total_distance = 0
    
    for t in trips:
        if y < 80:  # New page if needed
            pdf.showPage()
            y = height - 50
            # Redraw headers on new page
            pdf.setFont("Helvetica-Bold", 10)
            for x, h in zip(x_positions, headers):
                pdf.drawString(x, y, h)
            pdf.setFillColorRGB(0.2, 0.2, 0.2)
            pdf.line(50, y - 5, width - 50, y - 5)
            pdf.setFillColorRGB(0, 0, 0)
            pdf.setFont("Helvetica", 9)
            y -= 20

        # Draw row data with proper field names
        pdf.drawString(50, y, str(t.get('trip_date', '')))
        pdf.drawString(110, y, str(t.get('vehicle_registration', 'N/A')))
        pdf.drawString(180, y, str(t.get('from_address', ''))[:20])  # Limit length
        pdf.drawString(250, y, str(t.get('to_address', ''))[:20])    # Limit length
        pdf.drawString(320, y, str(t.get('purpose', ''))[:25])       # Limit length
        distance = t.get('distance', 0)
        pdf.drawString(410, y, f"{float(distance):.1f} km")
        pdf.drawString(470, y, str(t.get('trip_type', '')))
        total_distance += float(distance)
        y -= 15

    # Add total at bottom
    if y > 120:  # Only add total if there's space
        pdf.setFillColorRGB(0.2, 0.2, 0.2)
        pdf.line(50, y - 5, width - 50, y - 5)
        pdf.setFillColorRGB(0, 0, 0)
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(420, y - 20, f"Total Distance: {total_distance:.1f} km")
        y -= 20
        if y < 50:
            pdf.showPage()
            y = height - 50

    pdf.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name="trips.pdf", mimetype='application/pdf')


# ===============================================
# Export Vehicles CSV Files
# ===============================================
@app.route('/vehicles/export/csv')
@login_required
def export_vehicles_csv():
    user_id = session['user_id']
    vehicles = get_user_vehicles(user_id)

    def generate():
        header = ['Registration', 'Make', 'Model', 'Year', 'Odometer', 'Status', 'Purchase Date']
        yield ','.join(header) + '\n'

        for v in vehicles:
            row = [
                v.get('registration', ''),
                v.get('make', ''),
                v.get('model', ''),
                str(v.get('year', '')),
                str(v.get('odometer', '')),
                v.get('status', ''),
                v.get('purchase_date', '')
            ]
            yield ','.join(row) + '\n'

    return Response(generate(),
                    mimetype='text/csv',
                    headers={"Content-Disposition": "attachment;filename=vehicles.csv"})




# ===============================================
# Export Vehicles PDF Files
# ===============================================

@app.route('/vehicles/export/pdf')
@login_required
def export_vehicles_pdf():
    user_id = session['user_id']
    vehicles = get_user_vehicles(user_id)
    user = get_user_by_id(user_id)

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    # Get user information with proper fallback
    username = user.get('username') or user.get('email', 'User').split('@')[0] if user.get('email') else 'User'
    
    # Add BizDrive logo to left top header
    try:
        logo_path = os.path.join(os.path.dirname(__file__), 'static', 'images', 'BizDrive-logo.png')
        if os.path.exists(logo_path):
            pdf.drawImage(logo_path, 40, height - 80, width=60, height=40, preserveAspectRatio=True)
    except:
        pass  # Continue without logo if there's an issue

    # Title with proper positioning
    pdf.setTitle(f"{username}_Vehicles_Report")
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(120, height - 60, "BizDrive Fleet Management")
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(120, height - 80, f"Vehicles Report for {username}")
    
    # Add generation date
    pdf.setFont("Helvetica", 10)
    pdf.drawString(120, height - 95, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Draw line under header
    pdf.setStrokeColorRGB(0.2, 0.2, 0.2)
    pdf.line(40, height - 110, width - 40, height - 110)

    # Table headers
    pdf.setFont("Helvetica-Bold", 11)
    y = height - 130
    headers = ["Registration", "Make", "Model", "Year", "Odometer", "Status", "Purchase Date"]
    x_positions = [50, 130, 210, 270, 330, 400, 480]
    for x, h in zip(x_positions, headers):
        pdf.drawString(x, y, h)
    pdf.setFillColorRGB(0.2, 0.2, 0.2)
    pdf.line(50, y - 5, width - 50, y - 5)
    pdf.setFillColorRGB(0, 0, 0)

    # Data rows
    pdf.setFont("Helvetica", 10)
    y -= 20
    total_vehicles = len(vehicles)
    active_vehicles = 0
    
    for v in vehicles:
        if y < 80:  # New page if needed
            pdf.showPage()
            y = height - 50
            # Redraw headers on new page
            pdf.setFont("Helvetica-Bold", 11)
            for x, h in zip(x_positions, headers):
                pdf.drawString(x, y, h)
            pdf.setFillColorRGB(0.2, 0.2, 0.2)
            pdf.line(50, y - 5, width - 50, y - 5)
            pdf.setFillColorRGB(0, 0, 0)
            pdf.setFont("Helvetica", 10)
            y -= 20

        # Draw row data
        pdf.drawString(50, y, str(v.get('registration', '')))
        pdf.drawString(130, y, str(v.get('make', '')))
        pdf.drawString(210, y, str(v.get('model', '')))
        pdf.drawString(270, y, str(v.get('year', '')))
        pdf.drawString(330, y, str(v.get('odometer', '')))
        status = str(v.get('status', ''))
        pdf.drawString(400, y, status)
        pdf.drawString(480, y, str(v.get('purchase_date', '')))
        
        if status.lower() == 'active':
            active_vehicles += 1
        y -= 15

    # Add summary at bottom
    if y > 120:  # Only add summary if there's space
        pdf.setFillColorRGB(0.2, 0.2, 0.2)
        pdf.line(50, y - 5, width - 50, y - 5)
        pdf.setFillColorRGB(0, 0, 0)
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(50, y - 20, f"Total Vehicles: {total_vehicles}")
        pdf.drawString(200, y - 20, f"Active Vehicles: {active_vehicles}")
        pdf.drawString(350, y - 20, f"Inactive Vehicles: {total_vehicles - active_vehicles}")
        y -= 20
        if y < 50:
            pdf.showPage()
            y = height - 50

    pdf.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name="vehicles.pdf", mimetype='application/pdf')
# Admin Routes (Admin Only)
# ===============================================

@app.route('/admin')
@role_required('admin')
def admin_panel():
    """Admin panel - accessible only to admins."""
    return render_template('coming_soon.html', 
                         feature='Admin Panel', 
                         sprint='Sprint 7',
                         user=get_user_by_id(session['user_id']))


# ===============================================
# Admin Panel Routes (Sprint 7)
# ===============================================

@app.route('/admin/dashboard')
@login_required
@role_required('admin')
def admin_dashboard():
    """Admin dashboard with system-wide statistics."""
    import sqlite3
    
    conn = sqlite3.connect('bizdrive.db')
    cursor = conn.cursor()
    
    # Get system statistics
    stats = {}
    
    # Total users
    cursor.execute("SELECT COUNT(*) FROM users")
    stats['total_users'] = cursor.fetchone()[0]
    
    # Active users (assuming is_active column exists, otherwise all are active)
    stats['active_users'] = stats['total_users']
    
    # Total vehicles
    cursor.execute("SELECT COUNT(*) FROM vehicles")
    stats['total_vehicles'] = cursor.fetchone()[0]
    
    # Active vehicles
    cursor.execute("SELECT COUNT(*) FROM vehicles WHERE status = 'Active'")
    stats['active_vehicles'] = cursor.fetchone()[0]
    
    # Total trips
    cursor.execute("SELECT COUNT(*), COALESCE(SUM(distance), 0) FROM trips")
    trip_data = cursor.fetchone()
    stats['total_trips'] = trip_data[0]
    stats['total_distance'] = round(trip_data[1], 2)
    
    # Total expenses
    cursor.execute("SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM expenses")
    expense_data = cursor.fetchone()
    stats['expense_count'] = expense_data[0]
    stats['total_expenses'] = float(expense_data[1])
    
    # Recent users (last 5)
    cursor.execute("""
        SELECT username, email, role, 1 as is_active
        FROM users
        ORDER BY id DESC
        LIMIT 5
    """)
    recent_users = []
    for row in cursor.fetchall():
        recent_users.append({
            'username': row[0],
            'email': row[1],
            'role': row[2],
            'is_active': row[3]
        })
    
    # Recent accidents (last 5)
    cursor.execute("""
        SELECT a.accident_date, u.username, a.status, a.location
        FROM accidents a
        JOIN users u ON a.user_id = u.id
        ORDER BY a.accident_date DESC
        LIMIT 5
    """)
    recent_accidents = []
    for row in cursor.fetchall():
        recent_accidents.append({
            'accident_date': row[0],
            'username': row[1],
            'status': row[2],
            'location': row[3],
            'severity': 'N/A'  # Severity not in database schema
        })
    
    conn.close()
    
    return render_template('admin/dashboard.html',
                         stats=stats,
                         recent_users=recent_users,
                         recent_accidents=recent_accidents,
                         user=get_user_by_id(session['user_id']))


@app.route('/admin/users')
@login_required
@role_required('admin')
def admin_users():
    """User management page."""
    import sqlite3
    
    conn = sqlite3.connect('bizdrive.db')
    cursor = conn.cursor()
    
    # Get all users with their statistics
    cursor.execute("""
        SELECT 
            u.id,
            u.username,
            u.email,
            u.role,
            COUNT(DISTINCT v.id) as vehicle_count,
            COUNT(DISTINCT t.id) as trip_count,
            COALESCE(SUM(t.distance), 0) as total_distance
        FROM users u
        LEFT JOIN vehicles v ON u.id = v.user_id
        LEFT JOIN trips t ON u.id = t.user_id
        GROUP BY u.id, u.username, u.email, u.role
        ORDER BY u.id DESC
    """)
    
    users = []
    for row in cursor.fetchall():
        users.append({
            'id': row[0],
            'username': row[1],
            'email': row[2],
            'role': row[3],
            'vehicle_count': row[4],
            'trip_count': row[5],
            'total_distance': round(row[6], 2)
        })
    
    conn.close()
    
    return render_template('admin/users.html',
                         users=users,
                         user=get_user_by_id(session['user_id']))


@app.route('/admin/reports')
@login_required
@role_required('admin')
def admin_reports():
    """System reports page."""
    return render_template('admin/reports.html',
                         user=get_user_by_id(session['user_id']))


@app.route('/admin/settings')
@login_required
@role_required('admin')
def admin_settings():
    """System settings page."""
    import sqlite3
    
    conn = sqlite3.connect('bizdrive.db')
    cursor = conn.cursor()
    
    # Create settings table if it doesn't exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            setting_key TEXT UNIQUE NOT NULL,
            setting_value TEXT NOT NULL,
            setting_type TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Load settings from database
    settings = {}
    cursor.execute("SELECT setting_key, setting_value FROM settings")
    for row in cursor.fetchall():
        settings[row[0]] = row[1]
    
    # Load expense categories
    expense_categories = ['Fuel', 'Maintenance', 'Insurance', 'Registration', 'Parking', 'Tolls', 'Other']
    cursor.execute("SELECT setting_value FROM settings WHERE setting_type = 'expense_category'")
    custom_categories = [row[0] for row in cursor.fetchall()]
    expense_categories.extend(custom_categories)
    
    # Load accident severity levels
    accident_severity_levels = ['Minor', 'Moderate', 'Major', 'Severe']
    cursor.execute("SELECT setting_value FROM settings WHERE setting_type = 'accident_severity'")
    custom_severities = [row[0] for row in cursor.fetchall()]
    accident_severity_levels.extend(custom_severities)
    
    # Get system statistics
    stats = {}
    cursor.execute("SELECT COUNT(*) FROM users")
    stats['total_users'] = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM vehicles")
    stats['total_vehicles'] = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM trips")
    trips_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM expenses")
    expenses_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM accidents")
    accidents_count = cursor.fetchone()[0]
    
    stats['total_records'] = trips_count + expenses_count + accidents_count
    
    conn.close()
    
    return render_template('admin/settings.html',
                         settings=settings,
                         expense_categories=expense_categories,
                         accident_severity_levels=accident_severity_levels,
                         stats=stats,
                         user=get_user_by_id(session['user_id']))


@app.route('/admin/user/<int:user_id>')
@login_required
@role_required('admin')
def admin_user_details(user_id):
    """View detailed information about a specific user."""
    import sqlite3
    
    conn = sqlite3.connect('bizdrive.db')
    cursor = conn.cursor()
    
    # Get user details
    cursor.execute("SELECT id, username, email, role FROM users WHERE id = ?", (user_id,))
    user_row = cursor.fetchone()
    
    if not user_row:
        flash('User not found.', 'error')
        return redirect(url_for('admin_users'))
    
    target_user = {
        'id': user_row[0],
        'username': user_row[1],
        'email': user_row[2],
        'role': user_row[3]
    }
    
    # Get user's vehicles
    cursor.execute("SELECT id, registration, make, model, status FROM vehicles WHERE user_id = ?", (user_id,))
    vehicles = [{'id': r[0], 'registration': r[1], 'make': r[2], 'model': r[3], 'status': r[4]} 
                for r in cursor.fetchall()]
    
    # Get user's trip stats
    cursor.execute("""
        SELECT COUNT(*), COALESCE(SUM(distance), 0), COALESCE(SUM(reimbursement_amount), 0)
        FROM trips WHERE user_id = ?
    """, (user_id,))
    trip_stats = cursor.fetchone()
    
    # Get user's expense stats
    cursor.execute("""
        SELECT COUNT(*), COALESCE(SUM(amount), 0)
        FROM expenses WHERE user_id = ?
    """, (user_id,))
    expense_stats = cursor.fetchone()
    
    conn.close()
    
    return render_template('admin/user_details.html',
                         target_user=target_user,
                         vehicles=vehicles,
                         trip_count=trip_stats[0],
                         total_distance=round(trip_stats[1], 2),
                         total_reimbursement=round(trip_stats[2], 2),
                         expense_count=expense_stats[0],
                         total_expenses=float(expense_stats[1]),
                         user=get_user_by_id(session['user_id']))


@app.route('/admin/user/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_edit_user(user_id):
    """Edit user role and permissions."""
    if request.method == 'POST':
        new_role = request.form.get('role')
        
        if new_role not in ['driver', 'fleet_manager', 'admin']:
            flash('Invalid role selected.', 'error')
            return redirect(url_for('admin_edit_user', user_id=user_id))
        
        import sqlite3
        conn = sqlite3.connect('bizdrive.db')
        cursor = conn.cursor()
        
        cursor.execute("UPDATE users SET role = ? WHERE id = ?", (new_role, user_id))
        conn.commit()
        conn.close()
        
        flash(f'User role updated to {new_role}.', 'success')
        return redirect(url_for('admin_user_details', user_id=user_id))
    
    # GET request - show edit form
    import sqlite3
    conn = sqlite3.connect('bizdrive.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, email, role FROM users WHERE id = ?", (user_id,))
    user_row = cursor.fetchone()
    conn.close()
    
    if not user_row:
        flash('User not found.', 'error')
        return redirect(url_for('admin_users'))
    
    target_user = {
        'id': user_row[0],
        'username': user_row[1],
        'email': user_row[2],
        'role': user_row[3]
    }
    
    return render_template('admin/edit_user.html',
                         target_user=target_user,
                         user=get_user_by_id(session['user_id']))


# Export routes
@app.route('/admin/export/users')
@login_required
@role_required('admin')
def admin_export_users():
    """Export all users to CSV."""
    import csv
    from io import StringIO
    
    import sqlite3
    conn = sqlite3.connect('bizdrive.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, email, role FROM users")
    users = cursor.fetchall()
    conn.close()
    
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Username', 'Email', 'Role'])
    writer.writerows(users)
    
    response = Response(output.getvalue(), mimetype='text/csv')
    response.headers['Content-Disposition'] = 'attachment; filename=users_export.csv'
    return response


@app.route('/admin/export/vehicles')
@login_required
@role_required('admin')
def admin_export_vehicles():
    """Export all vehicles to CSV."""
    import csv
    from io import StringIO
    
    import sqlite3
    conn = sqlite3.connect('bizdrive.db')
    cursor = conn.cursor()
    cursor.execute("""
        SELECT v.id, u.username, v.registration, v.make, v.model, v.year, v.status
        FROM vehicles v
        JOIN users u ON v.user_id = u.id
    """)
    vehicles = cursor.fetchall()
    conn.close()
    
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Owner', 'Registration', 'Make', 'Model', 'Year', 'Status'])
    writer.writerows(vehicles)
    
    response = Response(output.getvalue(), mimetype='text/csv')
    response.headers['Content-Disposition'] = 'attachment; filename=vehicles_export.csv'
    return response


@app.route('/admin/export/trips')
@login_required
@role_required('admin')
def admin_export_trips():
    """Export all trips to CSV."""
    import csv
    from io import StringIO
    
    import sqlite3
    conn = sqlite3.connect('bizdrive.db')
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.id, u.username, v.registration, t.trip_date, t.from_address, 
               t.to_address, t.distance, t.trip_type, t.reimbursement_amount
        FROM trips t
        JOIN users u ON t.user_id = u.id
        LEFT JOIN vehicles v ON t.vehicle_id = v.id
    """)
    trips = cursor.fetchall()
    conn.close()
    
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'User', 'Vehicle', 'Date', 'From', 'To', 'Distance', 'Type', 'Reimbursement'])
    writer.writerows(trips)
    
    response = Response(output.getvalue(), mimetype='text/csv')
    response.headers['Content-Disposition'] = 'attachment; filename=trips_export.csv'
    return response


@app.route('/admin/export/expenses')
@login_required
@role_required('admin')
def admin_export_expenses():
    """Export all expenses to CSV."""
    import csv
    from io import StringIO
    
    import sqlite3
    conn = sqlite3.connect('bizdrive.db')
    cursor = conn.cursor()
    cursor.execute("""
        SELECT e.id, u.username, e.expense_date, e.expense_type, e.amount, e.notes
        FROM expenses e
        JOIN users u ON e.user_id = u.id
    """)
    expenses = cursor.fetchall()
    conn.close()
    
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'User', 'Date', 'Category', 'Amount', 'Notes'])
    writer.writerows(expenses)
    
    response = Response(output.getvalue(), mimetype='text/csv')
    response.headers['Content-Disposition'] = 'attachment; filename=expenses_export.csv'
    return response


@app.route('/admin/export/accidents')
@login_required
@role_required('admin')
def admin_export_accidents():
    """Export all accidents to CSV."""
    import csv
    from io import StringIO
    
    import sqlite3
    conn = sqlite3.connect('bizdrive.db')
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.id, u.username, v.registration, a.accident_date, a.location, 
               a.status, a.circumstances
        FROM accidents a
        JOIN users u ON a.user_id = u.id
        LEFT JOIN vehicles v ON a.vehicle_id = v.id
    """)
    accidents = cursor.fetchall()
    conn.close()
    
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'User', 'Vehicle', 'Date', 'Location', 'Status', 'Circumstances'])
    writer.writerows(accidents)
    
    response = Response(output.getvalue(), mimetype='text/csv')
    response.headers['Content-Disposition'] = 'attachment; filename=accidents_export.csv'
    return response


# ===============================================
# Admin PDF Report Routes
# ===============================================

@app.route('/admin/reports/monthly-pdf')
@login_required
@role_required('admin')
def admin_monthly_report():
    """Generate monthly summary PDF report"""
    import sqlite3
    from datetime import datetime, date
    
    conn = sqlite3.connect(os.path.join(os.path.dirname(__file__), 'bizdrive.db'))
    cursor = conn.cursor()
    
    # Get current month data
    current_date = datetime.now()
    current_month = current_date.strftime('%Y-%m')
    
    # Get monthly statistics
    stats = {}
    
    # Users
    cursor.execute("SELECT COUNT(*) FROM users")
    stats['total_users'] = cursor.fetchone()[0]
    
    # Vehicles
    cursor.execute("SELECT COUNT(*) FROM vehicles")
    stats['total_vehicles'] = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM vehicles WHERE status = 'Active'")
    stats['active_vehicles'] = cursor.fetchone()[0]
    
    # Monthly trips
    cursor.execute("""
        SELECT COUNT(*), COALESCE(SUM(distance), 0)
        FROM trips 
        WHERE strftime('%Y-%m', trip_date) = ?
    """, (current_month,))
    trip_data = cursor.fetchone()
    stats['monthly_trips'] = trip_data[0]
    stats['monthly_distance'] = round(trip_data[1], 2) if trip_data[1] else 0
    
    # Monthly expenses
    cursor.execute("""
        SELECT COUNT(*), COALESCE(SUM(amount), 0)
        FROM expenses 
        WHERE strftime('%Y-%m', expense_date) = ?
    """, (current_month,))
    expense_data = cursor.fetchone()
    stats['monthly_expenses_count'] = expense_data[0]
    stats['monthly_expenses_total'] = float(expense_data[1]) if expense_data[1] else 0
    
    # Monthly accidents
    cursor.execute("""
        SELECT COUNT(*)
        FROM accidents 
        WHERE strftime('%Y-%m', accident_date) = ?
    """, (current_month,))
    stats['monthly_accidents'] = cursor.fetchone()[0]
    
    conn.close()
    
    # Generate PDF
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    # Add BizDrive logo
    try:
        logo_path = os.path.join(os.path.dirname(__file__), 'static', 'images', 'BizDrive-logo.png')
        if os.path.exists(logo_path):
            pdf.drawImage(logo_path, 40, height - 80, width=60, height=40, preserveAspectRatio=True)
    except:
        pass
    
    # Header
    pdf.setTitle("BizDrive_Monthly_Report")
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(120, height - 60, "BizDrive Fleet Management")
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(120, height - 80, f"Monthly Summary Report - {current_date.strftime('%B %Y')}")
    
    pdf.setFont("Helvetica", 10)
    pdf.drawString(120, height - 95, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    pdf.setStrokeColorRGB(0.2, 0.2, 0.2)
    pdf.line(40, height - 110, width - 40, height - 110)
    
    # Statistics
    y = height - 140
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(50, y, "System Overview")
    y -= 25
    
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(50, y, f"Total Users:")
    pdf.drawString(200, y, str(stats['total_users']))
    y -= 20
    
    pdf.drawString(50, y, f"Total Vehicles:")
    pdf.drawString(200, y, f"{stats['total_vehicles']} ({stats['active_vehicles']} active)")
    y -= 30
    
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(50, y, f"Monthly Activity - {current_date.strftime('%B %Y')}")
    y -= 25
    
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(50, y, f"Total Trips:")
    pdf.drawString(200, y, f"{stats['monthly_trips']} trips")
    y -= 20
    
    pdf.drawString(50, y, f"Total Distance:")
    pdf.drawString(200, y, f"{stats['monthly_distance']} km")
    y -= 20
    
    pdf.drawString(50, y, f"Total Expenses:")
    pdf.drawString(200, y, f"${stats['monthly_expenses_total']:.2f} ({stats['monthly_expenses_count']} transactions)")
    y -= 20
    
    pdf.drawString(50, y, f"Total Accidents:")
    pdf.drawString(200, y, str(stats['monthly_accidents']))
    
    pdf.save()
    buffer.seek(0)
    
    return send_file(buffer, as_attachment=True, download_name=f"monthly_report_{current_month}.pdf", mimetype='application/pdf')


@app.route('/admin/reports/annual-pdf')
@login_required
@role_required('admin')
def admin_annual_report():
    """Generate annual summary PDF report"""
    import sqlite3
    from datetime import datetime
    
    conn = sqlite3.connect(os.path.join(os.path.dirname(__file__), 'bizdrive.db'))
    cursor = conn.cursor()
    
    current_year = datetime.now().year
    
    # Get annual statistics
    cursor.execute("""
        SELECT 
            COUNT(*) as total_trips,
            COALESCE(SUM(distance), 0) as total_distance,
            COUNT(DISTINCT vehicle_id) as vehicles_used
        FROM trips 
        WHERE strftime('%Y', trip_date) = ?
    """, (str(current_year),))
    trip_stats = cursor.fetchone()
    
    cursor.execute("""
        SELECT 
            COUNT(*) as total_expenses,
            COALESCE(SUM(amount), 0) as total_amount
        FROM expenses 
        WHERE strftime('%Y', expense_date) = ?
    """, (str(current_year),))
    expense_stats = cursor.fetchone()
    
    cursor.execute("""
        SELECT COUNT(*) as total_accidents
        FROM accidents 
        WHERE strftime('%Y', accident_date) = ?
    """, (str(current_year),))
    accident_stats = cursor.fetchone()
    
    # Monthly breakdown
    cursor.execute("""
        SELECT 
            strftime('%m', trip_date) as month,
            COUNT(*) as trips,
            COALESCE(SUM(distance), 0) as distance
        FROM trips 
        WHERE strftime('%Y', trip_date) = ?
        GROUP BY month
        ORDER BY month
    """, (str(current_year),))
    monthly_data = cursor.fetchall()
    
    conn.close()
    
    # Generate PDF
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    # Add BizDrive logo
    try:
        logo_path = os.path.join(os.path.dirname(__file__), 'static', 'images', 'BizDrive-logo.png')
        if os.path.exists(logo_path):
            pdf.drawImage(logo_path, 40, height - 80, width=60, height=40, preserveAspectRatio=True)
    except:
        pass
    
    # Header
    pdf.setTitle(f"BizDrive_Annual_Report_{current_year}")
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(120, height - 60, "BizDrive Fleet Management")
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(120, height - 80, f"Annual Summary Report - {current_year}")
    
    pdf.setFont("Helvetica", 10)
    pdf.drawString(120, height - 95, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    pdf.setStrokeColorRGB(0.2, 0.2, 0.2)
    pdf.line(40, height - 110, width - 40, height - 110)
    
    # Annual Summary
    y = height - 140
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(50, y, "Annual Overview")
    y -= 25
    
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(50, y, f"Total Trips:")
    pdf.drawString(200, y, f"{trip_stats[0]} trips")
    y -= 20
    
    pdf.drawString(50, y, f"Total Distance:")
    pdf.drawString(200, y, f"{trip_stats[1]:.2f} km")
    y -= 20
    
    pdf.drawString(50, y, f"Vehicles Used:")
    pdf.drawString(200, y, f"{trip_stats[2]} vehicles")
    y -= 20
    
    pdf.drawString(50, y, f"Total Expenses:")
    pdf.drawString(200, y, f"${expense_stats[1]:.2f} ({expense_stats[0]} transactions)")
    y -= 20
    
    pdf.drawString(50, y, f"Total Accidents:")
    pdf.drawString(200, y, str(accident_stats[0]))
    
    pdf.save()
    buffer.seek(0)
    
    return send_file(buffer, as_attachment=True, download_name=f"annual_report_{current_year}.pdf", mimetype='application/pdf')


@app.route('/admin/reports/full-pdf')
@login_required
@role_required('admin')
def admin_full_report():
    """Generate complete system PDF report"""
    import sqlite3
    from datetime import datetime
    
    conn = sqlite3.connect(os.path.join(os.path.dirname(__file__), 'bizdrive.db'))
    cursor = conn.cursor()
    
    # Get comprehensive system data
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM vehicles")
    total_vehicles = cursor.fetchone()[0]
    
    cursor.execute("""
        SELECT COUNT(*), COALESCE(SUM(distance), 0)
        FROM trips
    """)
    trip_stats = cursor.fetchone()
    
    cursor.execute("""
        SELECT COUNT(*), COALESCE(SUM(amount), 0)
        FROM expenses
    """)
    expense_stats = cursor.fetchone()
    
    cursor.execute("SELECT COUNT(*) FROM accidents")
    total_accidents = cursor.fetchone()[0]
    
    # Get recent activity
    cursor.execute("""
        SELECT 'Trip' as type, trip_date as date, 
               'Distance: ' || distance || 'km' as details
        FROM trips 
        ORDER BY trip_date DESC 
        LIMIT 3
    """)
    recent_trips = cursor.fetchall()
    
    cursor.execute("""
        SELECT 'Expense' as type, expense_date as date,
               expense_type || ': $' || amount as details
        FROM expenses 
        ORDER BY expense_date DESC 
        LIMIT 3
    """)
    recent_expenses = cursor.fetchall()
    
    conn.close()
    
    # Generate PDF
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    # Add BizDrive logo
    try:
        logo_path = os.path.join(os.path.dirname(__file__), 'static', 'images', 'BizDrive-logo.png')
        if os.path.exists(logo_path):
            pdf.drawImage(logo_path, 40, height - 80, width=60, height=40, preserveAspectRatio=True)
    except:
        pass
    
    # Header
    pdf.setTitle("BizDrive_Complete_System_Report")
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(120, height - 60, "BizDrive Fleet Management")
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(120, height - 80, "Complete System Report")
    
    pdf.setFont("Helvetica", 10)
    pdf.drawString(120, height - 95, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    pdf.setStrokeColorRGB(0.2, 0.2, 0.2)
    pdf.line(40, height - 110, width - 40, height - 110)
    
    # System Summary
    y = height - 140
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(50, y, "Complete System Overview")
    y -= 25
    
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(50, y, f"Total Users:")
    pdf.drawString(200, y, str(total_users))
    y -= 20
    
    pdf.drawString(50, y, f"Total Vehicles:")
    pdf.drawString(200, y, str(total_vehicles))
    y -= 20
    
    pdf.drawString(50, y, f"Total Trips:")
    pdf.drawString(200, y, f"{trip_stats[0]} trips ({trip_stats[1]:.2f} km)")
    y -= 20
    
    pdf.drawString(50, y, f"Total Expenses:")
    pdf.drawString(200, y, f"${expense_stats[1]:.2f} ({expense_stats[0]} transactions)")
    y -= 20
    
    pdf.drawString(50, y, f"Total Accidents:")
    pdf.drawString(200, y, str(total_accidents))
    
    pdf.save()
    buffer.seek(0)
    
    return send_file(buffer, as_attachment=True, download_name="complete_system_report.pdf", mimetype='application/pdf')


# Routes referenced in admin_reports.html template


@app.route('/admin/settings/update', methods=['POST'])
@login_required
@role_required('admin')
def admin_update_settings():
    """Update system settings."""
    setting_type = request.form.get('setting_type')
    
    import sqlite3
    conn = sqlite3.connect('bizdrive.db')
    cursor = conn.cursor()
    
    # Create settings table if it doesn't exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            setting_key TEXT UNIQUE NOT NULL,
            setting_value TEXT NOT NULL,
            setting_type TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    try:
        if setting_type == 'reimbursement':
            # Update reimbursement settings
            default_rate = request.form.get('default_rate', '0.88').strip()
            min_distance = request.form.get('min_distance', '1.0').strip()
            
            cursor.execute('''
                INSERT OR REPLACE INTO settings (setting_key, setting_value, setting_type)
                VALUES ('reimbursement_rate', ?, 'reimbursement'),
                       ('min_distance', ?, 'reimbursement')
            ''', (default_rate if default_rate else '0.88', 
                  min_distance if min_distance else '1.0'))
            
        elif setting_type == 'company':
            # Update company information
            company_name = request.form.get('company_name', 'BizDrive Fleet Management').strip()
            contact_email = request.form.get('contact_email', 'admin@bizdrive.com').strip()
            phone = request.form.get('phone', '').strip() or '+1-555-0000'
            
            cursor.execute('''
                INSERT OR REPLACE INTO settings (setting_key, setting_value, setting_type)
                VALUES ('company_name', ?, 'company'),
                       ('contact_email', ?, 'company'),
                       ('phone', ?, 'company')
            ''', (company_name, contact_email, phone))
                  
        elif setting_type == 'expense_category':
            # Add new expense category
            new_category = request.form.get('new_category', '').strip()
            if new_category:
                cursor.execute('''
                    INSERT OR REPLACE INTO settings (setting_key, setting_value, setting_type)
                    VALUES (?, ?, 'expense_category')
                ''', (f'expense_category_{new_category.lower()}', new_category))
                flash(f'Expense category "{new_category}" added successfully!', 'success')
            else:
                flash('Please enter a category name', 'warning')
                return redirect(url_for('admin_settings'))
                
        elif setting_type == 'accident_severity':
            # Add new accident severity level
            new_severity = request.form.get('new_severity', '').strip()
            if new_severity:
                cursor.execute('''
                    INSERT OR REPLACE INTO settings (setting_key, setting_value, setting_type)
                    VALUES (?, ?, 'accident_severity')
                ''', (f'severity_{new_severity.lower()}', new_severity))
                flash(f'Accident severity level "{new_severity}" added successfully!', 'success')
            else:
                flash('Please enter a severity level', 'warning')
                return redirect(url_for('admin_settings'))
                
        elif setting_type == 'remove_expense_category':
            # Remove expense category
            category_key = request.form.get('category_key')
            if category_key:
                cursor.execute("DELETE FROM settings WHERE setting_key = ? AND setting_type = 'expense_category'", 
                             (category_key,))
                flash('Expense category removed successfully!', 'success')
            return redirect(url_for('admin_settings'))
            
        elif setting_type == 'remove_accident_severity':
            # Remove accident severity level
            severity_key = request.form.get('severity_key')
            if severity_key:
                cursor.execute("DELETE FROM settings WHERE setting_key = ? AND setting_type = 'accident_severity'", 
                             (severity_key,))
                flash('Accident severity level removed successfully!', 'success')
            return redirect(url_for('admin_settings'))
                
        elif setting_type == 'security':
            # Update security settings
            session_timeout = request.form.get('session_timeout', '30').strip() or '30'
            password_min_length = request.form.get('password_min_length', '8').strip() or '8'
            require_2fa = '1' if request.form.get('require_2fa') else '0'
            
            cursor.execute('''
                INSERT OR REPLACE INTO settings (setting_key, setting_value, setting_type)
                VALUES ('session_timeout', ?, 'security'),
                       ('password_min_length', ?, 'security'),
                       ('require_2fa', ?, 'security')
            ''', (session_timeout, password_min_length, require_2fa))
                  
        elif setting_type == 'notifications':
            # Update notification settings
            email_expenses = '1' if request.form.get('email_expenses') else '0'
            email_accidents = '1' if request.form.get('email_accidents') else '0'
            email_maintenance = '1' if request.form.get('email_maintenance') else '0'
            admin_notification_email = request.form.get('admin_notification_email', '').strip() or 'admin@bizdrive.com'
            
            cursor.execute('''
                INSERT OR REPLACE INTO settings (setting_key, setting_value, setting_type)
                VALUES ('email_expenses', ?, 'notifications'),
                       ('email_accidents', ?, 'notifications'),
                       ('email_maintenance', ?, 'notifications'),
                       ('admin_notification_email', ?, 'notifications')
            ''', (email_expenses, email_accidents, email_maintenance, admin_notification_email))
        
        conn.commit()
        flash(f'{setting_type.title()} settings updated successfully!', 'success')
        
    except Exception as e:
        conn.rollback()
        flash(f'Error updating settings: {str(e)}', 'danger')
        
    finally:
        conn.close()
    
    return redirect(url_for('admin_settings'))


# ===============================================
# Admin Custom Report
# ===============================================

@app.route('/admin/reports/custom')
@login_required
@role_required('admin')
def admin_custom_report():
    """Generate custom admin report based on parameters."""
    # Get report parameters
    report_type = request.args.get('report_type', 'summary')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    user_id = request.args.get('user_id', type=int)
    
    import sqlite3
    from datetime import datetime
    
    conn = sqlite3.connect('bizdrive.db')
    cursor = conn.cursor()
    
    # Build the base query
    query_parts = []
    params = []
    
    if report_type == 'users':
        query_parts.append("""
            SELECT u.id, u.username, u.email, 
                   COUNT(DISTINCT v.id) as vehicle_count,
                   COUNT(DISTINCT t.id) as trip_count,
                   COALESCE(SUM(t.distance), 0) as total_distance,
                   COALESCE(SUM(t.reimbursement_amount), 0) as total_reimbursement
            FROM users u
            LEFT JOIN vehicles v ON u.id = v.user_id
            LEFT JOIN trips t ON u.id = t.user_id
        """)
    elif report_type == 'expenses':
        query_parts.append("""
            SELECT e.id, u.username, v.registration, e.category, 
                   e.amount, e.expense_date, e.description
            FROM expenses e
            JOIN users u ON e.user_id = u.id
            LEFT JOIN vehicles v ON e.vehicle_id = v.id
        """)
    else:  # summary
        query_parts.append("""
            SELECT 
                COUNT(DISTINCT u.id) as total_users,
                COUNT(DISTINCT v.id) as total_vehicles,
                COUNT(DISTINCT t.id) as total_trips,
                COUNT(DISTINCT e.id) as total_expenses,
                COALESCE(SUM(t.distance), 0) as total_distance,
                COALESCE(SUM(e.amount), 0) as total_expense_amount,
                COALESCE(SUM(t.reimbursement_amount), 0) as total_reimbursement
            FROM users u
            LEFT JOIN vehicles v ON u.id = v.user_id
            LEFT JOIN trips t ON u.id = t.user_id
            LEFT JOIN expenses e ON u.id = e.user_id
        """)
    
    # Add date filters if provided
    if start_date and report_type in ['trips', 'expenses']:
        if report_type == 'trips':
            query_parts.append("WHERE t.trip_date >= ?")
            params.append(start_date)
        else:
            query_parts.append("WHERE e.expense_date >= ?")
            params.append(start_date)
    
    if end_date and report_type in ['trips', 'expenses']:
        if len(query_parts) > 1 and "WHERE" in query_parts[-2]:
            query_parts.append("AND t.trip_date <= ?" if report_type == 'trips' else "AND e.expense_date <= ?")
        else:
            query_parts.append("WHERE t.trip_date <= ?" if report_type == 'trips' else "WHERE e.expense_date <= ?")
        params.append(end_date)
    
    # Add user filter if provided
    if user_id:
        if len(query_parts) > 1 and ("WHERE" in query_parts[-2] or "WHERE" in query_parts[-1]):
            query_parts.append("AND u.id = ?")
        else:
            query_parts.append("WHERE u.id = ?")
        params.append(user_id)
    
    # Add GROUP BY for user reports
    if report_type == 'users':
        query_parts.append("GROUP BY u.id, u.username, u.email")
    
    # Combine query parts
    full_query = " ".join(query_parts)
    
    cursor.execute(full_query, params)
    results = cursor.fetchall()
    
    # Get column names
    if report_type == 'users':
        columns = ['User ID', 'Username', 'Email', 'Vehicles', 'Trips', 'Distance', 'Reimbursement']
    elif report_type == 'expenses':
        columns = ['Expense ID', 'Username', 'Vehicle', 'Category', 'Amount', 'Date', 'Description']
    else:
        columns = ['Users', 'Vehicles', 'Trips', 'Expenses', 'Total Distance', 'Total Amount', 'Total Reimbursement']
    
    conn.close()
    
    # Create CSV response
    output = StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(['BizDrive Custom Report'])
    writer.writerow(['Report Type:', report_type.title()])
    if start_date:
        writer.writerow(['Start Date:', start_date])
    if end_date:
        writer.writerow(['End Date:', end_date])
    if user_id:
        writer.writerow(['User ID:', user_id])
    writer.writerow(['Generated:', datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
    writer.writerow([])
    
    # Write column headers
    writer.writerow(columns)
    
    # Write data
    for row in results:
        writer.writerow(row)
    
    # Create response
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = f'attachment; filename=bizdrive_custom_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    
    return response

# ===============================================
# Error Handlers
# ===============================================

@app.errorhandler(404)
def page_not_found(e):
    """Handle 404 errors."""
    return render_template('error.html', 
                         error_code=404, 
                         error_message='Page not found'), 404


@app.errorhandler(500)
def internal_server_error(e):
    """Handle 500 errors."""
    return render_template('error.html', 
                         error_code=500, 
                         error_message='Internal server error'), 500


# ===============================================
# Application Entry Point
# ===============================================

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False, port=5001)