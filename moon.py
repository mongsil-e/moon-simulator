
import datetime
from skyfield import almanac
import skyfield.api as sf
from skyfield.api import load, N, E, wgs84
import pytz
from datetime import timedelta

def calculate_moonrise(ts, topos, date, planets, moon):
    t0 = ts.utc(date.year, date.month, date.day)
    t1 = ts.utc(date.year, date.month, date.day + 1)
    
    t, y = almanac.find_discrete(t0, t1, almanac.risings_and_settings(planets, moon, topos))
    
    for ti, yi in zip(t, y):
        if yi:  # True for rising
            return ti, None  # azimuth는 main에서 계산
    return None, None

def main():
    print("달 뜨는 위치 시뮬레이터")
    lat = float(input("위도 (예: 37.5665 for 서울): "))
    lon = float(input("경도 (예: 126.9780 for 서울): "))
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
        kst_time = ti.astimezone(kst).strftime('%Y-%m-%d %H:%M:%S')
        alt, az, dist = observer.at(ti).observe(moon).apparent().altaz()
        print(f"{date}에 {location}에서 달이 뜨는 시간 (KST): {kst_time}")
        print(f"달이 뜨는 방위각: {az.degrees:.2f} 도")
        
        print("\n달 뜨기 후 8시간 동안 1시간 단위 위치:")
        for i in range(9):  # 0 to 8 hours
            delta_hours = i / 24.0  # float
            new_tt = float(ti.tt + delta_hours)  # 명시적 float 변환
            new_t = ts.tt_jd(new_tt)
            alt, az, dist = observer.at(new_t).observe(moon).apparent().altaz()
            new_kst = new_t.astimezone(kst).strftime('%H:%M')
            print(f"{new_kst} (KST): 방위각 {az.degrees:.2f} 도, 고도 {alt.degrees:.2f} 도")
    else:
        print("해당 날짜에 달 뜨는 정보가 없습니다.")

if __name__ == "__main__":
    main()

