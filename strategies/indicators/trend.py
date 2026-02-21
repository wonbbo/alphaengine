"""
Trend Indicators

추세 관련 지표: SMA, EMA, MACD 등
"""

from typing import Any

import pandas as pd


def sma(ohlcv: pd.DataFrame, params: dict[str, Any]) -> pd.Series:
    """단순 이동평균 (Simple Moving Average)
    
    Args:
        ohlcv: OHLCV DataFrame
        params: {
            "period": int (필수) - 이동평균 기간
            "source": str (선택, 기본 "close") - 계산 대상 컬럼
        }
        
    Returns:
        pd.Series: SMA 값 (같은 index)
        
    Raises:
        ValueError: period 파라미터 누락 시
        
    Example:
        >>> sma_20 = sma(ohlcv, {"period": 20})
        >>> sma_5_high = sma(ohlcv, {"period": 5, "source": "high"})
    """
    period = params.get("period")
    if period is None:
        raise ValueError("params['period'] is required for SMA")
    
    source = params.get("source", "close")
    
    return ohlcv[source].rolling(window=int(period)).mean()


def ema(ohlcv: pd.DataFrame, params: dict[str, Any]) -> pd.Series:
    """지수 이동평균 (Exponential Moving Average)
    
    Args:
        ohlcv: OHLCV DataFrame
        params: {
            "period": int (필수) - EMA 기간
            "source": str (선택, 기본 "close") - 계산 대상 컬럼
        }
        
    Returns:
        pd.Series: EMA 값
        
    Raises:
        ValueError: period 파라미터 누락 시
        
    Example:
        >>> ema_12 = ema(ohlcv, {"period": 12})
        >>> ema_26 = ema(ohlcv, {"period": 26})
    """
    period = params.get("period")
    if period is None:
        raise ValueError("params['period'] is required for EMA")
    
    source = params.get("source", "close")
    
    return ohlcv[source].ewm(span=int(period), adjust=False).mean()


def macd(
    ohlcv: pd.DataFrame,
    params: dict[str, Any],
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """MACD (Moving Average Convergence Divergence)
    
    Args:
        ohlcv: OHLCV DataFrame
        params: {
            "fast_period": int (선택, 기본 12)
            "slow_period": int (선택, 기본 26)
            "signal_period": int (선택, 기본 9)
            "source": str (선택, 기본 "close")
        }
        
    Returns:
        tuple[pd.Series, pd.Series, pd.Series]:
            - macd_line: MACD 라인 (fast_ema - slow_ema)
            - signal_line: 시그널 라인 (macd의 EMA)
            - histogram: 히스토그램 (macd - signal)
            
    Example:
        >>> macd_line, signal, hist = macd(ohlcv, {})
        >>> macd_line, signal, hist = macd(ohlcv, {
        ...     "fast_period": 8,
        ...     "slow_period": 21,
        ...     "signal_period": 5,
        ... })
    """
    fast = int(params.get("fast_period", 12))
    slow = int(params.get("slow_period", 26))
    signal_period = int(params.get("signal_period", 9))
    source = params.get("source", "close")
    
    prices = ohlcv[source]
    
    fast_ema = prices.ewm(span=fast, adjust=False).mean()
    slow_ema = prices.ewm(span=slow, adjust=False).mean()
    
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    histogram = macd_line - signal_line
    
    return macd_line, signal_line, histogram
