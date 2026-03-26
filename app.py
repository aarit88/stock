import random
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, get_flashed_messages
from werkzeug.security import generate_password_hash, check_password_hash
import yfinance as yf
from functools import wraps
# --- NEW IMPORTS FOR EMAIL ---
from flask_mail import Mail, Message
# --- NEW IMPORT FOR TIMESTAMP ---
from datetime import datetime, timedelta 
import time
# --- NEW IMPORT FOR PANDAS (FIXES THE ERROR) ---
import pandas as pd
import json
import os

# --- Configuration and Initialization ---
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'super_secret_stock_key')

USER_DATA_FILE = 'users.json'

def load_users():
    if os.path.exists(USER_DATA_FILE):
        try:
            with open(USER_DATA_FILE, 'r') as f:
                data = json.load(f)
                # Convert string timestamps back to datetime objects
                for username, user_info in data.items():
                    if 'otp_expiry' in user_info and user_info['otp_expiry']:
                         user_info['otp_expiry'] = datetime.fromisoformat(user_info['otp_expiry'])
                return data
        except Exception as e:
            print(f"Error loading users: {e}")
    return {}

def save_users():
    try:
        # Create a copy to avoid modifying the original during serialization
        data_to_save = {}
        for username, user_info in users.items():
            user_copy = user_info.copy()
            if 'otp_expiry' in user_copy and isinstance(user_copy['otp_expiry'], datetime):
                user_copy['otp_expiry'] = user_copy['otp_expiry'].isoformat()
            data_to_save[username] = user_copy
            
        with open(USER_DATA_FILE, 'w') as f:
            json.dump(data_to_save, f, indent=4)
    except Exception as e:
        print(f"Error saving users: {e}")

# In-memory user storage (now persisted)
users = load_users()
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
# Replace with your actual sender email address
app.config['MAIL_USERNAME'] = '1da23cs011.cs@drait.edu.in' 
# Replace with the App Password you generated in your Google account
app.config['MAIL_PASSWORD'] = 'eckm zhbz hbnm pkvi' 

mail = Mail(app)

# In-memory user storage (now persisted via load_users() above)
# Format: {username: {'hash': hashed_password, 'email': user_email, 'phone': user_phone, 'verified': True/False, 'help_queries': []}}

# Stock options for the main dashboard dropdown (Zomato removed)
STOCK_OPTIONS = {
    "Reliance Industries": "RELIANCE.NS",
    "Tata Consultancy Services": "TCS.NS",
    "Infosys": "INFY.NS",
    "HDFC Bank": "HDFCBANK.NS",
    "SBI": "SBIN.NS",
    "Tata Motors": "TATAMOTORS.NS",
    # "Zomato": "ZOMATO.NS", # REMOVED as requested due to data fetching issues
    "Apollo Hospitals": "APOLLOHOSP.NS",
    "HUL": "HINDUNILVR.NS",
    "Asian Paints": "ASIANPAINT.NS",
    "Wipro": "WIPRO.NS",
}

# --- *** NEW: BROKERAGE AND DEMAT CONFIG *** ---

# Simplified fee models for all 29 brokers
BROKERAGE_CONFIG = {
    # Discount / Flat Fee Brokers
    "groww": {"name": "Groww", "type": "flat", "rate": 20.0},
    "upstox": {"name": "Upstox", "type": "flat", "rate": 20.0},
    "5paisa": {"name": "5Paisa", "type": "flat", "rate": 20.0},
    "fyers": {"name": "Fyers", "type": "flat", "rate": 20.0},
    "dhan": {"name": "Dhan", "type": "flat", "rate": 20.0},
    "paytmmoney": {"name": "Paytm Money", "type": "flat", "rate": 20.0},
    "mstock": {"name": "mStock", "type": "flat", "rate": 0.0}, # Often has zero brokerage plans
    "stoxkart": {"name": "Stoxkart", "type": "flat", "rate": 15.0},
    "aliceblue": {"name": "Alice Blue", "type": "flat", "rate": 15.0},
    
    # Bank / Full-Service Brokers (Simulated as Per-Share)
    "icicidirect": {"name": "ICICI Direct", "type": "per_share", "rate": 0.10},
    "hdfcsky": {"name": "HDFC SKY", "type": "flat", "rate": 20.0},
    "sbisecurities": {"name": "SBI Securities", "type": "per_share", "rate": 0.15},
    "kotaksecurities": {"name": "Kotak Securities", "type": "flat", "rate": 0.0}, # Often has zero brokerage plans
    "axisdirect": {"name": "Axis Direct", "type": "flat", "rate": 20.0},
    
    # Other Full-Service / Traditional Brokers
    "iiflsecurities": {"name": "IIFL Securities", "type": "flat", "rate": 20.0},
    "samco": {"name": "Samco", "type": "flat", "rate": 20.0},
    "bigul": {"name": "Bigul", "type": "per_share", "rate": 0.08},
    "venturasecurities": {"name": "Ventura Securities", "type": "per_share", "rate": 0.10},
    "gclbroking": {"name": "GCL Broking", "type": "per_share", "rate": 0.10},
    "choiceindia": {"name": "Choice India", "type": "per_share", "rate": 0.05},
    "motilaloswal": {"name": "Motilal Oswal", "type": "per_share", "rate": 0.10},
    "edelweiss": {"name": "Edelweiss (Nuvama)", "type": "flat", "rate": 10.0},
    "bajajfinserv": {"name": "Bajaj Finserv", "type": "flat", "rate": 17.0},
    "emkayglobal": {"name": "Emkay Global", "type": "per_share", "rate": 0.15},
    "geojit": {"name": "Geojit", "type": "per_share", "rate": 0.10},
    "smcglobal": {"name": "SMC Global", "type": "per_share", "rate": 0.12},
    "anandrathi": {"name": "Anand Rathi", "type": "per_share", "rate": 0.15},

    # New/Fintech
    "appreciate": {"name": "Appreciate", "type": "per_share", "rate": 0.05},
    "univest": {"name": "Univest", "type": "flat", "rate": 10.0},
    "dhanistocks": {"name": "Dhani Stocks", "type": "flat", "rate": 20.0},
}

