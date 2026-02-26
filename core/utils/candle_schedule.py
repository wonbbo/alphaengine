"""
봉 마감 시각 계산 유틸리티

전략 틱을 봉 마감 시점(0초 근처)에만 호출하기 위한 다음 봉 마감 시각(UTC) 계산.
"""

from datetime import datetime, timezone, timedelta

# Binance Kline interval 문자열 → 분 단위
TIMEFRAME_TO_MINUTES: dict[str, int] = {
    "1m": 1,
    "3m": 3,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "2h": 120,
    "4h": 240,
    "6h": 360,
    "8h": 480,
    "12h": 720,
    "1d": 1440,
}

DEFAULT_TIMEFRAME_MINUTES = 5


def timeframe_to_minutes(timeframe: str) -> int:
    """timeframe 문자열을 분 단위로 변환 (예: '5m' -> 5, '1h' -> 60)"""
    if not timeframe:
        return DEFAULT_TIMEFRAME_MINUTES
    normalized = timeframe.strip().lower()
    return TIMEFRAME_TO_MINUTES.get(normalized, DEFAULT_TIMEFRAME_MINUTES)


def get_next_candle_close_utc(now_utc: datetime, interval_minutes: int) -> datetime:
    """다음 봉 마감 시각(UTC) 반환. 초·마이크로초는 0.
    
    예: 5분봉 기준 now=12:03:00 -> 12:05:00, now=12:05:00 -> 12:10:00
    """
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    total_minutes = now_utc.hour * 60 + now_utc.minute
    next_close_total = ((total_minutes // interval_minutes) + 1) * interval_minutes
    if next_close_total >= 24 * 60:
        # 다음 날 00:00 또는 해당 분
        next_close = (
            now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
            + timedelta(days=1)
            + timedelta(minutes=next_close_total - 24 * 60)
        )
    else:
        next_close = now_utc.replace(
            hour=next_close_total // 60,
            minute=next_close_total % 60,
            second=0,
            microsecond=0,
        )
    return next_close


def get_last_candle_close_utc(now_utc: datetime, interval_minutes: int) -> datetime:
    """now_utc 이하인 가장 최근 봉 마감 시각(UTC) 반환. 초·마이크로초는 0.
    
    예: 5분봉 기준 now=12:05:01 -> 12:05:00, now=12:04:59 -> 12:00:00
    """
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    total_minutes = now_utc.hour * 60 + now_utc.minute
    last_close_total = (total_minutes // interval_minutes) * interval_minutes
    last_close = now_utc.replace(
        hour=last_close_total // 60,
        minute=last_close_total % 60,
        second=0,
        microsecond=0,
    )
    return last_close


def get_run_at_after_close(
    next_close_utc: datetime,
    delay_seconds: int = 1,
) -> datetime:
    """봉 마감 후 delay_seconds 초 시점(전략 틱 실행 시각) 반환.
    
    거래소가 봉을 확정한 뒤 호출하기 위해 0초 직후(기본 1초)에 실행.
    """
    return next_close_utc + timedelta(seconds=delay_seconds)
