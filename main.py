from __future__ import annotations

import os
import sys
from pathlib import Path

from channel_agent.data_store import DataStore
from channel_agent.query_service import QueryService, load_env_file


def resolve_data_dir(root: Path) -> Path:
    configured = os.environ.get("DATA_DIR", "").strip().strip('"').strip("'")
    if configured:
        return Path(configured)
    return root / "data"


def main() -> int:
    root = Path(__file__).resolve().parent
    load_env_file(root / ".env")

    data_dir = resolve_data_dir(root)
    store = DataStore.from_directory(data_dir)
    service = QueryService(store)

    query = " ".join(sys.argv[1:]).strip()
    if query:
        print(_safe_answer(service, query))
        return 0

    print("대화형 조회 모드입니다. 질문을 입력하세요. 종료하려면 `종료`, `exit`, `q`를 입력하세요.")
    while True:
        try:
            query = input("> ").strip()
        except EOFError:
            break

        if not query:
            continue
        if query.lower() in {"종료", "exit", "q"}:
            break

        print(_safe_answer(service, query))
        print()
    return 0


def _safe_answer(service: QueryService, query: str) -> str:
    try:
        return service.answer_query(query)
    except ValueError as exc:
        return "\n".join(
            [
                "# 조회 결과",
                "",
                "- 질의 유형: 조회형",
                "- 상태: 추가 확인 필요",
                f"- 사유: {exc}",
                "- 안내: 예) 2025년 4월 업적이 얼마였지?",
            ]
        )


if __name__ == "__main__":
    raise SystemExit(main())
