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

from services.ai_analyzer import generate_keywords
from services.crawler import crawl_homepage
from services.keyword_grouper import group_keywords
from services.naver_api import get_keyword_stats

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
    anthropic_api_key: Optional[str] = None


# 마지막 결과 캐시 (단일 사용자 기준)
_last_result: Optional[dict] = None


@app.post("/api/extract")
async def extract_keywords(req: ExtractRequest):
    global _last_result

    # 1. 홈페이지 크롤링
    homepage_data = await crawl_homepage(req.homepage_url)
    if homepage_data.get("error"):
        # 크롤링 실패해도 AI 분석은 진행
        homepage_data["body_text"] = f"메인 키워드: {req.main_keyword}"

    # 2. AI 키워드 생성
    try:
        anthropic_key = req.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
        keywords = await generate_keywords(homepage_data, req.main_keyword, anthropic_key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 키워드 생성 실패: {str(e)}")

    if not keywords:
        raise HTTPException(status_code=500, detail="키워드를 추출할 수 없습니다.")

    # 3. 네이버 API 키워드 통계 조회
    customer_id = req.naver_customer_id or os.getenv("NAVER_CUSTOMER_ID", "")
    access_license = req.naver_access_license or os.getenv("NAVER_ACCESS_LICENSE", "")
    secret_key = req.naver_secret_key or os.getenv("NAVER_SECRET_KEY", "")

    keyword_stats = {}
    naver_api_used = False

    if customer_id and access_license and secret_key:
        try:
            keyword_stats = await get_keyword_stats(
                keywords, customer_id, access_license, secret_key
            )
            naver_api_used = True
        except Exception:
            # API 실패 시 빈 통계로 계속
            pass

    # 4. 키워드 그룹핑
    groups = group_keywords(keywords, keyword_stats, req.main_keyword, req.brand_name or "")

    result = {
        "total_keywords": len(keywords),
        "naver_api_used": naver_api_used,
        "crawl_success": homepage_data.get("error") is None,
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
        headers={
            "Content-Disposition": "attachment; filename=naver_keywords.csv"
        },
    )


app.mount("/", StaticFiles(directory="static", html=True), name="static")
