import anthropic
import json
import os
from typing import Optional


async def generate_keywords(
    homepage_data: dict,
    main_keyword: str,
    api_key: Optional[str] = None,
) -> list[str]:
    """Claude AI를 사용하여 네이버 파워링크 키워드를 생성합니다."""
    client = anthropic.AsyncAnthropic(
        api_key=api_key or os.getenv("ANTHROPIC_API_KEY")
    )

    # 홈페이지 정보 요약
    site_info = f"""
홈페이지 URL: {homepage_data.get('url', '')}
사이트 제목: {homepage_data.get('title', '')}
메타 설명: {homepage_data.get('description', '')}
메타 키워드: {homepage_data.get('meta_keywords', '')}
주요 헤딩: {', '.join(homepage_data.get('headings', [])[:10])}
본문 내용 (일부): {homepage_data.get('body_text', '')[:1500]}
"""

    system_prompt = """당신은 네이버 검색광고 파워링크 전문가입니다.
홈페이지 분석을 통해 광고 효율이 높은 키워드를 추출하고 추천합니다.
반드시 JSON 형식으로만 응답하세요."""

    user_prompt = f"""다음 홈페이지 정보와 메인 키워드를 분석하여, 네이버 파워링크에 등록할 최적의 키워드 목록을 추출해주세요.

[메인 키워드]
{main_keyword}

[홈페이지 정보]
{site_info}

[요구사항]
1. 총 40~50개의 키워드를 추출하세요
2. 다음 유형을 골고루 포함하세요:
   - 브랜드/상호명 관련 키워드 (5~8개)
   - 핵심 제품/서비스 키워드 (15~20개)
   - 정보성 키워드 (방법, 추천, 비교, 후기, 가격, 비용 포함) (10~12개)
   - 지역 키워드 (서울, 부산, 수도권 등 지역명 포함) (5~8개)
   - 경쟁/대안 키워드 (유사 서비스/제품 검색어) (5~8개)
3. 한국어 키워드 위주로 구성하세요
4. 실제 사용자가 네이버에서 검색할 법한 자연스러운 키워드를 사용하세요
5. 너무 포괄적이거나 너무 구체적인 키워드는 피하세요

반드시 아래 JSON 형식으로만 응답하세요:
{{
  "keywords": ["키워드1", "키워드2", ...]
}}"""

    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=[
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_prompt}],
    )

    content = response.content[0].text.strip()

    # JSON 파싱
    try:
        # 마크다운 코드블록 제거
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        data = json.loads(content)
        return data.get("keywords", [])
    except json.JSONDecodeError:
        # JSON 파싱 실패 시 텍스트에서 추출 시도
        lines = [line.strip().strip('",') for line in content.split("\n")]
        keywords = [line for line in lines if line and not line.startswith("{") and not line.startswith("}")]
        return keywords[:50]
