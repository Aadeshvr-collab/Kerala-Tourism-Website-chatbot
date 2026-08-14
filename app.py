"""
app.py — Kerala Tourism AI Chatbot Application
================================================
Main Flask server that handles:
- Routing (URL → Page)
- API endpoints for chatbot and data
- Session management (login system)
- Serving all HTML templates

HOW IT WORKS:
User visits URL → Flask route function runs → Returns HTML page (template)
Frontend JS calls API routes → Flask returns JSON data

RUN WITH:
    python app.py
Then open: http://localhost:5000
"""

# ---- Imports ----
from flask import (
    Flask,          # Main Flask class
    render_template, # Renders HTML templates from /templates folder
    request,        # Access to request data (form, JSON, args)
    redirect,       # Redirect to another URL
    url_for,        # Generate URL from function name
    session,        # Server-side session (stores login state)
    jsonify         # Convert Python dict to JSON response
)

import json          # For reading JSON data files
import os            # For file paths
import random        # For varied chatbot responses
import re            # For regex validation (email, phone, name)
import datetime      # For DOB age calculation
import urllib.request  # For calling Gemini API (no extra library needed)
import urllib.error

# Import our custom NLP engine
from chatbot.nlp_engine import get_bot_instance

# ============================================================
# AI CHATBOT CONFIGURATION
# ============================================================
# Gemini is FREE — get your key at: https://aistudio.google.com/app/apikey
# Paste your key below (between the quotes) and restart the server.
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', 'AIzaSyBRnD3u81b75RRNGlDIRXXXBJyzZ90cnhQ')
GEMINI_MODEL   = 'gemini-2.5-flash-lite'

# Legacy / unused
GROK_API_KEY   = os.environ.get('GROK_API_KEY', '')
GROK_MODEL     = 'grok-beta'
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
CLAUDE_MODEL   = 'claude-sonnet-4-20250514'

# OPTION 3: DeepSeek  —  platform.deepseek.com
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', 'YOUR_DEEPSEEK_API_KEY_HERE')
DEEPSEEK_MODEL   = 'deepseek-chat'

# Kerala Tourism system prompt
KERALA_AI_SYSTEM_PROMPT = """You are an expert Kerala Tourism AI Assistant called Kerala Tourism AI.
You ONLY answer questions about Kerala tourism, travel, places, culture, food, weather, hotels, and travel planning.
Use emojis, bold place names (**name**) and bullet points. Keep responses under 350 words.
Kerala has 14 districts: Thiruvananthapuram, Kollam, Pathanamthitta, Alappuzha, Kottayam,
Idukki (Munnar), Ernakulam (Kochi), Thrissur, Palakkad, Malappuram, Kozhikode, Wayanad, Kannur, Kasaragod."""


# ============================================================
# APP INITIALIZATION
# ============================================================

app = Flask(__name__)

# Secret key for signing session cookies (change in production!)
app.secret_key = 'kerala_tourism_secret_key_2024_gods_own_country'

# Path to the /data directory
DATA_DIR   = os.path.join(os.path.dirname(__file__), 'data')
USERS_FILE = os.path.join(os.path.dirname(__file__), 'data', 'users.json')


def load_users():
    """Load users from users.json. Returns list of user dicts."""
    if not os.path.exists(USERS_FILE):
        return []
    with open(USERS_FILE, 'r') as f:
        data = json.load(f)
    return data.get('users', [])


def save_users(users):
    """Save users list back to users.json."""
    with open(USERS_FILE, 'w') as f:
        json.dump({'users': users}, f, indent=2)


def find_user(username):
    """Find a user by username. Returns user dict or None."""
    for u in load_users():
        if u['username'].lower() == username.lower():
            return u
    return None


# ============================================================
# HELPER FUNCTIONS — Load JSON data
# ============================================================

def load_json(filename):
    """
    Load a JSON file from the /data directory.
    
    Args:
        filename (str): JSON filename (e.g., 'places.json')
        
    Returns:
        dict/list: Parsed JSON data
    """
    filepath = os.path.join(DATA_DIR, filename)
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_all_places_flat():
    """
    Return a flat list of all places across all districts.
    Used for search and category filtering.
    
    Returns:
        list: Each item is a place dict with 'district' added
    """
    data = load_json('places.json')
    all_places = []
    for district in data['districts']:
        for place in district['places']:
            place_copy = place.copy()
            place_copy['district_id'] = district['id']
            place_copy['district_name'] = district['name']
            all_places.append(place_copy)
    return all_places


