import csv
import io
import os
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from services.crawler import crawl_homepage
from services.keyword_grouper import group_keywords
from services.naver_api import fetch_related_keywords

load_dotenv()

app = FastAPI(title="네이버 파워링크 키워드 추출기")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ExtractRequest(BaseModel):
    homepage_url: str
    main_keyword: str
    brand_name: Optional[str] = ""
    naver_customer_id: Optional[str] = None
    naver_access_license: Optional[str] = None
    naver_secret_key: Optional[str] = None


_last_result: Optional[dict] = None


@app.post("/api/extract")
async def extract_keywords(req: ExtractRequest):
    global _last_result

    customer_id = req.naver_customer_id or os.getenv("NAVER_CUSTOMER_ID", "")
    access_license = req.naver_access_license or os.getenv("NAVER_ACCESS_LICENSE", "")
    secret_key = req.naver_secret_key or os.getenv("NAVER_SECRET_KEY", "")

    if not (customer_id and access_license and secret_key):
        raise HTTPException(status_code=400, detail="네이버 검색광고 API 키를 입력하세요.")

    # 1. 홈페이지 크롤링으로 추가 힌트 키워드 추출
    hint_keywords = [req.main_keyword]
    crawl_success = False

    homepage_data = await crawl_homepage(req.homepage_url)
    if not homepage_data.get("error"):
        crawl_success = True
        # 헤딩에서 짧은 키워드 추출해 힌트로 활용
        for heading in homepage_data.get("headings", [])[:5]:
            if 2 <= len(heading) <= 15:
                hint_keywords.append(heading)

    # 중복 제거, 최대 10개 힌트
    seen = set()
    unique_hints = []
    for kw in hint_keywords:
        if kw not in seen:
            seen.add(kw)
            unique_hints.append(kw)
        if len(unique_hints) >= 10:
            break

    # 2. 네이버 API로 연관 키워드 + 통계 한번에 조회
    try:
        keyword_stats = await fetch_related_keywords(
            unique_hints, customer_id, access_license, secret_key
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"네이버 API 조회 실패: {str(e)}")

    if not keyword_stats:
        raise HTTPException(status_code=500, detail="키워드를 조회할 수 없습니다. API 키를 확인하세요.")

    keywords = list(keyword_stats.keys())

    # 3. 키워드 그룹핑
    groups = group_keywords(keywords, keyword_stats, req.main_keyword, req.brand_name or "")

    result = {
        "total_keywords": len(keywords),
        "naver_api_used": True,
        "crawl_success": crawl_success,
        "site_title": homepage_data.get("title", ""),
        "groups": groups,
    }

    _last_result = result
    return result


@app.get("/api/download-csv")
async def download_csv():
    if not _last_result:
        raise HTTPException(status_code=404, detail="추출된 키워드가 없습니다. 먼저 키워드를 추출하세요.")

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "그룹", "키워드", "월간검색수(PC)", "월간검색수(모바일)",
        "월간검색수(합계)", "경쟁강도", "입찰 전략",
    ])

    competition_map = {"LOW": "낮음", "MEDIUM": "중간", "HIGH": "높음", "UNKNOWN": "-"}

    for group in _last_result.get("groups", []):
        for item in group.get("keywords", []):
            writer.writerow([
                group["group_name"],
                item["keyword"],
                item["monthly_pc"],
                item["monthly_mobile"],
                item["monthly_total"],
                competition_map.get(item["competition"], "-"),
                item["bid_strategy"],
            ])

    output.seek(0)
    content = "﻿" + output.getvalue()  # BOM for Excel compatibility

    return StreamingResponse(
        io.BytesIO(content.encode("utf-8")),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=naver_keywords.csv"},
    )


app.mount("/", StaticFiles(directory="static", html=True), name="static")
