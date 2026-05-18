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


async def fetch_related_keywords(
    hint_keywords: list[str],
    customer_id: str,
    access_license: str,
    secret_key: str,
) -> dict[str, dict]:
    """네이버 키워드 도구 API로 연관 키워드와 통계를 한번에 조회합니다."""
    results = {}

    # 5개씩 배치 처리 (API 제한)
    batch_size = 5
    for i in range(0, len(hint_keywords), batch_size):
        batch = hint_keywords[i : i + batch_size]

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
                    if not kw:
                        continue
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
            pass

        if i + batch_size < len(hint_keywords):
            await asyncio.sleep(0.5)

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
