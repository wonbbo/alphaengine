"""
DepositWithdrawPoller

외부 입출금 이력을 주기적으로 폴링.
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
from core.utils.dedup import make_deposit_dedup_key, make_withdraw_dedup_key

logger = logging.getLogger(__name__)


class DepositWithdrawPoller(BasePoller):
    """Deposit/Withdraw History Poller
    
    외부 입출금 이력을 6시간마다 폴링.
    
    Args:
        rest_client: Binance REST 클라이언트
        event_store: 이벤트 저장소
        config_store: 설정 저장소
        scope: 거래 범위
        poll_interval_seconds: 폴링 간격 (기본 6시간)
    """
    
    DEFAULT_POLL_INTERVAL = 6 * 60 * 60
    
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
        return "deposit_withdraw"
    
    async def _do_poll(self, since: datetime) -> int:
        """Deposit/Withdraw History 폴링 실행"""
        events_created = 0
        
        start_ms = int(since.timestamp() * 1000)
        end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        
        deposit_count = await self._poll_deposits(start_ms, end_ms)
        events_created += deposit_count
        
        withdraw_count = await self._poll_withdraws()
        events_created += withdraw_count
        
        return events_created
    
    async def _poll_deposits(self, start_ms: int, end_ms: int) -> int:
        """입금 이력 폴링"""
        events_created = 0
        
        try:
            deposits = await self.rest_client.get_deposit_history(
                status=1,
                start_time=start_ms,
                end_time=end_ms,
                limit=1000,
            )
            
            for deposit in deposits:
                saved = await self._create_deposit_event(deposit)
                if saved:
                    events_created += 1
                    
        except Exception as e:
            logger.error(f"Deposit History 조회 실패: {e}")
        
        return events_created
    
    async def _poll_withdraws(self) -> int:
        """출금 이력 폴링"""
        events_created = 0
        
        try:
            withdraws = await self.rest_client.get_withdraw_history(
                status=6,
                limit=1000,
            )
            
            for withdraw in withdraws:
                saved = await self._create_withdraw_event(withdraw)
                if saved:
                    events_created += 1
                    
        except Exception as e:
            logger.error(f"Withdraw History 조회 실패: {e}")
        
        return events_created
    
    async def _create_deposit_event(self, deposit: dict[str, Any]) -> bool:
        """Deposit 데이터를 이벤트로 변환 및 저장"""
        deposit_id = str(deposit.get("id", deposit.get("txId", "")))
        
        dedup_key = make_deposit_dedup_key(
            exchange=self.scope.exchange,
            deposit_id=deposit_id,
        )
        
        payload = {
            "id": deposit_id,
            "amount": deposit.get("amount", "0"),
            "coin": deposit.get("coin", ""),
            "network": deposit.get("network", ""),
            "status": deposit.get("status", 0),
            "address": deposit.get("address", ""),
            "tx_id": deposit.get("txId", ""),
            "insert_time": deposit.get("insertTime", 0),
            "source": "poller",
        }
        
        insert_time = deposit.get("insertTime", 0)
        event_ts = (
            datetime.fromtimestamp(insert_time / 1000, tz=timezone.utc)
            if insert_time
            else datetime.now(timezone.utc)
        )
        
        base_event = Event.create(
            event_type=EventTypes.DEPOSIT_DETECTED,
            source="BOT",
            entity_kind="DEPOSIT",
            entity_id=deposit_id,
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
    
    async def _create_withdraw_event(self, withdraw: dict[str, Any]) -> bool:
        """Withdraw 데이터를 이벤트로 변환 및 저장"""
        withdraw_id = str(withdraw.get("id", ""))
        
        dedup_key = make_withdraw_dedup_key(
            exchange=self.scope.exchange,
            withdraw_id=withdraw_id,
        )
        
        payload = {
            "id": withdraw_id,
            "amount": withdraw.get("amount", "0"),
            "transaction_fee": withdraw.get("transactionFee", "0"),
            "coin": withdraw.get("coin", ""),
            "status": withdraw.get("status", 0),
            "address": withdraw.get("address", ""),
            "tx_id": withdraw.get("txId", ""),
            "apply_time": withdraw.get("applyTime", ""),
            "network": withdraw.get("network", ""),
            "complete_time": withdraw.get("completeTime", ""),
            "source": "poller",
        }
        
        base_event = Event.create(
            event_type=EventTypes.WITHDRAW_COMPLETED,
            source="BOT",
            entity_kind="WITHDRAW",
            entity_id=withdraw_id,
            scope=self.scope,
            dedup_key=dedup_key,
            payload=payload,
        )
        
        return await self.event_store.append(base_event)
