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
    if "$GPGGA" in message:
        data = parse_gps_data(message)
        if data:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(send_mqtt_message_to_clients(data))
            loop.close()

def parse_gps_data(gps_data):
    try:
        fields = gps_data.split(',')
        utc_time = fields[1]
        latitude = convert_to_decimal_degrees(fields[2], fields[3])
        longitude = convert_to_decimal_degrees(fields[4], fields[5])
        return {'time': utc_time, 'lat': latitude, 'lon': longitude}
    except Exception as e:
        print(f"Error parsing GPS data: {e}")
        return None

def convert_to_decimal_degrees(coord, direction):
    degrees = int(coord[:len(coord)-7])
    minutes = float(coord[len(coord)-7:])
    decimal_degrees = degrees + (minutes / 60)
    if direction in ['S', 'W']:
        decimal_degrees *= -1
    return decimal_degrees

async def send_mqtt_message_to_clients(data):
    if connected_clients:  # Only send if there are connected clients
        tasks = [asyncio.create_task(client.send(json.dumps(data))) for client in connected_clients]
        await asyncio.wait(tasks)
        print(f"Sent: {data}")  # Debug print

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
