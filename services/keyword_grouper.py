REGIONAL_TERMS = [
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
    "수원", "성남", "고양", "용인", "부천", "안산", "안양", "남양주",
    "화성", "평택", "의정부", "시흥", "파주", "김포", "광명", "군포",
    "강남", "강북", "강서", "강동", "마포", "송파", "노원", "은평",
    "종로", "중구", "서초", "양천", "구로", "영등포", "동작", "관악",
    "성북", "동대문", "중랑", "광진", "성동", "용산", "도봉", "금천",
]

INFORMATIONAL_TERMS = [
    "방법", "추천", "비교", "후기", "리뷰", "가격", "비용", "요금",
    "종류", "차이", "장단점", "선택", "구매", "주의", "팁", "노하우",
    "이유", "효과", "장점", "단점", "특징", "원리", "이해", "정리",
]


def group_keywords(
    keywords: list[str],
    keyword_stats: dict[str, dict],
    main_keyword: str,
    brand_name: str = "",
) -> list[dict]:
    """키워드를 광고 연관지수 개선을 위한 그룹으로 분류합니다."""
    groups: dict[str, list] = {
        "브랜드 키워드": [],
        "제품/서비스 키워드": [],
        "정보성 키워드": [],
        "지역 키워드": [],
        "경쟁/대안 키워드": [],
    }

    brand_tokens = _extract_brand_tokens(brand_name, main_keyword)

    for kw in keywords:
        stats = keyword_stats.get(kw, {
            "monthly_pc": 0,
            "monthly_mobile": 0,
            "monthly_total": 0,
            "competition": "UNKNOWN",
        })
        entry = {
            "keyword": kw,
            "monthly_pc": stats["monthly_pc"],
            "monthly_mobile": stats["monthly_mobile"],
            "monthly_total": stats["monthly_total"],
            "competition": stats["competition"],
            "bid_strategy": "",
        }

        if _is_brand(kw, brand_tokens):
            entry["bid_strategy"] = "높은 입찰가 (브랜드 방어)"
            groups["브랜드 키워드"].append(entry)
        elif _is_regional(kw):
            entry["bid_strategy"] = "중간 입찰가 (지역 타겟팅)"
            groups["지역 키워드"].append(entry)
        elif _is_informational(kw):
            entry["bid_strategy"] = "중간 입찰가 (정보 탐색 단계)"
            groups["정보성 키워드"].append(entry)
        elif _is_competitive(kw, stats):
            entry["bid_strategy"] = "전략적 입찰가 (경쟁 키워드)"
            groups["경쟁/대안 키워드"].append(entry)
        else:
            entry["bid_strategy"] = "높은 입찰가 (핵심 서비스)"
            groups["제품/서비스 키워드"].append(entry)

    result = []
    group_order = [
        "브랜드 키워드",
        "제품/서비스 키워드",
        "정보성 키워드",
        "지역 키워드",
        "경쟁/대안 키워드",
    ]

    for group_name in group_order:
        items = groups[group_name]
        # 검색량 내림차순 정렬
        items.sort(key=lambda x: x["monthly_total"], reverse=True)

        total_search = sum(i["monthly_total"] for i in items)
        avg_search = total_search // len(items) if items else 0

        result.append({
            "group_name": group_name,
            "keywords": items,
            "total_keywords": len(items),
            "avg_monthly_search": avg_search,
        })

    return result


def _extract_brand_tokens(brand_name: str, main_keyword: str) -> list[str]:
    tokens = []
    if brand_name:
        tokens.append(brand_name.lower())
        # 공백 기준 분리
        tokens.extend(brand_name.lower().split())
    return [t for t in tokens if len(t) >= 2]


def _is_brand(keyword: str, brand_tokens: list[str]) -> bool:
    kw_lower = keyword.lower()
    return any(token in kw_lower for token in brand_tokens)


def _is_regional(keyword: str) -> bool:
    return any(region in keyword for region in REGIONAL_TERMS)


def _is_informational(keyword: str) -> bool:
    return any(term in keyword for term in INFORMATIONAL_TERMS)


def _is_competitive(keyword: str, stats: dict) -> bool:
    # 경쟁강도 높음이거나 검색량이 매우 높은 경우
    return stats.get("competition") == "HIGH" or stats.get("monthly_total", 0) > 50000
