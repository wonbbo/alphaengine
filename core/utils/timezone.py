"""
타임존 유틸리티

내부 저장: UTC | 외부 표시: KST 원칙 준수를 위한 헬퍼 함수
"""

from datetime import datetime, timezone, timedelta

# KST 타임존 (UTC+9)
KST = timezone(timedelta(hours=9))


def to_kst(dt: datetime) -> datetime:
    """UTC datetime을 KST로 변환
    
    Args:
        dt: datetime 객체 (UTC 권장, naive면 UTC로 간주)
        
    Returns:
        KST 타임존의 datetime
        
    Example:
        >>> utc_dt = datetime(2026, 2, 20, 16, 0, 0, tzinfo=timezone.utc)
        >>> kst_dt = to_kst(utc_dt)
        >>> kst_dt.hour
        1  # 다음날 01:00
    """
    if dt.tzinfo is None:
        # naive datetime은 UTC로 간주
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(KST)


def format_kst(dt: datetime, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """UTC datetime을 KST 문자열로 포맷
    
    Args:
        dt: datetime 객체 (UTC 권장)
        fmt: strftime 포맷 문자열
        
    Returns:
        KST 시간의 포맷된 문자열
        
    Example:
        >>> utc_dt = datetime.now(timezone.utc)
        >>> format_kst(utc_dt)
        '2026-02-21 01:00:00'
    """
    return to_kst(dt).strftime(fmt)


def format_kst_ms(dt: datetime) -> str:
    """UTC datetime을 KST 밀리초 포함 문자열로 포맷
    
    Args:
        dt: datetime 객체 (UTC 권장)
        
    Returns:
        KST 시간의 밀리초 포함 문자열
        
    Example:
        >>> format_kst_ms(datetime.now(timezone.utc))
        '2026-02-21 01:00:00.123'
    """
    kst_dt = to_kst(dt)
    base = kst_dt.strftime("%Y-%m-%d %H:%M:%S")
    ms = kst_dt.microsecond // 1000
    return f"{base}.{ms:03d}"


def now_utc() -> datetime:
    """현재 UTC 시간 반환 (타임존 명시)
    
    datetime.now(timezone.utc)의 축약형.
    
    Returns:
        현재 UTC 시간 (tzinfo=timezone.utc)
    """
    return datetime.now(timezone.utc)


def now_kst() -> datetime:
    """현재 KST 시간 반환
    
    Returns:
        현재 KST 시간 (tzinfo=KST)
    """
    return datetime.now(KST)


def utc_from_timestamp_ms(ts_ms: int) -> datetime:
    """밀리초 타임스탬프를 UTC datetime으로 변환
    
    Args:
        ts_ms: Unix 타임스탬프 (밀리초)
        
    Returns:
        UTC datetime
        
    Example:
        >>> utc_from_timestamp_ms(1708444800000)
        datetime(2024, 2, 20, 16, 0, 0, tzinfo=timezone.utc)
    """
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)


def to_timestamp_ms(dt: datetime) -> int:
    """datetime을 밀리초 타임스탬프로 변환
    
    Args:
        dt: datetime 객체 (타임존 포함 권장)
        
    Returns:
        Unix 타임스탬프 (밀리초)
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)
