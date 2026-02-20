"""
Binance Rate Limit 관리

응답 헤더에서 Rate Limit 정보를 추적하고,
임계값 초과 시 경고 또는 요청 제한.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from core.constants import RateLimitThresholds


class RateLimitError(Exception):
    """Rate Limit 초과 에러
    
    429 응답 수신 시 발생.
    retry_after 초 후 재시도 필요.
    """
    
    def __init__(self, retry_after: int, message: str = "Rate limit exceeded"):
        self.retry_after = retry_after
        self.message = message
        super().__init__(f"{message}. Retry after {retry_after} seconds.")


class BinanceApiError(Exception):
    """Binance API 에러
    
    API 응답에서 에러 코드를 받았을 때 발생.
    """
    
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"Binance API Error [{code}]: {message}")


class OrderError(BinanceApiError):
    """주문 관련 에러
    
    주문 생성/취소 실패 시 발생.
    """
    pass


@dataclass
class RateLimitTracker:
    """Rate Limit 추적기
    
    Binance API 응답 헤더에서 Rate Limit 정보를 추출하여 추적.
    임계값 기반으로 요청 속도 조절 여부 결정.
    
    Binance Rate Limit 헤더:
    - X-MBX-USED-WEIGHT-1m: 1분간 사용된 요청 가중치
    - X-MBX-ORDER-COUNT-1m: 1분간 주문 수
    - Retry-After: 429 응답 시 대기 시간 (초)
    """
    
    used_weight_1m: int = 0
    order_count_1m: int = 0
    retry_after: int = 0
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def update_from_headers(self, headers: dict[str, Any]) -> None:
        """응답 헤더에서 Rate Limit 정보 업데이트
        
        Args:
            headers: HTTP 응답 헤더 (대소문자 무관)
        """
        # 헤더 키는 대소문자 무관하게 처리
        headers_lower = {k.lower(): v for k, v in headers.items()}
        
        weight = headers_lower.get("x-mbx-used-weight-1m")
        if weight is not None:
            self.used_weight_1m = int(weight)
        
        order_count = headers_lower.get("x-mbx-order-count-1m")
        if order_count is not None:
            self.order_count_1m = int(order_count)
        
        retry_after = headers_lower.get("retry-after")
        if retry_after is not None:
            self.retry_after = int(retry_after)
        
        self.last_updated = datetime.now(timezone.utc)
    
    @property
    def should_warn(self) -> bool:
        """경고 임계값 도달 여부"""
        return self.used_weight_1m >= RateLimitThresholds.WEIGHT_WARN
    
    @property
    def should_slow_down(self) -> bool:
        """속도 저하 필요 여부"""
        return self.used_weight_1m >= RateLimitThresholds.WEIGHT_SLOW
    
    @property
    def should_stop(self) -> bool:
        """요청 중단 필요 여부"""
        return self.used_weight_1m >= RateLimitThresholds.WEIGHT_STOP
    
    @property
    def remaining_weight(self) -> int:
        """남은 가중치 (STOP 임계값 기준)"""
        return max(0, RateLimitThresholds.WEIGHT_STOP - self.used_weight_1m)
    
    def reset(self) -> None:
        """카운터 리셋 (분 경계에서 자동 리셋되지만 수동 리셋 가능)"""
        self.used_weight_1m = 0
        self.order_count_1m = 0
        self.retry_after = 0
        self.last_updated = datetime.now(timezone.utc)
    
    def to_dict(self) -> dict[str, Any]:
        """딕셔너리로 변환 (로깅용)"""
        return {
            "used_weight_1m": self.used_weight_1m,
            "order_count_1m": self.order_count_1m,
            "retry_after": self.retry_after,
            "last_updated": self.last_updated.isoformat(),
            "should_warn": self.should_warn,
            "should_slow_down": self.should_slow_down,
            "should_stop": self.should_stop,
        }
