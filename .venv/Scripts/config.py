# config.py
from datetime import timedelta

DB_CONFIG = {
    'host': 'localhost',  # Update with your MySQL host
    'user': 'root',       # Update with your MySQL username
    'password': 'Br0ssard',  # Update with your MySQL password
    'database': 'iot_db'     # Update with your database name
}

# JWT Configuration
JWT_SECRET_KEY = 'your-super-secret-jwt-key-change-this-in-production'
JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)  # Token expires in 24 hours

# Legacy API token (keep for backward compatibility)
API_TOKEN = 'your-secure-token'