import sys
import os
import threading
import time
import webbrowser
import uvicorn


def get_base_path():
    # PyInstaller로 빌드된 exe 실행 시 임시 폴더 경로 반환
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def open_browser():
    time.sleep(2)
    webbrowser.open("http://127.0.0.1:8000")


if __name__ == "__main__":
    base = get_base_path()

    # static 폴더 경로를 환경변수로 전달
    os.environ["STATIC_DIR"] = os.path.join(base, "static")

    # .env 파일이 exe 옆에 있으면 로드
    env_path = os.path.join(os.path.dirname(sys.executable if getattr(sys, "frozen", False) else __file__), ".env")
    if os.path.exists(env_path):
        from dotenv import load_dotenv
        load_dotenv(env_path)

    print("=" * 45)
    print("  네이버 파워링크 키워드 추출기")
    print("=" * 45)
    print("  서버 시작 중...")
    print("  브라우저: http://127.0.0.1:8000")
    print("  종료: 이 창을 닫으세요")
    print("=" * 45)

    threading.Thread(target=open_browser, daemon=True).start()

    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        log_level="warning",
    )
