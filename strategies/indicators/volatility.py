"""
Volatility Indicators

변동성 관련 지표: ATR, Bollinger Bands 등
"""

from typing import Any

import pandas as pd


def atr(ohlcv: pd.DataFrame, params: dict[str, Any]) -> pd.Series:
    """Average True Range
    
    Args:
        ohlcv: OHLCV DataFrame
        params: {
            "period": int (선택, 기본 14)
        }
        
    Returns:
        pd.Series: ATR 값
        
    Example:
        >>> atr_14 = atr(ohlcv, {"period": 14})
        >>> atr_20 = atr(ohlcv, {"period": 20})
    """
    period = int(params.get("period", 14))
    
    high = ohlcv["high"]
    low = ohlcv["low"]
    close = ohlcv["close"]
    prev_close = close.shift(1)
    
    # True Range 계산
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # ATR = True Range의 이동평균
    return true_range.rolling(window=period).mean()


def bollinger_bands(
    ohlcv: pd.DataFrame,
    params: dict[str, Any],
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """볼린저 밴드 (Bollinger Bands)
    
    Args:
        ohlcv: OHLCV DataFrame
        params: {
            "period": int (선택, 기본 20)
            "std_dev": float (선택, 기본 2.0)
            "source": str (선택, 기본 "close")
        }
        
    Returns:
        tuple[pd.Series, pd.Series, pd.Series]:
            - upper: 상단 밴드
            - middle: 중간 밴드 (SMA)
            - lower: 하단 밴드
            
    Example:
        >>> upper, middle, lower = bollinger_bands(ohlcv, {"period": 20})
        >>> upper, middle, lower = bollinger_bands(ohlcv, {
        ...     "period": 20,
        ...     "std_dev": 2.5,
        ... })
    """
    period = int(params.get("period", 20))
    std_dev = float(params.get("std_dev", 2.0))
    source = params.get("source", "close")
    
    prices = ohlcv[source]
    
    middle = prices.rolling(window=period).mean()
    std = prices.rolling(window=period).std()
    
    upper = middle + (std * std_dev)
    lower = middle - (std * std_dev)
    
    return upper, middle, lower
