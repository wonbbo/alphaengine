"""
Volatility Indicators 테스트

ATR, Bollinger Bands 테스트
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

from strategies.indicators.volatility import atr, bollinger_bands


def create_sample_ohlcv(num_rows: int = 50) -> pd.DataFrame:
    """테스트용 OHLCV DataFrame 생성"""
    base_time = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    
    times = [base_time + timedelta(minutes=5 * i) for i in range(num_rows)]
    
    base_price = 100.0
    closes = [base_price + i * 0.5 + np.sin(i / 5) * 2 for i in range(num_rows)]
    highs = [c + 1.0 for c in closes]
    lows = [c - 1.0 for c in closes]
    opens = [c - 0.1 for c in closes]
    volumes = [1000000.0 + i * 10000 for i in range(num_rows)]
    
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


class TestAtr:
    """ATR 테스트"""
    
    def test_atr_basic(self):
        """기본 ATR 계산"""
        ohlcv = create_sample_ohlcv()
        
        result = atr(ohlcv, {"period": 14})
        
        assert isinstance(result, pd.Series)
        assert len(result) == len(ohlcv)
        # 처음 period-1개는 NaN
        assert pd.isna(result.iloc[0])
        assert not pd.isna(result.iloc[13])  # 14번째부터 값
    
    def test_atr_default_period(self):
        """기본 period = 14"""
        ohlcv = create_sample_ohlcv()
        
        result_default = atr(ohlcv, {})
        result_14 = atr(ohlcv, {"period": 14})
        
        # 마지막 값 비교 (float 비교이므로 근사치)
        assert abs(result_default.iloc[-1] - result_14.iloc[-1]) < 1e-10
    
    def test_atr_positive_values(self):
        """ATR은 항상 양수"""
        ohlcv = create_sample_ohlcv()
        
        result = atr(ohlcv, {"period": 14})
        
        # NaN 제외한 값은 모두 양수
        valid_values = result.dropna()
        assert (valid_values > 0).all()
    
    def test_atr_constant_range(self):
        """일정한 변동성에서 ATR 계산"""
        base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
        df = pd.DataFrame({
            "time": [base_time + timedelta(minutes=i) for i in range(20)],
            "open": [100.0] * 20,
            "high": [102.0] * 20,  # 항상 2 높음
            "low": [98.0] * 20,   # 항상 2 낮음
            "close": [100.0] * 20,
            "volume": [100.0] * 20,
        })
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df = df.set_index("time")
        
        result = atr(df, {"period": 5})
        
        # True Range = 4 (high - low), ATR = 4
        assert abs(result.iloc[-1] - 4.0) < 0.01


class TestBollingerBands:
    """볼린저 밴드 테스트"""
    
    def test_bollinger_bands_basic(self):
        """기본 볼린저 밴드 계산"""
        ohlcv = create_sample_ohlcv()
        
        upper, middle, lower = bollinger_bands(ohlcv, {"period": 20})
        
        assert isinstance(upper, pd.Series)
        assert isinstance(middle, pd.Series)
        assert isinstance(lower, pd.Series)
        assert len(upper) == len(ohlcv)
    
    def test_bollinger_bands_middle_is_sma(self):
        """중간 밴드는 SMA"""
        ohlcv = create_sample_ohlcv()
        
        from strategies.indicators.trend import sma
        
        _, middle, _ = bollinger_bands(ohlcv, {"period": 20})
        sma_20 = sma(ohlcv, {"period": 20})
        
        # 마지막 값 비교
        assert abs(middle.iloc[-1] - sma_20.iloc[-1]) < 1e-10
    
    def test_bollinger_bands_symmetry(self):
        """상하 밴드 대칭성"""
        ohlcv = create_sample_ohlcv()
        
        upper, middle, lower = bollinger_bands(ohlcv, {"period": 20})
        
        # upper - middle == middle - lower
        upper_distance = upper.iloc[-1] - middle.iloc[-1]
        lower_distance = middle.iloc[-1] - lower.iloc[-1]
        
        assert abs(upper_distance - lower_distance) < 1e-10
    
    def test_bollinger_bands_order(self):
        """상단 > 중간 > 하단 순서"""
        ohlcv = create_sample_ohlcv()
        
        upper, middle, lower = bollinger_bands(ohlcv, {"period": 20})
        
        valid_idx = ~(pd.isna(upper) | pd.isna(middle) | pd.isna(lower))
        
        assert (upper[valid_idx] >= middle[valid_idx]).all()
        assert (middle[valid_idx] >= lower[valid_idx]).all()
    
    def test_bollinger_bands_custom_std(self):
        """커스텀 표준편차 배수"""
        ohlcv = create_sample_ohlcv()
        
        upper1, middle1, lower1 = bollinger_bands(ohlcv, {"period": 20, "std_dev": 2.0})
        upper2, middle2, lower2 = bollinger_bands(ohlcv, {"period": 20, "std_dev": 3.0})
        
        # std_dev가 크면 밴드 폭도 커짐
        width1 = upper1.iloc[-1] - lower1.iloc[-1]
        width2 = upper2.iloc[-1] - lower2.iloc[-1]
        
        assert width2 > width1
