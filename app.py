import datetime
import math
import pytz
import skyfield.api as sf
from flask import Flask, jsonify, render_template, request
from skyfield import almanac
from skyfield.api import E, N, load, wgs84

app = Flask(__name__)

# Skyfield 객체 전역 로드
planets = load('de421.bsp')
earth = planets['earth']
moon = planets['moon']
ts = load.timescale()

def calculate_moonrise(ts, topos, date, planets, moon):
    t0 = ts.utc(date.year, date.month, date.day)
    t1 = ts.utc(date.year, date.month, date.day + 1)
    
    t, y = almanac.find_discrete(t0, t1, almanac.risings_and_settings(planets, moon, topos))
    
    for ti, yi in zip(t, y):
        if yi:  # True for rising
            return ti
    return None

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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/calculate', methods=['POST'])
def calculate():
    data = request.get_json()
    try:
        lat = float(data['lat'])
        lon = float(data['lon'])
        date_str = data['date']
        date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except (ValueError, KeyError):
        return jsonify({'error': 'Invalid input data'}), 400

    topos = wgs84.latlon(lat * N, lon * E)
    observer = earth + topos
    
    ti = calculate_moonrise(ts, topos, date, planets, moon)
    
    if ti is not None:
        kst = pytz.timezone('Asia/Seoul')
        kst_time_str = ti.astimezone(kst).strftime('%Y-%m-%d %H:%M:%S')
        
        alt, az, dist = observer.at(ti).observe(moon).apparent().altaz()
        az_degrees = az.degrees
        
        hourly_positions = []
        for i in range(9):  # 0 to 8 hours
            delta_hours = i / 24.0
            new_tt = ti.tt + delta_hours
            new_t = ts.tt_jd(new_tt)
            
            alt, az, dist = observer.at(new_t).observe(moon).apparent().altaz()
            dest_lat, dest_lon = calculate_destination(lat, lon, az.degrees)
            
            # astimezone() returns a datetime object, so we can call strftime on it.
            # The linter seems to be mistaken about the return type.
            new_kst = new_t.astimezone(kst).strftime('%H:%M')
            hourly_positions.append({
                'time': new_kst,
                'azimuth': az.degrees,
                'altitude': alt.degrees,
                'dest_lat': dest_lat,
                'dest_lon': dest_lon
            })
        
        return jsonify({
            'location': {'lat': lat, 'lon': lon},
            'moonrise_time_kst': kst_time_str,
            'moonrise_azimuth': az_degrees,
            'hourly_positions': hourly_positions
        })
    else:
        return jsonify({'error': '해당 날짜에 달 뜨는 정보가 없습니다.'})

if __name__ == "__main__":
    app.run(debug=True) 