# ============================================================
# LOGIN CHECK DECORATOR
# ============================================================

def login_required(f):
    """
    Decorator: If user is not logged in, redirect to login page.
    
    Usage: @login_required above any route that needs login
    """
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))  # Redirect to login
        return f(*args, **kwargs)              # Otherwise, run the route
    return decorated_function


# ============================================================
# PAGE ROUTES — Each URL pattern maps to a function
# ============================================================

# ---- Home Page ----
@app.route('/')
def index():
    """
    HOME PAGE
    URL: http://localhost:5000/
    
    Shows:
    - Kerala hero section with background video/image
    - Welcome message and intro
    - Quick navigation cards
    """
    data = load_json('places.json')
    hotels_data = load_json('hotels.json')
    total_places = sum(len(d.get('places', [])) for d in data['districts'])
    total_hotels = len(hotels_data.get('hotels', hotels_data) if isinstance(hotels_data, dict) else hotels_data)
    return render_template('index.html', total_places=total_places, total_hotels=total_hotels)


# ---- Register Page ----
@app.route('/register', methods=['GET', 'POST'])
def register():
    """
    REGISTER PAGE — Create a new user account.
    Stores name, username, password, place, DOB in users.json.
    """
    if session.get('logged_in'):
        return redirect(url_for('dashboard'))

    error = None
    success = None

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        username  = request.form.get('username', '').strip()
        password  = request.form.get('password', '').strip()
        confirm   = request.form.get('confirm_password', '').strip()
        place     = request.form.get('place', '').strip()
        dob       = request.form.get('dob', '').strip()
        email     = request.form.get('email', '').strip()
        phone     = request.form.get('phone', '').strip()

        # Normalise to Title Case — "manu" → "Manu", "MANU K" → "Manu K"
        full_name_clean = full_name.title() if (full_name.isupper() or full_name.islower()) else full_name

        # --- Helper validators ---
        def is_valid_full_name(name):
            """Allow only letters, spaces, dots, hyphens. Min 2 words or min 2 chars."""
            if not re.match(r"^[A-Za-z][A-Za-z\s.\-']{1,}$", name):
                return False
            # Must contain at least 2 alphabetic characters
            return len(re.findall(r'[A-Za-z]', name)) >= 2

        def is_valid_gmail(email_addr):
            """Strict Gmail format: localpart@gmail.com"""
            return bool(re.fullmatch(r'[a-zA-Z0-9._%+\-]+@gmail\.com', email_addr))

        def is_valid_indian_phone(number):
            """Indian mobile: exactly 10 digits, starts with 6–9."""
            return bool(re.fullmatch(r'[6-9]\d{9}', number))

        def is_valid_dob(dob_str):
            """DOB must be parseable, person must be between 1 and 80 years old."""
            try:
                dob_date = datetime.date.fromisoformat(dob_str)
            except ValueError:
                return False, 'Invalid date format.'
            today = datetime.date.today()
            age_years = (today - dob_date).days / 365.25
            if age_years < 1:
                return False, 'Date of birth cannot be in the future or too recent.'
            if age_years > 80:
                return False, 'Registration is only allowed for people up to 80 years old.'
            return True, ''

        # --- Validation ---
        if not all([full_name, username, password, confirm, place, dob, phone]):
            error = 'All fields are required.'
        elif not is_valid_full_name(full_name_clean):
            error = 'Full name must contain only letters, spaces, dots or hyphens (no numbers or symbols).'
        elif len(username) < 4:
            error = 'Username must be at least 4 characters.'
        elif email and not is_valid_gmail(email):
            error = 'Email must be a valid Gmail address (e.g. yourname@gmail.com).'
        elif not is_valid_indian_phone(phone):
            error = 'Phone number must be a 10-digit Indian mobile number starting with 6, 7, 8, or 9.'
        else:
            dob_ok, dob_err = is_valid_dob(dob)
            if not dob_ok:
                error = dob_err
            elif len(password) < 6:
                error = 'Password must be at least 6 characters.'
            elif password != confirm:
                error = 'Passwords do not match.'
            elif find_user(username):
                error = f'Username "{username}" is already taken. Choose another.'
            else:
                # --- Save new user ---
                import hashlib
                password_hash = hashlib.sha256(password.encode()).hexdigest()
                users = load_users()
                users.append({
                    'username':      username,
                    'password_hash': password_hash,
                    'full_name':     full_name_clean,
                    'email':         email,
                    'phone':         phone,
                    'place':         place,
                    'dob':           dob,
                    'joined':        datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
                })
                save_users(users)
                success = f'Account created! Welcome {full_name_clean}. Please login.'

    now_date = datetime.date.today().isoformat()
    # Compute min DOB date (80 years ago)
    min_dob = (datetime.date.today() - datetime.timedelta(days=80*365+20)).isoformat()
    return render_template('register.html', error=error, success=success, now_date=now_date, min_dob=min_dob)


