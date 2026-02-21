"""
BasePoller

모든 Poller의 베이스 클래스.
공통 폴링 로직과 마지막 폴링 시간 관리 제공.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone, timedelta
from typing import Any

from adapters.binance.rest_client import BinanceRestClient
from core.storage.event_store import EventStore
from core.storage.config_store import ConfigStore
from core.types import Scope

logger = logging.getLogger(__name__)


class BasePoller(ABC):
    """Poller 베이스 클래스
    
    주기적으로 REST API를 호출하여 이벤트를 수집하는 공통 로직 제공.
    
    Args:
        rest_client: Binance REST 클라이언트
        event_store: 이벤트 저장소
        config_store: 설정 저장소 (마지막 폴링 시간 저장)
        scope: 거래 범위
        poll_interval_seconds: 폴링 간격 (초)
    """
    
    def __init__(
        self,
        rest_client: BinanceRestClient,
        event_store: EventStore,
        config_store: ConfigStore,
        scope: Scope,
        poll_interval_seconds: int,
    ):
        self.rest_client = rest_client
        self.event_store = event_store
        self.config_store = config_store
        self.scope = scope
        self.poll_interval_seconds = poll_interval_seconds
        
        self._last_poll_time: datetime | None = None
        self._is_running: bool = False
    
    @property
    @abstractmethod
    def poller_name(self) -> str:
        """Poller 이름 (로깅 및 설정 키용)"""
        ...
    
    @property
    def config_key(self) -> str:
        """설정 저장 키"""
        return f"poller_{self.poller_name}_last_poll"
    
    async def initialize(self) -> None:
        """초기화: 마지막 폴링 시간 복구"""
        saved_state = await self.config_store.get(self.config_key)
        
        if saved_state and "last_poll_time" in saved_state:
            last_poll_str = saved_state["last_poll_time"]
            self._last_poll_time = datetime.fromisoformat(last_poll_str)
            
            logger.info(
                f"{self.poller_name} Poller 초기화: 마지막 폴링 시간 복구됨",
                extra={"last_poll_time": last_poll_str},
            )
        else:
            self._last_poll_time = None
            logger.info(f"{self.poller_name} Poller 초기화: 첫 실행")
    
    async def should_poll(self) -> bool:
        """폴링 필요 여부 확인
        
        마지막 폴링 이후 poll_interval_seconds가 경과했는지 확인.
        
        Returns:
            True if 폴링 필요, False otherwise
        """
        if self._is_running:
            return False
        
        if self._last_poll_time is None:
            return True
        
        now = datetime.now(timezone.utc)
        elapsed = (now - self._last_poll_time).total_seconds()
        
        return elapsed >= self.poll_interval_seconds
    
    async def poll(self) -> dict[str, Any]:
        """폴링 실행
        
        Returns:
            폴링 결과:
            {
                "events_created": int,
                "poll_time": datetime,
                "duration_ms": float,
            }
        """
        if self._is_running:
            logger.warning(f"{self.poller_name} Poller가 이미 실행 중입니다")
            return {"events_created": 0, "skipped": True}
        
        self._is_running = True
        start_time = datetime.now(timezone.utc)
        
        try:
            logger.debug(f"{self.poller_name} Poller 시작")
            
            since = self._get_poll_start_time()
            
            events_created = await self._do_poll(since)
            
            self._last_poll_time = start_time
            await self._save_last_poll_time()
            
            end_time = datetime.now(timezone.utc)
            duration_ms = (end_time - start_time).total_seconds() * 1000
            
            if events_created > 0:
                logger.info(
                    f"{self.poller_name} Poller 완료",
                    extra={
                        "events_created": events_created,
                        "duration_ms": duration_ms,
                    },
                )
            else:
                logger.debug(f"{self.poller_name} Poller 완료: 신규 이벤트 없음")
            
            return {
                "events_created": events_created,
                "poll_time": start_time,
                "duration_ms": duration_ms,
            }
            
        except Exception as e:
            logger.error(
                f"{self.poller_name} Poller 실패",
                extra={"error": str(e)},
                exc_info=True,
            )
            return {"events_created": 0, "error": str(e)}
            
        finally:
            self._is_running = False
    
    def _get_poll_start_time(self) -> datetime:
        """폴링 시작 시간 계산
        
        마지막 폴링 시간이 있으면 그 이후, 없으면 1시간 전부터.
        """
        if self._last_poll_time:
            return self._last_poll_time - timedelta(minutes=1)
        
        return datetime.now(timezone.utc) - timedelta(hours=1)
    
    async def _save_last_poll_time(self) -> None:
        """마지막 폴링 시간 저장"""
        if self._last_poll_time:
            await self.config_store.set(
                self.config_key,
                {"last_poll_time": self._last_poll_time.isoformat()},
            )
    
    @abstractmethod
    async def _do_poll(self, since: datetime) -> int:
        """실제 폴링 로직 구현
        
        Args:
            since: 이 시간 이후의 데이터만 조회
            
        Returns:
            생성된 이벤트 수
        """
        ...
    
    async def stop(self) -> None:
        """Poller 정지"""
        logger.info(f"{self.poller_name} Poller 정지")
        await self._save_last_poll_time()
