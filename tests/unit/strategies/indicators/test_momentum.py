"""
Momentum Indicators 테스트

RSI, Stochastic 테스트
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

from strategies.indicators.momentum import rsi, stochastic


def create_sample_ohlcv(num_rows: int = 50, trend: str = "up") -> pd.DataFrame:
    """테스트용 OHLCV DataFrame 생성
    
    Args:
        num_rows: 행 수
        trend: "up", "down", "flat" 중 하나
    """
    base_time = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    times = [base_time + timedelta(minutes=5 * i) for i in range(num_rows)]
    
    base_price = 100.0
    
    if trend == "up":
        closes = [base_price + i * 0.5 for i in range(num_rows)]
    elif trend == "down":
        closes = [base_price - i * 0.5 for i in range(num_rows)]
    else:  # flat
        closes = [base_price + np.sin(i / 5) * 2 for i in range(num_rows)]
    
    highs = [c + 1.0 for c in closes]
    lows = [c - 1.0 for c in closes]
    opens = [c - 0.1 for c in closes]
    volumes = [1000000.0] * num_rows
    
    df = pd.DataFrame({
        "time": times,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })
    
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.set_index("time")
    
    return df


class TestRsi:
    """RSI 테스트"""
    
    def test_rsi_basic(self):
        """기본 RSI 계산"""
        ohlcv = create_sample_ohlcv()
        
        result = rsi(ohlcv, {"period": 14})
        
        assert isinstance(result, pd.Series)
        assert len(result) == len(ohlcv)
        # 마지막 값은 유효해야 함
        assert not pd.isna(result.iloc[-1])
    
    def test_rsi_range(self):
        """RSI 범위는 0-100"""
        ohlcv = create_sample_ohlcv(100)
        
        result = rsi(ohlcv, {"period": 14})
        
        # NaN 제외한 값들 검증
        valid_values = result.dropna()
        assert (valid_values >= 0).all()
        assert (valid_values <= 100).all()
    
    def test_rsi_uptrend_high(self):
        """강한 상승 추세에서 RSI는 높음"""
        ohlcv = create_sample_ohlcv(50, trend="up")
        
        result = rsi(ohlcv, {"period": 14})
        
        # 상승 추세에서 RSI > 50
        assert result.iloc[-1] > 50
    
    def test_rsi_downtrend_low(self):
        """강한 하락 추세에서 RSI는 낮음"""
        ohlcv = create_sample_ohlcv(50, trend="down")
        
        result = rsi(ohlcv, {"period": 14})
        
        # 하락 추세에서 RSI < 50
        assert result.iloc[-1] < 50
    
    def test_rsi_default_period(self):
        """기본 period = 14"""
        ohlcv = create_sample_ohlcv()
        
        result_default = rsi(ohlcv, {})
        result_14 = rsi(ohlcv, {"period": 14})
        
        assert abs(result_default.iloc[-1] - result_14.iloc[-1]) < 1e-10


class TestStochastic:
    """Stochastic 테스트"""
    
    def test_stochastic_basic(self):
        """기본 Stochastic 계산"""
        ohlcv = create_sample_ohlcv()
        
        percent_k, percent_d = stochastic(ohlcv, {})
        
        assert isinstance(percent_k, pd.Series)
        assert isinstance(percent_d, pd.Series)
        assert len(percent_k) == len(ohlcv)
        assert len(percent_d) == len(ohlcv)
    
    def test_stochastic_range(self):
        """Stochastic 범위는 0-100"""
        ohlcv = create_sample_ohlcv(100)
        
        percent_k, percent_d = stochastic(ohlcv, {"k_period": 14})
        
        # 유효한 값만 검증
        valid_k = percent_k.dropna()
        valid_d = percent_d.dropna()
        
        assert (valid_k >= 0).all()
        assert (valid_k <= 100).all()
        assert (valid_d >= 0).all()
        assert (valid_d <= 100).all()
    
    def test_stochastic_uptrend_high(self):
        """상승 추세에서 Stochastic은 높음"""
        ohlcv = create_sample_ohlcv(50, trend="up")
        
        percent_k, _ = stochastic(ohlcv, {})
        
        # 최근 가격이 최고점 근처이므로 K > 50
        assert percent_k.iloc[-1] > 50
    
    def test_stochastic_d_is_smoothed_k(self):
        """%D는 %K의 이동평균"""
        ohlcv = create_sample_ohlcv()
        
        percent_k, percent_d = stochastic(ohlcv, {
            "k_period": 14,
            "d_period": 3,
            "smooth_k": 3,
        })
        
        # %D는 %K의 SMA(3)
        expected_d = percent_k.rolling(window=3).mean()
        
        # 마지막 값 비교
        assert abs(percent_d.iloc[-1] - expected_d.iloc[-1]) < 1e-10
    
    def test_stochastic_custom_periods(self):
        """커스텀 기간 설정"""
        ohlcv = create_sample_ohlcv()
        
        k1, d1 = stochastic(ohlcv, {
            "k_period": 14,
            "d_period": 3,
            "smooth_k": 3,
        })
        
        k2, d2 = stochastic(ohlcv, {
            "k_period": 5,
            "d_period": 5,
            "smooth_k": 1,
        })
        
        # 다른 기간이면 다른 결과
        assert k1.iloc[-1] != k2.iloc[-1]
