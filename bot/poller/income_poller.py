"""
IncomePoller

Futures Income History를 주기적으로 폴링.
펀딩비, 수수료 리베이트 등을 수집.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from bot.poller.base import BasePoller
from adapters.binance.rest_client import BinanceRestClient
from core.domain.events import Event, EventTypes
from core.storage.event_store import EventStore
from core.storage.config_store import ConfigStore
from core.types import Scope
from core.utils.dedup import (
    make_funding_dedup_key,
    make_commission_rebate_dedup_key,
)

logger = logging.getLogger(__name__)


class IncomePoller(BasePoller):
    """Income History Poller
    
    펀딩비, 수수료 리베이트 등 Futures Income을 5분마다 폴링.
    
    Args:
        rest_client: Binance REST 클라이언트
        event_store: 이벤트 저장소
        config_store: 설정 저장소
        scope: 거래 범위
        poll_interval_seconds: 폴링 간격 (기본 5분)
    """
    
    DEFAULT_POLL_INTERVAL = 5 * 60
    
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
        return "income"
    
    async def _do_poll(self, since: datetime) -> int:
        """Income History 폴링 실행"""
        events_created = 0
        
        start_ms = int(since.timestamp() * 1000)
        end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        
        try:
            income_list = await self.rest_client.get_income_history(
                start_time=start_ms,
                end_time=end_ms,
                limit=1000,
            )
            
            for income in income_list:
                saved = await self._process_income(income)
                if saved:
                    events_created += 1
                    
        except Exception as e:
            logger.error(f"Income History 조회 실패: {e}")
        
        return events_created
    
    async def _process_income(self, income: dict[str, Any]) -> bool:
        """Income 데이터를 이벤트로 변환 및 저장"""
        income_type = income.get("incomeType", "")
        
        if income_type == "FUNDING_FEE":
            return await self._create_funding_event(income)
        elif income_type == "COMMISSION_REBATE":
            return await self._create_rebate_event(income)
        
        return False
    
    async def _create_funding_event(self, income: dict[str, Any]) -> bool:
        """FundingApplied 이벤트 생성"""
        symbol = income.get("symbol", "")
        funding_ts = income.get("time", 0)
        
        dedup_key = make_funding_dedup_key(
            exchange=self.scope.exchange,
            symbol=symbol,
            funding_ts=funding_ts,
        )
        
        income_amount = Decimal(income.get("income", "0"))
        
        payload = {
            "symbol": symbol,
            "funding_rate": "",
            "funding_fee": str(income_amount),
            "asset": income.get("asset", "USDT"),
            "tran_id": str(income.get("tranId", 0)),
            "time": funding_ts,
            "source": "poller",
        }
        
        event_ts = datetime.fromtimestamp(funding_ts / 1000, tz=timezone.utc)
        
        event = Event(
            event_id=Event.create(
                event_type=EventTypes.FUNDING_APPLIED,
                source="BOT",
                entity_kind="FUNDING",
                entity_id=str(income.get("tranId", 0)),
                scope=self.scope,
                dedup_key=dedup_key,
                payload=payload,
            ).event_id,
            event_type=EventTypes.FUNDING_APPLIED,
            ts=event_ts,
            correlation_id=Event.create(
                event_type=EventTypes.FUNDING_APPLIED,
                source="BOT",
                entity_kind="FUNDING",
                entity_id=str(income.get("tranId", 0)),
                scope=self.scope,
                dedup_key=dedup_key,
                payload=payload,
            ).correlation_id,
            causation_id=None,
            command_id=None,
            source="BOT",
            entity_kind="FUNDING",
            entity_id=str(income.get("tranId", 0)),
            scope=self.scope,
            dedup_key=dedup_key,
            payload=payload,
        )
        
        return await self.event_store.append(event)
    
    async def _create_rebate_event(self, income: dict[str, Any]) -> bool:
        """CommissionRebateReceived 이벤트 생성"""
        tran_id = income.get("tranId", 0)
        
        dedup_key = make_commission_rebate_dedup_key(
            exchange=self.scope.exchange,
            tran_id=tran_id,
        )
        
        income_amount = Decimal(income.get("income", "0"))
        
        payload = {
            "symbol": income.get("symbol", ""),
            "rebate_amount": str(income_amount),
            "asset": income.get("asset", "USDT"),
            "tran_id": str(tran_id),
            "time": income.get("time", 0),
            "source": "poller",
        }
        
        event_ts = datetime.fromtimestamp(
            income.get("time", 0) / 1000, tz=timezone.utc
        )
        
        event = Event(
            event_id=Event.create(
                event_type=EventTypes.COMMISSION_REBATE_RECEIVED,
                source="BOT",
                entity_kind="REBATE",
                entity_id=str(tran_id),
                scope=self.scope,
                dedup_key=dedup_key,
                payload=payload,
            ).event_id,
            event_type=EventTypes.COMMISSION_REBATE_RECEIVED,
            ts=event_ts,
            correlation_id=Event.create(
                event_type=EventTypes.COMMISSION_REBATE_RECEIVED,
                source="BOT",
                entity_kind="REBATE",
                entity_id=str(tran_id),
                scope=self.scope,
                dedup_key=dedup_key,
                payload=payload,
            ).correlation_id,
            causation_id=None,
            command_id=None,
            source="BOT",
            entity_kind="REBATE",
            entity_id=str(tran_id),
            scope=self.scope,
            dedup_key=dedup_key,
            payload=payload,
        )
        
        return await self.event_store.append(event)
