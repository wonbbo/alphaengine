"""
Momentum Indicators

모멘텀 관련 지표: RSI, Stochastic 등
"""

from typing import Any

import pandas as pd


def rsi(ohlcv: pd.DataFrame, params: dict[str, Any]) -> pd.Series:
    """Relative Strength Index (RSI)
    
    Args:
        ohlcv: OHLCV DataFrame
        params: {
            "period": int (선택, 기본 14)
            "source": str (선택, 기본 "close")
        }
        
    Returns:
        pd.Series: RSI 값 (0-100 범위)
        
    Example:
        >>> rsi_14 = rsi(ohlcv, {"period": 14})
        >>> rsi_7 = rsi(ohlcv, {"period": 7})
    """
    period = int(params.get("period", 14))
    source = params.get("source", "close")
    
    delta = ohlcv[source].diff()
    
    # 상승/하락 분리
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    
    # EMA 사용 (Wilder's smoothing)
    avg_gain = gain.ewm(span=period, adjust=False).mean()
    avg_loss = loss.ewm(span=period, adjust=False).mean()
    
    # RS 계산
    # avg_loss가 0이면 RSI는 100 (순수 상승)
    # avg_gain이 0이면 RSI는 0 (순수 하락)
    
    # 기본 케이스: avg_loss > 0
    rs = avg_gain / avg_loss
    # inf 처리 (avg_loss가 0일 때 발생)
    rs = rs.replace([float("inf"), -float("inf")], float("nan"))
    rsi_values = 100 - (100 / (1 + rs))
    
    # avg_loss가 0인 경우 처리 (순수 상승 → RSI = 100)
    rsi_values = rsi_values.where(avg_loss != 0, 100.0)
    
    # avg_gain이 0인 경우 처리 (순수 하락 → RSI = 0)
    rsi_values = rsi_values.where(avg_gain != 0, 0.0)
    
    return rsi_values


def stochastic(
    ohlcv: pd.DataFrame,
    params: dict[str, Any],
) -> tuple[pd.Series, pd.Series]:
    """Stochastic Oscillator
    
    Args:
        ohlcv: OHLCV DataFrame
        params: {
            "k_period": int (선택, 기본 14) - %K 기간
            "d_period": int (선택, 기본 3) - %D smoothing
            "smooth_k": int (선택, 기본 3) - %K smoothing
        }
        
    Returns:
        tuple[pd.Series, pd.Series]:
            - percent_k: %K 라인 (Slow %K)
            - percent_d: %D 라인 (시그널)
            
    Example:
        >>> percent_k, percent_d = stochastic(ohlcv, {})
        >>> percent_k, percent_d = stochastic(ohlcv, {
        ...     "k_period": 14,
        ...     "d_period": 3,
        ...     "smooth_k": 3,
        ... })
    """
    k_period = int(params.get("k_period", 14))
    d_period = int(params.get("d_period", 3))
    smooth_k = int(params.get("smooth_k", 3))
    
    low_min = ohlcv["low"].rolling(window=k_period).min()
    high_max = ohlcv["high"].rolling(window=k_period).max()
    
    # 분모가 0인 경우 처리
    denominator = high_max - low_min
    denominator = denominator.replace(0, float("nan"))
    
    # Fast %K
    fast_k = 100 * (ohlcv["close"] - low_min) / denominator
    
    # Slow %K (Fast %K의 SMA)
    percent_k = fast_k.rolling(window=smooth_k).mean()
    
    # %D (Slow %K의 SMA)
    percent_d = percent_k.rolling(window=d_period).mean()
    
    return percent_k, percent_d
