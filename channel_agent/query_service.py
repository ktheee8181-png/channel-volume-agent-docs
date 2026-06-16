from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .data_store import DataStore, Period
from .query_parser import parse_query


def load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return

    import os

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class QueryContext:
    query_text: str
    data_dir: Path


class QueryService:
    def __init__(self, store: DataStore):
        self.store = store

    def answer_query(self, query: str) -> str:
        parsed = parse_query(query, self.store.channels)
        if parsed.query_type == "비교형":
            if parsed.compare_year is None:
                raise ValueError("질문에서 비교할 연도 2개를 찾지 못했습니다.")
            return self._answer_rank_comparison_query(parsed.year, parsed.compare_year)

        if parsed.query_type == "예측형":
            return self._answer_forecast_query(query)

        if parsed.query_type == "설명형":
            return self._answer_explanation_query(query, parsed.year, parsed.month, parsed.channel)

        if parsed.query_type == "평균분석형":
            return self._answer_average_analysis_query(parsed.year, parsed.month)

        if parsed.query_type == "분석형":
            return self._answer_analysis_query(parsed.year, parsed.month)

        if parsed.month is None:
            raise ValueError("질문에서 월을 찾지 못했습니다.")

        period = Period(parsed.year, parsed.month)

        if not self.store.has_period(period):
            return self._render_follow_up(
                period=period,
                reason="요청한 기준월 데이터가 없습니다.",
            )

        if not self.store.is_summary_valid(period):
            return self._render_follow_up(
                period=period,
                reason="해당 월 데이터의 합계 검산이 맞지 않습니다.",
            )

        if parsed.channel:
            target = parsed.channel
            value = self.store.get_channel_total(period, parsed.channel)
            source_label = "main_fact 채널 합계"
        else:
            target = "전체"
            value = self.store.get_total_value(period)
            source_label = "monthly_summary 월초"

        if value is None:
            return self._render_follow_up(
                period=period,
                reason="조회 대상에 해당하는 값이 없습니다.",
            )

        previous_value = self.store.get_channel_total(period.previous_month(), parsed.channel) if parsed.channel else self.store.get_total_value(period.previous_month())
        previous_year_value = self.store.get_channel_total(period.previous_year(), parsed.channel) if parsed.channel else self.store.get_total_value(period.previous_year())

        lines = [
            "# 조회 결과",
            "",
            f"- 질의 유형: {parsed.query_type}",
            f"- 질의 시점: {date.today().isoformat()}",
            f"- 기준월: {period.format()}",
            f"- 사용 데이터 기준월: {self.store.latest_period().format()}",
            f"- 조회 대상: {target}",
            f"- 조회값: {value:.1f}",
            f"- 데이터 소스: {source_label}",
            f"- 전월 비교: {self._format_delta(previous_value, value)}",
            f"- 전년 동월 비교: {self._format_delta(previous_year_value, value)}",
            "- 검산 상태: 정상",
        ]
        return "\n".join(lines)

    def _answer_explanation_query(
        self,
        query: str,
        year: int,
        month: int | None,
        channel: str | None,
    ) -> str:
        if month is None:
            raise ValueError("설명형 질문에는 연도와 월이 필요합니다.")

        period = Period(year, month)
        if not self.store.has_period(period):
            return self._render_follow_up(
                period=period,
                reason="요청한 기준월 데이터가 없습니다.",
                title="설명 결과",
                query_type="설명형",
                period_label=period.format(),
                period_key="기준기간",
            )

        if not self.store.is_summary_valid(period):
            return self._render_follow_up(
                period=period,
                reason="해당 월 데이터의 합계 검산이 맞지 않습니다.",
                title="설명 결과",
                query_type="설명형",
                period_label=period.format(),
                period_key="기준기간",
            )

        if "구조" in query and "채널별" in query:
            return self._answer_structure_explanation(period)
        if channel:
            return self._answer_channel_explanation(period, channel)
        return self._answer_total_explanation(period)

    def _answer_total_explanation(self, period: Period) -> str:
        current_value = self.store.get_total_value(period) or 0.0
        previous_value = self.store.get_total_value(period.previous_month())
        category_deltas = self.store.get_category_deltas_for_period(period, period.previous_month())
        channel_deltas = self.store.get_channel_deltas_for_period(period, period.previous_month())
        increase = previous_value is None or current_value >= previous_value
        top_category, top_category_delta = self._pick_primary_driver(category_deltas, prefer_positive=increase)
        top_channel, top_channel_delta = self._pick_primary_driver(channel_deltas, prefer_positive=increase)
        summary_line = (
            f"{self._format_period_korean(period)} 전체 업적은 "
            f"{self._format_change_plain(previous_value, current_value)}."
        )
        interpretation_line = (
            f"{top_category} 대분류 {self._delta_direction_word(top_category_delta, noun='증가')}와 "
            f"{top_channel} 채널 {self._delta_direction_word(top_channel_delta, noun='확대')}가 "
            "주된 배경으로 보입니다."
        )
        event_line = self._build_event_interpretation(
            period=period,
            preferred_targets=["전체"],
            current_change=current_value - previous_value if previous_value is not None else 0.0,
        )
        working_day_line = self._build_working_day_interpretation(
            period=period,
            current_change=current_value - previous_value if previous_value is not None else 0.0,
            positive_template="영업일수는 전월보다 {days}일 적어, 일수 효과보다는 상품/채널 요인의 영향이 더 컸을 가능성이 있습니다.",
            negative_template="영업일수는 전월보다 {days}일 적어, 일정 요인도 일부 부담으로 작용했을 가능성이 있습니다.",
            flat_template="영업일수는 전월과 같아, 일정 요인보다 상품/채널 구성이 더 크게 작용했을 가능성이 있습니다.",
            higher_positive_template="영업일수는 전월보다 {days}일 많아, 일정상 지원 효과도 일부 있었을 것으로 보입니다.",
            higher_negative_template="영업일수는 전월보다 {days}일 많았지만 실적은 감소해, 일정 요인보다 수요/채널 요인이 더 크게 작용한 것으로 보입니다.",
        )

        lines = [
            "# 설명 결과",
            "",
            "- 질의 유형: 설명형",
            f"- 질의 시점: {date.today().isoformat()}",
            f"- 기준기간: {period.format()}",
            f"- 사용 데이터 기준월: {self.store.latest_period().format()}",
            "- 설명 대상: 전체",
            f"- 실제 변화: {self._format_change(previous_value, current_value)}",
            f"- 설명 요약: {summary_line}",
            f"- 추론 해석: {interpretation_line}",
            f"- 보조 추론: {event_line}",
            f"- 영업일수 해석: {working_day_line}",
            "- 확인 포인트: 건강/종신 증가가 다음달에도 유지되는지와 이벤트 영향이 연금저축 흐름에 얼마나 반영되는지 함께 점검이 필요합니다.",
        ]
        return "\n".join(lines)

    def _answer_channel_explanation(self, period: Period, channel: str) -> str:
        current_value = self.store.get_channel_total(period, channel)
        if current_value is None:
            return self._render_follow_up(
                period=period,
                reason="해당 채널 데이터가 없습니다.",
                title="설명 결과",
                query_type="설명형",
                period_label=period.format(),
                period_key="기준기간",
            )

        previous_value = self.store.get_channel_total(period.previous_month(), channel)
        category_deltas = self.store.get_category_deltas_for_period(period, period.previous_month(), channel)
        subcategory_deltas = self.store.get_subcategory_deltas_for_period(period, period.previous_month(), channel)
        relevant_categories = [name for name, _ in category_deltas[:2]]
        increase = previous_value is None or current_value >= previous_value
        top_categories = self._pick_top_drivers(category_deltas, prefer_positive=increase, limit=2)
        top_subcategory, _ = self._pick_primary_driver(subcategory_deltas, prefer_positive=increase)
        primary_category, primary_delta = top_categories[0]
        secondary_category, secondary_delta = top_categories[1] if len(top_categories) > 1 else top_categories[0]
        summary_line = (
            f"{self._format_period_korean(period)} {channel} 업적은 "
            f"{self._format_change_plain(previous_value, current_value)}."
        )
        interpretation_line = (
            f"{primary_category}과 {secondary_category} {self._delta_direction_word(primary_delta, noun='확대')}가 "
            f"{'증가' if increase else '감소'}를 이끈 것으로 보입니다."
        )
        detail_line = (
            f"세부적으로는 {top_subcategory}이 가장 크게 "
            f"{'늘어' if increase else '줄어'} {channel} 내 "
            f"{'성장을' if increase else '둔화를'} 주도했습니다."
        )
        event_line = self._build_channel_event_interpretation(
            period=period,
            channel=channel,
            preferred_targets=[channel, *relevant_categories],
            current_change=current_value - previous_value if previous_value is not None else 0.0,
            primary_categories=[primary_category, secondary_category],
        )
        special_line = self._build_special_product_interpretation(period, preferred_categories=relevant_categories)
        working_day_line = self._build_working_day_interpretation(
            period=period,
            current_change=current_value - previous_value if previous_value is not None else 0.0,
            positive_template=f"영업일수는 전월보다 {{days}}일 적어, {channel} 증가를 단순 영업일수 효과로 보기는 어렵습니다.",
            negative_template=f"영업일수는 전월보다 {{days}}일 적어, {channel} 둔화에도 일정 부담이 일부 작용했을 가능성이 있습니다.",
            flat_template=f"영업일수는 전월과 같아, {channel} 변화는 일정보다는 상품 믹스 영향이 더 컸을 가능성이 있습니다.",
            higher_positive_template=f"영업일수는 전월보다 {{days}}일 많아, {channel} 증가에 일정상 도움도 일부 있었을 것으로 보입니다.",
            higher_negative_template=f"영업일수는 전월보다 {{days}}일 많았지만 {channel} 업적은 약해져, 일정 외 요인이 더 크게 작용한 것으로 보입니다.",
        )

        lines = [
            "# 설명 결과",
            "",
            "- 질의 유형: 설명형",
            f"- 질의 시점: {date.today().isoformat()}",
            f"- 기준기간: {period.format()}",
            f"- 사용 데이터 기준월: {self.store.latest_period().format()}",
            f"- 설명 대상: {channel}",
            f"- 실제 변화: {self._format_change(previous_value, current_value)}",
            f"- 설명 요약: {summary_line}",
            f"- 추론 해석: {interpretation_line}",
            f"- 세부 해석: {detail_line}",
            f"- 보조 추론: {event_line}",
            f"- 상품 단서: {special_line}",
            f"- 영업일수 해석: {working_day_line}",
            f"- 확인 포인트: {primary_category}/{secondary_category} 기여 변화가 일시적인지와 {channel} 채널 실행력 영향이 이어지는지 함께 확인이 필요합니다.",
        ]
        return "\n".join(lines)

    def _answer_structure_explanation(self, period: Period) -> str:
        channel_rows = self.store.get_channel_breakdown_for_period(period)
        category_rows = self.store.get_category_breakdown_for_period(period)
        top_three_share = round(sum(share for _, _, share in channel_rows[:3]), 1)
        primary_channel, primary_value, primary_share = channel_rows[0]
        primary_category, _, primary_category_share = category_rows[0]
        summary_line = (
            f"{self._format_period_korean(period)} 채널 구조는 "
            f"{primary_channel} 비중 {primary_share:.1f}%와 상위 3개 채널 비중 {top_three_share:.1f}%로 "
            "집중도가 높은 편입니다."
        )
        interpretation_line = (
            f"{primary_category} 비중 {primary_category_share:.1f}%가 가장 높아 "
            "보장성 중심 구조를 만든 것으로 보입니다."
        )
        event_line = self._build_structure_event_interpretation(period, current_primary_channel=primary_channel)
        working_day_line = self._build_working_day_interpretation(
            period=period,
            current_change=(self.store.get_total_value(period) or 0.0) - (self.store.get_total_value(period.previous_month()) or 0.0),
            positive_template=(
                f"영업일수는 전월보다 {{days}}일 적었지만 {primary_channel} 비중이 높게 유지돼 "
                "핵심 채널 집중이 구조를 방어한 것으로 보입니다."
            ),
            negative_template=(
                f"영업일수는 전월보다 {{days}}일 적어 구조 전반의 확산보다 상위 채널 집중이 더 두드러졌을 가능성이 있습니다."
            ),
            flat_template=(
                f"영업일수는 전월과 유사해, 채널 구조는 일정보다는 {primary_channel} 중심 집중도가 더 크게 설명합니다."
            ),
            higher_positive_template=(
                f"영업일수는 전월보다 {{days}}일 많았고, {primary_channel} 중심 집중도도 유지돼 구조 안정성이 높았던 것으로 보입니다."
            ),
            higher_negative_template=(
                f"영업일수는 전월보다 {{days}}일 많았지만 상위 채널 집중이 더 강해져 구조적 쏠림이 유지된 것으로 보입니다."
            ),
        )
        special_line = self._build_special_product_interpretation(period, preferred_categories=["종신", "건강"])

        lines = [
            "# 설명 결과",
            "",
            "- 질의 유형: 설명형",
            f"- 질의 시점: {date.today().isoformat()}",
            f"- 기준기간: {period.format()}",
            f"- 사용 데이터 기준월: {self.store.latest_period().format()}",
            "- 설명 대상: 채널 구조",
            f"- 설명 요약: {summary_line}",
            f"- 추론 해석: {interpretation_line}",
            f"- 보조 추론: {event_line}",
            f"- 상품 단서: {special_line}",
            f"- 영업일수 해석: {working_day_line}",
            f"- 확인 포인트: 상위 채널 집중도가 다음달에도 유지되는지와 {primary_category} 중심 구성이 계속 이어지는지 재확인이 필요합니다.",
        ]
        return "\n".join(lines)

    def _answer_forecast_query(self, query: str) -> str:
        recent_periods = self.store.recent_periods(3)
        target_period = self._current_target_period()

        if len(recent_periods) < 3:
            return self._render_follow_up(
                period=target_period,
                reason="예측에 필요한 최근 3개월 데이터가 부족합니다.",
                title="예측 결과",
                query_type="예측형",
                period_label=target_period.format(),
                period_key="예측 대상월",
            )

        if not all(self.store.is_summary_valid(period) for period in recent_periods):
            return self._render_follow_up(
                period=target_period,
                reason="최근 3개월 데이터의 합계 검산이 맞지 않아 예측을 진행하기 어렵습니다.",
                title="예측 결과",
                query_type="예측형",
                period_label=target_period.format(),
                period_key="예측 대상월",
            )

        recent_values = [self.store.get_total_value(period) or 0.0 for period in recent_periods]
        center = round(sum(recent_values) / len(recent_values), 1)
        low = round(min(recent_values), 1)
        high = round(max(recent_values), 1)
        seasonal_deltas = self._get_same_month_deltas(target_period)
        confidence = self._estimate_forecast_confidence()

        block_lines = [
            f"□ 중심 전망: {self._format_period_korean(target_period)} 총계는 {center:.1f} 수준으로 봅니다.",
            f"□ 예측 범위: 최근 3개월 변동폭 기준 {low:.1f} ~ {high:.1f} 범위를 우선 전망합니다.",
            f"□ 산출 근거: {self._build_forecast_basis_line(recent_periods, center, target_period, seasonal_deltas)}",
        ]
        block_lines.extend(self._build_forecast_insight_lines(recent_periods, seasonal_deltas))

        if self._wants_channel_directions(query):
            block_lines.append(f"□ 채널별 방향성: {self._build_channel_direction_line(recent_periods)}")

        block_lines.append(f"□ 신뢰도: {confidence}")

        lines = [
            "# 예측 결과",
            "",
            "- 질의 유형: 예측형",
            f"- 질의 시점: {date.today().isoformat()}",
            f"- 사용 데이터 기준월: {self.store.latest_period().format()}",
            f"- 예측 대상월: {target_period.format()}",
        ]
        lines.extend(block_lines)
        return "\n".join(lines)

    def _answer_analysis_query(self, year: int, month: int | None) -> str:
        if month is None:
            return self._answer_yearly_channel_analysis(year)
        return self._answer_monthly_channel_analysis(Period(year, month))

    def _answer_average_analysis_query(self, year: int, month: int | None) -> str:
        if month is not None:
            return "\n".join(
                [
                    "# 평균 분석 결과",
                    "",
                    "- 질의 유형: 평균분석형",
                    f"- 질의 시점: {date.today().isoformat()}",
                    f"- 기준기간: {year:04d}-{month:02d}",
                    f"- 사용 데이터 기준월: {self.store.latest_period().format()}",
                    "- 상태: 추가 확인 필요",
                    "- 사유: 월 단위 평균업적 분석은 아직 지원하지 않습니다.",
                ]
            )

        periods = self.store.periods_for_year(year)
        if not periods:
            return "\n".join(
                [
                    "# 평균 분석 결과",
                    "",
                    "- 질의 유형: 평균분석형",
                    f"- 질의 시점: {date.today().isoformat()}",
                    f"- 기준기간: {year}년",
                    f"- 사용 데이터 기준월: {self.store.latest_period().format()}",
                    "- 상태: 추가 확인 필요",
                    "- 사유: 요청한 기준연도 데이터가 없습니다.",
                ]
            )

        if not self.store.is_year_valid(year):
            return "\n".join(
                [
                    "# 평균 분석 결과",
                    "",
                    "- 질의 유형: 평균분석형",
                    f"- 질의 시점: {date.today().isoformat()}",
                    f"- 기준기간: {year}년",
                    f"- 사용 데이터 기준월: {self.store.latest_period().format()}",
                    "- 상태: 추가 확인 필요",
                    "- 사유: 해당 연도 데이터의 합계 검산이 맞지 않습니다.",
                ]
            )

        month_count = self.store.get_year_month_count(year)
        average_total = self.store.get_year_average_total(year) or 0.0
        previous_average = self.store.get_year_average_total(year - 1)
        ranked_rows = self.store.get_channel_average_breakdown_for_year(year)

        lines = [
            "# 평균 분석 결과",
            "",
            "- 질의 유형: 평균분석형",
            f"- 질의 시점: {date.today().isoformat()}",
            f"- 기준기간: {year}년 전체",
            f"- 사용 데이터 기준월: {self.store.latest_period().format()}",
            f"- 집계 월수: {month_count}개월",
            f"- 월평균 총 업적: {average_total:.1f}",
            f"- 전년 평균 비교: {self._format_delta(previous_average, average_total)}",
            "- 채널별 월평균 순위:",
        ]
        lines.extend(self._render_ranked_rows(ranked_rows))
        return "\n".join(lines)

    def _answer_rank_comparison_query(self, year: int, compare_year: int) -> str:
        current_periods = self.store.periods_for_year(year)
        compare_periods = self.store.periods_for_year(compare_year)
        if not current_periods or not compare_periods:
            return "\n".join(
                [
                    "# 순위 비교 결과",
                    "",
                    "- 질의 유형: 비교형",
                    f"- 질의 시점: {date.today().isoformat()}",
                    f"- 비교 기준: {year}년 vs {compare_year}년",
                    f"- 사용 데이터 기준월: {self.store.latest_period().format()}",
                    "- 상태: 추가 확인 필요",
                    "- 사유: 비교할 연도 데이터가 부족합니다.",
                ]
            )

        if not self.store.is_year_valid(year) or not self.store.is_year_valid(compare_year):
            return "\n".join(
                [
                    "# 순위 비교 결과",
                    "",
                    "- 질의 유형: 비교형",
                    f"- 질의 시점: {date.today().isoformat()}",
                    f"- 비교 기준: {year}년 vs {compare_year}년",
                    f"- 사용 데이터 기준월: {self.store.latest_period().format()}",
                    "- 상태: 추가 확인 필요",
                    "- 사유: 비교 대상 연도의 합계 검산이 맞지 않습니다.",
                ]
            )

        current_total = self.store.get_year_total(year) or 0.0
        compare_total = self.store.get_year_total(compare_year) or 0.0
        current_rank_map = self.store.get_year_rank_map(year)
        compare_rank_map = self.store.get_year_rank_map(compare_year)

        common_channels = [
            channel
            for channel, (rank, _, _) in sorted(current_rank_map.items(), key=lambda item: item[1][0])
            if channel in compare_rank_map
        ]

        improved = 0
        declined = 0
        stable = 0
        detail_lines: list[str] = []

        for channel in common_channels:
            current_rank, current_value, current_share = current_rank_map[channel]
            compare_rank, compare_value, compare_share = compare_rank_map[channel]

            if current_rank < compare_rank:
                improved += 1
            elif current_rank > compare_rank:
                declined += 1
            else:
                stable += 1

            value_delta = current_value - compare_value
            share_delta = current_share - compare_share
            detail_lines.append(
                f"- {channel}: {compare_rank}위 -> {current_rank}위, 금액 {value_delta:+.1f}, 비중 {share_delta:+.1f}%p"
            )

        lines = [
            "# 순위 비교 결과",
            "",
            "- 질의 유형: 비교형",
            f"- 질의 시점: {date.today().isoformat()}",
            f"- 비교 기준: {year}년 vs {compare_year}년",
            f"- 사용 데이터 기준월: {self.store.latest_period().format()}",
            f"- 총 업적 비교: {self._format_delta(compare_total, current_total)}",
            f"- 상승 채널 수: {improved}",
            f"- 하락 채널 수: {declined}",
            f"- 유지 채널 수: {stable}",
            "- 채널별 순위 비교:",
        ]
        lines.extend(detail_lines)
        return "\n".join(lines)

    def _answer_yearly_channel_analysis(self, year: int) -> str:
        periods = self.store.periods_for_year(year)
        if not periods:
            latest = self.store.latest_period().format()
            return "\n".join(
                [
                    "# 분석 결과",
                    "",
                    "- 질의 유형: 분석형",
                    f"- 질의 시점: {date.today().isoformat()}",
                    f"- 기준기간: {year}년",
                    f"- 사용 데이터 기준월: {latest}",
                    "- 상태: 추가 확인 필요",
                    "- 사유: 요청한 기준연도 데이터가 없습니다.",
                ]
            )

        if not self.store.is_year_valid(year):
            return "\n".join(
                [
                    "# 분석 결과",
                    "",
                    "- 질의 유형: 분석형",
                    f"- 질의 시점: {date.today().isoformat()}",
                    f"- 기준기간: {year}년",
                    f"- 사용 데이터 기준월: {self.store.latest_period().format()}",
                    "- 상태: 추가 확인 필요",
                    "- 사유: 해당 연도 데이터의 합계 검산이 맞지 않습니다.",
                ]
            )

        total_value = self.store.get_year_total(year) or 0.0
        previous_year_value = self.store.get_year_total(year - 1)
        ranked_rows = self.store.get_channel_breakdown_for_year(year)

        if len(periods) == 12:
            period_label = f"{year}년 전체"
        else:
            period_label = f"{year}년 누계 ({periods[0].month:02d}~{periods[-1].month:02d}월)"

        lines = [
            "# 분석 결과",
            "",
            "- 질의 유형: 분석형",
            f"- 질의 시점: {date.today().isoformat()}",
            f"- 기준기간: {period_label}",
            f"- 사용 데이터 기준월: {self.store.latest_period().format()}",
            f"- 총 업적: {total_value:.1f}",
            f"- 전년 비교: {self._format_delta(previous_year_value, total_value)}",
            "- 채널별 순위:",
        ]
        lines.extend(self._render_ranked_rows(ranked_rows))
        return "\n".join(lines)

    def _answer_monthly_channel_analysis(self, period: Period) -> str:
        if not self.store.has_period(period):
            return self._render_follow_up(
                period=period,
                reason="요청한 기준월 데이터가 없습니다.",
                title="분석 결과",
                query_type="분석형",
                period_label=period.format(),
                period_key="기준기간",
            )

        if not self.store.is_summary_valid(period):
            return self._render_follow_up(
                period=period,
                reason="해당 월 데이터의 합계 검산이 맞지 않습니다.",
                title="분석 결과",
                query_type="분석형",
                period_label=period.format(),
                period_key="기준기간",
            )

        total_value = self.store.get_total_value(period) or 0.0
        previous_value = self.store.get_total_value(period.previous_month())
        previous_year_value = self.store.get_total_value(period.previous_year())
        ranked_rows = self.store.get_channel_breakdown_for_period(period)

        lines = [
            "# 분석 결과",
            "",
            "- 질의 유형: 분석형",
            f"- 질의 시점: {date.today().isoformat()}",
            f"- 기준기간: {period.format()}",
            f"- 사용 데이터 기준월: {self.store.latest_period().format()}",
            f"- 총 업적: {total_value:.1f}",
            f"- 전월 비교: {self._format_delta(previous_value, total_value)}",
            f"- 전년 동월 비교: {self._format_delta(previous_year_value, total_value)}",
            "- 채널별 순위:",
        ]
        lines.extend(self._render_ranked_rows(ranked_rows))
        return "\n".join(lines)

    def _render_ranked_rows(self, ranked_rows: list[tuple[str, float, float]]) -> list[str]:
        lines: list[str] = []
        for index, (channel, value, share) in enumerate(ranked_rows, start=1):
            lines.append(f"- {index}위 채널: {channel} {value:.1f} ({share:.1f}%)")
        return lines

    def _render_event_line(self, period: Period, preferred_targets: list[str]) -> str:
        events = self.store.get_events_for_period(period)
        if not events:
            return "해당 월 이벤트 데이터가 없습니다."

        normalized_targets = [target.upper() for target in preferred_targets]
        for event in events:
            target_text = event["영향대상"].upper()
            if target_text == "전체" or any(target in target_text for target in normalized_targets):
                return (
                    f"{event['유형']} / {event['영향방향']} / {event['강도']} - "
                    f"{event['시나리오']}"
                )

        event = events[0]
        return f"{event['유형']} / {event['영향방향']} / {event['강도']} - {event['시나리오']}"

    def _render_special_product_line(self, period: Period, preferred_categories: list[str]) -> str:
        products = self.store.get_special_products_for_period(period)
        if not products:
            return "해당 월 신상품/세부관리 상품 데이터가 없습니다."

        preferred = []
        fallback = []
        for product in products:
            item = f"{product['상품명']} ({product['대분류']} {product['월초']})"
            if product["대분류"] in preferred_categories:
                preferred.append(item)
            else:
                fallback.append(item)

        selected = preferred[:2] if preferred else fallback[:2]
        return ", ".join(selected)

    def _build_event_interpretation(
        self,
        period: Period,
        preferred_targets: list[str],
        current_change: float,
    ) -> str:
        events = self.store.get_events_for_period(period)
        if not events:
            return "같은 달에 확인된 이벤트 데이터는 없습니다."

        event = self._select_event(period, preferred_targets)
        target_phrase = self._format_event_target_phrase(event["영향대상"])
        scenario = event["시나리오"]
        direction = event["영향방향"]

        if direction == "하방":
            lead = f"{event['유형']} 이슈로 {target_phrase}은 상대적으로 약했을 것으로 보입니다."
        else:
            lead = f"{event['유형']} 이슈로 {target_phrase}에는 추가 지원 효과가 있었을 것으로 보입니다."

        if direction == "상방" and current_change < 0:
            lead = f"{event['유형']} 이슈로 {target_phrase}에는 일부 지원 요인이 있었지만 전체 흐름을 바꾸기에는 부족했던 것으로 보입니다."

        return f"{lead} 같은 달에는 {scenario}"

    def _build_channel_event_interpretation(
        self,
        period: Period,
        channel: str,
        preferred_targets: list[str],
        current_change: float,
        primary_categories: list[str],
    ) -> str:
        base_line = self._build_event_interpretation(period, preferred_targets, current_change)
        if current_change >= 0:
            return (
                f"{base_line} 그럼에도 {channel}는 {primary_categories[0]}/{primary_categories[1]} 쪽 확대로 "
                "이를 상쇄한 것으로 보입니다."
            )
        return (
            f"{base_line} 여기에 {channel} 내부의 {primary_categories[0]}/{primary_categories[1]} 둔화가 겹치며 "
            "감소 폭이 커졌을 가능성이 있습니다."
        )

    def _build_structure_event_interpretation(self, period: Period, current_primary_channel: str) -> str:
        event = self._select_event(period, ["전체"])
        target_core = self._format_event_target_core(event["영향대상"])
        if event["영향방향"] == "하방":
            return (
                f"{event['유형']} 이슈로 {target_core}이 상대적으로 약했던 점도 "
                "건강·종신 중심 구조를 강화한 배경으로 해석됩니다."
            )
        return (
            f"{event['유형']} 이슈로 {target_core}이 상대적으로 강했던 점도 "
            f"{current_primary_channel} 중심 구조를 유지한 배경으로 해석됩니다."
        )

    def _build_special_product_interpretation(self, period: Period, preferred_categories: list[str]) -> str:
        line = self._render_special_product_line(period, preferred_categories)
        if "데이터가 없습니다" in line:
            return line
        return f"{line} 같은 상품 노출이 해당 월 구성 변화에 일부 영향을 줬을 가능성이 있습니다."

    def _build_forecast_basis_line(
        self,
        recent_periods: list[Period],
        center: float,
        target_period: Period,
        seasonal_deltas: list[float],
    ) -> str:
        recent_values = [self.store.get_total_value(period) or 0.0 for period in recent_periods]
        recent_text = " -> ".join(f"{value:.1f}" for value in recent_values)
        if seasonal_deltas:
            seasonal_avg = round(sum(seasonal_deltas) / len(seasonal_deltas), 1)
            return (
                f"최근 3개월 실적은 {recent_text}이며 평균은 {center:.1f}입니다. "
                f"과거 동일 월({target_period.month}월) 패턴은 직전월 대비 평균 {seasonal_avg:+.1f}였습니다."
            )
        return f"최근 3개월 실적은 {recent_text}이며 평균은 {center:.1f}입니다."

    def _build_forecast_insight_lines(self, recent_periods: list[Period], seasonal_deltas: list[float]) -> list[str]:
        recent_values = [self.store.get_total_value(period) or 0.0 for period in recent_periods]
        low = round(min(recent_values), 1)
        high = round(max(recent_values), 1)
        latest_period = recent_periods[-1]
        latest_total = self.store.get_total_value(latest_period) or 0.0
        latest_channel_rows = self.store.get_channel_breakdown_for_period(latest_period)
        latest_category_rows = self.store.get_category_breakdown_for_period(latest_period)
        primary_channel, _, primary_channel_share = latest_channel_rows[0]
        primary_category, primary_category_value, _ = latest_category_rows[0]
        primary_category_share = 0.0 if latest_total == 0 else round((primary_category_value / latest_total) * 100, 1)
        working_days = [int(self.store.get_summary_metric(period, "영업일수") or 0) for period in recent_periods]
        promotion_values = [self.store.get_summary_metric(period, "판촉비총량") or 0.0 for period in recent_periods]
        latest_event = self._select_event(latest_period, ["전체"])
        insight_lines = [
            f"□ 인사이트 1: 최근 3개월 실적 밴드는 {low:.1f}~{high:.1f}로 아주 넓지는 않아, 기본 범위는 비교적 안정적으로 보입니다.",
        ]

        if seasonal_deltas:
            insight_lines.append(
                f"□ 인사이트 2: 과거 동일 월 패턴은 직전월 대비 {min(seasonal_deltas):+.1f}~{max(seasonal_deltas):+.1f} 범위여서 계절 효과를 함께 볼 필요가 있습니다."
            )
        else:
            insight_lines.append("□ 인사이트 2: 과거 동일 월 패턴 데이터가 충분하지 않아 계절 효과는 보수적으로 해석할 필요가 있습니다.")

        insight_lines.append(
            f"□ 인사이트 3: {primary_channel} 비중 {primary_channel_share:.1f}%와 {primary_category} 비중 {primary_category_share:.1f}%가 높아 특정 채널·상품 집중이 전체 변동성에 영향을 줄 수 있습니다."
        )
        insight_lines.append(
            f"□ 인사이트 4: 영업일수는 최근 {min(working_days)}~{max(working_days)}일, 판촉비총량은 {min(promotion_values):.1f}~{max(promotion_values):.1f} 범위에서 움직여 운영 조건 변화도 함께 봐야 합니다."
        )
        insight_lines.append(
            f"□ 인사이트 5: 최근 이벤트로는 {latest_event['시나리오']} 영향이 남아 있을 가능성이 있습니다."
        )
        return insight_lines

    def _build_channel_direction_line(self, recent_periods: list[Period]) -> str:
        latest_period = recent_periods[-1]
        latest_ranked_channels = [channel for channel, _, _ in self.store.get_channel_breakdown_for_period(latest_period)]
        increases: list[str] = []
        flats: list[str] = []
        decreases: list[str] = []

        for channel in latest_ranked_channels:
            values = [self.store.get_channel_total(period, channel) or 0.0 for period in recent_periods]
            average_value = sum(values) / len(values)
            latest_value = values[-1]
            if average_value <= 0:
                flats.append(channel)
                continue

            ratio = ((latest_value - average_value) / average_value) * 100
            if ratio > 1.0:
                increases.append(channel)
            elif ratio < -1.0:
                decreases.append(channel)
            else:
                flats.append(channel)

        parts: list[str] = []
        if increases:
            parts.append(f"상승 가능성은 {'·'.join(increases)}")
        if flats:
            parts.append(f"보합은 {'·'.join(flats)}")
        if decreases:
            parts.append(f"하방 압력은 {'·'.join(decreases)}")
        return ", ".join(parts) + "로 봅니다."

    def _current_target_period(self) -> Period:
        today = date.today()
        current_period = Period(today.year, today.month)
        return current_period.next_month()

    def _get_same_month_deltas(self, target_period: Period) -> list[float]:
        deltas: list[float] = []
        for period in self.store.periods_for_month(target_period.month):
            if period.year >= target_period.year:
                continue
            current_value = self.store.get_total_value(period)
            previous_value = self.store.get_total_value(period.previous_month())
            if current_value is None or previous_value is None:
                continue
            deltas.append(round(current_value - previous_value, 1))
        return deltas

    def _estimate_forecast_confidence(self) -> str:
        backtests = self._build_forecast_backtests()
        if len(backtests) < 6:
            return "낮음"

        recent = backtests[-12:]
        hit_rate = sum(1 for item in recent if item["within_range"]) / len(recent)
        average_ape = sum(item["ape"] for item in recent) / len(recent)

        if hit_rate >= 0.5 and average_ape <= 3.0:
            return "높음"
        if hit_rate >= 0.25 and average_ape <= 6.0:
            return "중간"
        return "낮음"

    def _build_forecast_backtests(self) -> list[dict[str, float | bool]]:
        periods = self.store.recent_periods(9999)
        if len(periods) < 4:
            return []

        backtests: list[dict[str, float | bool]] = []
        for index in range(3, len(periods)):
            history = periods[index - 3:index]
            target = periods[index]
            if not all(self.store.is_summary_valid(period) for period in history + [target]):
                continue

            history_values = [self.store.get_total_value(period) or 0.0 for period in history]
            actual = self.store.get_total_value(target) or 0.0
            center = round(sum(history_values) / len(history_values), 1)
            low = round(min(history_values), 1)
            high = round(max(history_values), 1)
            ape = 0.0 if actual == 0 else abs(actual - center) / actual * 100
            backtests.append(
                {
                    "within_range": low <= actual <= high,
                    "ape": ape,
                }
            )

        return backtests

    def _wants_channel_directions(self, query: str) -> bool:
        return "채널별 방향성" in query or ("채널별" in query and "방향" in query)

    def _build_working_day_interpretation(
        self,
        period: Period,
        current_change: float,
        positive_template: str,
        negative_template: str,
        flat_template: str,
        higher_positive_template: str,
        higher_negative_template: str,
    ) -> str:
        current_row = self.store.get_summary_row(period)
        previous_row = self.store.get_summary_row(period.previous_month())
        if current_row is None or previous_row is None:
            return "영업일수 비교 기준이 부족해 일정 효과는 추가 확인이 필요합니다."

        current_days = int(current_row["영업일수"])
        previous_days = int(previous_row["영업일수"])
        diff = current_days - previous_days

        if diff < 0:
            template = positive_template if current_change >= 0 else negative_template
            return template.format(days=abs(diff))
        if diff > 0:
            template = higher_positive_template if current_change >= 0 else higher_negative_template
            return template.format(days=abs(diff))
        return flat_template

    def _pick_primary_driver(
        self,
        deltas: list[tuple[str, float]],
        prefer_positive: bool,
    ) -> tuple[str, float]:
        ranked = self._pick_top_drivers(deltas, prefer_positive=prefer_positive, limit=1)
        if ranked:
            return ranked[0]
        return deltas[0] if deltas else ("확인 필요", 0.0)

    def _pick_top_drivers(
        self,
        deltas: list[tuple[str, float]],
        prefer_positive: bool,
        limit: int,
    ) -> list[tuple[str, float]]:
        if prefer_positive:
            preferred = [item for item in deltas if item[1] > 0]
            preferred.sort(key=lambda item: (-item[1], item[0]))
        else:
            preferred = [item for item in deltas if item[1] < 0]
            preferred.sort(key=lambda item: (item[1], item[0]))

        if len(preferred) >= limit:
            return preferred[:limit]

        fallback = sorted(deltas, key=lambda item: (-abs(item[1]), item[0]))
        results = preferred[:]
        for item in fallback:
            if item not in results:
                results.append(item)
            if len(results) == limit:
                break
        return results

    def _select_event(self, period: Period, preferred_targets: list[str]) -> dict[str, str]:
        events = self.store.get_events_for_period(period)
        normalized_targets = [target.upper() for target in preferred_targets]
        for event in events:
            target_text = event["영향대상"].upper()
            if target_text == "전체" or any(target in target_text for target in normalized_targets):
                return event
        return events[0]

    def _format_event_target_phrase(self, target_text: str) -> str:
        cleaned = target_text.replace(",", "·").strip()
        if cleaned == "전체":
            return "전체 흐름"
        if cleaned in {"건강", "종신", "연금저축"}:
            return f"{cleaned} 흐름"
        if "채널" in cleaned or cleaned in self.store.channels:
            return f"{cleaned} 채널 흐름"
        return f"{cleaned} 흐름"

    def _format_event_target_core(self, target_text: str) -> str:
        cleaned = target_text.replace(",", "·").strip()
        if cleaned == "전체":
            return "전체 흐름"
        return cleaned

    def _format_period_korean(self, period: Period) -> str:
        return f"{period.year}년 {period.month}월"

    def _format_change_plain(self, base_value: float | None, current_value: float) -> str:
        if base_value is None:
            return "변화를 비교하기 어렵습니다"
        delta = round(current_value - base_value, 1)
        if abs(delta) < 1e-6:
            return "전월 대비 변화가 거의 없었습니다"
        direction = "증가" if delta > 0 else "감소"
        return f"전월 대비 {abs(delta):.1f} {direction}했습니다"

    def _delta_direction_word(self, delta: float, noun: str) -> str:
        if delta > 0:
            return noun
        if delta < 0:
            return "약세"
        return "변화"

    def _format_delta(self, base_value: float | None, current_value: float) -> str:
        if base_value is None:
            return "추가 확인 필요"
        delta = current_value - base_value
        if abs(base_value) < 1e-6:
            return f"{delta:+.1f} (비교 기준값 0.0)"
        ratio = (delta / base_value) * 100
        return f"{delta:+.1f} ({ratio:+.1f}%)"

    def _format_change(self, base_value: float | None, current_value: float) -> str:
        delta_text = self._format_delta(base_value, current_value)
        if base_value is None:
            return delta_text
        delta = current_value - base_value
        if abs(delta) < 1e-6:
            return f"전월 대비 {delta_text} 보합"
        direction = "증가" if delta > 0 else "감소"
        return f"전월 대비 {delta_text} {direction}"

    def _render_follow_up(
        self,
        period: Period,
        reason: str,
        title: str = "조회 결과",
        query_type: str = "조회형",
        period_label: str | None = None,
        period_key: str = "기준월",
    ) -> str:
        return "\n".join(
            [
                f"# {title}",
                "",
                f"- 질의 유형: {query_type}",
                f"- 질의 시점: {date.today().isoformat()}",
                f"- {period_key}: {period_label or period.format()}",
                f"- 사용 데이터 기준월: {self.store.latest_period().format()}",
                "- 상태: 추가 확인 필요",
                f"- 사유: {reason}",
            ]
        )
