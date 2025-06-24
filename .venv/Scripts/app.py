# main app file

from flask import Flask, request, jsonify, render_template
from config import API_TOKEN
from models.reading import Reading

app = Flask(__name__)

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
def get_readings():
    start = request.args.get('start')
    end = request.args.get('end')

    if not start or not end:
        return jsonify({'error': 'Start and end parameters are required'}), 400

    readings = Reading.get_by_date_range(start, end)
    return jsonify(readings)

@app.route('/v1/data/latest', methods=['GET'])
def get_latest_reading():
    readings = Reading.get_last_n(1)
    return jsonify(readings[0] if readings else {})

@app.route('/v1/data/last-n/<int:n>', methods=['GET'])
def get_last_n(n):
    readings = Reading.get_last_n(n)
    return jsonify(readings)

@app.route('/v1/data/dates', methods=['GET'])
def get_dates():
    dates = Reading.get_available_dates()
    return jsonify(dates)

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'API running'})


if __name__ == '__main__':
    app.run()