# Information for the new broker panel
DEMAT_INFO = {
    "groww": {"desc": "Low-cost, max ₹20 brokerage. Free MF/IPO.", "url": "https://groww.in/"},
    "upstox": {"desc": "₹150 referral bonus, free account opening.", "url": "https://upstox.com/"},
    "5paisa": {"desc": "₹250 referral bonus, 12.5% commission.", "url": "https://www.5paisa.com/"},
    "icicidirect": {"desc": "₹100 referral bonus, 10% commission.", "url": "https://www.icicidirect.com/"},
    "hdfcsky": {"desc": "₹200 referral bonus.", "url": "https://www.hdfcsky.com/"},
    "mstock": {"desc": "₹555 referral bonus.", "url": "https://www.mstock.com/"},
    "iiflsecurities": {"desc": "₹500 referral bonus.", "url": "https://www.iiflsecurities.com/"},
    "samco": {"desc": "₹150 referral, 10% commission.", "url": "https://www.samco.in/"},
    "fyers": {"desc": "20% commission on trades.", "url": "https://fyers.in/"},
    "stoxkart": {"desc": "₹300 referral, 15% commission.", "url": "https://www.stoxkart.com/"},
    "bigul": {"desc": "₹300 referral, 15% commission.", "url": "https://bigul.co/"},
    "dhan": {"desc": "20% commission on trades.", "url": "https://dhan.co/"},
    "venturasecurities": {"desc": "₹450 referral bonus.", "url": "https://www.venturasecurities.com/"},
    "gclbroking": {"desc": "₹500 referral, 20% commission.", "url": "https://gclbroking.com/"},
    "paytmmoney": {"desc": "₹400 referral, 50% commission.", "url": "https://www.paytmmoney.com/"},
    "sbisecurities": {"desc": "₹300 referral bonus.", "url": "https://www.sbisecurities.in/"},
    "choiceindia": {"desc": "₹100 referral bonus.", "url": "https://choiceindia.com/"},
    "kotaksecurities": {"desc": "Free account opening, no min balance.", "url": "https://www.kotaksecurities.com/"},
    "motilaloswal": {"desc": "Free account opening, research/advisory.", "url": "https://www.motilaloswal.com/"},
    "edelweiss": {"desc": "Free account opening, advanced tools.", "url": "https://www.nuvama.com/"},
    "bajajfinserv": {"desc": "Free account opening, integrated services.", "url": "https://www.bajajfinservsecurities.in/"},
    "axisdirect": {"desc": "Free account opening, wide range of products.", "url": "https://www.axisdirect.in/"},
    "emkayglobal": {"desc": "Free account opening, access to global markets.", "url": "https://emkayglobal.com/"},
    "appreciate": {"desc": "Free account opening, user-friendly interface.", "url": "https://appreciatewealth.com/"},
    "univest": {"desc": "Free account opening, focus on customer service.", "url": "https://www.univest.in/"},
    "dhanistocks": {"desc": "Free account opening, simple onboarding.", "url": "https://www.dhani.com/stocks/"},
    "geojit": {"desc": "Free account opening, research/advisory.", "url": "https://www.geojit.com/"},
    "smcglobal": {"desc": "Free account opening, range of products.", "url": "https://www.smcglobal.com/"},
    "aliceblue": {"desc": "Free account opening, technology-driven.", "url": "https://aliceblueonline.com/"},
    "anandrathi": {"desc": "Free account opening, wide range of products.", "url": "https://www.anandrathi.com/"},
}


STT_DELIVERY_PERCENT = 0.001  # 0.1% on Sell side
STT_INTRADAY_PERCENT = 0.00025 # 0.025% on Sell side
LEVERAGE_MULTIPLIER = 5 # 5x leverage


# --- Utility Functions and Decorators ---

def login_required(f):
    """Decorator to require login for a route."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            flash('Please log in to access this page.', 'danger')
            return redirect(url_for('login'))
        
        username = session['username']
        user_info = users.get(username)
        
        if not user_info:
             # Case where session exists but app restarted and user not in persisting store (rare now)
             # or session is invalid.
             session.pop('username', None)
             flash('User session expired. Please log in again.', 'warning')
             return redirect(url_for('login'))

        if not user_info.get('verified', False):
            flash('Please verify your account via OTP to access this page.', 'danger')
            return redirect(url_for('otp_verification'))
        return f(*args, **kwargs)
    return decorated_function

def generate_otp():
    """Generates a 6-digit OTP."""
    return str(random.randint(100000, 999999))

def send_otp_email(email, otp):
    """Sends the OTP to the user's email."""
    try:
        msg = Message(
            'Your StockScraper Verification Code',
            sender=app.config['MAIL_USERNAME'],
            recipients=[email]
        )
        msg.body = f'Your StockScraper OTP is: {otp}\n\nThis code will expire in 5 minutes.'
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

