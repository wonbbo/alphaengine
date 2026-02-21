"""
Trend Indicators 테스트

SMA, EMA, MACD 테스트
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

from strategies.indicators.trend import sma, ema, macd


def create_sample_ohlcv(num_rows: int = 50) -> pd.DataFrame:
    """테스트용 OHLCV DataFrame 생성"""
    base_time = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    
    # 시간 인덱스 생성
    times = [base_time + timedelta(minutes=5 * i) for i in range(num_rows)]
    
    # 가격 데이터 생성 (상승 추세)
    base_price = 100.0
    closes = [base_price + i * 0.5 + np.sin(i / 5) * 2 for i in range(num_rows)]
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
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


class TestSma:
    """SMA 테스트"""
    
    def test_sma_basic(self):
        """기본 SMA 계산"""
        ohlcv = create_sample_ohlcv(30)
        
        result = sma(ohlcv, {"period": 5})
        
        assert isinstance(result, pd.Series)
        assert len(result) == 30
        # 처음 4개는 NaN
        assert pd.isna(result.iloc[0])
        assert pd.isna(result.iloc[3])
        # 5번째부터 값 있음
        assert not pd.isna(result.iloc[4])
    
    def test_sma_period_required(self):
        """period 파라미터 필수"""
        ohlcv = create_sample_ohlcv()
        
        with pytest.raises(ValueError, match="period"):
            sma(ohlcv, {})
    
    def test_sma_custom_source(self):
        """다른 source 컬럼 사용"""
        ohlcv = create_sample_ohlcv()
        
        result_close = sma(ohlcv, {"period": 5, "source": "close"})
        result_high = sma(ohlcv, {"period": 5, "source": "high"})
        
        # high가 close보다 높으므로 SMA도 높아야 함
        assert result_high.iloc[-1] > result_close.iloc[-1]
    
    def test_sma_calculation_accuracy(self):
        """SMA 계산 정확성"""
        # 간단한 데이터로 수동 검증
        base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
        df = pd.DataFrame({
            "time": [base_time + timedelta(minutes=i) for i in range(5)],
            "open": [10.0, 10.0, 10.0, 10.0, 10.0],
            "high": [11.0, 11.0, 11.0, 11.0, 11.0],
            "low": [9.0, 9.0, 9.0, 9.0, 9.0],
            "close": [10.0, 20.0, 30.0, 40.0, 50.0],
            "volume": [100.0, 100.0, 100.0, 100.0, 100.0],
        })
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df = df.set_index("time")
        
        result = sma(df, {"period": 5})
        
        # SMA(5) = (10 + 20 + 30 + 40 + 50) / 5 = 30
        assert result.iloc[-1] == 30.0


class TestEma:
    """EMA 테스트"""
    
    def test_ema_basic(self):
        """기본 EMA 계산"""
        ohlcv = create_sample_ohlcv()
        
        result = ema(ohlcv, {"period": 12})
        
        assert isinstance(result, pd.Series)
        assert len(result) == len(ohlcv)
        # EMA는 첫 값부터 계산됨 (NaN 없음, 단 첫 몇 개는 불안정)
        assert not pd.isna(result.iloc[-1])
    
    def test_ema_period_required(self):
        """period 파라미터 필수"""
        ohlcv = create_sample_ohlcv()
        
        with pytest.raises(ValueError, match="period"):
            ema(ohlcv, {})
    
    def test_ema_more_responsive_than_sma(self):
        """EMA는 SMA보다 최근 가격에 민감"""
        ohlcv = create_sample_ohlcv(30)
        
        sma_result = sma(ohlcv, {"period": 10})
        ema_result = ema(ohlcv, {"period": 10})
        
        # 상승 추세에서 EMA가 SMA보다 높아야 함 (최근 가격 반영)
        assert ema_result.iloc[-1] > sma_result.iloc[-1]


class TestMacd:
    """MACD 테스트"""
    
    def test_macd_basic(self):
        """기본 MACD 계산"""
        ohlcv = create_sample_ohlcv(50)
        
        macd_line, signal, histogram = macd(ohlcv, {})
        
        assert isinstance(macd_line, pd.Series)
        assert isinstance(signal, pd.Series)
        assert isinstance(histogram, pd.Series)
        assert len(macd_line) == len(ohlcv)
        assert len(signal) == len(ohlcv)
        assert len(histogram) == len(ohlcv)
    
    def test_macd_histogram_equals_difference(self):
        """히스토그램 = MACD - Signal"""
        ohlcv = create_sample_ohlcv()
        
        macd_line, signal, histogram = macd(ohlcv, {})
        
        # 마지막 값에서 히스토그램 검증
        expected = macd_line.iloc[-1] - signal.iloc[-1]
        assert abs(histogram.iloc[-1] - expected) < 1e-10
    
    def test_macd_custom_periods(self):
        """커스텀 기간 설정"""
        ohlcv = create_sample_ohlcv()
        
        macd_line1, _, _ = macd(ohlcv, {
            "fast_period": 8,
            "slow_period": 21,
            "signal_period": 5,
        })
        
        macd_line2, _, _ = macd(ohlcv, {
            "fast_period": 12,
            "slow_period": 26,
            "signal_period": 9,
        })
        
        # 다른 기간이면 다른 결과
        assert macd_line1.iloc[-1] != macd_line2.iloc[-1]
