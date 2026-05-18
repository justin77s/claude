import asyncio
import base64
import hashlib
import hmac
import time
from typing import Optional

import httpx


BASE_URL = "https://api.naver.com"
KEYWORD_TOOL_PATH = "/keywordstool"


def _make_signature(timestamp: str, secret_key: str) -> str:
    message = f"{timestamp}.GET.{KEYWORD_TOOL_PATH}"
    hash_bytes = hmac.new(
        secret_key.encode("utf-8"),
        message.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    return base64.b64encode(hash_bytes).decode("utf-8")


async def get_keyword_stats(
    keywords: list[str],
    customer_id: str,
    access_license: str,
    secret_key: str,
) -> dict[str, dict]:
    """네이버 검색광고 API로 키워드 통계를 조회합니다."""
    results = {}

    # 5개씩 배치 처리
    batch_size = 5
    for i in range(0, len(keywords), batch_size):
        batch = keywords[i : i + batch_size]

        timestamp = str(int(time.time() * 1000))
        signature = _make_signature(timestamp, secret_key)

        headers = {
            "X-Timestamp": timestamp,
            "X-API-KEY": access_license,
            "X-Customer": customer_id,
            "X-Signature": signature,
            "Content-Type": "application/json; charset=UTF-8",
        }

        params = {
            "hintKeywords": ",".join(batch),
            "showDetail": "1",
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    BASE_URL + KEYWORD_TOOL_PATH,
                    headers=headers,
                    params=params,
                )
                response.raise_for_status()
                data = response.json()

                for item in data.get("keywordList", []):
                    kw = item.get("relKeyword", "")
                    pc = int(item.get("monthlyPcQcCnt", 0) or 0)
                    mobile = int(item.get("monthlyMobileQcCnt", 0) or 0)
                    comp = item.get("compIdx", "UNKNOWN")

                    results[kw] = {
                        "monthly_pc": pc,
                        "monthly_mobile": mobile,
                        "monthly_total": pc + mobile,
                        "competition": _normalize_competition(comp),
                    }
        except Exception:
            # API 실패 시 해당 배치 건너뜀
            for kw in batch:
                if kw not in results:
                    results[kw] = {
                        "monthly_pc": 0,
                        "monthly_mobile": 0,
                        "monthly_total": 0,
                        "competition": "UNKNOWN",
                    }

        # 배치 간 딜레이
        if i + batch_size < len(keywords):
            await asyncio.sleep(0.5)

    # API에서 반환되지 않은 키워드는 기본값 추가
    for kw in keywords:
        if kw not in results:
            results[kw] = {
                "monthly_pc": 0,
                "monthly_mobile": 0,
                "monthly_total": 0,
                "competition": "UNKNOWN",
            }

    return results


def _normalize_competition(comp: str) -> str:
    mapping = {
        "낮음": "LOW",
        "중간": "MEDIUM",
        "높음": "HIGH",
        "LOW": "LOW",
        "MEDIUM": "MEDIUM",
        "HIGH": "HIGH",
    }
    return mapping.get(str(comp).upper(), mapping.get(comp, "UNKNOWN"))
