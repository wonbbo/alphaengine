"""
Indicators - 기술적 지표 라이브러리

OHLCV DataFrame을 입력으로 받아 pd.Series 또는 tuple[pd.Series, ...]를 반환하는
재사용 가능한 indicator 함수들을 제공합니다.

사용법:
    from strategies.indicators import sma, ema, atr, rsi, macd

    # 단일 리턴 indicator
    sma_20 = sma(ohlcv, {"period": 20})
    atr_14 = atr(ohlcv, {"period": 14})
    rsi_14 = rsi(ohlcv, {"period": 14})
    
    # 복수 리턴 indicator
    macd_line, signal, histogram = macd(ohlcv, {})
    upper, middle, lower = bollinger_bands(ohlcv, {"period": 20})
    percent_k, percent_d = stochastic(ohlcv, {})

OHLCV DataFrame 표준:
    - Index: DatetimeIndex (UTC, timezone-aware), name='time'
    - Columns: open, high, low, close, volume (float64)
"""

# Trend Indicators
from strategies.indicators.trend import (
    sma,
    ema,
    macd,
)

# Volatility Indicators
from strategies.indicators.volatility import (
    atr,
    bollinger_bands,
)

# Momentum Indicators
from strategies.indicators.momentum import (
    rsi,
    stochastic,
)

__all__ = [
    # Trend
    "sma",
    "ema",
    "macd",
    # Volatility
    "atr",
    "bollinger_bands",
    # Momentum
    "rsi",
    "stochastic",
]
