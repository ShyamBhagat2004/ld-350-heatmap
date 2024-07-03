import math

# Updated base coordinates for Athens, Greece
base_lat = 38.002729
base_lon = 23.675644

# Earth's radius in kilometers
earth_radius = 6371.0

def parse_nmea_message(message):
    parts = message.split(',')
    if parts[0].startswith('$WIMLI'):
        corrected_distance_miles = float(parts[1])
        bearing_degrees = float(parts[3].split('*')[0])
        return corrected_distance_miles, bearing_degrees
    return None

def convert_to_coordinates(lat, lon, distance, bearing):
    # Convert distance from miles to kilometers
    distance_km = distance * 1.60934
    
    # Convert bearing to radians
    bearing_rad = math.radians(bearing)
    
    # Latitude in radians
    lat_rad = math.radians(lat)
    
    # Longitude in radians
    lon_rad = math.radians(lon)
    
    # New latitude in radians
    new_lat_rad = math.asin(math.sin(lat_rad) * math.cos(distance_km / earth_radius) +
                            math.cos(lat_rad) * math.sin(distance_km / earth_radius) * math.cos(bearing_rad))
    
    # New longitude in radians
    new_lon_rad = lon_rad + math.atan2(math.sin(bearing_rad) * math.sin(distance_km / earth_radius) * math.cos(lat_rad),
                                       math.cos(distance_km / earth_radius) - math.sin(lat_rad) * math.sin(new_lat_rad))
    
    # Convert radians back to degrees
    new_lat = math.degrees(new_lat_rad)
    new_lon = math.degrees(new_lon_rad)
    
    return new_lat, new_lon

# Example messages from your output
messages = [
    "$WIMLI,254,306,066.6*5E",
    "$WIMLI,254,334,285.5*61",
    "$WIMLI,254,349,089.3*67",
    "$WIMLI,254,404,172.3*58",
    "$WIMLI,254,383,099.4*67"
]

# Process each message
for message in messages:
    result = parse_nmea_message(message)
    if result:
        distance, bearing = result
        new_lat, new_lon = convert_to_coordinates(base_lat, base_lon, distance, bearing)
        print(f"Original Message: {message} -> New Coordinates: Latitude {new_lat}, Longitude {new_lon}")
