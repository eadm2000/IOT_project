# main app.py
from flask import Flask, request, jsonify, render_template
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from config import API_TOKEN, JWT_SECRET_KEY, JWT_ACCESS_TOKEN_EXPIRES
from models.reading import SensorReading, Machine, SystemLog, Reading
from services.database import get_connection
import bcrypt
import json

app = Flask(__name__)

# JWT Configuration
app.config['JWT_SECRET_KEY'] = JWT_SECRET_KEY
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = JWT_ACCESS_TOKEN_EXPIRES
jwt = JWTManager(app)


# Authentication endpoints
@app.route('/register', methods=['POST'])
def register():
    """Register a new user"""
    try:
        data = request.get_json()

        if not data or 'username' not in data or 'password' not in data:
            return jsonify({'error': 'Username and password are required'}), 400

        username = data['username']
        password = data['password']
        email = data.get('email', '')

        # Hash the password
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

        db = get_connection()
        cursor = db.cursor()

        try:
            # Check if user already exists
            cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
            if cursor.fetchone():
                return jsonify({'error': 'Username already exists'}), 409

            # Insert new user
            cursor.execute("""
                INSERT INTO users (username, password_hash, email, created_at)
                VALUES (%s, %s, %s, NOW())
            """, (username, password_hash, email))

            db.commit()

            return jsonify({'message': 'User registered successfully'}), 201

        except Exception as e:
            db.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            cursor.close()
            db.close()

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/login', methods=['POST'])
def login():
    """User login endpoint"""
    try:
        if not request.is_json:
            return jsonify({"error": "Missing JSON in request"}), 400

        username = request.json.get('username')
        password = request.json.get('password')

        if not username or not password:
            return jsonify({"error": "Missing username or password"}), 400

        db = get_connection()
        cursor = db.cursor(dictionary=True)

        try:
            # Get user from database
            cursor.execute(
                "SELECT id, username, password_hash FROM users WHERE username = %s",
                (username,)
            )
            user = cursor.fetchone()

            if not user or not bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
                return jsonify({"error": "Invalid username or password"}), 401

            # Create access token
            access_token = create_access_token(identity=username)

            # Log the login
            cursor.execute("""
                INSERT INTO user_sessions (user_id, token, created_at, last_used)
                VALUES (%s, %s, NOW(), NOW())
            """, (user['id'], access_token))

            db.commit()

            return jsonify({
                'access_token': access_token,
                'username': username,
                'message': 'Login successful'
            }), 200

        finally:
            cursor.close()
            db.close()

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    """User logout endpoint"""
    try:
        current_user = get_jwt_identity()
        # In a real app, you'd want to blacklist the token
        return jsonify({'message': f'User {current_user} logged out successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Protected helper function
def auth_required(f):
    """Custom decorator that allows both JWT and API token authentication"""

    def decorated_function(*args, **kwargs):
        # Check for JWT token first
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            # JWT token provided, use JWT authentication
            try:
                from flask_jwt_extended import verify_jwt_in_request
                verify_jwt_in_request()
                return f(*args, **kwargs)
            except:
                return jsonify({'error': 'Invalid JWT token'}), 401

        # Check for legacy API token
        elif auth_header == API_TOKEN:
            return f(*args, **kwargs)

        else:
            return jsonify({'error': 'Authentication required. Provide JWT token or API key.'}), 401

    decorated_function.__name__ = f.__name__
    return decorated_function


# Legacy endpoints (keep for backward compatibility with API token)
@app.route('/v1/data', methods=['POST'])
def receive_data():
    token = request.headers.get('Authorization')
    if token != API_TOKEN:
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json()
    required_fields = ['timestamp', 'temperature', 'humidity']
    if not all(field in data for field in required_fields):
        return jsonify({'error': 'Missing fields'}), 400

    reading = Reading(data['timestamp'], data['temperature'], data['humidity'])
    reading.save()
    return jsonify({'status': 'saved'}), 201


@app.route('/v1/data', methods=['GET'])
@auth_required
def get_readings():
    start = request.args.get('start')
    end = request.args.get('end')

    if not start or not end:
        return jsonify({'error': 'Start and end parameters are required'}), 400

    readings = Reading.get_by_date_range(start, end)
    return jsonify(readings)


@app.route('/v1/data/latest', methods=['GET'])
@auth_required
def get_latest_reading():
    readings = Reading.get_last_n(1)
    return jsonify(readings[0] if readings else {})


@app.route('/v1/data/last-n/<int:n>', methods=['GET'])
@auth_required
def get_last_n(n):
    readings = Reading.get_last_n(n)
    return jsonify(readings)


@app.route('/v1/data/dates', methods=['GET'])
@auth_required
def get_dates():
    dates = Reading.get_available_dates()
    return jsonify(dates)


@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'API running'})


