@echo off
chcp 65001 > nul
title 네이버 파워링크 키워드 추출기

echo [1/3] Python 환경 확인 중...
python --version > nul 2>&1
if errorlevel 1 (
    echo [오류] Python이 설치되지 않았습니다.
    echo https://www.python.org/downloads/ 에서 설치 후 다시 시도하세요.
    pause
    exit /b 1
)

echo [2/3] 패키지 설치 확인 중...
pip install -r requirements.txt -q

echo [3/3] 서버 시작 중...
echo.
echo 브라우저에서 http://localhost:8000 으로 접속하세요.
echo 종료하려면 이 창에서 Ctrl+C 를 누르세요.
echo.

start "" http://localhost:8000
uvicorn main:app --host 127.0.0.1 --port 8000

pause
