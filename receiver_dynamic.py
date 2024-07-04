from flask import Flask, render_template
from flask_socketio import SocketIO
import folium
import paho.mqtt.client as mqtt
import math
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app)

base_lat = 38.002729
base_lon = 23.675644
earth_radius = 6371.0

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected to MQTT Broker!")
        client.subscribe("NMEA_Lightning")
    else:
        print(f"Failed to connect, return code {rc}")

def on_message(client, userdata, msg):
    message = msg.payload.decode()
    print(f"Received MQTT message: {message}")  # Debug print
    if message.startswith("$WIMLI,"):
        data = parse_lightning_message(message)
        if data:
            print(f"Parsed strike data: {data}")  # Debug print
            # Emit from within the Flask application context
            with app.app_context():
                socketio.emit('new_strike', {'lat': data[0], 'lon': data[1]}, namespace='/test')
                print("Emitted new_strike event")  # Debug print

def parse_lightning_message(message):
    try:
        parts = message.split(',')
        corrected_distance_miles = float(parts[1])
        bearing_degrees = float(parts[2].split('*')[0])
        print(message)
        return convert_to_coordinates(base_lat, base_lon, corrected_distance_miles, bearing_degrees)
        
    except Exception as e:
        print(f"Error parsing message: {e}")
        return None

def convert_to_coordinates(lat, lon, distance, bearing):
    distance_km = distance * 1.60934
    bearing_rad = math.radians(bearing)
    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)
    new_lat_rad = math.asin(math.sin(lat_rad) * math.cos(distance_km / earth_radius) +
                            math.cos(lat_rad) * math.sin(distance_km / earth_radius) * math.cos(bearing_rad))
    new_lon_rad = lon_rad + math.atan2(math.sin(bearing_rad) * math.sin(distance_km / earth_radius) * math.cos(lat_rad),
                                       math.cos(distance_km / earth_radius) - math.sin(lat_rad) * math.sin(new_lat_rad))
    return math.degrees(new_lat_rad), math.degrees(new_lon_rad)

@app.route('/')
def index():
    # Start the Flask-SocketIO map
    return render_template('index.html')

@app.route('/emit_test')
def emit_test():
    test_data = {'lat': base_lat, 'lon': base_lon}
    with app.app_context():
        socketio.emit('new_strike', test_data, namespace='/test')
    return "Test event emitted!"

@socketio.on('connect', namespace='/test')
def test_connect(sid, environ):
    print('Client connected, SID:', sid)

@socketio.on('disconnect', namespace='/test')
def test_disconnect(sid):
    print('Client disconnected, SID:', sid)

if __name__ == '__main__':
    mqtt_client = mqtt.Client()
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    mqtt_client.connect("broker.mqtt.cool", 1883, 60)
    mqtt_client.loop_start()
    socketio.run(app, debug=True, host='0.0.0.0', port=5001)