# Device LED Control endpoints
@app.route('/device_status', methods=['POST'])
@auth_required
def update_device_status():
    """Update device status including filtered LED states (status + activity only)"""
    try:
        data = request.get_json()

        # Ensure machine_id is provided
        if 'machine_id' not in data:
            return jsonify({'error': 'machine_id is required'}), 400

        # Define which LEDs are supported (status + activity)
        valid_leds = ['status', 'activity']
        incoming_leds = data.get('led_states', {})

        # Only keep allowed LED states
        filtered_leds = {k: v for k, v in incoming_leds.items() if k in valid_leds}

        # Save to database
        db = get_connection()
        cursor = db.cursor()
        try:
            cursor.execute("""
                INSERT INTO device_status (machine_id, led_states, last_updated)
                VALUES (%s, %s, NOW())
                ON DUPLICATE KEY UPDATE
                led_states = VALUES(led_states),
                last_updated = NOW()
            """, (data['machine_id'], json.dumps(filtered_leds)))

            db.commit()
            return jsonify({'status': 'device status updated'}), 200

        finally:
            cursor.close()
            db.close()

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/device_status/<machine_id>', methods=['GET'])
@jwt_required()
def get_device_status(machine_id):
    """Get current device status including only 'status' and 'activity' LED states"""
    try:
        db = get_connection()
        cursor = db.cursor(dictionary=True)

        try:
            cursor.execute("""
                SELECT ds.*, m.machine_name, m.location
                FROM device_status ds
                JOIN machines m ON ds.machine_id = m.machine_id
                WHERE ds.machine_id = %s
            """, (machine_id,))

            status = cursor.fetchone()

            if not status:
                return jsonify({'error': 'Device not found'}), 404

            # Parse and filter LED states
            if status.get('led_states'):
                try:
                    raw_leds = json.loads(status['led_states'])
                    valid_leds = ['status', 'activity']
                    filtered_leds = {k: v for k, v in raw_leds.items() if k in valid_leds}
                    status['led_states'] = filtered_leds
                except Exception:
                    status['led_states'] = {}  # fallback if JSON parsing fails

            return jsonify(status), 200

        finally:
            cursor.close()
            db.close()

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/led_control/<machine_id>', methods=['POST'])
@jwt_required()
def control_led(machine_id):
    """Send LED control command to device"""
    try:
        data = request.get_json()
        current_user = get_jwt_identity()

        required_fields = ['led', 'state']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400

        valid_leds = ['status', 'activity']
        if data['led'] not in valid_leds:
            return jsonify({'error': f'Invalid LED name. Must be one of: {valid_leds}'}), 400

        if not isinstance(data['state'], bool):
            return jsonify({'error': 'State must be true or false'}), 400

        db = get_connection()
        cursor = db.cursor()

        try:
            cursor.execute("""
                INSERT INTO device_commands (machine_id, command_type, command_data, created_by, created_at)
                VALUES (%s, 'led_control', %s, %s, NOW())
            """, (machine_id, json.dumps({
                'type': 'led_control',
                'led': data['led'],
                'state': data['state']
            }), current_user))

            command_id = cursor.lastrowid
            db.commit()

            return jsonify({
                'status': 'command queued',
                'command_id': command_id,
                'machine_id': machine_id,
                'led': data['led'],
                'state': data['state']
            }), 200

        finally:
            cursor.close()
            db.close()

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/device_status/<machine_id>', methods=['GET'])
@jwt_required()
def get_device_status(machine_id):
    """Get current device status including LED states"""
    try:
        db = get_connection()
        cursor = db.cursor(dictionary=True)

        try:
            cursor.execute("""
                SELECT ds.*, m.machine_name, m.location
                FROM device_status ds
                JOIN machines m ON ds.machine_id = m.machine_id
                WHERE ds.machine_id = %s
            """, (machine_id,))

            status = cursor.fetchone()

            if not status:
                return jsonify({'error': 'Device not found'}), 404

            # Parse LED states JSON
            if status['led_states']:
                status['led_states'] = json.loads(status['led_states'])

            return jsonify(status), 200

        finally:
            cursor.close()
            db.close()

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# New IoT endpoints (protected with JWT)
@app.route('/sensor_reading', methods=['POST'])
@auth_required
def add_sensor_reading():
    """Add new sensor reading"""
    try:
        data = request.get_json()

        # Validate required fields
        required_fields = ['machine_id', 'temperature', 'humidity']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400

        # Create and save sensor reading
        reading = SensorReading(
            machine_id=data['machine_id'],
            temperature=data['temperature'],
            humidity=data['humidity'],
            temp_unit=data.get('temp_unit', 'C'),
            status=data.get('status', 'active'),
            machine_name=data.get('machine_name'),
            location=data.get('location')
        )

        reading_id = reading.save()

        return jsonify({
            'status': 'success',
            'id': reading_id,
            'machine_id': data['machine_id'],
            'temperature': data['temperature'],
            'humidity': data['humidity']
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/log', methods=['POST'])
@jwt_required()
def add_log():
    """Add system log entry"""
    try:
        current_user = get_jwt_identity()
        data = request.get_json()

        if 'machine_id' not in data or 'message' not in data:
            return jsonify({'error': 'machine_id and message are required'}), 400

        log = SystemLog(
            machine_id=data['machine_id'],
            log_level=data.get('log_level', 'info'),
            message=f"[{current_user}] {data['message']}",  # Include user in log
            error_code=data.get('error_code')
        )

        log_id = log.save()

        return jsonify({'status': 'logged', 'id': log_id}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/latest_readings', methods=['GET'])
@jwt_required()
def get_latest_readings():
    """Get the most recent reading from each machine"""
    try:
        readings = SensorReading.get_latest_readings()
        return jsonify(readings), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/readings/<machine_id>', methods=['GET'])
@jwt_required()
def get_machine_readings(machine_id):
    """Get recent readings for a specific machine"""
    try:
        limit = request.args.get('limit', 50, type=int)
        readings = SensorReading.get_latest_n(machine_id, limit)
        return jsonify({
            'machine_id': machine_id,
            'limit': limit,
            'total_readings': len(readings),
            'readings': readings
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/readings_range/<machine_id>', methods=['GET'])
@jwt_required()
def get_readings_by_date_range(machine_id):
    """Get readings for a machine between two dates"""
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        if not start_date or not end_date:
            return jsonify({'error': 'start_date and end_date parameters are required (YYYY-MM-DD format)'}), 400

        readings = SensorReading.get_by_date_range(machine_id, start_date, end_date)

        return jsonify({
            'machine_id': machine_id,
            'start_date': start_date,
            'end_date': end_date,
            'total_readings': len(readings),
            'readings': readings
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/readings_latest/<machine_id>', methods=['GET'])
@jwt_required()
def get_latest_n_readings(machine_id):
    """Get latest N readings for a machine"""
    try:
        limit = request.args.get('limit', 10, type=int)

        if limit > 1000:
            limit = 1000

        readings = SensorReading.get_latest_n(machine_id, limit)

        return jsonify({
            'machine_id': machine_id,
            'limit': limit,
            'total_readings': len(readings),
            'readings': readings
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/all_readings_range', methods=['GET'])
@jwt_required()
def get_all_readings_by_date_range():
    """Get readings for ALL machines between two dates"""
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        if not start_date or not end_date:
            return jsonify({'error': 'start_date and end_date parameters are required (YYYY-MM-DD format)'}), 400

        readings = SensorReading.get_all_by_date_range(start_date, end_date)

        return jsonify({
            'start_date': start_date,
            'end_date': end_date,
            'total_readings': len(readings),
            'readings': readings
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/all_readings_latest', methods=['GET'])
@jwt_required()
def get_all_latest_readings():
    """Get latest N readings from ALL machines"""
    try:
        limit = request.args.get('limit', 50, type=int)

        if limit > 1000:
            limit = 1000

        readings = SensorReading.get_all_latest_n(limit)

        return jsonify({
            'limit': limit,
            'total_readings': len(readings),
            'readings': readings
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/statistics/<machine_id>', methods=['GET'])
@jwt_required()
def get_machine_statistics(machine_id):
    """Get temperature/humidity statistics for a machine"""
    try:
        days = request.args.get('days', 1, type=int)
        stats = SensorReading.get_statistics(machine_id, days)

        return jsonify({
            'machine_id': machine_id,
            'period_days': days,
            'statistics': stats
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/machine/<machine_id>', methods=['PUT'])
@jwt_required()
def update_machine(machine_id):
    """Update machine information"""
    try:
        data = request.get_json()

        machine = Machine(
            machine_id=machine_id,
            machine_name=data.get('machine_name'),
            location=data.get('location'),
            sensor_type=data.get('sensor_type', 'DHT22')
        )

        machine.save()

        return jsonify({'status': 'machine updated'}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/machines', methods=['GET'])
@jwt_required()
def get_all_machines():
    """Get all registered machines"""
    try:
        machines = Machine.get_all()
        return jsonify(machines), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/machine/<machine_id>', methods=['GET'])
@jwt_required()
def get_machine(machine_id):
    """Get machine information"""
    try:
        machine = Machine.get_by_id(machine_id)
        if not machine:
            return jsonify({'error': 'Machine not found'}), 404
        return jsonify(machine), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/logs/<machine_id>', methods=['GET'])
@jwt_required()
def get_machine_logs(machine_id):
    """Get logs for a specific machine"""
    try:
        limit = request.args.get('limit', 100, type=int)
        logs = SystemLog.get_by_machine(machine_id, limit)
        return jsonify({
            'machine_id': machine_id,
            'limit': limit,
            'logs': logs
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/logs', methods=['GET'])
@jwt_required()
def get_all_logs():
    """Get recent logs from all machines"""
    try:
        limit = request.args.get('limit', 100, type=int)
        logs = SystemLog.get_recent(limit)
        return jsonify({
            'limit': limit,
            'logs': logs
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)