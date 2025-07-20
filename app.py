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

def find_moon_events(ts, topos, date, planets, moon):
    """주어진 날짜의 월출 및 월몰 시간을 찾습니다."""
    t0 = ts.utc(date.year, date.month, date.day)
    t1 = ts.utc(date.year, date.month, date.day + 1)
    t, y = almanac.find_discrete(t0, t1, almanac.risings_and_settings(planets, moon, topos))
    
    events = {'rise': None, 'set': None}
    # y=True (1) is rise, y=False (0) is set.
    for ti, yi in zip(t,y):
        if yi and events['rise'] is None:
            events['rise'] = ti
        elif not yi and events['set'] is None:
            events['set'] = ti
        if events['rise'] is not None and events['set'] is not None:
            break
    return events

def get_moon_phase_kr(angle_degrees):
    """달의 위상 각도를 한국어 이름으로 변환합니다."""
    if angle_degrees < 5: return "삭 (New Moon)"
    if angle_degrees < 85: return "초승달 (Waxing Crescent)"
    if angle_degrees <= 95: return "상현 (First Quarter)"
    if angle_degrees < 175: return "차가는 달 (Waxing Gibbous)"
    if angle_degrees <= 185: return "망 (Full Moon)"
    if angle_degrees < 265: return "기우는 달 (Waning Gibbous)"
    if angle_degrees <= 275: return "하현 (Last Quarter)"
    return "그믐달 (Waning Crescent)"

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
        elevation = float(data.get('elevation', 0))
        date_str = data['date']
        date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except (ValueError, KeyError):
        return jsonify({'error': 'Invalid input data'}), 400

    topos = wgs84.latlon(lat * N, lon * E, elevation_m=elevation)
    observer = earth + topos
    
    kst = pytz.timezone('Asia/Seoul')
    events = find_moon_events(ts, topos, date, planets, moon)
    ti_rise = events.get('rise')
    ti_set = events.get('set')

    if ti_rise is None and ti_set is None:
        return jsonify({'error': f'{date_str}에 달의 출몰 정보가 없습니다.'})

    response = {
        'location': {'lat': lat, 'lon': lon},
        'date': date_str,
        'moonrise_time_kst': None,
        'moonrise_azimuth': None,
        'moonset_time_kst': None,
        'moonset_azimuth': None,
        'moon_phase': None,
        'hourly_positions': None
    }
    
    # 달 위상은 월출 또는 월몰 시간 중 빠른 시간을 기준으로 계산
    ref_time = ti_rise if ti_rise is not None and (ti_set is None or ti_rise.tt < ti_set.tt) else ti_set
    if ref_time is not None:
        illumination = almanac.fraction_illuminated(planets, 'moon', ref_time)
        phase_angle = almanac.moon_phase(planets, ref_time).degrees
        response['moon_phase'] = {
            'illumination': illumination * 100,
            'name_korean': get_moon_phase_kr(phase_angle)
        }

    if ti_rise is not None:
        response['moonrise_time_kst'] = ti_rise.astimezone(kst).strftime('%Y-%m-%d %H:%M:%S')
        alt, az, dist = observer.at(ti_rise).observe(moon).apparent().altaz()
        response['moonrise_azimuth'] = az.degrees
        
        hourly_positions = []
        for i in range(9):  # 월출 후 8시간 동안의 위치
            new_t = ts.tt_jd(ti_rise.tt + i / 24.0)
            alt, az, dist = observer.at(new_t).observe(moon).apparent().altaz()
            dest_lat, dest_lon = calculate_destination(lat, lon, az.degrees)
            
            new_kst = new_t.astimezone(kst).strftime('%H:%M')
            hourly_positions.append({
                'time': new_kst,
                'azimuth': az.degrees,
                'altitude': alt.degrees,
                'dest_lat': dest_lat,
                'dest_lon': dest_lon
            })
        response['hourly_positions'] = hourly_positions

    if ti_set is not None:
        response['moonset_time_kst'] = ti_set.astimezone(kst).strftime('%Y-%m-%d %H:%M:%S')
        alt, az, dist = observer.at(ti_set).observe(moon).apparent().altaz()
        response['moonset_azimuth'] = az.degrees

    return jsonify(response)


if __name__ == "__main__":
    app.run(debug=True) 