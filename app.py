import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv

load_dotenv()
# Initialize the Flask Application
app = Flask(__name__)
app.secret_key = "needs_for_home_super_secret_key" 

def create_db_connection():
    """Establishes a connection to the AWS MySQL Database."""
    try:
        connection = mysql.connector.connect(
            host='needsforhome-mysql.cxoi6kg06bb7.us-east-2.rds.amazonaws.com',
            user='admin',                               
            password= os.getenv('DB_PASS', "").strip(),              
            database='NeedsForHomeDB'            
        )
        return connection
    except Error as e:
        print(f"Error connecting to MySQL Database: {e}")
        return None

# --- AUTHENTICATION & REGISTRATION ---

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']
        zip_code = request.form.get('zip_code', '') 
        
        # Grab the service type (defaults to 'General Service' if they are a client)
        service_type = request.form.get('service_type', 'General Service')
        
        connection = create_db_connection()
        if connection:
            cursor = connection.cursor()
            # UPDATED: Insert service_type into the database
            query = "INSERT INTO User (name, email, password, role, zip_code, service_type) VALUES (%s, %s, %s, %s, %s, %s)"
            cursor.execute(query, (name, email, password, role, zip_code, service_type))
            connection.commit()
            connection.close()
            
            flash("Account created! Please log in.")
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        connection = create_db_connection()
        if connection:
            cursor = connection.cursor(dictionary=True)
            query = "SELECT * FROM User WHERE email = %s AND password = %s"
            cursor.execute(query, (email, password))
            user = cursor.fetchone()
            
            if user:
                session['user_loggedin'] = True
                session['user_id'] = user['user_id']
                session['name'] = user['name']
                session['role'] = user['role']

                if user['role'] == 'Provider':
                    return redirect(url_for('provider_dashboard'))
                else:
                    return redirect(url_for('dashboard'))
            else:
                flash("Invalid email or password!")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

# --- CLIENT DASHBOARD & BOOKING (CRUD + Business Logic) ---

@app.route('/dashboard')
def dashboard():
    if 'user_loggedin' not in session:
        return redirect(url_for('login'))
    
    connection = create_db_connection()
    user_bookings = []
    if connection:
        cursor = connection.cursor(dictionary=True)
        query = "SELECT * FROM Booking WHERE client_id = %s"
        cursor.execute(query, (session['user_id'],))
        user_bookings = cursor.fetchall()
        connection.close()

    return render_template('dashboard.html', name=session['name'], bookings=user_bookings)

@app.route('/book', methods=['POST'])
def create_booking():
    """Function Set 4.5: Geographic Matching & Cost Estimation"""
    if 'user_loggedin' not in session:
        return redirect(url_for('login'))

    provider_id = request.form['provider_id']
    user_zip = request.form['zip_code']
    service_date = request.form['service_date']
    hours = 1 # Standard service duration for computation

    # BUSINESS LOGIC: Geographic check (RGV Area)
    

    connection = create_db_connection()
    if connection:
        cursor = connection.cursor(dictionary=True)
        try:
            # BUSINESS LOGIC: Fetch Provider's rate for computation
            cursor.execute("SELECT hourly_rate FROM User WHERE user_id = %s", (provider_id,))
            provider = cursor.fetchone()
            rate = provider['hourly_rate'] if provider else 50.00
            total = float(rate) * hours

            query = """
                INSERT INTO Booking (client_id, provider_id, booking_date, status, zip_code, total_cost) 
                VALUES (%s, %s, %s, 'Pending', %s, %s)
            """
            cursor.execute(query, (session['user_id'], provider_id, service_date, user_zip, total))
            connection.commit()
            flash(f"Booking confirmed! Estimated Total: ${total:.2f}")
        except Error as e:
            flash(f"Database Error: {e}")
        finally:
            connection.close()
    return redirect(url_for('dashboard'))

# --- PROVIDER DASHBOARD & UPDATES ---

@app.route('/provider_dashboard')
def provider_dashboard():
    if 'user_loggedin' not in session or session.get('role') != 'Provider':
        return redirect(url_for('login'))
    
    connection = create_db_connection()
    jobs = []
    if connection:
        cursor = connection.cursor(dictionary=True)
        # Using JOIN to show Client Name (4.3) and grab total_cost
        query = """
            SELECT b.booking_id, b.booking_date, b.total_cost, u.name as client_name 
            FROM Booking b
            JOIN User u ON b.client_id = u.user_id
            WHERE b.provider_id = %s
        """
        cursor.execute(query, (session['user_id'],))
        jobs = cursor.fetchall()
        connection.close()
    return render_template('provider_dashboard.html', name=session['name'], jobs=jobs)

@app.route('/update_rate', methods=['POST'])
def update_rate():
    """Function Set 4.4: Update Operation for Provider Settings"""
    if 'user_loggedin' not in session or session['role'] != 'Provider':
        return redirect(url_for('login'))

    new_rate = request.form['rate']
    connection = create_db_connection()
    if connection:
        cursor = connection.cursor()
        cursor.execute("UPDATE User SET hourly_rate = %s WHERE user_id = %s", (new_rate, session['user_id']))
        connection.commit()
        connection.close()
        flash(f"Success! Your rate updated to ${new_rate}/hr")
    return redirect(url_for('provider_dashboard'))

# --- MODIFICATION & DELETION (4.4) ---

@app.route('/reschedule/<int:booking_id>', methods=['POST'])
def reschedule_booking(booking_id):
    if 'user_loggedin' not in session:
        return redirect(url_for('login'))
        
    new_date = request.form['new_date']
    connection = create_db_connection()
    if connection:
        cursor = connection.cursor()
        query = "UPDATE Booking SET booking_date = %s WHERE booking_id = %s AND client_id = %s"
        cursor.execute(query, (new_date, booking_id, session['user_id']))
        connection.commit()
        connection.close()
        flash("Rescheduled successfully!")
    return redirect(url_for('dashboard'))

@app.route('/cancel/<int:booking_id>')
def cancel_booking(booking_id):
    if 'user_loggedin' not in session:
        return redirect(url_for('login'))
        
    connection = create_db_connection()
    if connection:
        cursor = connection.cursor()
        query = "DELETE FROM Booking WHERE booking_id = %s AND client_id = %s"
        cursor.execute(query, (booking_id, session['user_id']))
        connection.commit()
        connection.close()
        flash("Booking canceled.")
    return redirect(url_for('dashboard'))

@app.route('/providers')
def view_providers():
    connection = create_db_connection()
    providers = []
    if connection:
        cursor = connection.cursor(dictionary=True)
        # UPDATED: Select service_type from the database
        cursor.execute("SELECT user_id, name, email, hourly_rate, zip_code, service_type FROM User WHERE role = 'Provider'")
        providers = cursor.fetchall()
        connection.close()
    return render_template('providers.html', providers=providers)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
