"""
Rate Limiter 테스트

RateLimitTracker 및 에러 클래스 테스트.
"""

from datetime import datetime, timezone

import pytest

from adapters.binance.rate_limiter import (
    RateLimitTracker,
    RateLimitError,
    BinanceApiError,
    OrderError,
)
from core.constants import RateLimitThresholds


class TestRateLimitError:
    """RateLimitError 테스트"""
    
    def test_create_error(self) -> None:
        """에러 생성"""
        error = RateLimitError(retry_after=30)
        
        assert error.retry_after == 30
        assert "30 seconds" in str(error)
    
    def test_custom_message(self) -> None:
        """커스텀 메시지"""
        error = RateLimitError(retry_after=60, message="Custom error")
        
        assert error.message == "Custom error"
        assert "Custom error" in str(error)


class TestBinanceApiError:
    """BinanceApiError 테스트"""
    
    def test_create_error(self) -> None:
        """에러 생성"""
        error = BinanceApiError(code=-1121, message="Invalid symbol")
        
        assert error.code == -1121
        assert error.message == "Invalid symbol"
        assert "-1121" in str(error)
        assert "Invalid symbol" in str(error)


class TestOrderError:
    """OrderError 테스트"""
    
    def test_order_error_is_binance_api_error(self) -> None:
        """OrderError는 BinanceApiError의 서브클래스"""
        error = OrderError(code=-2010, message="Order would immediately match")
        
        assert isinstance(error, BinanceApiError)
        assert error.code == -2010


class TestRateLimitTracker:
    """RateLimitTracker 테스트"""
    
    def test_default_values(self) -> None:
        """기본값 확인"""
        tracker = RateLimitTracker()
        
        assert tracker.used_weight_1m == 0
        assert tracker.order_count_1m == 0
        assert tracker.retry_after == 0
    
    def test_update_from_headers(self) -> None:
        """헤더에서 업데이트"""
        tracker = RateLimitTracker()
        
        headers = {
            "X-MBX-USED-WEIGHT-1m": "500",
            "X-MBX-ORDER-COUNT-1m": "10",
        }
        
        tracker.update_from_headers(headers)
        
        assert tracker.used_weight_1m == 500
        assert tracker.order_count_1m == 10
    
    def test_update_from_headers_case_insensitive(self) -> None:
        """헤더 키 대소문자 무관"""
        tracker = RateLimitTracker()
        
        headers = {
            "x-mbx-used-weight-1m": "300",
            "X-Mbx-Order-Count-1m": "5",
        }
        
        tracker.update_from_headers(headers)
        
        assert tracker.used_weight_1m == 300
        assert tracker.order_count_1m == 5
    
    def test_update_retry_after(self) -> None:
        """Retry-After 업데이트"""
        tracker = RateLimitTracker()
        
        headers = {"Retry-After": "60"}
        tracker.update_from_headers(headers)
        
        assert tracker.retry_after == 60
    
    def test_should_warn_threshold(self) -> None:
        """경고 임계값"""
        tracker = RateLimitTracker()
        
        tracker.used_weight_1m = RateLimitThresholds.WEIGHT_WARN - 1
        assert tracker.should_warn is False
        
        tracker.used_weight_1m = RateLimitThresholds.WEIGHT_WARN
        assert tracker.should_warn is True
    
    def test_should_slow_down_threshold(self) -> None:
        """속도 저하 임계값"""
        tracker = RateLimitTracker()
        
        tracker.used_weight_1m = RateLimitThresholds.WEIGHT_SLOW - 1
        assert tracker.should_slow_down is False
        
        tracker.used_weight_1m = RateLimitThresholds.WEIGHT_SLOW
        assert tracker.should_slow_down is True
    
    def test_should_stop_threshold(self) -> None:
        """중단 임계값"""
        tracker = RateLimitTracker()
        
        tracker.used_weight_1m = RateLimitThresholds.WEIGHT_STOP - 1
        assert tracker.should_stop is False
        
        tracker.used_weight_1m = RateLimitThresholds.WEIGHT_STOP
        assert tracker.should_stop is True
    
    def test_remaining_weight(self) -> None:
        """남은 가중치 계산"""
        tracker = RateLimitTracker()
        tracker.used_weight_1m = 1000
        
        expected = RateLimitThresholds.WEIGHT_STOP - 1000
        assert tracker.remaining_weight == expected
    
    def test_remaining_weight_minimum_zero(self) -> None:
        """남은 가중치 최소 0"""
        tracker = RateLimitTracker()
        tracker.used_weight_1m = 3000  # 임계값 초과
        
        assert tracker.remaining_weight == 0
    
    def test_reset(self) -> None:
        """리셋"""
        tracker = RateLimitTracker()
        tracker.used_weight_1m = 1000
        tracker.order_count_1m = 50
        tracker.retry_after = 30
        
        tracker.reset()
        
        assert tracker.used_weight_1m == 0
        assert tracker.order_count_1m == 0
        assert tracker.retry_after == 0
    
    def test_to_dict(self) -> None:
        """딕셔너리 변환"""
        tracker = RateLimitTracker()
        tracker.used_weight_1m = 1600  # WARN 초과
        
        result = tracker.to_dict()
        
        assert result["used_weight_1m"] == 1600
        assert result["should_warn"] is True
        assert "last_updated" in result
