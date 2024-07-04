import asyncio
import websockets
import json
import paho.mqtt.client as mqtt
import math

# MQTT settings
MQTT_BROKER = "broker.mqtt.cool"
MQTT_PORT = 1883
MQTT_TOPIC = "NMEA_Lightning"

connected_clients = set()

# Define base coordinates and earth radius
base_lat = 38.002729
base_lon = 23.675644
earth_radius = 6371.0

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
        client.subscribe(MQTT_TOPIC)
    else:
        print(f"Failed to connect, return code {rc}")

def on_message(client, userdata, msg):
    message = msg.payload.decode()
    print(f"Received MQTT message: {message}")  # Debug print
    if message.startswith("$WIMLI,"):
        data = parse_lightning_message(message)
        if data:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(send_mqtt_message_to_clients(data))
            loop.close()

def parse_lightning_message(message):
    try:
        parts = message.split(',')
        distance_miles = float(parts[1])
        bearing_degrees = float(parts[2].split('*')[0])
        print(message)
        return convert_to_coordinates(base_lat, base_lon, distance_miles, bearing_degrees)
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

async def send_mqtt_message_to_clients(data):
    strike_data = {'lat': data[0], 'lon': data[1]}
    if connected_clients:  # Only send if there are connected clients
        await asyncio.wait([client.send(json.dumps(strike_data)) for client in connected_clients])
        print(f"Sent: {strike_data}")  # Debug print

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
