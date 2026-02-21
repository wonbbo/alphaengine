"""
PriceCachePoller

주기적으로 주요 자산의 가격을 조회하여 config_store에 캐시.
Bot에서 조회, Web에서 사용 (Hybrid 방식).

- Bot 메인 루프에서 주기적으로 호출
- REST API로 가격 조회 후 config_store에 저장
- Web의 asset_service에서 캐시된 가격 사용
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from adapters.binance.rest_client import BinanceRestClient
from core.storage.config_store import ConfigStore

logger = logging.getLogger(__name__)


# 캐시할 자산 심볼 목록 (USDT 페어)
DEFAULT_CACHE_SYMBOLS = [
    "BNBUSDT",  # BNB
    "BTCUSDT",  # Bitcoin
    "ETHUSDT",  # Ethereum
    "XRPUSDT",  # XRP
    "USDCUSDT",  # USDC (스테이블코인)
]


class PriceCachePoller:
    """가격 캐시 Poller
    
    주기적으로 REST API로 가격을 조회하여 config_store에 저장.
    
    Args:
        rest_client: Binance REST 클라이언트
        config_store: 설정 저장소
        symbols: 캐시할 심볼 목록 (기본: BNBUSDT, BTCUSDT, ETHUSDT, XRPUSDT)
        poll_interval_seconds: 폴링 간격 (기본: 60초)
    
    사용 예시:
    ```python
    poller = PriceCachePoller(
        rest_client=rest_client,
        config_store=config_store,
        symbols=["BNBUSDT", "BTCUSDT"],
        poll_interval_seconds=60,
    )
    
    # 메인 루프에서 호출
    if await poller.should_poll():
        await poller.poll()
    ```
    """
    
    def __init__(
        self,
        rest_client: BinanceRestClient,
        config_store: ConfigStore,
        symbols: list[str] | None = None,
        poll_interval_seconds: int = 60,
    ):
        self.rest_client = rest_client
        self.config_store = config_store
        self.symbols = symbols or DEFAULT_CACHE_SYMBOLS
        self.poll_interval_seconds = poll_interval_seconds
        
        self._last_poll_time: datetime | None = None
        self._is_running: bool = False
    
    @property
    def poller_name(self) -> str:
        """Poller 이름"""
        return "price_cache"
    
    async def should_poll(self) -> bool:
        """폴링 필요 여부 확인"""
        if self._is_running:
            return False
        
        if self._last_poll_time is None:
            return True
        
        now = datetime.now(timezone.utc)
        elapsed = (now - self._last_poll_time).total_seconds()
        
        return elapsed >= self.poll_interval_seconds
    
    async def poll(self) -> dict[str, Any]:
        """가격 조회 및 캐시 업데이트
        
        Returns:
            폴링 결과:
            {
                "prices_updated": int,
                "poll_time": datetime,
                "duration_ms": float,
            }
        """
        if self._is_running:
            logger.debug("PriceCachePoller가 이미 실행 중입니다")
            return {"prices_updated": 0, "skipped": True}
        
        self._is_running = True
        start_time = datetime.now(timezone.utc)
        
        try:
            prices_to_cache: dict[str, str] = {}
            
            # 각 심볼의 가격 조회
            for symbol in self.symbols:
                try:
                    price = await self._fetch_price(symbol)
                    if price:
                        prices_to_cache[symbol] = str(price)
                except Exception as e:
                    logger.warning(f"가격 조회 실패 ({symbol}): {e}")
            
            # 캐시 업데이트 (하나라도 있으면)
            if prices_to_cache:
                await self.config_store.update_price_cache(prices_to_cache)
                logger.debug(
                    f"가격 캐시 업데이트 완료: {len(prices_to_cache)}개",
                    extra={"prices": prices_to_cache},
                )
            
            self._last_poll_time = start_time
            
            end_time = datetime.now(timezone.utc)
            duration_ms = (end_time - start_time).total_seconds() * 1000
            
            return {
                "prices_updated": len(prices_to_cache),
                "poll_time": start_time,
                "duration_ms": duration_ms,
            }
            
        except Exception as e:
            logger.error(f"PriceCachePoller 실패: {e}", exc_info=True)
            return {"prices_updated": 0, "error": str(e)}
            
        finally:
            self._is_running = False
    
    async def _fetch_price(self, symbol: str) -> Decimal | None:
        """특정 심볼의 현재 가격 조회
        
        Args:
            symbol: 심볼 (예: BNBUSDT)
            
        Returns:
            현재가 또는 None
        """
        try:
            data = await self.rest_client.get_ticker_price(symbol=symbol)
            
            if isinstance(data, dict) and "price" in data:
                return Decimal(data["price"])
            
            return None
            
        except Exception as e:
            logger.debug(f"가격 조회 실패 ({symbol}): {e}")
            return None
    
    async def stop(self) -> None:
        """Poller 정지"""
        logger.debug("PriceCachePoller 정지")
