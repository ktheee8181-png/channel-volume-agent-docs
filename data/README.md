# 삼성 보험 업적 더미데이터

이 저장소는 채널 물량 분석 에이전트 시연과 검증을 위한 보험 업적 더미데이터를 담고 있습니다.

실제 고객정보, 계약정보, 사내 기밀정보는 포함하지 않았습니다. 모든 값은 시연용 가상 데이터입니다.

## 문서

- [더미데이터 생성 기준](./docs/dummy.md)

## 데이터

- [엑셀 통합본](./data/channel_volume_dummy_data.xlsx)
- [JSON 번들](./data/dummy_data_bundle.json)
- [월별 요약 CSV](./data/monthly_summary.csv)
- [메인 팩트 CSV](./data/main_fact.csv)
- [월별 이벤트 CSV](./data/monthly_events.csv)
- [특수/신상품 CSV](./data/special_products.csv)
- [채널 기준 CSV](./data/channel_profile.csv)
- [상품 기준 CSV](./data/product_profile.csv)

## 주요 기준

- 월초 = 보장월초 + 연금월초
- 보장월초 = 건강월초 + 종신월초
- 채널별 합계와 상품군 합계는 동일해야 합니다.
- 신상품은 월별 1개만 생성합니다.
- 신상품은 건강:종신이 약 3:1 비율이 되도록 생성합니다.
- `special_products`의 설명 열에는 상품 중분류를 명시합니다.

