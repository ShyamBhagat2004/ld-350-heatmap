import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import folium
from folium.plugins import HeatMap

# Example DataFrame structure
data = {
    'time': ['2023-07-20 12:00', '2023-07-20 12:01'],
    'bearing': [66.6, 285.5],
    'distance': [306, 334],  # in miles, needs conversion to coordinates
    'corrected_distance': [254, 254]
}

df = pd.DataFrame(data)

# Function to convert distance and bearing to coordinates
def bearing_distance_to_coords(lon, lat, bearing, distance):
    # This function would need to correctly convert bearing and distance to longitude and latitude.
    # Placeholder for conversion logic
    return lon + 0.01, lat + 0.01  # simplistic placeholder for movement

# Assuming Athens' coordinates
athens_lon, athens_lat = 23.7275, 37.9838

# Apply conversion to DataFrame
df['coords'] = df.apply(lambda x: bearing_distance_to_coords(athens_lon, athens_lat, x['bearing'], x['distance']), axis=1)

# Split coordinates into separate columns
df[['longitude', 'latitude']] = pd.DataFrame(df['coords'].tolist(), index=df.index)

# Create a map centered around Athens
m = folium.Map(location=[athens_lat, athens_lon], zoom_start=10)

# Create a heatmap
HeatMap(data=df[['latitude', 'longitude']].values, radius=15).add_to(m)

# Save or show the map
m.save('heatmap.html')
