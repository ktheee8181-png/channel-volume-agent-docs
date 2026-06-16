from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


EPSILON = 1e-6


@dataclass(frozen=True)
class Period:
    year: int
    month: int

    def next_month(self) -> "Period":
        if self.month == 12:
            return Period(self.year + 1, 1)
        return Period(self.year, self.month + 1)

    def previous_month(self) -> "Period":
        if self.month == 1:
            return Period(self.year - 1, 12)
        return Period(self.year, self.month - 1)

    def previous_year(self) -> "Period":
        return Period(self.year - 1, self.month)

    def format(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"


class DataStore:
    def __init__(
        self,
        summary_rows: dict[tuple[int, int], dict[str, str]],
        main_fact_rows: list[dict[str, str]],
        event_rows: list[dict[str, str]],
        special_product_rows: list[dict[str, str]],
    ):
        self.summary_rows = summary_rows
        self.main_fact_rows = main_fact_rows
        self.event_rows = event_rows
        self.special_product_rows = special_product_rows
        self.channels = sorted({row["채널"] for row in main_fact_rows})

    @classmethod
    def from_directory(cls, data_dir: Path) -> "DataStore":
        summary_path = data_dir / "monthly_summary.csv"
        main_fact_path = data_dir / "main_fact.csv"
        events_path = data_dir / "monthly_events.csv"
        specials_path = data_dir / "special_products.csv"

        with summary_path.open(encoding="utf-8-sig", newline="") as summary_file:
            summary_rows = {}
            for row in csv.DictReader(summary_file):
                key = (int(row["연도"]), int(row["월"]))
                summary_rows[key] = row

        with main_fact_path.open(encoding="utf-8-sig", newline="") as main_fact_file:
            main_fact_rows = list(csv.DictReader(main_fact_file))

        with events_path.open(encoding="utf-8-sig", newline="") as events_file:
            event_rows = list(csv.DictReader(events_file))

        with specials_path.open(encoding="utf-8-sig", newline="") as specials_file:
            special_product_rows = list(csv.DictReader(specials_file))

        return cls(
            summary_rows=summary_rows,
            main_fact_rows=main_fact_rows,
            event_rows=event_rows,
            special_product_rows=special_product_rows,
        )

    def latest_period(self) -> Period:
        year, month = max(self.summary_rows)
        return Period(year=year, month=month)

    def periods_for_year(self, year: int) -> list[Period]:
        return [
            Period(year=row_year, month=row_month)
            for row_year, row_month in sorted(self.summary_rows)
            if row_year == year
        ]

    def periods_for_month(self, month: int) -> list[Period]:
        return [
            Period(year=row_year, month=row_month)
            for row_year, row_month in sorted(self.summary_rows)
            if row_month == month
        ]

    def recent_periods(self, count: int) -> list[Period]:
        periods = [Period(year=row_year, month=row_month) for row_year, row_month in sorted(self.summary_rows)]
        if count <= 0:
            return []
        return periods[-count:]

    def has_period(self, period: Period) -> bool:
        return (period.year, period.month) in self.summary_rows

    def get_summary_row(self, period: Period) -> dict[str, str] | None:
        return self.summary_rows.get((period.year, period.month))

    def is_summary_valid(self, period: Period) -> bool:
        row = self.get_summary_row(period)
        if row is None:
            return False

        channel_total = float(row["채널합계검산"])
        product_total = float(row["상품합계검산"])
        diff = float(row["합계차이"])
        return abs(channel_total - product_total) < EPSILON and abs(diff) < EPSILON

    def is_year_valid(self, year: int) -> bool:
        periods = self.periods_for_year(year)
        if not periods:
            return False
        if not all(self.is_summary_valid(period) for period in periods):
            return False
        total_value = self.get_year_total(year)
        channel_sum = sum(value for _, value, _ in self.get_channel_breakdown_for_year(year))
        return total_value is not None and abs(total_value - channel_sum) < EPSILON

    def get_total_value(self, period: Period) -> float | None:
        row = self.get_summary_row(period)
        if row is None:
            return None
        return float(row["월초"])

    def get_summary_metric(self, period: Period, field_name: str) -> float | None:
        row = self.get_summary_row(period)
        if row is None or field_name not in row:
            return None
        return float(row[field_name])

    def get_year_total(self, year: int) -> float | None:
        periods = self.periods_for_year(year)
        if not periods:
            return None
        return round(sum(self.get_total_value(period) or 0.0 for period in periods), 1)

    def get_year_month_count(self, year: int) -> int:
        return len(self.periods_for_year(year))

    def get_year_average_total(self, year: int) -> float | None:
        total = self.get_year_total(year)
        month_count = self.get_year_month_count(year)
        if total is None or month_count == 0:
            return None
        return round(total / month_count, 1)

    def get_channel_total(self, period: Period, channel: str) -> float | None:
        matched = [
            float(row["금액"])
            for row in self.main_fact_rows
            if int(row["연도"]) == period.year
            and int(row["월"]) == period.month
            and row["채널"].upper() == channel.upper()
        ]
        if not matched:
            return None
        return round(sum(matched), 1)

    def get_category_breakdown_for_period(
        self,
        period: Period,
        channel: str | None = None,
    ) -> list[tuple[str, float, float]]:
        totals: dict[str, float] = {}
        for row in self.main_fact_rows:
            if int(row["연도"]) != period.year or int(row["월"]) != period.month:
                continue
            if channel and row["채널"].upper() != channel.upper():
                continue
            category = row["대분류"]
            totals[category] = totals.get(category, 0.0) + float(row["금액"])

        if channel:
            total_value = self.get_channel_total(period, channel) or 0.0
        else:
            total_value = self.get_total_value(period) or 0.0
        for key, value in list(totals.items()):
            totals[key] = round(value, 1)
        return self._build_ranked_rows(totals, total_value)

    def get_category_deltas_for_period(
        self,
        period: Period,
        previous_period: Period,
        channel: str | None = None,
    ) -> list[tuple[str, float]]:
        current = {
            category: value
            for category, value, _ in self.get_category_breakdown_for_period(period, channel)
        }
        previous = {
            category: value
            for category, value, _ in self.get_category_breakdown_for_period(previous_period, channel)
        }
        categories = sorted(set(current) | set(previous))
        deltas = []
        for category in categories:
            delta = round(current.get(category, 0.0) - previous.get(category, 0.0), 1)
            deltas.append((category, delta))
        return sorted(deltas, key=lambda item: (-item[1], item[0]))

    def get_subcategory_deltas_for_period(
        self,
        period: Period,
        previous_period: Period,
        channel: str | None = None,
    ) -> list[tuple[str, float]]:
        current: dict[str, float] = {}
        previous: dict[str, float] = {}
        for row in self.main_fact_rows:
            row_period = (int(row["연도"]), int(row["월"]))
            if channel and row["채널"].upper() != channel.upper():
                continue
            subcategory = row["중분류"]
            value = float(row["금액"])
            if row_period == (period.year, period.month):
                current[subcategory] = current.get(subcategory, 0.0) + value
            elif row_period == (previous_period.year, previous_period.month):
                previous[subcategory] = previous.get(subcategory, 0.0) + value

        deltas = []
        for subcategory in sorted(set(current) | set(previous)):
            delta = round(current.get(subcategory, 0.0) - previous.get(subcategory, 0.0), 1)
            deltas.append((subcategory, delta))
        return sorted(deltas, key=lambda item: (-item[1], item[0]))

    def get_channel_deltas_for_period(self, period: Period, previous_period: Period) -> list[tuple[str, float]]:
        current = {
            channel: value
            for channel, value, _ in self.get_channel_breakdown_for_period(period)
        }
        previous = {
            channel: value
            for channel, value, _ in self.get_channel_breakdown_for_period(previous_period)
        }
        deltas = []
        for channel in sorted(set(current) | set(previous)):
            delta = round(current.get(channel, 0.0) - previous.get(channel, 0.0), 1)
            deltas.append((channel, delta))
        return sorted(deltas, key=lambda item: (-item[1], item[0]))

    def get_events_for_period(self, period: Period) -> list[dict[str, str]]:
        return [
            row
            for row in self.event_rows
            if int(row["연도"]) == period.year and int(row["월"]) == period.month
        ]

    def get_special_products_for_period(self, period: Period) -> list[dict[str, str]]:
        return [
            row
            for row in self.special_product_rows
            if int(row["연도"]) == period.year and int(row["월"]) == period.month
        ]

    def get_channel_breakdown_for_period(self, period: Period) -> list[tuple[str, float, float]]:
        totals: dict[str, float] = {}
        for channel in self.channels:
            value = self.get_channel_total(period, channel)
            if value is not None:
                totals[channel] = value
        total_value = self.get_total_value(period) or 0.0
        return self._build_ranked_rows(totals, total_value)

    def get_channel_breakdown_for_year(self, year: int) -> list[tuple[str, float, float]]:
        totals: dict[str, float] = {}
        for row in self.main_fact_rows:
            if int(row["연도"]) != year:
                continue
            channel = row["채널"]
            totals[channel] = totals.get(channel, 0.0) + float(row["금액"])
        for channel, value in list(totals.items()):
            totals[channel] = round(value, 1)
        total_value = self.get_year_total(year) or 0.0
        return self._build_ranked_rows(totals, total_value)

    def get_channel_average_breakdown_for_year(self, year: int) -> list[tuple[str, float, float]]:
        month_count = self.get_year_month_count(year)
        if month_count == 0:
            return []

        yearly_rows = self.get_channel_breakdown_for_year(year)
        average_total = self.get_year_average_total(year) or 0.0
        ranked_rows: list[tuple[str, float, float]] = []
        for channel, yearly_value, _ in yearly_rows:
            average_value = round(yearly_value / month_count, 1)
            share = 0.0 if abs(average_total) < EPSILON else round((average_value / average_total) * 100, 1)
            ranked_rows.append((channel, average_value, share))
        return ranked_rows

    def get_year_rank_map(self, year: int) -> dict[str, tuple[int, float, float]]:
        ranked_rows = self.get_channel_breakdown_for_year(year)
        rank_map: dict[str, tuple[int, float, float]] = {}
        for index, (channel, value, share) in enumerate(ranked_rows, start=1):
            rank_map[channel] = (index, value, share)
        return rank_map

    def _build_ranked_rows(self, totals: dict[str, float], total_value: float) -> list[tuple[str, float, float]]:
        rows = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
        ranked_rows: list[tuple[str, float, float]] = []
        for channel, value in rows:
            share = 0.0 if abs(total_value) < EPSILON else round((value / total_value) * 100, 1)
            ranked_rows.append((channel, value, share))
        return ranked_rows
