#to read database

from services.database import get_connection

class Reading:
    def __init__(self, timestamp, temperature, humidity):
        self.timestamp = timestamp
        self.temperature = temperature
        self.humidity = humidity

    def save(self):
        db = get_connection()
        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO readings (timestamp, temperature, humidity) VALUES (%s, %s, %s)",
            (self.timestamp, self.temperature, self.humidity)
        )
        db.commit()
        cursor.close()
        db.close()

    @staticmethod
    def get_by_date_range(start, end):
        db = get_connection()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM readings WHERE timestamp BETWEEN %s AND %s ORDER BY timestamp",
            (start, end)
        )
        results = cursor.fetchall()
        cursor.close()
        db.close()
        return results

@staticmethod
def get_last_n(n):
    db = get_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute(
        "SELECT * FROM readings ORDER BY timestamp DESC LIMIT %s",
        (n,)
    )
    results = cursor.fetchall()
    cursor.close()
    db.close()
    return list(reversed(results))  # to return oldest → newest

@staticmethod
def get_available_dates():
    db = get_connection()
    cursor = db.cursor()
    cursor.execute("SELECT DISTINCT DATE(timestamp) FROM readings ORDER BY timestamp DESC")
    results = [row[0].strftime('%Y-%m-%d') for row in cursor.fetchall()]
    cursor.close()
    db.close()
    return results
