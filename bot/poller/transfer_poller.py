"""
TransferPoller

SPOT ↔ FUTURES 이체 이력을 주기적으로 폴링.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from bot.poller.base import BasePoller
from adapters.binance.rest_client import BinanceRestClient
from core.domain.events import Event, EventTypes
from core.storage.event_store import EventStore
from core.storage.config_store import ConfigStore
from core.types import Scope
from core.utils.dedup import make_transfer_dedup_key

logger = logging.getLogger(__name__)


class TransferPoller(BasePoller):
    """Transfer History Poller
    
    SPOT ↔ FUTURES 내부 이체 이력을 30분마다 폴링.
    
    Args:
        rest_client: Binance REST 클라이언트
        event_store: 이벤트 저장소
        config_store: 설정 저장소
        scope: 거래 범위
        poll_interval_seconds: 폴링 간격 (기본 30분)
    """
    
    DEFAULT_POLL_INTERVAL = 30 * 60
    
    TRANSFER_TYPES = ["MAIN_UMFUTURE", "UMFUTURE_MAIN"]
    
    def __init__(
        self,
        rest_client: BinanceRestClient,
        event_store: EventStore,
        config_store: ConfigStore,
        scope: Scope,
        poll_interval_seconds: int | None = None,
    ):
        super().__init__(
            rest_client=rest_client,
            event_store=event_store,
            config_store=config_store,
            scope=scope,
            poll_interval_seconds=poll_interval_seconds or self.DEFAULT_POLL_INTERVAL,
        )
    
    @property
    def poller_name(self) -> str:
        return "transfer"
    
    async def _do_poll(self, since: datetime) -> int:
        """Transfer History 폴링 실행"""
        events_created = 0
        
        start_ms = int(since.timestamp() * 1000)
        end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        
        for transfer_type in self.TRANSFER_TYPES:
            try:
                current_page = 1
                
                while True:
                    result = await self.rest_client.get_transfer_history(
                        transfer_type=transfer_type,
                        start_time=start_ms,
                        end_time=end_ms,
                        current=current_page,
                        size=100,
                    )
                    
                    rows = result.get("rows", [])
                    if not rows:
                        break
                    
                    for transfer in rows:
                        saved = await self._create_transfer_event(transfer)
                        if saved:
                            events_created += 1
                    
                    if len(rows) < 100:
                        break
                    
                    current_page += 1
                    
            except Exception as e:
                logger.error(f"Transfer History 조회 실패 ({transfer_type}): {e}")
        
        return events_created
    
    async def _create_transfer_event(self, transfer: dict[str, Any]) -> bool:
        """Transfer 데이터를 이벤트로 변환 및 저장"""
        tran_id = str(transfer.get("tranId", 0))
        
        dedup_key = make_transfer_dedup_key(
            exchange=self.scope.exchange,
            transfer_id=tran_id,
        )
        
        payload = {
            "asset": transfer.get("asset", "USDT"),
            "amount": transfer.get("amount", "0"),
            "type": transfer.get("type", ""),
            "status": transfer.get("status", ""),
            "tran_id": tran_id,
            "timestamp": transfer.get("timestamp", 0),
            "source": "poller",
        }
        
        ts_ms = transfer.get("timestamp", 0)
        event_ts = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc) if ts_ms else datetime.now(timezone.utc)
        
        base_event = Event.create(
            event_type=EventTypes.INTERNAL_TRANSFER_COMPLETED,
            source="BOT",
            entity_kind="TRANSFER",
            entity_id=tran_id,
            scope=self.scope,
            dedup_key=dedup_key,
            payload=payload,
        )
        
        event = Event(
            event_id=base_event.event_id,
            event_type=base_event.event_type,
            ts=event_ts,
            correlation_id=base_event.correlation_id,
            causation_id=base_event.causation_id,
            command_id=base_event.command_id,
            source=base_event.source,
            entity_kind=base_event.entity_kind,
            entity_id=base_event.entity_id,
            scope=base_event.scope,
            dedup_key=base_event.dedup_key,
            payload=base_event.payload,
        )
        
        return await self.event_store.append(event)