# ---- Login Page ----
@app.route('/login', methods=['GET', 'POST'])
def login():
    """
    LOGIN PAGE — Validates against registered users in users.json.
    """
    if session.get('logged_in'):
        return redirect(url_for('dashboard'))

    error = None

    if request.method == 'POST':
        import hashlib
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        user = find_user(username)
        if user:
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            if user['password_hash'] == password_hash:
                # Always show a properly formatted name:
                # "MANU" → "Manu", "john doe" → "John Doe", "Manu K" → "Manu K" (kept)
                raw_name = user.get('full_name', username).strip()
                display_name = raw_name.title() if (raw_name.isupper() or raw_name.islower()) else raw_name
                session['logged_in']  = True
                session['username']   = user['username']
                session['user_name']  = display_name
                session['user_place'] = user.get('place', '')
                return redirect(url_for('dashboard'))
            else:
                error = 'Incorrect password. Please try again.'
        else:
            error = f'No account found for "{username}". Please register first.'

    return render_template('login.html', error=error)


# ---- Logout ----
@app.route('/logout')
def logout():
    """LOGOUT — Clears session and redirects to home."""
    session.clear()
    return redirect(url_for('index'))


# ---- Forgot Password ----
@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """
    FORGOT PASSWORD — 3-step flow (no email required):
      Step 1: Enter username
      Step 2: Verify identity via DOB + hometown
      Step 3: Set new password
    """
    import hashlib

    step    = request.args.get('step', '1')
    error   = None
    success = None
    username_val = ''

    if request.method == 'POST':
        action = request.form.get('action', '')

        # ── STEP 1: verify username exists ──────────────────────────
        if action == 'check_user':
            username_val = request.form.get('username', '').strip()
            user = find_user(username_val)
            if not user:
                error = 'No account found with that username.'
                step = '1'
            else:
                return redirect(url_for('forgot_password',
                                        step='2', u=username_val))

        # ── STEP 2: verify DOB + place ───────────────────────────────
        elif action == 'verify_identity':
            username_val = request.form.get('username', '').strip()
            dob_input    = request.form.get('dob', '').strip()
            place_input  = request.form.get('place', '').strip().lower()
            user         = find_user(username_val)

            if not user:
                error = 'Session expired. Please start again.'
                step = '1'
            elif user.get('dob', '') != dob_input or \
                 user.get('place', '').lower() != place_input:
                error = 'Details do not match our records. Please try again.'
                step = '2'
            else:
                return redirect(url_for('forgot_password',
                                        step='3', u=username_val))

        # ── STEP 3: set new password ─────────────────────────────────
        elif action == 'reset_password':
            username_val  = request.form.get('username', '').strip()
            new_password  = request.form.get('new_password', '').strip()
            confirm_pass  = request.form.get('confirm_password', '').strip()

            if len(new_password) < 6:
                error = 'Password must be at least 6 characters.'
                step = '3'
            elif new_password != confirm_pass:
                error = 'Passwords do not match.'
                step = '3'
            else:
                users = load_users()
                for u in users:
                    if u['username'] == username_val:
                        u['password_hash'] = hashlib.sha256(
                            new_password.encode()).hexdigest()
                        break
                save_users(users)
                success = 'Password reset successfully! You can now sign in.'
                step = 'done'

    else:
        step = request.args.get('step', '1')
        username_val = request.args.get('u', '')

    return render_template('forgot_password.html',
                           step=step,
                           username_val=username_val,
                           error=error,
                           success=success)


