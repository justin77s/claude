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


@app.get("/api/download-html")
async def download_html():
    if not _last_result:
        raise HTTPException(status_code=404, detail="추출된 키워드가 없습니다. 먼저 키워드를 추출하세요.")

    competition_map = {"LOW": "낮음", "MEDIUM": "중간", "HIGH": "높음", "UNKNOWN": "-"}
    comp_color = {"LOW": "#d4edda", "MEDIUM": "#fff3cd", "HIGH": "#f8d7da", "UNKNOWN": "#e9ecef"}
    comp_text_color = {"LOW": "#155724", "MEDIUM": "#856404", "HIGH": "#721c24", "UNKNOWN": "#666"}

    groups_html = ""
    for group in _last_result.get("groups", []):
        if not group["keywords"]:
            continue
        rows = ""
        for item in group["keywords"]:
            bg = comp_color.get(item["competition"], "#e9ecef")
            tc = comp_text_color.get(item["competition"], "#666")
            rows += f"""<tr>
              <td>{item['keyword']}</td>
              <td>{item['monthly_pc']:,}</td>
              <td>{item['monthly_mobile']:,}</td>
              <td><strong>{item['monthly_total']:,}</strong></td>
              <td><span style="background:{bg};color:{tc};padding:2px 10px;border-radius:12px;font-size:11px;font-weight:700;">{competition_map.get(item['competition'], '-')}</span></td>
              <td style="color:#03c75a;font-size:11px;font-weight:600;">{item['bid_strategy']}</td>
            </tr>"""

        groups_html += f"""
        <div class="group">
          <div class="group-title">{group['group_name']} <span class="badge">{group['total_keywords']}개</span>
            <span class="meta">평균 월간검색 {group['avg_monthly_search']:,}회</span>
          </div>
          <table>
            <thead><tr><th>키워드</th><th>월간검색(PC)</th><th>월간검색(모바일)</th><th>합계</th><th>경쟁강도</th><th>입찰 전략</th></tr></thead>
            <tbody>{rows}</tbody>
          </table>
        </div>"""

    from datetime import datetime
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    total = _last_result.get("total_keywords", 0)
    site_title = _last_result.get("site_title", "")

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>네이버 파워링크 키워드 리포트</title>
<style>
  body {{ font-family: 'Apple SD Gothic Neo', 'Noto Sans KR', sans-serif; margin: 0; background: #f5f6fa; color: #2d3436; }}
  .header {{ background: linear-gradient(135deg, #03c75a, #00a843); color: white; padding: 28px 40px; }}
  .header h1 {{ font-size: 22px; margin: 0 0 4px; }}
  .header p {{ font-size: 13px; opacity: 0.85; margin: 0; }}
  .container {{ max-width: 1000px; margin: 0 auto; padding: 28px 20px; }}
  .summary {{ display: flex; gap: 14px; margin-bottom: 28px; }}
  .summary-item {{ background: white; border-radius: 10px; padding: 16px 24px; flex: 1; border-left: 4px solid #03c75a; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
  .summary-item .num {{ font-size: 26px; font-weight: 800; color: #03c75a; }}
  .summary-item .lbl {{ font-size: 12px; color: #888; }}
  .group {{ background: white; border-radius: 12px; margin-bottom: 20px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
  .group-title {{ padding: 14px 20px; font-size: 15px; font-weight: 700; border-bottom: 1px solid #f0f0f0; }}
  .badge {{ background: #e8f5e9; color: #00a843; font-size: 12px; padding: 2px 10px; border-radius: 12px; margin-left: 8px; }}
  .meta {{ font-size: 12px; color: #888; font-weight: 400; margin-left: 12px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ background: #f8f9fa; padding: 10px 14px; text-align: left; font-weight: 700; color: #555; border-bottom: 2px solid #e9ecef; }}
  td {{ padding: 9px 14px; border-bottom: 1px solid #f5f5f5; }}
  tr:last-child td {{ border-bottom: none; }}
  .footer {{ text-align: center; font-size: 12px; color: #aaa; padding: 20px; }}
</style>
</head>
<body>
<div class="header">
  <h1>네이버 파워링크 키워드 리포트</h1>
  <p>{site_title} &nbsp;|&nbsp; 생성일시: {generated_at}</p>
</div>
<div class="container">
  <div class="summary">
    <div class="summary-item"><div class="num">{total}</div><div class="lbl">총 키워드</div></div>
    <div class="summary-item"><div class="num">{len([g for g in _last_result.get('groups', []) if g['total_keywords'] > 0])}</div><div class="lbl">키워드 그룹</div></div>
  </div>
  {groups_html}
</div>
<div class="footer">네이버 파워링크 키워드 추출기 &nbsp;|&nbsp; {generated_at}</div>
</body>
</html>"""

    return StreamingResponse(
        io.BytesIO(html.encode("utf-8")),
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=naver_keywords.html"},
    )


app.mount("/", StaticFiles(directory="static", html=True), name="static")
