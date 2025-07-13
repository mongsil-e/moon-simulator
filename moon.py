
import datetime
from skyfield import almanac
import skyfield.api as sf
from skyfield.api import load, N, E, wgs84
import pytz
from datetime import timedelta
import math
import folium

def calculate_moonrise(ts, topos, date, planets, moon):
    t0 = ts.utc(date.year, date.month, date.day)
    t1 = ts.utc(date.year, date.month, date.day + 1)
    
    t, y = almanac.find_discrete(t0, t1, almanac.risings_and_settings(planets, moon, topos))
    
    for ti, yi in zip(t, y):
        if yi:  # True for rising
            return ti, None  # azimuth는 main에서 계산
    return None, None

def calculate_destination(lat, lon, bearing, distance_km=5):
    """
    Calculate a destination point given a starting point, bearing, and distance.
    """
    R = 6371  # Earth radius in kilometers
    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)
    bearing_rad = math.radians(bearing)

    dest_lat_rad = math.asin(math.sin(lat_rad) * math.cos(distance_km / R) +
                             math.cos(lat_rad) * math.sin(distance_km / R) * math.cos(bearing_rad))
    dest_lon_rad = lon_rad + math.atan2(math.sin(bearing_rad) * math.sin(distance_km / R) * math.cos(lat_rad),
                                     math.cos(distance_km / R) - math.sin(lat_rad) * math.sin(dest_lat_rad))

    return math.degrees(dest_lat_rad), math.degrees(dest_lon_rad)

def create_moonrise_map(location, moonrise_time_kst, moonrise_azimuth, hourly_positions):
    lat, lon = location
    m = folium.Map(location=[lat, lon], zoom_start=12)

    popup_text = f"""
    <b>Moonrise Info</b><br>
    Initial Rise Time (KST): {moonrise_time_kst}<br>
    Initial Azimuth: {moonrise_azimuth:.2f}°
    """
    folium.Marker(
        location=[lat, lon],
        popup=folium.Popup(popup_text, max_width=300),
        tooltip="Your Location"
    ).add_to(m)

    # Loop through hourly positions to draw lines
    for i, pos in enumerate(hourly_positions):
        time = pos['time']
        azimuth = pos['azimuth']
        altitude = pos['altitude']

        # Calculate destination point for the arrow
        dest_lat, dest_lon = calculate_destination(lat, lon, azimuth)

        # Use a different color for the first line (moonrise)
        line_color = "red" if i == 0 else "orange"
        line_weight = 5 if i == 0 else 3
        
        # Add a PolyLine for each hour with a detailed tooltip
        folium.PolyLine(
            locations=[(lat, lon), (dest_lat, dest_lon)],
            color=line_color,
            weight=line_weight,
            tooltip=f"<b>Time: {time} (KST)</b><br>Azimuth: {azimuth:.2f}°<br>Altitude: {altitude:.2f}°"
        ).add_to(m)

    map_file = "moonrise_map.html"
    m.save(map_file)
    print(f"\nInteractive map saved to {map_file}")
    print(f"Open this file in a web browser to see the moon's path on a map.")

def main():
    print("달 뜨는 위치 시뮬레이터")
    lat = float(input("위도 (예: 37.5665): "))
    lon = float(input("경도 (예: 126.9780): "))
    date_str = input("날짜 (YYYY-MM-DD): ")
    date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    
    location = (lat, lon)
    planets = load('de421.bsp')
    earth = planets['earth']
    moon = planets['moon']
    ts = load.timescale()
    topos = wgs84.latlon(lat * N, lon * E)
    observer = earth + topos
    
    ti, _ = calculate_moonrise(ts, topos, date, planets, moon)
    
    if ti is not None:
        kst = pytz.timezone('Asia/Seoul')
        kst_time_str = ti.astimezone(kst).strftime('%Y-%m-%d %H:%M:%S')
        alt, az, dist = observer.at(ti).observe(moon).apparent().altaz()
        az_degrees = az.degrees
        print(f"{date}에 {location}에서 달이 뜨는 시간 (KST): {kst_time_str}")
        print(f"달이 뜨는 방위각: {az_degrees:.2f} 도")
        
        print("\n달 뜨기 후 8시간 동안 1시간 단위 위치:")
        hourly_positions = []
        for i in range(9):  # 0 to 8 hours
            delta_hours = i / 24.0  # float
            new_tt = ti.tt + delta_hours  # float addition
            new_t = ts.tt_jd(new_tt)  # type: ignore[attr-defined]
            alt, az, dist = observer.at(new_t).observe(moon).apparent().altaz()
            new_kst = new_t.astimezone(kst).strftime('%H:%M')  # type: ignore[attr-defined]
            print(f"{new_kst} (KST): 방위각 {az.degrees:.2f} 도, 고도 {alt.degrees:.2f} 도")
            hourly_positions.append({'time': new_kst, 'azimuth': az.degrees, 'altitude': alt.degrees})
        
        create_moonrise_map(location, kst_time_str, az_degrees, hourly_positions)
    else:
        print("해당 날짜에 달 뜨는 정보가 없습니다.")

if __name__ == "__main__":
    main()