# ---- Dashboard ----
@app.route('/dashboard')
@login_required
def dashboard():
    """
    DASHBOARD PAGE
    URL: http://localhost:5000/dashboard
    
    Shows:
    - Stats overview (districts, places count)
    - Quick access cards to all sections
    - Featured places carousel
    """
    data = load_json('places.json')
    hotels_data = load_json('hotels.json')
    
    # Calculate stats for dashboard cards
    total_places = sum(len(d['places']) for d in data['districts'])
    total_districts = len(data['districts'])
    total_hotels = len(hotels_data.get('hotels', hotels_data) if isinstance(hotels_data, dict) else hotels_data)

    # Get 6 featured places — one from each of 6 different districts for variety
    all_places = get_all_places_flat()
    # Group by district, pick best-rated from each, then sample 6 districts
    from collections import defaultdict
    by_district = defaultdict(list)
    for p in all_places:
        if p.get('image') and p.get('rating', 0) >= 4.0:
            by_district[p['district_id']].append(p)
    # Sort each district's places by rating desc
    district_picks = []
    for did, places in by_district.items():
        places.sort(key=lambda x: x.get('rating', 0), reverse=True)
        district_picks.append(places[0])  # top rated from each district
    # Shuffle and take 6
    random.shuffle(district_picks)
    featured = district_picks[:6]
    # Fallback if not enough
    if len(featured) < 6:
        featured = random.sample(all_places, min(6, len(all_places)))

    # ── Always resolve the display name fresh from users.json ───────
    # This ensures the welcome message reflects the registered full_name
    # even if the session is stale or the name was saved in the wrong case.
    _logged_username = session.get('username', '')
    _user_record     = find_user(_logged_username) if _logged_username else None
    if _user_record and _user_record.get('full_name', '').strip():
        raw = _user_record['full_name'].strip()
        # Normalise ALL-CAPS or all-lowercase names to Title Case
        display_name = raw.title() if (raw.isupper() or raw.islower()) else raw
        session['user_name'] = display_name   # keep session in sync
    else:
        display_name = session.get('user_name', 'Explorer')

    return render_template('dashboard.html',
        user_name=display_name,
        total_places=total_places,
        total_districts=total_districts,
        total_hotels=total_hotels,
        featured_places=featured
    )


# ---- Categories Page ----
@app.route('/categories')
@login_required
def categories():
    """
    CATEGORIES PAGE
    URL: http://localhost:5000/categories
    
    Shows all tourism categories as clickable cards:
    Hill Stations, Beaches, Hot Places, Cold Places, Food, etc.
    """
    data = load_json('places.json')
    return render_template('categories.html', categories=data['categories'])


# ---- Category Detail — Places filtered by category ----
@app.route('/category/<category_id>')
@login_required
def category_detail(category_id):
    """
    CATEGORY DETAIL PAGE
    URL: http://localhost:5000/category/beach
    
    Shows all places that belong to a specific category.
    
    Args:
        category_id (str): e.g., 'beach', 'hill', 'hot', 'cold'
    """
    data = load_json('places.json')
    
    # Get category info
    category = data['categories'].get(category_id)
    if not category:
        return redirect(url_for('categories'))

    # Filter places by category
    filtered_places = []
    for district in data['districts']:
        for place in district['places']:
            if category_id in place.get('category', []):
                place_copy = place.copy()
                place_copy['district_id'] = district['id']
                place_copy['district_name'] = district['name']
                filtered_places.append(place_copy)

    return render_template('category_detail.html',
        category=category,
        category_id=category_id,
        places=filtered_places
    )


# ---- Districts List Page ----
@app.route('/districts')
@login_required
def districts():
    """
    DISTRICTS PAGE
    URL: http://localhost:5000/districts
    
    Shows all 14 Kerala districts as cards.
    Each card shows district name, description, place count.
    """
    data = load_json('places.json')
    return render_template('districts.html', districts=data['districts'])


# ---- District Detail — All places in one district ----
@app.route('/district/<district_id>')
@login_required
def district_detail(district_id):
    """
    DISTRICT DETAIL PAGE
    URL: http://localhost:5000/district/munnar
    
    Shows all tourist places in the selected district.
    
    Args:
        district_id (str): District slug (e.g., 'munnar', 'ernakulam')
    """
    data = load_json('places.json')
    
    # Find the matching district
    district = next(
        (d for d in data['districts'] if d['id'] == district_id),
        None
    )

    if not district:
        return redirect(url_for('districts'))

    return render_template('district_detail.html',
        district=district,
        categories=data['categories']
    )


