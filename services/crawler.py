import httpx
from bs4 import BeautifulSoup
from typing import Optional


async def crawl_homepage(url: str) -> dict:
    """홈페이지를 크롤링하여 텍스트 콘텐츠를 추출합니다."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            verify=False,
        ) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            html = response.text
    except httpx.TimeoutException:
        return {"error": "홈페이지 로딩 시간이 초과되었습니다.", "url": url}
    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP 오류: {e.response.status_code}", "url": url}
    except Exception as e:
        return {"error": f"홈페이지 접속 실패: {str(e)}", "url": url}

    soup = BeautifulSoup(html, "html.parser")

    # 스크립트/스타일 제거
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    title = soup.find("title")
    title_text = title.get_text(strip=True) if title else ""

    meta_desc = soup.find("meta", attrs={"name": "description"})
    description = meta_desc.get("content", "") if meta_desc else ""

    meta_kw = soup.find("meta", attrs={"name": "keywords"})
    meta_keywords = meta_kw.get("content", "") if meta_kw else ""

    headings = []
    for tag in soup.find_all(["h1", "h2", "h3"]):
        text = tag.get_text(strip=True)
        if text:
            headings.append(text)

    body_text = soup.get_text(separator=" ", strip=True)
    body_text = " ".join(body_text.split())[:3000]

    return {
        "url": url,
        "title": title_text,
        "description": description,
        "meta_keywords": meta_keywords,
        "headings": headings[:20],
        "body_text": body_text,
        "error": None,
    }
