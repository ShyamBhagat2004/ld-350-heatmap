import asyncio
import websockets
import json
import paho.mqtt.client as mqtt
import math
import re
from collections import defaultdict
from datetime import datetime

# MQTT settings
MQTT_BROKER = "broker.mqtt.cool"
MQTT_PORT = 1883
MQTT_TOPICS = ["NMEA_Lightning_1", "NMEA_Lightning_2", "NMEA_Lightning_3"]

connected_clients = set()

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
TIME_WINDOW = 0.5  # seconds
# Time delay in seconds to accumulate data before processing
DELAY = 1.0  # seconds

# WebSocket connection handler
async def connection_handler(websocket, path):
    connected_clients.add(websocket)
    try:
        async for message in websocket:
            pass
    finally:
        connected_clients.remove(websocket)

# MQTT callbacks
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected to MQTT Broker!")
        for topic in MQTT_TOPICS:
            client.subscribe(topic)
    else:
        print(f"Failed to connect, return code {rc}")

def on_message(client, userdata, msg):
    message = msg.payload.decode()
    topic_index = MQTT_TOPICS.index(msg.topic) + 1

    lines = message.split('\n')
    timestamp_str = lines[0]
    try:
        timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
    except ValueError as e:
        print(f"Invalid timestamp format: {e}")
        return

    nmea_data = '\n'.join(lines[1:])

    # Extract all $WIMLI sentences using a regular expression
    wimli_sentences = re.findall(r'\$WIMLI,[^*]*\*\w{2}', nmea_data)
    for sentence in wimli_sentences:
        data = parse_lightning_message(sentence)
        if data:
            data['timestamp'] = timestamp
            recent_strikes[topic_index].append(data)
            # Introduce delay before processing
            asyncio.create_task(delay_and_process())

def parse_lightning_message(message):
    try:
        parts = message.split(',')
        if len(parts) < 4:
            return None
        
        distance_miles = float(parts[1])
        bearing_degrees = float(parts[2].split('*')[0])
        
        return {'distance': distance_miles * 1.60934, 'bearing': bearing_degrees}
    except Exception as e:
        return None

async def delay_and_process():
    await asyncio.sleep(DELAY)
    check_and_process_strikes()

def check_and_process_strikes():
    global recent_strikes

    # Find the closest set of timestamps from the three RPIs
    closest_set = find_closest_set(recent_strikes)
    if closest_set:
        timestamps = [data['timestamp'] for data in closest_set.values()]
        time_difference = max(timestamps) - min(timestamps)
        print(f"Chosen timestamps: {timestamps}")
        print(f"Time difference: {time_difference.total_seconds() * 1000:.2f} ms")

        coords = [convert_to_coordinates(base_coords[i][0], base_coords[i][1], data['distance'], data['bearing'])
                  for i, data in closest_set.items()]
        x, y = perform_tdoa(coords, list(closest_set.values()))
        asyncio.run(send_mqtt_message_to_clients((x, y)))

        # Clear the processed readings
        for i in closest_set.keys():
            recent_strikes[i].remove(closest_set[i])

def find_closest_set(strikes):
    if all(strikes.values()):
        # Generate all possible combinations of one reading from each RPI
        possible_sets = []
        for strike1 in strikes[1]:
            for strike2 in strikes[2]:
                for strike3 in strikes[3]:
                    possible_sets.append((strike1, strike2, strike3))

        # Find the set with the closest timestamps
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
    """
    Perform TDOA calculations to triangulate the lightning strike position.

    coords: List of tuples containing coordinates (lat, lon) of the RPIs.
    data: List of dictionaries containing distance, bearing, and timestamp information.

    Returns the estimated coordinates (lat, lon) of the lightning strike.
    """
    if len(data) < 3:
        return None, None

    # Convert lat/lon to Cartesian coordinates for each RPI
    xyz_coords = [latlon_to_xyz(lat, lon) for lat, lon in coords]

    # Calculate TDOA values (time differences)
    c = 300000.0  # Speed of light in km/s
    tdoa_ab = (data[1]['distance'] / c) - (data[0]['distance'] / c)
    tdoa_ac = (data[2]['distance'] / c) - (data[0]['distance'] / c)

    # Calculate position using multilateration
    x, y, z = multilateration(xyz_coords[0], xyz_coords[1], xyz_coords[2], tdoa_ab, tdoa_ac)

    # Convert Cartesian coordinates back to lat/lon
    lat, lon = xyz_to_latlon(x, y, z)
    return lat, lon

def latlon_to_xyz(lat, lon):
    """
    Convert latitude and longitude to Cartesian coordinates (x, y, z).
    """
    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)
    x = earth_radius * math.cos(lat_rad) * math.cos(lon_rad)
    y = earth_radius * math.cos(lat_rad) * math.sin(lon_rad)
    z = earth_radius * math.sin(lat_rad)
    return x, y, z

def xyz_to_latlon(x, y, z):
    """
    Convert Cartesian coordinates (x, y, z) to latitude and longitude.
    """
    lat = math.degrees(math.atan2(z, math.sqrt(x**2 + y**2)))
    lon = math.degrees(math.atan2(y, x))
    return lat, lon

def multilateration(p1, p2, p3, tdoa_ab, tdoa_ac):
    """
    Perform multilateration to find the source position given three reference points and TDOA values.
    """
    # Placeholder logic for multilateration, which needs to be implemented
    # This is a non-trivial mathematical problem that requires solving a system of equations
    # For simplicity, this function just returns the centroid of the reference points
    x = (p1[0] + p2[0] + p3[0]) / 3
    y = (p1[1] + p2[1] + p3[1]) / 3
    z = (p1[2] + p2[2] + p3[2]) / 3
    return x, y, z

async def send_mqtt_message_to_clients(data):
    strike_data = {'lat': data[0], 'lon': data[1]}
    if connected_clients:  # Only send if there are connected clients
        tasks = [asyncio.create_task(client.send(json.dumps(strike_data))) for client in connected_clients]
        await asyncio.wait(tasks)

# MQTT client setup
mqtt_client = mqtt.Client()
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
mqtt_client.loop_start()

# Start the WebSocket server
start_server = websockets.serve(connection_handler, "localhost", 6789)

# Run the WebSocket server
loop = asyncio.get_event_loop() 
loop.run_until_complete(start_server)
loop.run_forever()