# ---- Place Detail Page ----
@app.route('/place/<district_id>/<place_id>')
@login_required
def place_detail(district_id, place_id):
    """
    PLACE DETAIL PAGE
    URL: http://localhost:5000/place/munnar/munnar_tea
    
    Shows full details of one place:
    - Description, highlights
    - Google Maps (online) or OpenStreetMap (offline)
    - Nearby hotels
    - Best time, entry fee
    
    Args:
        district_id (str): Parent district ID
        place_id (str): Place ID
    """
    data = load_json('places.json')
    hotels_data = load_json('hotels.json')

    # Find the district
    district = next(
        (d for d in data['districts'] if d['id'] == district_id),
        None
    )
    if not district:
        return redirect(url_for('districts'))

    # Find the place within that district
    place = next(
        (p for p in district['places'] if p['id'] == place_id),
        None
    )
    if not place:
        return redirect(url_for('district_detail', district_id=district_id))

    # Find nearby hotels in same district
    nearby_hotels = [
        h for h in hotels_data['hotels']
        if h['district'] in [district_id, district_id.split('_')[0]]
    ][:3]  # Max 3 hotels shown

    return render_template('place_detail.html',
        place=place,
        district=district,
        nearby_hotels=nearby_hotels,
        google_maps_key='YOUR_GOOGLE_MAPS_API_KEY'  # Replace with real key
    )


# ---- Family Plans Page ----
@app.route('/plans')
@login_required
def family_plans():
    """
    FAMILY PLANS PAGE
    URL: http://localhost:5000/plans
    
    Shows 3 predefined travel packages:
    - Budget Plan (5 days, ₹8,500/person)
    - Family Plan (7 days, ₹18,500/person)
    - Luxury Plan (9 days, ₹45,000/person)
    """
    data = load_json('family_plans.json')
    return render_template('family_plans.html', plans=data['plans'])


# ---- Plan Detail with Day-wise Itinerary ----
@app.route('/plan/<plan_id>')
@login_required
def plan_detail(plan_id):
    """
    PLAN DETAIL PAGE
    URL: http://localhost:5000/plan/family_plan
    
    Shows day-by-day itinerary for selected travel plan.
    
    Args:
        plan_id (str): Plan ID (budget_plan, family_plan, luxury_plan)
    """
    data = load_json('family_plans.json')
    plan = next((p for p in data['plans'] if p['id'] == plan_id), None)

    if not plan:
        return redirect(url_for('family_plans'))

    return render_template('plan_detail.html', plan=plan)


# ---- Hotels Page ----
@app.route('/hotels')
@login_required
def hotels():
    """
    HOTELS PAGE
    URL: http://localhost:5000/hotels
    
    Shows all hotels as cards with:
    - Hotel name, category, price, rating
    - Location and amenities
    - 'Book Now' button (demo only)
    
    Supports filtering by district and category
    """
    data = load_json('hotels.json')
    places_data = load_json('places.json')

    # Get filter parameters from URL
    district_filter = request.args.get('district', 'all')
    category_filter = request.args.get('category', 'all')

    hotels_list = data['hotels']

    # Apply district filter
    if district_filter != 'all':
        hotels_list = [h for h in hotels_list if h['district'] == district_filter]

    # Apply category filter (budget/mid-range/luxury)
    if category_filter != 'all':
        hotels_list = [h for h in hotels_list if h['category'] == category_filter]

    # Get list of districts for filter dropdown
    districts = [(d['id'], d['name']) for d in places_data['districts']]

    return render_template('hotels.html',
        hotels=hotels_list,
        districts=districts,
        selected_district=district_filter,
        selected_category=category_filter
    )


