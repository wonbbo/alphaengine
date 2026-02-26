"""봉 마감 시각 계산 유틸리티 단위 테스트"""

from datetime import datetime, timezone

import pytest

from core.utils.candle_schedule import (
    timeframe_to_minutes,
    get_next_candle_close_utc,
    get_last_candle_close_utc,
    get_run_at_after_close,
    TIMEFRAME_TO_MINUTES,
    DEFAULT_TIMEFRAME_MINUTES,
)


class TestTimeframeToMinutes:
    def test_5m(self) -> None:
        assert timeframe_to_minutes("5m") == 5

    def test_15m(self) -> None:
        assert timeframe_to_minutes("15m") == 15

    def test_1h(self) -> None:
        assert timeframe_to_minutes("1h") == 60

    def test_empty_default(self) -> None:
        assert timeframe_to_minutes("") == DEFAULT_TIMEFRAME_MINUTES

    def test_unknown_default(self) -> None:
        assert timeframe_to_minutes("99m") == DEFAULT_TIMEFRAME_MINUTES


class TestGetNextCandleCloseUtc:
    def test_5m_before_boundary(self) -> None:
        # 12:03:00 -> 다음 마감 12:05:00
        now = datetime(2025, 2, 26, 12, 3, 0, tzinfo=timezone.utc)
        got = get_next_candle_close_utc(now, 5)
        assert got == datetime(2025, 2, 26, 12, 5, 0, 0, tzinfo=timezone.utc)

    def test_5m_just_after_boundary(self) -> None:
        # 12:05:00.001 -> 다음 마감 12:10:00
        now = datetime(2025, 2, 26, 12, 5, 0, 1000, tzinfo=timezone.utc)
        got = get_next_candle_close_utc(now, 5)
        assert got == datetime(2025, 2, 26, 12, 10, 0, 0, tzinfo=timezone.utc)

    def test_15m(self) -> None:
        now = datetime(2025, 2, 26, 12, 10, 0, tzinfo=timezone.utc)
        got = get_next_candle_close_utc(now, 15)
        assert got == datetime(2025, 2, 26, 12, 15, 0, 0, tzinfo=timezone.utc)

    def test_5m_end_of_hour(self) -> None:
        now = datetime(2025, 2, 26, 12, 57, 0, tzinfo=timezone.utc)
        got = get_next_candle_close_utc(now, 5)
        assert got == datetime(2025, 2, 26, 13, 0, 0, 0, tzinfo=timezone.utc)


class TestGetLastCandleCloseUtc:
    def test_just_after_close(self) -> None:
        # 12:05:01 -> 방금 지난 마감 12:05:00
        now = datetime(2025, 2, 26, 12, 5, 1, tzinfo=timezone.utc)
        got = get_last_candle_close_utc(now, 5)
        assert got == datetime(2025, 2, 26, 12, 5, 0, 0, tzinfo=timezone.utc)

    def test_mid_candle(self) -> None:
        # 12:03:00 -> 그 이전 마감 12:00:00
        now = datetime(2025, 2, 26, 12, 3, 0, tzinfo=timezone.utc)
        got = get_last_candle_close_utc(now, 5)
        assert got == datetime(2025, 2, 26, 12, 0, 0, 0, tzinfo=timezone.utc)

    def test_on_boundary(self) -> None:
        now = datetime(2025, 2, 26, 12, 5, 0, 0, tzinfo=timezone.utc)
        got = get_last_candle_close_utc(now, 5)
        assert got == datetime(2025, 2, 26, 12, 5, 0, 0, tzinfo=timezone.utc)


class TestGetRunAtAfterClose:
    def test_one_second_delay(self) -> None:
        close = datetime(2025, 2, 26, 12, 5, 0, 0, tzinfo=timezone.utc)
        got = get_run_at_after_close(close, delay_seconds=1)
        assert got == datetime(2025, 2, 26, 12, 5, 1, 0, tzinfo=timezone.utc)
