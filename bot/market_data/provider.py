"""
Market Data Provider

REST API를 통해 캔들스틱, 현재가 등 시장 데이터 조회.
전략에서 사용하는 OHLCV DataFrame을 제공.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Protocol

import pandas as pd

logger = logging.getLogger(__name__)


class IRestClient(Protocol):
    """REST 클라이언트 Protocol (MarketDataProvider 의존성)"""
    
    async def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> list[dict[str, Any]]:
        ...
    
    async def get_ticker_price(
        self,
        symbol: str | None = None,
    ) -> dict[str, str] | list[dict[str, str]]:
        ...


class MarketDataProvider:
    """시장 데이터 제공자
    
    REST API를 통해 캔들스틱(Kline) 데이터를 조회하고
    전략에서 사용하는 형식으로 변환.
    
    Args:
        rest_client: Binance REST 클라이언트
        default_timeframe: 기본 시간 간격 (기본: 5m)
        default_limit: 기본 조회 개수 (기본: 100)
        cache_ttl_seconds: 캐시 유효 시간 (초, 기본: 60)
        
    사용 예시:
    ```python
    provider = MarketDataProvider(rest_client)
    
    # OHLCV DataFrame 조회 (권장)
    ohlcv = await provider.get_ohlcv(symbol="XRPUSDT", timeframe="5m", limit=100)
    
    # 현재가 조회
    price = await provider.get_current_price("XRPUSDT")
    ```
    """
    
    # 유효한 timeframe 목록
    VALID_TIMEFRAMES = {
        "1m", "3m", "5m", "15m", "30m",
        "1h", "2h", "4h", "6h", "8h", "12h",
        "1d", "3d", "1w", "1M",
    }
    
    def __init__(
        self,
        rest_client: IRestClient,
        default_timeframe: str = "5m",
        default_limit: int = 100,
        cache_ttl_seconds: int = 60,
    ):
        self.rest_client = rest_client
        self.default_timeframe = default_timeframe
        self.default_limit = default_limit
        self.cache_ttl_seconds = cache_ttl_seconds
        
        # 간단한 캐시 (symbol:timeframe -> (timestamp, data))
        self._cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
        # OHLCV DataFrame 캐시
        self._ohlcv_cache: dict[str, tuple[float, pd.DataFrame]] = {}
    
    async def get_bars(
        self,
        symbol: str,
        timeframe: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """캔들스틱(Bar) 데이터 조회
        
        Args:
            symbol: 거래 심볼 (예: XRPUSDT)
            timeframe: 시간 간격 (None이면 기본값 사용)
            limit: 조회 개수 (None이면 기본값 사용)
            
        Returns:
            Bar 데이터 리스트 (오래된 것부터 최신 순)
            각 항목: {
                "ts": datetime,    # 시작 시간 (UTC)
                "open": str,       # 시가
                "high": str,       # 고가
                "low": str,        # 저가
                "close": str,      # 종가
                "volume": str,     # 거래량
            }
        """
        timeframe = timeframe or self.default_timeframe
        limit = limit or self.default_limit
        
        # timeframe 검증
        if timeframe not in self.VALID_TIMEFRAMES:
            logger.warning(f"Invalid timeframe: {timeframe}, using default: {self.default_timeframe}")
            timeframe = self.default_timeframe
        
        # 캐시 확인
        cache_key = f"{symbol}:{timeframe}"
        cached = self._get_from_cache(cache_key)
        if cached is not None:
            logger.debug(f"Cache hit for {cache_key}")
            return cached[:limit]
        
        # API 호출
        try:
            klines = await self.rest_client.get_klines(
                symbol=symbol,
                interval=timeframe,
                limit=limit,
            )
            
            # Bar 형식으로 변환
            bars = self._convert_klines_to_bars(klines)
            
            # 캐시에 저장
            self._set_cache(cache_key, bars)
            
            logger.debug(
                f"Fetched {len(bars)} bars for {symbol} ({timeframe})",
            )
            
            return bars
            
        except Exception as e:
            logger.error(f"Failed to get bars: {e}")
            return []
    
    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        """OHLCV DataFrame 조회
        
        Args:
            symbol: 거래 심볼 (예: XRPUSDT)
            timeframe: 시간 간격 (None이면 기본값 사용)
            limit: 조회 개수 (None이면 기본값 사용)
            
        Returns:
            OHLCV DataFrame
            - Index: DatetimeIndex (UTC, timezone-aware), name='time'
            - Columns: open, high, low, close, volume (float64)
            
        Example:
            >>> ohlcv = await provider.get_ohlcv("XRPUSDT", "5m", 100)
            >>> ohlcv.index  # DatetimeIndex
            >>> ohlcv["close"].iloc[-1]  # 최신 종가
        """
        timeframe = timeframe or self.default_timeframe
        limit = limit or self.default_limit
        
        # timeframe 검증
        if timeframe not in self.VALID_TIMEFRAMES:
            logger.warning(f"Invalid timeframe: {timeframe}, using default: {self.default_timeframe}")
            timeframe = self.default_timeframe
        
        # OHLCV 캐시 확인
        cache_key = f"{symbol}:{timeframe}"
        cached_df = self._get_ohlcv_from_cache(cache_key, limit)
        if cached_df is not None:
            logger.debug(f"OHLCV cache hit for {cache_key}")
            return cached_df
        
        # API 호출
        try:
            klines = await self.rest_client.get_klines(
                symbol=symbol,
                interval=timeframe,
                limit=limit,
            )
            
            # DataFrame으로 변환
            ohlcv = self._convert_klines_to_ohlcv(klines)
            
            # 캐시에 저장
            self._set_ohlcv_cache(cache_key, ohlcv)
            
            logger.debug(
                f"Fetched {len(ohlcv)} OHLCV rows for {symbol} ({timeframe})",
            )
            
            return ohlcv
            
        except Exception as e:
            logger.error(f"Failed to get OHLCV: {e}")
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    
    def _convert_klines_to_ohlcv(
        self,
        klines: list[dict[str, Any]],
    ) -> pd.DataFrame:
        """Kline 데이터를 OHLCV DataFrame으로 변환
        
        Returns:
            DataFrame with DatetimeIndex 'time' and columns: open, high, low, close, volume
        """
        if not klines:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        
        # 데이터 추출
        data = []
        for kline in klines:
            open_time_ms = kline.get("open_time", 0)
            time = datetime.fromtimestamp(open_time_ms / 1000, tz=timezone.utc)
            
            data.append({
                "time": time,
                "open": float(kline.get("open", 0)),
                "high": float(kline.get("high", 0)),
                "low": float(kline.get("low", 0)),
                "close": float(kline.get("close", 0)),
                "volume": float(kline.get("volume", 0)),
            })
        
        # DataFrame 생성
        df = pd.DataFrame(data)
        
        # time 컬럼을 DatetimeIndex로 설정
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df = df.set_index("time")
        
        return df
    
    def _get_ohlcv_from_cache(self, key: str, limit: int) -> pd.DataFrame | None:
        """OHLCV 캐시에서 데이터 조회"""
        if key not in self._ohlcv_cache:
            return None
        
        timestamp, df = self._ohlcv_cache[key]
        now = datetime.now(timezone.utc).timestamp()
        
        # TTL 확인
        if now - timestamp > self.cache_ttl_seconds:
            del self._ohlcv_cache[key]
            return None
        
        # limit 적용하여 반환
        return df.iloc[-limit:] if len(df) > limit else df
    
    def _set_ohlcv_cache(self, key: str, df: pd.DataFrame) -> None:
        """OHLCV 캐시에 데이터 저장"""
        now = datetime.now(timezone.utc).timestamp()
        self._ohlcv_cache[key] = (now, df)
    
    async def get_current_price(self, symbol: str) -> Decimal | None:
        """현재가 조회
        
        Args:
            symbol: 거래 심볼
            
        Returns:
            현재가 (Decimal) 또는 None
        """
        try:
            data = await self.rest_client.get_ticker_price(symbol=symbol)
            
            if isinstance(data, dict) and "price" in data:
                return Decimal(data["price"])
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get current price: {e}")
            return None
    
    def _convert_klines_to_bars(
        self,
        klines: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Kline 데이터를 Bar 형식으로 변환"""
        bars = []
        
        for kline in klines:
            # open_time을 datetime으로 변환
            open_time_ms = kline.get("open_time", 0)
            ts = datetime.fromtimestamp(open_time_ms / 1000, tz=timezone.utc)
            
            bars.append({
                "ts": ts,
                "open": kline.get("open", "0"),
                "high": kline.get("high", "0"),
                "low": kline.get("low", "0"),
                "close": kline.get("close", "0"),
                "volume": kline.get("volume", "0"),
            })
        
        return bars
    
    def _get_from_cache(self, key: str) -> list[dict[str, Any]] | None:
        """캐시에서 데이터 조회"""
        if key not in self._cache:
            return None
        
        timestamp, data = self._cache[key]
        now = datetime.now(timezone.utc).timestamp()
        
        # TTL 확인
        if now - timestamp > self.cache_ttl_seconds:
            del self._cache[key]
            return None
        
        return data
    
    def _set_cache(self, key: str, data: list[dict[str, Any]]) -> None:
        """캐시에 데이터 저장"""
        now = datetime.now(timezone.utc).timestamp()
        self._cache[key] = (now, data)
    
    def clear_cache(self) -> None:
        """캐시 초기화"""
        self._cache.clear()
        self._ohlcv_cache.clear()
        logger.debug("Market data cache cleared")
    
    def invalidate_cache(self, symbol: str, timeframe: str | None = None) -> None:
        """특정 심볼/타임프레임 캐시 무효화"""
        if timeframe:
            key = f"{symbol}:{timeframe}"
            if key in self._cache:
                del self._cache[key]
            if key in self._ohlcv_cache:
                del self._ohlcv_cache[key]
        else:
            # 해당 심볼의 모든 캐시 삭제
            keys_to_delete = [k for k in self._cache if k.startswith(f"{symbol}:")]
            for key in keys_to_delete:
                del self._cache[key]
            
            ohlcv_keys_to_delete = [k for k in self._ohlcv_cache if k.startswith(f"{symbol}:")]
            for key in ohlcv_keys_to_delete:
                del self._ohlcv_cache[key]
