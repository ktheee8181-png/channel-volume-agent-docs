from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ParsedQuery:
    query_type: str
    year: int
    month: int | None
    channel: str | None
    compare_year: int | None = None


def parse_query(query: str, channels: list[str]) -> ParsedQuery:
    query_type = _detect_query_type(query)
    if query_type == "예측형":
        today = date.today()
        channel = _extract_channel(query, channels)
        return ParsedQuery(
            query_type=query_type,
            year=today.year,
            month=today.month,
            channel=channel,
        )

    if query_type == "비교형":
        year, compare_year = _extract_year_pair(query)
        return ParsedQuery(
            query_type=query_type,
            year=year,
            month=None,
            channel=None,
            compare_year=compare_year,
        )

    year, month = _extract_period(query, require_month=query_type == "조회형")
    channel = _extract_channel(query, channels)
    return ParsedQuery(
        query_type=query_type,
        year=year,
        month=month,
        channel=channel,
    )


def _detect_query_type(query: str) -> str:
    if (
        "전망" in query
        or "흔들림" in query
        or "보고용" in query
        or "경영진" in query
        or "임원" in query
        or ("다음달" in query and ("정리" in query or "요약" in query or "알려" in query))
    ):
        return "예측형"
    if "순위" in query and "비교" in query:
        return "비교형"
    if "평균" in query and "채널별" in query:
        return "평균분석형"
    if "왜" in query or "이유" in query or "설명" in query or "구조" in query:
        return "설명형"
    if "분석" in query and "채널별" in query:
        return "분석형"
    return "조회형"


def _extract_period(query: str, require_month: bool) -> tuple[int, int | None]:
    match = re.search(r"(?P<year>\d{2,4})\s*(?:년|\.)\s*(?:(?P<month>\d{1,2})\s*월)?", query)
    if not match:
        if require_month:
            raise ValueError("질문에서 연도와 월을 찾지 못했습니다.")
        raise ValueError("질문에서 연도를 찾지 못했습니다.")

    year = int(match.group("year"))
    month_text = match.group("month")
    month = int(month_text) if month_text else None

    if year < 100:
        year += 2000
    if require_month and month is None:
        raise ValueError("질문에서 월을 찾지 못했습니다.")
    if month is not None and (month < 1 or month > 12):
        raise ValueError("질문의 월 값이 올바르지 않습니다.")

    return year, month


def _extract_channel(query: str, channels: list[str]) -> str | None:
    upper_query = query.upper()
    for channel in sorted(channels, key=len, reverse=True):
        if channel.upper() in upper_query:
            return channel
    return None


def _extract_year_pair(query: str) -> tuple[int, int]:
    matches = re.findall(r"(\d{2,4})\s*년", query)
    if len(matches) < 2:
        raise ValueError("질문에서 비교할 연도 2개를 찾지 못했습니다.")

    first = _normalize_year(int(matches[0]))
    second = _normalize_year(int(matches[1]))
    return first, second


def _normalize_year(year: int) -> int:
    if year < 100:
        return year + 2000
    return year