# --- Helper function for formatting large numbers ---
def format_large_number(num):
    """Formats a number into a readable string (e.g., 1.50T, 150.00B, 15.00Cr)."""
    if num is None:
        return 'N/A'
    try:
        num_float = float(num)
        if num_float > 1_00_00_00_00_00_000: # 100 Lakh Crore (Trillions)
            return f"{num_float / 1_00_00_00_00_00_000:.2f}T"
        if num_float > 1_00_00_00_00_000: # 1 Lakh Crore (Trillions)
            return f"{num_float / 1_00_00_00_00_00_000:.2f}T"
        elif num_float > 1_00_00_00_000: # 1000 Crore (Billions)
            return f"{num_float / 1_00_00_00_000:.2f}B"
        elif num_float > 1_00_00_000: # 1 Crore
            return f"{num_float / 1_00_00_000:.2f} Cr"
        else:
            return f"{num_float:,.2f}"
    except (ValueError, TypeError):
        return 'N/A'

# --- Helper function to safely get data from yfinance info ---
def safe_get(info, key, default='N/A'):
    """Safely get a value from the yfinance info dict."""
    val = info.get(key, default)
    return val if val is not None else default


# --- Authentication Routes (No Changes) ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    try:
        if 'username' in session and users.get(session['username'], {}).get('verified', False):
            return redirect(url_for('dashboard_home'))
    
        if request.method == 'POST':
            username = request.form['username']
            password = request.form['password']
            user = users.get(username)
    
            if user and check_password_hash(user['hash'], password):
                if user['verified']:
                    session['username'] = username
                    return redirect(url_for('dashboard_home'))
                else:
                    # User exists but is not verified
                    session['username'] = username # Store temp session
                    return redirect(url_for('otp_verification'))
            else:
                return render_template('login.html', error='Invalid username or password')
        return render_template('login.html')
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Internal Server Error (Login): {str(e)}", 500

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    try:
        if 'username' in session and users.get(session['username'], {}).get('verified', False):
            return redirect(url_for('dashboard_home'))
    
        if request.method == 'POST':
            username = request.form['username']
            password = request.form['password']
            email = request.form['email']
            mobile = request.form.get('mobile', 'N/A')
    
            if username in users:
                return render_template('signup.html', error='Username already exists')
    
            otp = generate_otp()
            otp_expiry = datetime.now() + timedelta(minutes=5)
            
            users[username] = {
                'hash': generate_password_hash(password),
                'email': email,
                'phone': mobile,
                'otp': otp,
                'otp_expiry': otp_expiry, # Store expiry
                'verified': False,
                'help_queries': []
            }
            
            if not send_otp_email(email, otp):
                users.pop(username) # Cleanup if email fails
                return render_template('signup.html', error='Failed to send verification email. Please check your email settings or try again later.')
    
            save_users() # Save new user (unverified)
            session['username'] = username # Store temp session for verification
            return redirect(url_for('otp_verification'))
        return render_template('signup.html')
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Internal Server Error (Signup): {str(e)}", 500

@app.route('/otp_verification', methods=['GET', 'POST'])
def otp_verification():
    try:
        if 'username' not in session:
            return redirect(url_for('login'))
        
        username = session['username']
        user_data = users.get(username)
    
        if not user_data:
            return redirect(url_for('signup'))
            
        if user_data.get('verified'):
            return redirect(url_for('dashboard_home'))
    
        if request.method == 'POST':
            otp = request.form['otp']
            
            if 'otp_expiry' not in user_data or datetime.now() > user_data['otp_expiry']:
                # Regenerate OTP and resend
                new_otp = generate_otp()
                user_data['otp'] = new_otp
                user_data['otp_expiry'] = datetime.now() + timedelta(minutes=5)
                send_otp_email(user_data['email'], new_otp)
                return render_template('otp_verification.html', error='OTP expired. A new OTP has been sent.', target_email=user_data['email'], target_mobile=user_data['phone'])
    
            if otp == user_data['otp']:
                user_data['verified'] = True
                user_data.pop('otp', None) # Clear OTP data
                user_data.pop('otp_expiry', None)
                
                save_users() # Save verified status
    
                # --- MODIFIED: Initialize full mock account ---
                session['mock_cash'] = 100000.00
                session['mock_portfolio'] = []
                session['transaction_history'] = [] 
                
                flash('Account verified successfully! You can now log in.', 'success')
                return redirect(url_for('login'))
            else:
                return render_template('otp_verification.html', error='Invalid OTP. Please try again.', target_email=user_data['email'], target_mobile=user_data['phone'])
    
        return render_template(
            'otp_verification.html', 
            target_email=user_data['email'], 
            target_mobile=user_data['phone']
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Internal Server Error (OTP): {str(e)}", 500

@app.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('mock_cash', None)
    session.pop('mock_portfolio', None)
    session.pop('transaction_history', None) 
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))


# --- Dashboard Routes (Main, Trading, Scraper, Help) ---