# ---- Hotel Booking Demo ----
@app.route('/book/<hotel_id>', methods=['GET', 'POST'])
@login_required
def book_hotel(hotel_id):
    """
    HOTEL BOOKING PAGE (DEMO)
    URL: http://localhost:5000/book/h001
    
    GET: Shows booking form
    POST: Shows booking confirmation (simulated)
    
    IMPORTANT: This is a DEMO only. No real payment is processed.
    
    Args:
        hotel_id (str): Hotel ID to book
    """
    data = load_json('hotels.json')
    hotel = next((h for h in data['hotels'] if h['id'] == hotel_id), None)

    if not hotel:
        return redirect(url_for('hotels'))

    booking_confirmed = False
    booking_ref = None
    booking_error = None

    today = datetime.date.today()
    today_iso = today.isoformat()
    # Check-in can be booked up to 1 year in advance (reasonable cap)
    max_checkin_iso = (today + datetime.timedelta(days=365)).isoformat()

    if request.method == 'POST':
        full_name  = request.form.get('full_name', '').strip()
        email      = request.form.get('email', '').strip()
        phone      = request.form.get('phone', '').strip()
        check_in   = request.form.get('check_in', '').strip()
        check_out  = request.form.get('check_out', '').strip()

        # --- Validators ---
        def valid_gmail(e):
            return bool(re.fullmatch(r'[a-zA-Z0-9._%+\-]+@gmail\.com', e))

        def valid_indian_phone(p):
            digits = re.sub(r'\D', '', p)
            # Accept with or without +91 / 91 prefix
            if digits.startswith('91') and len(digits) == 12:
                digits = digits[2:]
            return bool(re.fullmatch(r'[6-9]\d{9}', digits))

        def valid_date(d):
            try:
                return datetime.date.fromisoformat(d)
            except ValueError:
                return None

        if not all([full_name, email, phone, check_in, check_out]):
            booking_error = 'All fields are required.'
        elif not valid_gmail(email):
            booking_error = 'Email must be a valid Gmail address (e.g. yourname@gmail.com).'
        elif not valid_indian_phone(phone):
            booking_error = 'Phone must be a 10-digit Indian mobile number starting with 6, 7, 8 or 9.'
        else:
            ci_date = valid_date(check_in)
            co_date = valid_date(check_out)
            if not ci_date or not co_date:
                booking_error = 'Please enter valid check-in and check-out dates.'
            elif ci_date < today:
                booking_error = f'Check-in date cannot be in the past. Today is {today.strftime("%d %b %Y")}.'
            elif co_date <= ci_date:
                booking_error = 'Check-out date must be at least one day after check-in.'
            elif (co_date - ci_date).days > 7:
                booking_error = 'Maximum booking duration is 7 nights (1 week).'
            else:
                booking_ref = f"KTB{random.randint(100000, 999999)}"
                booking_confirmed = True

    return render_template('book_hotel.html',
        hotel=hotel,
        booking_confirmed=booking_confirmed,
        booking_ref=booking_ref,
        booking_error=booking_error,
        today_iso=today_iso,
        max_checkin_iso=max_checkin_iso
    )


# ---- Chatbot Page ----
@app.route('/chatbot')
@login_required
def chatbot():
    """
    CHATBOT PAGE
    URL: http://localhost:5000/chatbot
    
    The AI assistant interface.
    Frontend sends messages to /api/chat endpoint.
    """
    return render_template('chatbot.html',
        user_name=session.get('user_name', 'Explorer')
    )


# ============================================================
# API ROUTES — Return JSON data (called by JavaScript)
# ============================================================

@app.route('/api/chat', methods=['POST'])
def api_chat():
    """
    OFFLINE CHATBOT API ENDPOINT
    URL: POST /api/chat
    
    Uses local TF-IDF + Entity Detection NLP (works without internet).
    Receives: { "message": "user's text" }
    Returns:  { "response": "...", "intent": "...", "confidence": 0.85, "mode": "offline" }
    """
    body = request.get_json()
    user_message = body.get('message', '').strip() if body else ''

    bot = get_bot_instance(os.path.join(DATA_DIR, 'chatbot_intents.json'))
    result = bot.get_response(user_message)
    result['mode'] = 'offline'

    return jsonify(result)


@app.route('/api/chat/online', methods=['POST'])
def api_chat_online():
    """
    ONLINE AI CHATBOT — powered by Gemini (free) server-side.
    Set GEMINI_API_KEY in the config above, then restart.
    Get a FREE key at: https://aistudio.google.com/app/apikey
    """
    body = request.get_json()
    if not body:
        return jsonify({'error': 'No data provided'}), 400

    user_message = body.get('message', '').strip()
    history      = body.get('history', [])

    if not user_message:
        return jsonify({'error': 'Empty message'}), 400

    # Check key is configured
    if not GEMINI_API_KEY or GEMINI_API_KEY.startswith('YOUR_'):
        return jsonify({
            'error': 'Gemini API key not set. Open app.py and paste your free key from aistudio.google.com/app/apikey into GEMINI_API_KEY, then restart.',
            'fallback': True
        }), 503

    # Build Gemini contents array
    contents = []
    for turn in history[-10:]:
        role = 'model' if turn.get('role') == 'model' else 'user'
        text = turn.get('text', '').strip()
        if text:
            contents.append({'role': role, 'parts': [{'text': text}]})
    # Must start with user turn
    while contents and contents[0]['role'] != 'user':
        contents.pop(0)
    contents.append({'role': 'user', 'parts': [{'text': user_message}]})

    try:
        url = ('https://generativelanguage.googleapis.com/v1beta/models/'
               'gemini-2.5-flash-lite:generateContent?key=' + GEMINI_API_KEY)
        payload = {
            'system_instruction': {'parts': [{'text': KERALA_AI_SYSTEM_PROMPT}]},
            'contents': contents,
            'generationConfig': {'maxOutputTokens': 600, 'temperature': 0.7}
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=25) as r:
            data = json.loads(r.read())
        text = data['candidates'][0]['content']['parts'][0]['text'].strip()
        return jsonify({
            'response': text,
            'mode': 'online',
            'model': GEMINI_MODEL,
            'provider': 'gemini',
            'intent': 'ai_response',
            'confidence': 1.0
        })
    except urllib.error.HTTPError as e:
        err_body = e.read().decode('utf-8', errors='replace') if e.fp else ''
        print(f"[Gemini HTTP {e.code}] {err_body[:300]}")
        if e.code in (401, 403):
            msg = 'Gemini API key is invalid. Get a new free key at aistudio.google.com/app/apikey'
        elif e.code == 429:
            msg = 'Gemini quota exceeded. Wait a moment and try again.'
        else:
            try:
                em = json.loads(err_body).get('error', {}).get('message', err_body[:120])
            except Exception:
                em = err_body[:120]
            msg = f'Gemini error ({e.code}): {em}'
        return jsonify({'error': msg, 'fallback': True}), 503
    except Exception as e:
        print(f"[Gemini] {type(e).__name__}: {e}")
        return jsonify({'error': f'Online AI error: {str(e)}', 'fallback': True}), 503


