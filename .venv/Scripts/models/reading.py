# models/reading.py
from services.database import get_connection
from datetime import datetime


class SensorReading:
    def __init__(self, machine_id, temperature, humidity, temp_unit='C', status='active', machine_name=None,
                 location=None):
        self.machine_id = machine_id
        self.temperature = temperature
        self.humidity = humidity
        self.temp_unit = temp_unit
        self.status = status
        self.machine_name = machine_name
        self.location = location
        self.recorded_at = None
        self.id = None

    def save(self):
        """Save sensor reading and update machine info"""
        db = get_connection()
        cursor = db.cursor()

        try:
            # First, set all previous readings for this machine to is_latest = FALSE
            cursor.execute(
                "UPDATE sensor_readings SET is_latest = FALSE WHERE machine_id = %s",
                (self.machine_id,)
            )

            # Insert new sensor reading with is_latest = TRUE
            cursor.execute("""
                INSERT INTO sensor_readings (machine_id, temperature, humidity, temp_unit, status, is_latest)
                VALUES (%s, %s, %s, %s, %s, TRUE)
            """, (self.machine_id, self.temperature, self.humidity, self.temp_unit, self.status))

            self.id = cursor.lastrowid

            # Update or create machine record
            if self.machine_name or self.location:
                cursor.execute("""
                    INSERT INTO machines (machine_id, machine_name, location, last_seen)
                    VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                    ON DUPLICATE KEY UPDATE 
                    machine_name = COALESCE(VALUES(machine_name), machine_name),
                    location = COALESCE(VALUES(location), location),
                    last_seen = CURRENT_TIMESTAMP
                """, (self.machine_id, self.machine_name, self.location))
            else:
                # Just update last_seen
                cursor.execute("""
                    UPDATE machines SET last_seen = CURRENT_TIMESTAMP WHERE machine_id = %s
                """, (self.machine_id,))

            db.commit()
            return self.id

        except Exception as e:
            db.rollback()
            raise e
        finally:
            cursor.close()
            db.close()

    @staticmethod
    def get_by_date_range(machine_id, start_date, end_date):
        """Get readings for a specific machine between dates"""
        db = get_connection()
        cursor = db.cursor(dictionary=True)

        try:
            cursor.execute("""
                SELECT sr.*, m.machine_name, m.location
                FROM sensor_readings sr
                JOIN machines m ON sr.machine_id = m.machine_id
                WHERE sr.machine_id = %s 
                AND DATE(sr.recorded_at) >= %s 
                AND DATE(sr.recorded_at) <= %s
                ORDER BY sr.recorded_at DESC
            """, (machine_id, start_date, end_date))

            return cursor.fetchall()
        finally:
            cursor.close()
            db.close()

    @staticmethod
    def get_all_by_date_range(start_date, end_date):
        """Get readings for ALL machines between dates"""
        db = get_connection()
        cursor = db.cursor(dictionary=True)

        try:
            cursor.execute("""
                SELECT sr.*, m.machine_name, m.location
                FROM sensor_readings sr
                JOIN machines m ON sr.machine_id = m.machine_id
                WHERE DATE(sr.recorded_at) >= %s 
                AND DATE(sr.recorded_at) <= %s
                ORDER BY sr.recorded_at DESC
            """, (start_date, end_date))

            return cursor.fetchall()
        finally:
            cursor.close()
            db.close()

    @staticmethod
    def get_latest_n(machine_id, limit=10):
        """Get latest N readings for a specific machine"""
        db = get_connection()
        cursor = db.cursor(dictionary=True)

        try:
            cursor.execute("""
                SELECT sr.*, m.machine_name, m.location
                FROM sensor_readings sr
                JOIN machines m ON sr.machine_id = m.machine_id
                WHERE sr.machine_id = %s 
                ORDER BY sr.recorded_at DESC 
                LIMIT %s
            """, (machine_id, limit))

            return cursor.fetchall()
        finally:
            cursor.close()
            db.close()

    @staticmethod
    def get_all_latest_n(limit=50):
        """Get latest N readings from ALL machines"""
        db = get_connection()
        cursor = db.cursor(dictionary=True)

        try:
            cursor.execute("""
                SELECT sr.*, m.machine_name, m.location
                FROM sensor_readings sr
                JOIN machines m ON sr.machine_id = m.machine_id
                ORDER BY sr.recorded_at DESC 
                LIMIT %s
            """, (limit,))

            return cursor.fetchall()
        finally:
            cursor.close()
            db.close()

    @staticmethod
    def get_latest_readings():
        """Get the most recent reading from each machine"""
        db = get_connection()
        cursor = db.cursor(dictionary=True)

        try:
            cursor.execute("""
                SELECT sr.*, m.machine_name, m.location
                FROM sensor_readings sr
                JOIN machines m ON sr.machine_id = m.machine_id
                WHERE sr.is_latest = TRUE
                ORDER BY sr.recorded_at DESC
            """)

            return cursor.fetchall()
        finally:
            cursor.close()
            db.close()

    @staticmethod
    def get_statistics(machine_id, days=1):
        """Get temperature/humidity statistics for a machine"""
        db = get_connection()
        cursor = db.cursor(dictionary=True)

        try:
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_readings,
                    AVG(temperature) as avg_temp,
                    MIN(temperature) as min_temp,
                    MAX(temperature) as max_temp,
                    AVG(humidity) as avg_humidity,
                    MIN(humidity) as min_humidity,
                    MAX(humidity) as max_humidity,
                    MIN(recorded_at) as first_reading,
                    MAX(recorded_at) as last_reading
                FROM sensor_readings 
                WHERE machine_id = %s 
                AND recorded_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
            """, (machine_id, days))

            return cursor.fetchone()
        finally:
            cursor.close()
            db.close()


class Machine:
    def __init__(self, machine_id, machine_name=None, location=None, sensor_type='DHT22'):
        self.machine_id = machine_id
        self.machine_name = machine_name or machine_id
        self.location = location or 'Unknown'
        self.sensor_type = sensor_type
        self.created_at = None
        self.last_seen = None
        self.is_active = True

    def save(self):
        """Create or update machine record"""
        db = get_connection()
        cursor = db.cursor()

        try:
            cursor.execute("""
                INSERT INTO machines (machine_id, machine_name, location, sensor_type)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                machine_name = VALUES(machine_name),
                location = VALUES(location),
                sensor_type = VALUES(sensor_type)
            """, (self.machine_id, self.machine_name, self.location, self.sensor_type))

            db.commit()
        finally:
            cursor.close()
            db.close()

    @staticmethod
    def get_all():
        """Get all machines"""
        db = get_connection()
        cursor = db.cursor(dictionary=True)

        try:
            cursor.execute("SELECT * FROM machines ORDER BY created_at DESC")
            return cursor.fetchall()
        finally:
            cursor.close()
            db.close()

    @staticmethod
    def get_by_id(machine_id):
        """Get machine by ID"""
        db = get_connection()
        cursor = db.cursor(dictionary=True)

        try:
            cursor.execute("SELECT * FROM machines WHERE machine_id = %s", (machine_id,))
            return cursor.fetchone()
        finally:
            cursor.close()
            db.close()


class SystemLog:
    def __init__(self, machine_id, log_level='info', message='', error_code=None):
        self.machine_id = machine_id
        self.log_level = log_level
        self.message = message
        self.error_code = error_code
        self.logged_at = None
        self.id = None

    def save(self):
        """Save log entry"""
        db = get_connection()
        cursor = db.cursor()

        try:
            cursor.execute("""
                INSERT INTO system_logs (machine_id, log_level, message, error_code)
                VALUES (%s, %s, %s, %s)
            """, (self.machine_id, self.log_level, self.message, self.error_code))

            self.id = cursor.lastrowid
            db.commit()
            return self.id
        finally:
            cursor.close()
            db.close()

    @staticmethod
    def get_by_machine(machine_id, limit=100):
        """Get logs for a specific machine"""
        db = get_connection()
        cursor = db.cursor(dictionary=True)

        try:
            cursor.execute("""
                SELECT * FROM system_logs 
                WHERE machine_id = %s 
                ORDER BY logged_at DESC 
                LIMIT %s
            """, (machine_id, limit))

            return cursor.fetchall()
        finally:
            cursor.close()
            db.close()

    @staticmethod
    def get_recent(limit=100):
        """Get recent logs from all machines"""
        db = get_connection()
        cursor = db.cursor(dictionary=True)

        try:
            cursor.execute("""
                SELECT * FROM system_logs 
                ORDER BY logged_at DESC 
                LIMIT %s
            """, (limit,))

            return cursor.fetchall()
        finally:
            cursor.close()
            db.close()


# Legacy Reading class for backward compatibility
class Reading:
    def __init__(self, timestamp, temperature, humidity):
        # Map to new structure
        self.sensor_reading = SensorReading(
            machine_id='LEGACY_DEVICE',
            temperature=temperature,
            humidity=humidity
        )
        self.timestamp = timestamp

    def save(self):
        return self.sensor_reading.save()

    @staticmethod
    def get_by_date_range(start, end):
        return SensorReading.get_by_date_range('LEGACY_DEVICE', start, end)

    @staticmethod
    def get_last_n(n):
        return SensorReading.get_latest_n('LEGACY_DEVICE', n)

    @staticmethod
    def get_available_dates():
        db = get_connection()
        cursor = db.cursor()

        try:
            cursor.execute("SELECT DISTINCT DATE(recorded_at) FROM sensor_readings ORDER BY recorded_at DESC")
            results = [row[0].strftime('%Y-%m-%d') for row in cursor.fetchall()]
            return results
        finally:
            cursor.close()
            db.close()