@app.route('/')
@login_required
def dashboard_home():
    try:
        return render_template(
            'dashboard_home.html', 
            user=session['username'], 
            active_page='home'
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Internal Server Error (Home): {str(e)}", 500

@app.route('/main_dashboard')
@login_required
def main_dashboard():
    try:
        return render_template(
            'main_dashboard.html', 
            user=session['username'], 
            active_page='main', 
            stock_options=STOCK_OPTIONS
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Internal Server Error (Main Analytics): {str(e)}", 500

# --- MODIFIED: Trading Dashboard (GET) ---
@app.route('/trading_dashboard')
@login_required
def trading_dashboard():
    # Ensure user has a trading account initialized in session
    if 'mock_cash' not in session:
        session['mock_cash'] = 100000.00
    if 'mock_portfolio' not in session:
        session['mock_portfolio'] = []
    if 'transaction_history' not in session:
        session['transaction_history'] = []

    portfolio = session['mock_portfolio']
    live_portfolio = update_mock_prices(portfolio)
    session['mock_portfolio'] = live_portfolio # Update session with latest prices
    session.modified = True # Ensure session saves the nested changes
    
    return render_template(
        'trading_dashboard.html', 
        user=session['username'], 
        active_page='trading', 
        stock_options=STOCK_OPTIONS,
        portfolio=live_portfolio,
        cash=session['mock_cash'],
        history=session.get('transaction_history', []),
        broker_config=BROKERAGE_CONFIG, # NEW
        demat_info=DEMAT_INFO # NEW
    )

@app.route('/scraper_dashboard')
@login_required
def scraper_dashboard():
    return render_template(
        'scraper_dashboard.html', 
        user=session['username'], 
        active_page='scraper'
    )

@app.route('/help_dashboard', methods=['GET', 'POST'])
@login_required
def help_dashboard():
    username = session['username']
    user_data = users.get(username)

    if request.method == 'POST':
        # Handle the support ticket submission
        name = request.form['name']
        email = request.form['email']
        query = request.form['query']
        
        if not name or not email or not query:
            flash('All fields are required.', 'danger')
        else:
            # 1. Create the query object with new fields
            ticket_id = f"T{int(time.time())}" # Unique ticket ID
            
            new_query = {
                'id': ticket_id,
                'name': name,
                'email': email,
                'query': query,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'response': 'Pending...' # NEW: Default response
            }
            
            # 2. Store the query in our "database"
            user_data['help_queries'].insert(0, new_query)
            save_users() # Persistent support tickets
            
            # 3. Send the email to the new admin address
            try:
                msg = Message(
                    subject=f"New Support Query [Ticket: {ticket_id}] - From {name}",
                    sender=app.config['MAIL_USERNAME'],
                    recipients=['1da23cs019.cs@drait.edu.in'] # <-- NEW ADMIN EMAIL
                )
                msg.body = f"""
                You have received a new support query from:
                
                User: {username}
                Name: {name}
                Email: {email}
                Ticket ID: {ticket_id}
                
                Query:
                -------------------
                {query}
                -------------------
                
                To respond, please go to the Admin Panel on the website: /admin
                (Replying directly to this email will NOT update the website.)
                """
                
                mail.send(msg)
                flash('Your query has been submitted successfully! Support has been notified.', 'success')

            except Exception as e:
                print(f"EMAIL SENDING FAILED: {e}")
                # The query is saved, but the email failed.
                flash('Your query was saved, but the email notification to support failed. Please try again later.', 'danger')
                
            return redirect(url_for('help_dashboard')) # Redirect to GET

    return render_template(
        'help_dashboard.html', 
        user=username, 
        active_page='help',
        help_queries=user_data.get('help_queries', [])
    )

# --- Admin Panel Route (No Changes) ---
@app.route('/admin', methods=['GET', 'POST'])
def admin_panel():
    # Note: This is NOT password-protected for simplicity.
    
    if request.method == 'POST':
        # Admin is submitting a response
        ticket_id = request.form['ticket_id']
        response_text = request.form['response_text']
        username_to_update = request.form['username']
        
        user_email_to_notify = ""
        user_name = ""
        original_query = ""
        
        if username_to_update in users:
            for query in users[username_to_update]['help_queries']:
                if query['id'] == ticket_id:
                    query['response'] = response_text
                    save_users() # Persistent admin response
                    
                    user_email_to_notify = query['email']
                    user_name = query['name']
                    original_query = query['query']
                    break
        
        if user_email_to_notify:
            try:
                msg = Message(
                    subject=f"Response to your StockScraper query [Ticket: {ticket_id}]",
                    sender=app.config['MAIL_USERNAME'],
                    recipients=[user_email_to_notify] # Send to the user's email
                )
                msg.body = f"""
                Hi {user_name},
                
                You have received a response from the StockScraper support team regarding your query.
                
                Ticket ID: {ticket_id}
                
                Your Original Query:
                -------------------
                {original_query}
                -------------------
                
                Support Response:
                -------------------
                {response_text}
                -------------------
                
                You can also view this response on your 'Help & Support' page on the website.
                """
                mail.send(msg)
                flash(f"Response submitted for {ticket_id} and email sent to user.", 'success')
                
            except Exception as e:
                print(f"EMAIL SENDING FAILED (to user): {e}")
                flash(f"Response saved for {ticket_id}, but the email notification to the user FAILED.", 'danger')
        else:
            flash(f"Response saved for {ticket_id}, but user email could not be found.", 'danger')

        return redirect(url_for('admin_panel'))

    # GET request: Show all queries from all users
    all_queries = []
    for username, data in users.items():
        for query in data['help_queries']:
            all_queries.append({
                'username': username,
                'ticket_id': query['id'],
                'name': query['name'],
                'email': query['email'],
                'timestamp': query['timestamp'],
                'query': query['query'],
                'response': query['response']
            })
    
    # Sort by timestamp, newest first
    all_queries.sort(key=lambda x: x['timestamp'], reverse=True)
    
    pending_queries = [q for q in all_queries if q['response'] == 'Pending...']
    completed_queries = [q for q in all_queries if q['response'] != 'Pending...']
    
    return render_template(
        'admin.html', 
        pending_queries=pending_queries,
        completed_queries=completed_queries
    )


# --- API Endpoint for Analytics Dashboard (No Changes) ---

@app.route('/get_stock_data', methods=['POST'])
@login_required
def get_stock_data():
    try:
        data = request.get_json()
        ticker_symbol = data.get('ticker')
        chart_type = data.get('chart_type', 'line')
        period = data.get('period', '1y') 

        if not ticker_symbol:
            return jsonify({"success": False, "message": "No ticker symbol provided."}), 400

        stock = yf.Ticker(ticker_symbol)
        hist = stock.history(period=period)
        
        if hist.empty:
            return jsonify({"success": False, "message": f"Could not find historical data for {ticker_symbol}."}), 404
            
        hist = hist.reset_index()
        hist['Date'] = hist['Date'].dt.strftime('%Y-%m-%d')

        chart_data = {
            'dates': hist['Date'].tolist(),
            'opens': hist['Open'].tolist(),
            'highs': hist['High'].tolist(),
            'lows': hist['Low'].tolist(),
            'closes': hist['Close'].tolist(),
            'volumes': hist['Volume'].tolist()
        }
        
        info = stock.info
        
        # Safely get prices and ensure they are numbers
        try:
            current_price = safe_get(info, 'currentPrice', hist['Close'].iloc[-1])
            if pd.isna(current_price):
                 current_price = hist['Close'].iloc[-1]
            
            previous_close = safe_get(info, 'previousClose', hist['Close'].iloc[-2] if len(hist) > 1 else 'N/A')
            if pd.isna(previous_close) and len(hist) > 1:
                previous_close = hist['Close'].iloc[-2]
        except Exception:
            current_price = 'N/A'
            previous_close = 'N/A'
        
        # Robust change calculation
        try:
            current_price_f = float(current_price)
            previous_close_f = float(previous_close)
            change = current_price_f - previous_close_f
            change_pct = (change / previous_close_f * 100) if previous_close_f != 0 else 0
        except (ValueError, TypeError):
            change = 'N/A'
            change_pct = 'N/A'
        
        market_intelligence = {
            "Current Price": f"₹{current_price:,.2f}" if isinstance(current_price, (int, float)) and not pd.isna(current_price) else (f"₹{current_price}" if current_price != 'N/A' else 'N/A'),
            "Change": f"₹{change:,.2f}" if isinstance(change, (int, float)) and not pd.isna(change) else 'N/A',
            "Change %": f"{change_pct:,.2f}%" if isinstance(change_pct, (int, float)) and not pd.isna(change_pct) else 'N/A',
            "Day High": f"₹{safe_get(info, 'dayHigh'):,.2f}" if isinstance(safe_get(info, 'dayHigh'), (int, float)) and not pd.isna(safe_get(info, 'dayHigh')) else 'N/A',
            "Day Low": f"₹{safe_get(info, 'dayLow'):,.2f}" if isinstance(safe_get(info, 'dayLow'), (int, float)) and not pd.isna(safe_get(info, 'dayLow')) else 'N/A',
            "52 Week High": f"₹{safe_get(info, 'fiftyTwoWeekHigh'):,.2f}" if isinstance(safe_get(info, 'fiftyTwoWeekHigh'), (int, float)) and not pd.isna(safe_get(info, 'fiftyTwoWeekHigh')) else 'N/A',
            "52 Week Low": f"₹{safe_get(info, 'fiftyTwoWeekLow'):,.2f}" if isinstance(safe_get(info, 'fiftyTwoWeekLow'), (int, float)) and not pd.isna(safe_get(info, 'fiftyTwoWeekLow')) else 'N/A',
            "Volume": f"{safe_get(info, 'regularMarketVolume'):,}" if isinstance(safe_get(info, 'regularMarketVolume'), (int, float)) and not pd.isna(safe_get(info, 'regularMarketVolume')) else 'N/A',
            "Previous Close": f"₹{previous_close:,.2f}" if isinstance(previous_close, (int, float)) and not pd.isna(previous_close) else 'N/A'
        }

        fundamental_data = {
            "Stock": f"{safe_get(info, 'shortName', ticker_symbol)} ({ticker_symbol})",
            "Industry": safe_get(info, 'industry'),
            "Base Country": safe_get(info, 'country'),
            "CMP Rs.": market_intelligence.get('Current Price'),
            "P/E Ratio": f"{safe_get(info, 'trailingPE'):.2f}" if isinstance(safe_get(info, 'trailingPE'), (int, float)) else 'N/A',
            "Mar Cap Rs. Cr.": format_large_number(safe_get(info, 'marketCap')),
            "Div Yld %": f"{safe_get(info, 'dividendYield') * 100:.2f}%" if isinstance(safe_get(info, 'dividendYield'), (int, float)) else 'N/A',
            "NP Qtr Rs. Cr.": format_large_number(safe_get(info, 'netIncomeToCommon')), # Net Profit
            "Qtr Profit Var %": f"{safe_get(info, 'profitMargins') * 100:.2f}%" if isinstance(safe_get(info, 'profitMargins'), (int, float)) else 'N/A',
            "Sales Qtr Rs. Cr.": format_large_number(safe_get(info, 'totalRevenue')),
            "Qtr Sales Var %": f"{safe_get(info, 'revenueGrowth') * 100:.2f}%" if isinstance(safe_get(info, 'revenueGrowth'), (int, float)) else 'N/A',
            "ROCE %": f"{safe_get(info, 'returnOnEquity') * 100:.2f}%" if isinstance(safe_get(info, 'returnOnEquity'), (int, float)) else 'N/A',
        }

        return jsonify({
            "success": True, 
            "data": {
                "chart_data": chart_data,
                "chart_type": chart_type, 
                "period": period, 
                "market_intelligence": market_intelligence,
                "fundamental_data": fundamental_data
            }
        })

    except Exception as e:
        import traceback
        print(f"Error fetching stock data: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "message": f"An error occurred while fetching data for {ticker_symbol}. Details: {str(e)}"}), 500


# --- *** MODIFIED: Trading Panel Logic *** ---

def update_mock_prices(portfolio):
    """Updates the 'current' price for all items in the portfolio."""
    if not portfolio:
        return []
    
    tickers = [item['symbol'] for item in portfolio]
    try:
        # --- NEW: Try to get 1m interval data for a "live" feel ---
        data = yf.download(tickers, period="1d", interval="1m", progress=False)
        if data.empty:
            # Fallback for non-market hours
            print("DEBUG: 1m interval empty, falling back to 1d data for price update.")
            data = yf.download(tickers, period="1d", progress=False)
            if data.empty:
                return portfolio # No data at all

        prices = {}
        for ticker in tickers:
            try:
                if len(tickers) == 1:
                    price_data = data
                else:
                    price_data = data.loc[:, (slice(None), ticker)]
                
                # Get the last valid price (Close, then Open)
                last_price = price_data['Close'].iloc[-1]
                if pd.isna(last_price): 
                    last_price = price_data['Open'].iloc[-1]
                
                # If still no price, keep the old one
                if not pd.isna(last_price):
                    prices[ticker] = last_price
                else:
                    for item in portfolio:
                         if item['symbol'] == ticker:
                            prices[ticker] = item['current'] # Keep old price
                            break
            except Exception:
                for item in portfolio:
                    if item['symbol'] == ticker:
                        prices[ticker] = item['current']
                        break
        
        # --- THIS IS THE G/L FIX ---
        # Update portfolio with new prices AND recalculate G/L
        for item in portfolio:
            if item['symbol'] in prices:
                new_price = prices[item['symbol']]
                if not pd.isna(new_price):
                    item['current'] = float(new_price)
                    
                # The G/L is now calculated HERE, based on live price vs avg cost
                # Safely handle potential non-numeric data
                try:
                    curr = float(item.get('current', 0))
                    cost = float(item.get('cost', 0))
                    shares = int(item.get('shares', 0))
                    item['gain_loss'] = (curr - cost) * shares
                except (ValueError, TypeError):
                    item['gain_loss'] = 0.0

    except Exception as e:
        print(f"Error updating mock prices: {e}")
    
    return portfolio

def execute_trade_logic(symbol, quantity, action, trade_type, use_margin, broker):
    """Handles the logic for buying or selling a stock, including fees and history."""
    try:
        stock = yf.Ticker(symbol)
        hist = stock.history(period="1d")
        if hist.empty:
            flash(f"Error: Could not find price data for {symbol}.", 'danger')
            return False
            
        price = hist['Close'].iloc[-1]
        if price is None or price == 0 or pd.isna(price):
            price = hist['Open'].iloc[-1] # Fallback
            
        if price is None or price == 0 or pd.isna(price):
            flash(f"Error: Could not determine a valid price for {symbol}.", 'danger')
            return False

    except Exception:
        flash(f"Error: Invalid ticker symbol '{symbol}'.", 'danger')
        return False
        
    
    portfolio = session.get('mock_portfolio', [])
    cash = session.get('mock_cash', 0)
    
    if 'transaction_history' not in session:
        session['transaction_history'] = []
    
    # --- NEW: Get dynamic brokerage rate ---
    broker_config = BROKERAGE_CONFIG.get(broker, BROKERAGE_CONFIG['groww']) # Default to Groww
    brokerage_rate = broker_config['rate']
    brokerage_type = broker_config['type']
    
    # Calculate brokerage fee
    if brokerage_type == 'flat':
        brokerage_fee = brokerage_rate
    else: # per_share
        brokerage_fee = brokerage_rate * quantity
        
    # --- NEW: Leverage Logic ---
    trade_value = price * quantity
    leverage = 1
    if trade_type == 'intraday' and use_margin:
        leverage = LEVERAGE_MULTIPLIER
        
    margin_required = trade_value / leverage
    
    
    if action == 'buy':
        total_cost = margin_required + brokerage_fee
        
        if cash < total_cost:
            flash(f"Not enough cash. You need ₹{total_cost:,.2f} (Margin: ₹{margin_required:,.2f} + Fee: ₹{brokerage_fee:,.2f}) but only have ₹{cash:,.2f}.", 'danger')
            return False
        
        session['mock_cash'] = cash - total_cost
        
        found = False
        for item in portfolio:
            if item['symbol'] == symbol:
                # Update existing position
                # Cost basis is always the full price, not the margin price
                new_total_shares = item['shares'] + quantity
                new_total_cost = (item['cost'] * item['shares']) + (price * quantity) 
                item['cost'] = new_total_cost / new_total_shares # New avg cost
                item['shares'] = new_total_shares
                item['current'] = price
                found = True
                break
        
        if not found:
            # New position
            portfolio.append({
                'symbol': symbol, 'shares': quantity, 'cost': price, 
                'current': price, 'gain_loss': 0.0
            })
        
        # Log the transaction
        log_entry = {
            'type': 'Buy', 'trade_type': trade_type, 'symbol': symbol, 'shares': quantity, 'price': price,
            'broker': broker_config['name'], 'leverage': f"{leverage}x",
            'total_value': margin_required, 'fees': brokerage_fee, 'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        session['transaction_history'].insert(0, log_entry)
        
        flash(f"Bought {quantity} shares of {symbol}. Margin blocked: ₹{margin_required:,.2f} (Fee: ₹{brokerage_fee:,.2f})", 'success')
        
    elif action == 'sell':
        found = False
        for item in portfolio:
            if item['symbol'] == symbol:
                if item['shares'] < quantity:
                    flash(f"Cannot sell {quantity} shares. You only own {item['shares']} shares of {symbol}.", 'danger')
                    return False
                
                # --- NEW: Calculate sell fees based on trade type ---
                if trade_type == 'intraday':
                    stt_fee = trade_value * STT_INTRADAY_PERCENT
                else: # Default to delivery
                    stt_fee = trade_value * STT_DELIVERY_PERCENT
                
                total_fees = brokerage_fee + stt_fee
                
                # --- NEW: Calculate cash return based on margin ---
                profit_loss = (price - item['cost']) * quantity
                
                # Check if this was a margin trade (by checking if margin was used for *any* buy of this)
                # Simple check: if intraday, assume margin was used.
                # In a real app, this would be tracked per-position.
                if trade_type == 'intraday' and use_margin:
                    # We get our margin back, plus the profit/loss, minus fees
                    cash_return = margin_required + profit_loss - total_fees
                else:
                    # No margin, so we get the full trade value, minus fees
                    cash_return = trade_value - total_fees
                
                # Execute sale
                session['mock_cash'] = cash + cash_return
                item['shares'] -= quantity
                
                if item['shares'] == 0:
                    portfolio.remove(item)
                
                # Log the transaction
                log_entry = {
                    'type': 'Sell', 'trade_type': trade_type, 'symbol': symbol, 'shares': quantity, 'price': price,
                    'broker': broker_config['name'], 'leverage': f"{leverage}x",
                    'total_value': cash_return, 'fees': total_fees, 'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                session['transaction_history'].insert(0, log_entry)

                flash(f"Sold {quantity} shares of {symbol}. Cash returned: ₹{cash_return:,.2f} (P/L: ₹{profit_loss:,.2f} - Fees: ₹{total_fees:,.2f})", 'success')
                found = True
                break
        
        if not found:
            flash(f"You do not own any shares of {symbol}.", 'danger')
            return False
            
    session['mock_portfolio'] = portfolio
    session.modified = True
    return True


# --- *** MODIFIED: API Endpoint for Trading *** ---
@app.route('/execute_trade', methods=['POST'])
@login_required
def execute_trade():
    try:
        data = request.get_json()
        symbol = data.get('symbol', '').upper()
        
        if not symbol:
            flash("Ticker symbol is required.", 'danger')
            return jsonify({"success": False, "message": "Ticker symbol is required."})
            
        try:
            quantity = int(data.get('quantity', 0))
            if quantity <= 0:
                raise ValueError()
        except (ValueError, TypeError):
            flash("Quantity must be a positive whole number.", 'danger')
            return jsonify({"success": False, "message": "Quantity must be a positive whole number."})
            
        action = data.get('action')
        if action not in ['buy', 'sell']:
            flash("Invalid action.", 'danger')
            return jsonify({"success": False, "message": "Invalid action."})
    
        # --- NEW: Get form data ---
        trade_type = data.get('trade_type', 'delivery')
        use_margin = data.get('use_margin', False)
        broker = data.get('broker', 'groww') # Default to groww
    
        # Pass to logic function
        if execute_trade_logic(symbol, quantity, action, trade_type, use_margin, broker):
            portfolio = session['mock_portfolio']
            cash = session['mock_cash']
            shares = 0
            for item in portfolio:
                if item['symbol'] == symbol:
                    shares = item['shares']
                    break
            
            return jsonify({"success": True, "message": "Trade executed.", "cash": cash, "shares": shares})
        else:
            messages = [msg[1] for msg in get_flashed_messages(with_categories=True)]
            flash_message = messages[-1] if messages else "Trade failed due to an unknown error."
            return jsonify({"success": False, "message": flash_message})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": f"Internal Server Error during trade execution: {str(e)}"}), 500


# --- Helper Functions for Scraper (No Changes) ---

def find_news_title(item):
    """Intelligibly finds a title from a news item dictionary."""
    possible_keys = ['title', 'headline', 'summary', 'description']
    for key in possible_keys:
        if item.get(key) and isinstance(item[key], str):
            if key in ['description', 'summary'] and len(item[key]) > 150:
                return item[key][:150] + "..." 
            return item[key]
    return None

def find_news_link(item):
    """Intelligibly finds a link from a news item dictionary."""
    if item.get('canonicalUrl') and isinstance(item.get('canonicalUrl'), dict) and item['canonicalUrl'].get('url'):
        return item['canonicalUrl']['url']
    if item.get('clickThroughUrl') and isinstance(item.get('clickThroughUrl'), dict) and item['clickThroughUrl'].get('url'):
        return item['clickThroughUrl']['url']
    possible_keys = ['link', 'url', 'articleUrl', 'storyUrl']
    for key in possible_keys:
        if item.get(key) and isinstance(item[key], str) and item[key].startswith('http'):
            return item[key]
    if item.get('provider') and isinstance(item.get('provider'), dict) and item['provider'].get('url'):
        return item['provider']['url'] 
    return None

# --- API Endpoint for Scraper (No Changes) ---

@app.route('/scrape_news', methods=['POST'])
@login_required
def scrape_news():
    data = request.get_json()
    ticker_symbol = data.get('ticker')

    if not ticker_symbol:
        return jsonify({"success": False, "message": "No ticker symbol provided."}), 400

    try:
        stock = yf.Ticker(ticker_symbol)
        
        info = stock.info
        news_list = info.get('news', []) 

        if not news_list:
            print(f"DEBUG: 'stock.info' has no news for {ticker_symbol}. Trying 'stock.news'...")
            try:
                news_list = stock.news 
            except KeyError as e:
                print(f"ERROR: yfinance 'stock.news' failed with KeyError: {e}.")
                return jsonify({"success": False, "message": f"Could not fetch news for {ticker_symbol}. (KeyError: {e})."}), 500
            except Exception as e:
                print(f"ERROR: 'stock.news' failed with exception: {e}")
                return jsonify({"success": False, "message": f"An error occurred while fetching news for {ticker_symbol}."}), 500
        else:
            print(f"DEBUG: Found news for {ticker_symbol} in 'stock.info'.")
            
        if not news_list:
            return jsonify({"success": False, "message": f"No news found for {ticker_symbol}."}), 404

        formatted_news = []
        
        if news_list:
            print(f"\n\nDEBUG: Keys in first news item for {ticker_symbol}: {news_list[0].keys()}\n\n")

        for item in news_list:
            content_item = item.get('content')
            
            if content_item and isinstance(content_item, dict):
                print("DEBUG: Processing 'content' dictionary format.")
                title = find_news_title(content_item)
                link = find_news_link(content_item)
                publisher = content_item.get('provider', {}).get('displayName', 'N/A')
            else:
                print("DEBUG: Processing flat dictionary format.")
                title = find_news_title(item)
                link = find_news_link(item)
                publisher = item.get('publisher', 'N/A')
            
            if title and link:
                formatted_news.append({
                    'title': title,
                    'publisher': publisher,
                    'link': link,
                })
        
        if not formatted_news:
             if news_list:
                print(f"\n\nDEBUG: No items matched filter. First news item was: {news_list[0]}\n\n")
             return jsonify({"success": False, "message": f"No valid news articles found for {ticker_symbol} (Data format mismatch)."}), 404

        return jsonify({"success": True, "news": formatted_news})

    except Exception as e:
        import traceback
        print(f"Error scraping news: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "message": f"An error occurred while fetching news. Details: {str(e)}"}), 500


# --- Global Error Handler ---
@app.errorhandler(500)
def internal_error(error):
    import traceback
    traceback.print_exc()
    return f"<h1>Internal Server Error</h1><pre>{str(error)}</pre>", 500

@app.errorhandler(Exception)
def handle_exception(e):
    import traceback
    traceback.print_exc()
    return f"<h1>Server Error</h1><pre>{str(e)}</pre>", 500


if __name__ == '__main__':
    # Initialize mock data for a test user if it doesn't exist
    if 'testuser' not in users:
        users['testuser'] = {
            'hash': generate_password_hash('testpass'),
            'email': 'test@example.com',
            'phone': '9876543210',
            'otp': generate_otp(),
            'otp_expiry': datetime.now() + timedelta(minutes=5),
            'verified': True,
            'help_queries': [ 
                {
                    'id': 'T1731580200',
                    'name': 'Test User',
                    'email': 'test@example.com',
                    'query': 'My trading panel cash balance did not update after a sale. Can you check the transaction log for "TCS.NS"?',
                    'timestamp': datetime(2025, 11, 14, 10, 30, 0).strftime('%Y-%m-%d %H:%M:%S'),
                    'response': 'Our engineering team has reviewed the log and corrected the balance. Please check again.' # Example of a response
                },
                {
                    'id': 'T1731498300',
                    'name': 'Test User',
                    'email': 'test@example.com',
                    'query': 'How do I use the new Data Scraper feature? The guide seems incomplete.',
                    'timestamp': datetime(2025, 11, 13, 15, 45, 0).strftime('%Y-%m-%d %H:%M:%S'),
                    'response': 'Pending...'
                }
            ],
            'transaction_history': [] 
        }
        
    app.run(debug=True)