@app.route('/api/ai/status', methods=['GET'])
def api_ai_status():
    """Check which AI providers are configured."""
    gemini_ok   = bool(GEMINI_API_KEY)   and not GEMINI_API_KEY.startswith('YOUR_')
    grok_ok     = bool(GROK_API_KEY)     and not GROK_API_KEY.startswith('YOUR_')
    deepseek_ok = bool(DEEPSEEK_API_KEY) and not DEEPSEEK_API_KEY.startswith('YOUR_')
    return jsonify({
        'gemini':   {'configured': gemini_ok,   'model': GEMINI_MODEL,   'get_key': 'https://aistudio.google.com/app/apikey', 'free': True},
        'grok':     {'configured': grok_ok,     'model': GROK_MODEL,     'get_key': 'https://console.x.ai'},
        'deepseek': {'configured': deepseek_ok, 'model': DEEPSEEK_MODEL, 'get_key': 'https://platform.deepseek.com'},
        'any_configured': gemini_ok or grok_ok or deepseek_ok
    })


@app.route('/api/test-key', methods=['POST'])
def api_test_key():
    """
    Quick key validation — sends a tiny test message to verify the key works.
    POST { "api_key": "AIza...", "provider": "gemini" }
    Returns { "ok": true/false, "error": "..." }
    """
    body     = request.get_json() or {}
    api_key  = body.get('api_key', '').strip()
    provider = body.get('provider', 'gemini')

    if not api_key:
        return jsonify({'ok': False, 'error': 'No key provided'})

    try:
        if provider == 'gemini':
            url = ('https://generativelanguage.googleapis.com/v1beta/models/'
                   'gemini-2.0-flash:generateContent?key=' + api_key)
            payload = {
                'contents': [{'role': 'user', 'parts': [{'text': 'Say hello in one word.'}]}],
                'generationConfig': {'maxOutputTokens': 10}
            }
            req = urllib.request.Request(
                url, data=json.dumps(payload).encode(),
                headers={'Content-Type': 'application/json'}, method='POST')
            with urllib.request.urlopen(req, timeout=10) as r:
                json.loads(r.read())
            return jsonify({'ok': True, 'provider': 'gemini'})
        else:
            urls = {'grok': 'https://api.x.ai/v1/chat/completions',
                    'deepseek': 'https://api.deepseek.com/v1/chat/completions'}
            models = {'grok': GROK_MODEL, 'deepseek': DEEPSEEK_MODEL}
            payload = {'model': models.get(provider, provider),
                       'messages': [{'role':'user','content':'Hi'}], 'max_tokens': 5}
            req = urllib.request.Request(
                urls.get(provider,''), data=json.dumps(payload).encode(),
                headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
                method='POST')
            with urllib.request.urlopen(req, timeout=10) as r:
                json.loads(r.read())
            return jsonify({'ok': True, 'provider': provider})
    except urllib.error.HTTPError as e:
        err = e.read().decode('utf-8', errors='replace') if e.fp else str(e.code)
        try:
            msg = json.loads(err).get('error', {}).get('message', err[:100])
        except Exception:
            msg = err[:100]
        return jsonify({'ok': False, 'error': f'HTTP {e.code}: {msg}'})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/places')
