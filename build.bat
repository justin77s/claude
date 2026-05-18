@echo off
chcp 65001 > nul
title 키워드 추출기 빌드

echo [1/3] PyInstaller 설치 확인 중...
pip install pyinstaller -q
pip install -r requirements.txt -q

echo [2/3] exe 빌드 중... (1~3분 소요)
pyinstaller --noconfirm --onefile --console ^
  --name "네이버키워드추출기" ^
  --add-data "static;static" ^
  --add-data "services;services" ^
  --hidden-import "uvicorn.logging" ^
  --hidden-import "uvicorn.loops.auto" ^
  --hidden-import "uvicorn.protocols.http.auto" ^
  --hidden-import "uvicorn.lifespan.on" ^
  --hidden-import "anyio._backends._asyncio" ^
  --hidden-import "httpx" ^
  --hidden-import "bs4" ^
  launcher.py

echo [3/3] 완료!
echo.
echo dist 폴더 안의 "네이버키워드추출기.exe" 를 사용하세요.
echo .env 파일을 exe 파일 옆에 같이 놓으면 API 키 자동 로드됩니다.
echo.
pause
