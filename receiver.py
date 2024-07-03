import paho.mqtt.client as mqtt
import math
import time

# Base coordinates for Athens, Greece
base_lat = 38.002729
base_lon = 23.675644

# Earth's radius in kilometers
earth_radius = 6371.0

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected to MQTT Broker!")
        client.subscribe("NMEA_Lightning")
    else:
        print(f"Failed to connect, return code {rc}\n")

def on_message(client, userdata, message):
    msg = message.payload.decode()
    #print("Received message:", msg)
    process_message(msg)

def process_message(message):
    if message.startswith("$WIMLI,"):
        data = parse_lightning_message(message)
        if data:
            new_lat, new_lon = convert_to_coordinates(base_lat, base_lon, *data)
            print(f"Lightning strike data -> New Coordinates: Latitude {new_lat}, Longitude {new_lon}")
    elif message.startswith("$WIMLN*"):
        pass
        #print("Noise message detected, ignoring.")
    else:
        pass
        #print("Unrecognized message type:", message)

def parse_lightning_message(message):
    parts = message.split(',')
    try:
        corrected_distance_miles = float(parts[1])
        bearing_degrees = float(parts[3].split('*')[0])
        return corrected_distance_miles, bearing_degrees
    except Exception as e:
        print("Error parsing message:", e)
        return None

def convert_to_coordinates(lat, lon, distance, bearing):
    distance_km = distance * 1.60934  # Convert distance from miles to kilometers
    bearing_rad = math.radians(bearing)  # Convert bearing to radians

    lat_rad = math.radians(lat)  # Convert latitude to radians
    lon_rad = math.radians(lon)  # Convert longitude to radians

    new_lat_rad = math.asin(math.sin(lat_rad) * math.cos(distance_km / earth_radius) +
                            math.cos(lat_rad) * math.sin(distance_km / earth_radius) * math.cos(bearing_rad))

    new_lon_rad = lon_rad + math.atan2(math.sin(bearing_rad) * math.sin(distance_km / earth_radius) * math.cos(lat_rad),
                                       math.cos(distance_km / earth_radius) - math.sin(lat_rad) * math.sin(new_lat_rad))

    new_lat = math.degrees(new_lat_rad)  # Convert radians back to degrees
    new_lon = math.degrees(new_lon_rad)

    return new_lat, new_lon

broker_address = "broker.mqtt.cool"
port = 1883
client_id = f"python-mqtt-receiver-{int(time.time())}"

# Updated client creation for Paho MQTT v2.0 compatibility
client = mqtt.Client(client_id=client_id, callback_api_version=mqtt.CallbackAPIVersion.VERSION1)
client.on_connect = on_connect
client.on_message = on_message

try:
    client.connect(broker_address, port, keepalive=60)
    client.loop_start()  # Start the network loop in a separate thread for handling MQTT communication.
except Exception as e:
    print(f"Could not connect to MQTT broker: {e}")
    sys.exit(1)

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("Script interrupted by user")
finally:
    client.loop_stop()  # Stop the MQTT client's network loop.
    client.disconnect()  # Disconnect from the MQTT broker.
    print("MQTT client disconnected.")