def api_places():
    """
    PLACES API ENDPOINT
    URL: GET /api/places?category=beach&district=ernakulam
    
    Returns filtered list of places as JSON.
    Used by JavaScript for dynamic filtering.
    """
    category = request.args.get('category')
    district = request.args.get('district')

    all_places = get_all_places_flat()

    # Apply filters if provided
    if category:
        all_places = [p for p in all_places if category in p.get('category', [])]
    if district:
        all_places = [p for p in all_places if p['district_id'] == district]

    return jsonify({'places': all_places})


@app.route('/api/hotels')
def api_hotels():
    """
    HOTELS API ENDPOINT
    URL: GET /api/hotels?district=munnar&category=luxury
    
    Returns filtered hotels list as JSON.
    """
    data = load_json('hotels.json')
    hotels_list = data['hotels']

    district = request.args.get('district')
    category = request.args.get('category')

    if district:
        hotels_list = [h for h in hotels_list if h['district'] == district]
    if category:
        hotels_list = [h for h in hotels_list if h['category'] == category]

    return jsonify({'hotels': hotels_list})


@app.route('/api/search')
def api_search():
    """
    SEARCH API ENDPOINT
    URL: GET /api/search?q=beach
    
    Full-text search across places and districts.
    Returns matching places as JSON.
    """
    query = request.args.get('q', '').lower().strip()

    if not query:
        return jsonify({'results': []})

    all_places = get_all_places_flat()
    results = []

    for place in all_places:
        # Search in name and description
        if (query in place['name'].lower() or
            query in place.get('description', '').lower() or
            any(query in cat.lower() for cat in place.get('category', []))):
            results.append(place)

    return jsonify({'results': results[:20]})  # Max 20 results


@app.route('/api/weather')
def api_weather():
    """
    WEATHER API ENDPOINT (DEMO)
    URL: GET /api/weather?location=Munnar
    
    In a real app, this would call OpenWeatherMap API.
    For demo purposes, returns simulated weather data.
    """
    location = request.args.get('location', 'Kerala')

    # Simulated weather data (replace with real API call)
    weather_data = {
        'location': location,
        'temperature': random.randint(18, 32),
        'feels_like': random.randint(17, 33),
        'humidity': random.randint(55, 85),
        'description': random.choice([
            'Partly cloudy', 'Clear sky', 'Warm and pleasant',
            'Light breeze', 'Mostly sunny', 'Warm tropical weather'
        ]),
        'icon': '⛅',
        'wind_speed': random.randint(8, 20),
        'source': 'Demo Data (Connect OpenWeatherMap API)'
    }

    return jsonify(weather_data)


@app.route('/api/connectivity')
def api_connectivity():
    """
    CONNECTIVITY CHECK ENDPOINT
    URL: GET /api/connectivity
    
    Frontend calls this to check if they can reach the server.
    Returns simple 200 OK response.
    Used as part of online/offline detection logic.
    """
    return jsonify({'status': 'online', 'server': 'Kerala Tourism AI'})


# ============================================================
# MAIN ENTRY POINT
# ============================================================


# ---- Image Proxy — serves Wikimedia images through Flask to bypass hotlink restrictions ----
@app.route('/api/imgproxy')
def img_proxy():
    from flask import Response
    import urllib.parse
    raw_url = request.args.get('url', '')
    if not raw_url:
        return '', 400
    if 'upload.wikimedia.org' not in raw_url:
        return '', 403
    try:
        req = urllib.request.Request(raw_url, headers={
            'User-Agent': 'KeralaToursimApp/1.0 (educational project)',
            'Referer': 'https://commons.wikimedia.org/'
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            ct = resp.headers.get('Content-Type', 'image/jpeg')
            data = resp.read()
        return Response(data, content_type=ct)
    except Exception as e:
        return f'proxy error: {e}', 502

if __name__ == '__main__':
    """
    Run the Flask development server.
    
    In production, use: gunicorn app:app
    """
    print("=" * 60)
    print("🌴 Kerala Tourism AI Chatbot")
    print("=" * 60)
    print("Starting server at: http://localhost:5000")
    print("Login: admin / kerala123")
    print("=" * 60)

    app.run(
        host='0.0.0.0',    # Listen on all network interfaces
        port=5000,          # Port number
        debug=True          # Auto-reload on code changes (dev only)
    )
