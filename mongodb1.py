import json
import paho.mqtt.client as mqtt
import math
import re
from datetime import datetime
from pymongo import MongoClient, errors

# MQTT settings
MQTT_BROKER = "broker.mqtt.cool"
MQTT_PORT = 1883
MQTT_TOPICS = ["NMEA_Lightning_1", "NMEA_Lightning_2", "NMEA_Lightning_3"]

# MongoDB settings
MONGO_URI = "mongodb://mongo:dqYcjoKEmBwihxZeEFlHMwkNZBaGWWem@roundhouse.proxy.rlwy.net:33410"
try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client.lightning_data
    collection = db.strikes
    # Attempt to retrieve server information to verify connection
    client.server_info()
    print("Connected to MongoDB!")
except errors.ServerSelectionTimeoutError as err:
    print(f"Could not connect to MongoDB: {err}")
    exit(1)

# Define base coordinates and earth radius
base_coords = {
    1: (38.002729, 23.675644),  # Coordinates for RPI 1
    2: (38.002729, 23.675644),  # Coordinates for RPI 2
    3: (38.002729, 23.675644)   # Coordinates for RPI 3
}
earth_radius = 6371.0  # Radius of Earth in kilometers

# Storage for recent messages from each RPI
recent_strikes = {1: [], 2: [], 3: []}

# Time window in seconds to consider the strikes as the same event
TIME_WINDOW = 0.4  # seconds

# MQTT callbacks
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected to MQTT Broker!")
        for topic in MQTT_TOPICS:
            client.subscribe(topic)
            print(f"Subscribed to {topic}")
    else:
        print(f"Failed to connect, return code {rc}")

def on_message(client, userdata, msg):
    print(f"Received message on {msg.topic}")
    message = msg.payload.decode()
    print(f"Message: {message}")
    topic_index = MQTT_TOPICS.index(msg.topic) + 1

    lines = message.split('\n')
    timestamp_str = lines[0]
    try:
        timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        print(f"Timestamp: {timestamp}")
    except ValueError as e:
        print(f"Invalid timestamp format: {e}")
        return

    nmea_data = '\n'.join(lines[1:])

    # Extract all $WIMLI sentences using a regular expression
    wimli_sentences = re.findall(r'\$WIMLI,[^*]*\*\w{2}', nmea_data)
    print(f"Extracted WIMLI sentences: {wimli_sentences}")
    for sentence in wimli_sentences:
        data = parse_lightning_message(sentence)
        if data:
            data['timestamp'] = timestamp
            recent_strikes[topic_index].append(data)
            check_and_process_strikes()

def parse_lightning_message(message):
    try:
        parts = message.split(',')
        if len(parts) < 4:
            print(f"Skipping message due to insufficient parts: {message}")
            return None
        
        distance_miles = float(parts[1])
        bearing_degrees = float(parts[2].split('*')[0])
        
        return {'distance': distance_miles * 1.60934, 'bearing': bearing_degrees}
    except Exception as e:
        print(f"Error parsing message: {e}")
        return None

def check_and_process_strikes():
    global recent_strikes

    closest_set = find_closest_set(recent_strikes)
    if closest_set:
        timestamps = [data['timestamp'] for data in closest_set.values()]
        time_difference = max(timestamps) - min(timestamps)
        print(f"Chosen timestamps: {timestamps}")
        print(f"Time difference: {time_difference.total_seconds() * 1000:.2f} ms")

        coords = [convert_to_coordinates(base_coords[i][0], base_coords[i][1], data['distance'], data['bearing'])
                  for i, data in closest_set.items()]
        combined_lat, combined_lon = perform_tdoa(coords, list(closest_set.values()))
        
        strike_data = {
            'timestamps': [ts.isoformat() for ts in timestamps],
            'time_difference_ms': time_difference.total_seconds() * 1000,
            'rpi_coords': [
                {'rpi': i, 'lat': coord[0], 'lon': coord[1]}
                for i, coord in zip(range(1, 4), coords)
            ],
            'combined_coords': {'lat': combined_lat, 'lon': combined_lon}
        }
        
        print(f"Inserting strike data into MongoDB: {strike_data}")
        try:
            collection.insert_one(strike_data)
            print("Data successfully inserted into MongoDB.")
        except errors.PyMongoError as e:
            print(f"Error inserting data into MongoDB: {e}")

        for i in closest_set.keys():
            recent_strikes[i].remove(closest_set[i])

def find_closest_set(strikes):
    if all(strikes.values()):
        possible_sets = []
        for strike1 in strikes[1]:
            for strike2 in strikes[2]:
                for strike3 in strikes[3]:
                    possible_sets.append((strike1, strike2, strike3))

        closest_set = min(possible_sets, key=lambda x: max(s['timestamp'] for s in x) - min(s['timestamp'] for s in x))
        time_difference = (max(s['timestamp'] for s in closest_set) - min(s['timestamp'] for s in closest_set)).total_seconds()

        if time_difference <= TIME_WINDOW:
            return {1: closest_set[0], 2: closest_set[1], 3: closest_set[2]}
    return None

def convert_to_coordinates(lat, lon, distance, bearing):
    bearing_rad = math.radians(bearing)
    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)
    new_lat_rad = math.asin(math.sin(lat_rad) * math.cos(distance / earth_radius) +
                            math.cos(lat_rad) * math.sin(distance / earth_radius) * math.cos(bearing_rad))
    new_lon_rad = lon_rad + math.atan2(math.sin(bearing_rad) * math.sin(distance / earth_radius) * math.cos(lat_rad),
                                       math.cos(distance / earth_radius) - math.sin(lat_rad) * math.sin(new_lat_rad))
    return math.degrees(new_lat_rad), math.degrees(new_lon_rad)

def perform_tdoa(coords, data):
    if len(data) < 3:
        return None, None

    xyz_coords = [latlon_to_xyz(lat, lon) for lat, lon in coords]

    c = 300000.0
    tdoa_ab = (data[1]['distance'] / c) - (data[0]['distance'] / c)
    tdoa_ac = (data[2]['distance'] / c) - (data[0]['distance'] / c)

    x, y, z = multilateration(xyz_coords[0], xyz_coords[1], xyz_coords[2], tdoa_ab, tdoa_ac)

    lat, lon = xyz_to_latlon(x, y, z)
    return lat, lon

def latlon_to_xyz(lat, lon):
    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)
    x = earth_radius * math.cos(lat) * math.cos(lon)
    y = earth_radius * math.cos(lat) * math.sin(lon)
    z = earth_radius * math.sin(lat)
    return x, y, z

def xyz_to_latlon(x, y, z):
    lat = math.degrees(math.atan2(z, math.sqrt(x**2 + y**2)))
    lon = math.degrees(math.atan2(y, x))
    return lat, lon

def multilateration(p1, p2, p3, tdoa_ab, tdoa_ac):
    x = (p1[0] + p2[0] + p3[0]) / 3
    y = (p1[1] + p2[1] + p3[1]) / 3
    z = (p1[2] + p2[2] + p3[2]) / 3
    return x, y, z

# MQTT client setup
mqtt_client = mqtt.Client()
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
mqtt_client.loop_start()

# Run the MQTT client loop
try:
    while True:
        pass
except KeyboardInterrupt:
    print("Exiting...")
    mqtt_client.loop_stop()
    mqtt_client.disconnect()
