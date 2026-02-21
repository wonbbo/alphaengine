"""
ConvertPoller

간편 전환(Convert) 이력을 주기적으로 폴링.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from bot.poller.base import BasePoller
from adapters.binance.rest_client import BinanceRestClient
from core.domain.events import Event, EventTypes
from core.storage.event_store import EventStore
from core.storage.config_store import ConfigStore
from core.types import Scope
from core.utils.dedup import make_convert_dedup_key

logger = logging.getLogger(__name__)


class ConvertPoller(BasePoller):
    """Convert Trade History Poller
    
    간편 전환(Convert) 이력을 1시간마다 폴링.
    
    Args:
        rest_client: Binance REST 클라이언트
        event_store: 이벤트 저장소
        config_store: 설정 저장소
        scope: 거래 범위
        poll_interval_seconds: 폴링 간격 (기본 1시간)
    """
    
    DEFAULT_POLL_INTERVAL = 60 * 60
    
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
        return "convert"
    
    async def _do_poll(self, since: datetime) -> int:
        """Convert History 폴링 실행"""
        events_created = 0
        
        start_ms = int(since.timestamp() * 1000)
        end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        
        try:
            result = await self.rest_client.get_convert_history(
                start_time=start_ms,
                end_time=end_ms,
                limit=1000,
            )
            
            convert_list = result.get("list", [])
            
            for convert in convert_list:
                saved = await self._create_convert_event(convert)
                if saved:
                    events_created += 1
                    
        except Exception as e:
            logger.error(f"Convert History 조회 실패: {e}")
        
        return events_created
    
    async def _create_convert_event(self, convert: dict[str, Any]) -> bool:
        """Convert 데이터를 이벤트로 변환 및 저장"""
        order_id = str(convert.get("orderId", 0))
        
        dedup_key = make_convert_dedup_key(
            exchange=self.scope.exchange,
            order_id=order_id,
        )
        
        payload = {
            "quote_id": convert.get("quoteId", ""),
            "order_id": order_id,
            "order_status": convert.get("orderStatus", ""),
            "from_asset": convert.get("fromAsset", ""),
            "from_amount": convert.get("fromAmount", "0"),
            "to_asset": convert.get("toAsset", ""),
            "to_amount": convert.get("toAmount", "0"),
            "ratio": convert.get("ratio", ""),
            "inverse_ratio": convert.get("inverseRatio", ""),
            "create_time": convert.get("createTime", 0),
            "source": "poller",
        }
        
        create_time = convert.get("createTime", 0)
        event_ts = (
            datetime.fromtimestamp(create_time / 1000, tz=timezone.utc)
            if create_time
            else datetime.now(timezone.utc)
        )
        
        base_event = Event.create(
            event_type=EventTypes.CONVERT_EXECUTED,
            source="BOT",
            entity_kind="CONVERT",
            entity_id=order_id,
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
