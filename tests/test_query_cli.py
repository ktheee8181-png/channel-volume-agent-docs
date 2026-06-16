from datetime import date
from pathlib import Path
import subprocess
import unittest


PYTHON = r"C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
ROOT = Path(__file__).resolve().parents[1]


def next_month_label() -> str:
    today = date.today()
    if today.month == 12:
        return f"{today.year + 1:04d}-01"
    return f"{today.year:04d}-{today.month + 1:02d}"


def run_cli(query: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [PYTHON, str(ROOT / "main.py"), query],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )


class QueryCliTests(unittest.TestCase):
    def test_forecast_report_returns_range_based_outlook(self) -> None:
        result = run_cli("다음달 총계 전망을 보고용으로 정리해줘")

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("질의 유형: 예측형", result.stdout)
        self.assertIn(f"예측 대상월: {next_month_label()}", result.stdout)
        self.assertIn("□ 중심 전망: ", result.stdout)
        self.assertIn("261.8", result.stdout)
        self.assertIn("□ 예측 범위: 최근 3개월 변동폭 기준 259.0 ~ 263.7", result.stdout)
        self.assertIn("과거 동일 월(7월) 패턴은 직전월 대비 평균 -1.3", result.stdout)
        self.assertIn("□ 인사이트 1: 최근 3개월 실적 밴드는 259.0~263.7", result.stdout)
        self.assertIn("□ 인사이트 2: 과거 동일 월 패턴은 직전월 대비 -6.2~+0.4", result.stdout)
        self.assertIn("□ 인사이트 3: FC 비중 56.8%", result.stdout)
        self.assertIn("□ 인사이트 4: 영업일수는 최근 22~26일", result.stdout)
        self.assertIn("□ 신뢰도: 중간", result.stdout)

    def test_forecast_with_channel_request_returns_channel_directions(self) -> None:
        result = run_cli("다음달 총계 전망과 채널별 방향성 알려줘")

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("질의 유형: 예측형", result.stdout)
        self.assertIn("□ 채널별 방향성: ", result.stdout)
        self.assertIn("상승 가능성은 신채널", result.stdout)
        self.assertIn("보합은 AFC", result.stdout)
        self.assertIn("하방 압력은 FC·GA·GFC·BA·금융서비스·디지털", result.stdout)

    def test_total_explanation_returns_key_reasons(self) -> None:
        result = run_cli("왜 2025년 4월 업적이 전월 대비 늘었어?")

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("질의 유형: 설명형", result.stdout)
        self.assertIn("설명 대상: 전체", result.stdout)
        self.assertIn("설명 요약: 2025년 4월 전체 업적은 전월 대비 8.0 증가했습니다.", result.stdout)
        self.assertIn("건강 대분류 증가와 FC 채널 확대가 주된 배경으로 보입니다.", result.stdout)
        self.assertIn("시장 자금 이동 이슈로 연금저축 흐름은 상대적으로 약했을 것으로 보입니다.", result.stdout)
        self.assertIn("영업일수는 전월보다 4일 적어, 일수 효과보다는 상품/채널 요인의 영향이 더 컸을 가능성이 있습니다.", result.stdout)

    def test_channel_explanation_returns_channel_reasons(self) -> None:
        result = run_cli("왜 2025년 4월 FC 업적이 늘었어?")

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("질의 유형: 설명형", result.stdout)
        self.assertIn("설명 대상: FC", result.stdout)
        self.assertIn("설명 요약: 2025년 4월 FC 업적은 전월 대비 4.6 증가했습니다.", result.stdout)
        self.assertIn("건강과 종신 확대가 증가를 이끈 것으로 보입니다.", result.stdout)
        self.assertIn("세부적으로는 순수형이 가장 크게 늘어 FC 내 성장을 주도했습니다.", result.stdout)
        self.assertIn("영업일수는 전월보다 4일 적어, FC 증가를 단순 영업일수 효과로 보기는 어렵습니다.", result.stdout)

    def test_structure_explanation_returns_mix_reasons(self) -> None:
        result = run_cli("왜 2025년 4월 채널별 업적 구조가 이렇게 나왔어?")

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("질의 유형: 설명형", result.stdout)
        self.assertIn("설명 대상: 채널 구조", result.stdout)
        self.assertIn("설명 요약: 2025년 4월 채널 구조는 FC 비중 56.6%와 상위 3개 채널 비중 81.4%로 집중도가 높은 편입니다.", result.stdout)
        self.assertIn("건강 비중 52.1%가 가장 높아 보장성 중심 구조를 만든 것으로 보입니다.", result.stdout)
        self.assertIn("시장 자금 이동 이슈로 연금저축이 상대적으로 약했던 점도 건강·종신 중심 구조를 강화한 배경으로 해석됩니다.", result.stdout)
        self.assertIn("영업일수는 전월보다 4일 적었지만 FC 비중이 높게 유지돼 핵심 채널 집중이 구조를 방어한 것으로 보입니다.", result.stdout)

    def test_yearly_channel_average_analysis_returns_average_breakdown(self) -> None:
        result = run_cli("2025년 채널별 평균업적 분석해줘")

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("질의 유형: 평균분석형", result.stdout)
        self.assertIn("기준기간: 2025년 전체", result.stdout)
        self.assertIn("집계 월수: 12개월", result.stdout)
        self.assertIn("월평균 총 업적: 250.0", result.stdout)
        self.assertIn("1위 채널: FC 141.4 (56.6%)", result.stdout)
        self.assertIn("2위 채널: GA 31.8 (12.7%)", result.stdout)
        self.assertIn("7위 채널: 신채널 3.9 (1.6%)", result.stdout)

    def test_rank_comparison_returns_rank_and_share_diff(self) -> None:
        result = run_cli("2025년과 2024년 채널별 순위 비교해줘")

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("질의 유형: 비교형", result.stdout)
        self.assertIn("비교 기준: 2025년 vs 2024년", result.stdout)
        self.assertIn("총 업적 비교: +60.2 (+2.0%)", result.stdout)
        self.assertIn("상승 채널 수: 0", result.stdout)
        self.assertIn("유지 채널 수: 8", result.stdout)
        self.assertIn("FC: 1위 -> 1위, 금액 +40.5, 비중 +0.2%p", result.stdout)

    def test_yearly_channel_analysis_returns_ranked_breakdown(self) -> None:
        result = run_cli("2025년 채널별 업적 분석해줘")

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("질의 유형: 분석형", result.stdout)
        self.assertIn("기준기간: 2025년 전체", result.stdout)
        self.assertIn("총 업적: 3000.1", result.stdout)
        self.assertIn("1위 채널: FC 1697.3 (56.6%)", result.stdout)
        self.assertIn("2위 채널: GA 382.0 (12.7%)", result.stdout)
        self.assertIn("8위 채널: AFC 46.9 (1.6%)", result.stdout)

    def test_monthly_channel_analysis_returns_ranked_breakdown(self) -> None:
        result = run_cli("2025년 4월 채널별 업적 분석해줘")

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("질의 유형: 분석형", result.stdout)
        self.assertIn("기준기간: 2025-04", result.stdout)
        self.assertIn("총 업적: 258.6", result.stdout)
        self.assertIn("1위 채널: FC 146.4 (56.6%)", result.stdout)
        self.assertIn("2위 채널: GA 33.0 (12.8%)", result.stdout)

    def test_interactive_mode_answers_query_and_exits(self) -> None:
        result = subprocess.run(
            [PYTHON, str(ROOT / "main.py")],
            input="2025년 4월 업적이 얼마였지?\n종료\n",
            capture_output=True,
            text=True,
            cwd=ROOT,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("대화형 조회 모드", result.stdout)
        self.assertIn("조회값: 258.6", result.stdout)

    def test_total_query_returns_month_total(self) -> None:
        result = run_cli("2025년 4월 업적이 얼마였지?")

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("질의 유형: 조회형", result.stdout)
        self.assertIn("조회 대상: 전체", result.stdout)
        self.assertIn("기준월: 2025-04", result.stdout)
        self.assertIn("조회값: 258.6", result.stdout)

    def test_channel_query_returns_channel_total(self) -> None:
        result = run_cli("2025년 4월 FC 업적이 얼마였지?")

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("질의 유형: 조회형", result.stdout)
        self.assertIn("조회 대상: FC", result.stdout)
        self.assertIn("기준월: 2025-04", result.stdout)
        self.assertIn("조회값: 146.4", result.stdout)

    def test_missing_month_returns_follow_up_flag(self) -> None:
        result = run_cli("2030년 1월 업적이 얼마였지?")

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("추가 확인 필요", result.stdout)

    def test_invalid_query_returns_guidance_instead_of_traceback(self) -> None:
        result = run_cli("업적이 얼마였지?")

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("추가 확인 필요", result.stdout)
        self.assertIn("연도와 월", result.stdout)


if __name__ == "__main__":
    unittest.main()
