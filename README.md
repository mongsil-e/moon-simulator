# Moon Rise Simulator

이 프로그램은 사용자가 지정한 장소(위도, 경도)와 날짜에 달이 뜨는 시간과 방위각을 계산합니다.

## 설치
'git clone https://github.com/mongsil-e/moon-simulator.git'


1. Python 3.x 설치.
2. `pip install -r requirements.txt` 명령어 실행

## 사용법
1. `python app.py` 실행.
2. https://127.0.0.1:5000에 실행됩니다.
3. 위도, 경도, 날짜를 순서대로 입력.
   

## 유효기간
- 2050년까지 유효합니다.
- de421.bsp 파일의 유효기간이 2050년 까지라네요
  
### de421.bsp 파일은 "행성 궤도력 데이터 파일"입니다.
- 제작: NASA의 제트추진연구소(JPL)에서 만듭니다.
- 역할: 특정 기간(DE421의 경우 1900년~2050년) 동안의 태양, 지구, 달, 행성들의 정밀한 3차원 위치와 속도 정보를 담고 있는 일종의 데이터베이스입니다.
- 사용: skyfield 라이브러리는 이 de421.bsp 파일을 읽어서 "2025년 8월 11일에 달이 정확히 어디에 있을까?"와 같은 천문학적 계산을 수행합니다. 즉, 우리 시뮬레이터가 정확한 달의 위치를 계산할 수 있도록 하는 핵심 데이터 소스입니다.
- .bsp는 Binary SPK(Spacecraft and Planet Kernel)의 약자입니다.


