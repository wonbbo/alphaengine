"""
Volatility Indicators

변동성 관련 지표: ATR, Bollinger Bands 등
"""

from typing import Any

import pandas as pd
from ta.volatility import AverageTrueRange, BollingerBands

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

    return AverageTrueRange(ohlcv["high"], ohlcv["low"], ohlcv["close"], window=period).average_true_range().bfill()


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
        ...     "std_dev": 2.0,
        ... })
    """
    period = int(params.get("period", 20))
    std_dev = float(params.get("std_dev", 2.0))
    
    bollinger = BollingerBands(ohlcv["close"], window=period, std=std_dev)
    
    middle = bollinger.bollinger_mavg().bfill()
    upper = bollinger.bollinger_hband().bfill()
    lower = bollinger.bollinger_lband().bfill()

    return upper, middle, lower
