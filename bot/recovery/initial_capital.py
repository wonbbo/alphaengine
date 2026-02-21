"""
InitialCapitalRecorder

Bot 최초 실행 시 초기 자산을 기록하는 컴포넌트.
Daily Account Snapshot API를 사용하여 SPOT/FUTURES 계좌의 자산 상태를 조회.
"""

import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any

from adapters.binance.rest_client import BinanceRestClient
from core.domain.events import Event, EventTypes
from core.storage.event_store import EventStore
from core.storage.config_store import ConfigStore
from core.types import Scope
from core.utils.dedup import make_initial_capital_dedup_key

logger = logging.getLogger(__name__)


class InitialCapitalRecorder:
    """초기 자산 기록기
    
    Bot 최초 실행 시 Daily Snapshot API로 초기 자산을 조회하고
    InitialCapitalEstablished 이벤트를 생성합니다.
    
    Args:
        rest_client: Binance REST 클라이언트
        event_store: 이벤트 저장소
        config_store: 설정 저장소
        scope: 거래 범위
    """
    
    def __init__(
        self,
        rest_client: BinanceRestClient,
        event_store: EventStore,
        config_store: ConfigStore,
        scope: Scope,
    ):
        self.rest_client = rest_client
        self.event_store = event_store
        self.config_store = config_store
        self.scope = scope
    
    async def is_initialized(self) -> bool:
        """초기 자산이 이미 기록되었는지 확인"""
        initial_capital = await self.config_store.get("initial_capital")
        
        if initial_capital is None:
            return False
        
        return initial_capital.get("initialized", False)
    
    async def record(self, target_date: datetime | None = None) -> dict[str, Any]:
        """초기 자산 기록
        
        Args:
            target_date: 스냅샷 조회 대상 날짜 (None이면 현재 시점 기준)
            
        Returns:
            기록된 초기 자산 정보:
            {
                "USDT": "500.00",
                "SPOT_USDT": "100.00",
                "FUTURES_USDT": "400.00",
                "epoch_date": "2024-01-15",
                "initialized": True,
                "recorded_at": "2024-01-20T12:00:00Z"
            }
        """
        if await self.is_initialized():
            logger.info("초기 자산이 이미 기록되어 있습니다. 건너뜁니다.")
            return await self.config_store.get("initial_capital")
        
        logger.info("초기 자산 기록 시작...")
        
        if target_date is None:
            target_date = datetime.now(timezone.utc)
        
        snapshot_result = await self._fetch_snapshots(target_date)
        
        initial_capital = await self._save_initial_capital(snapshot_result)
        
        await self._create_event(snapshot_result)
        
        logger.info(
            "초기 자산 기록 완료",
            extra={
                "total_usdt": snapshot_result["total_usdt"],
                "spot_usdt": snapshot_result["spot_usdt"],
                "futures_usdt": snapshot_result["futures_usdt"],
                "snapshot_date": snapshot_result["snapshot_date"],
            },
        )
        
        return initial_capital
    
    async def _fetch_snapshots(self, target_date: datetime) -> dict[str, Any]:
        """Daily Snapshot 조회
        
        SPOT과 FUTURES 계좌의 스냅샷을 조회합니다.
        
        Args:
            target_date: 스냅샷 조회 대상 날짜
            
        Returns:
            스냅샷 결과:
            {
                "spot_usdt": Decimal,
                "futures_usdt": Decimal,
                "total_usdt": Decimal,
                "snapshot_date": str (YYYY-MM-DD),
                "spot_balances": [...],
                "futures_assets": [...],
            }
        """
        start_time_ms = int((target_date - timedelta(days=3)).timestamp() * 1000)
        end_time_ms = int((target_date + timedelta(days=1)).timestamp() * 1000)
        
        spot_usdt = Decimal("0")
        futures_usdt = Decimal("0")
        spot_balances: list[dict] = []
        futures_assets: list[dict] = []
        snapshot_date = target_date.date().isoformat()
        
        try:
            spot_response = await self.rest_client.get_account_snapshot(
                account_type="SPOT",
                start_time=start_time_ms,
                end_time=end_time_ms,
                limit=7,
            )
            
            if spot_response.get("code") == 200:
                for snapshot in spot_response.get("snapshotVos", []):
                    balances = snapshot.get("data", {}).get("balances", [])
                    update_time = snapshot.get("updateTime", 0)
                    
                    for balance in balances:
                        if balance["asset"] == "USDT":
                            free = Decimal(balance.get("free", "0"))
                            locked = Decimal(balance.get("locked", "0"))
                            spot_usdt = free + locked
                            break
                    
                    spot_balances = balances
                    if update_time:
                        snapshot_date = datetime.fromtimestamp(
                            update_time / 1000, tz=timezone.utc
                        ).date().isoformat()
                    break
                    
        except Exception as e:
            logger.warning(f"SPOT 스냅샷 조회 실패: {e}")
        
        try:
            futures_response = await self.rest_client.get_account_snapshot(
                account_type="FUTURES",
                start_time=start_time_ms,
                end_time=end_time_ms,
                limit=7,
            )
            
            if futures_response.get("code") == 200:
                for snapshot in futures_response.get("snapshotVos", []):
                    assets = snapshot.get("data", {}).get("assets", [])
                    
                    for asset in assets:
                        if asset["asset"] == "USDT":
                            futures_usdt = Decimal(asset.get("walletBalance", "0"))
                            break
                    
                    futures_assets = assets
                    break
                    
        except Exception as e:
            logger.warning(f"FUTURES 스냅샷 조회 실패: {e}")
        
        total_usdt = spot_usdt + futures_usdt
        
        return {
            "spot_usdt": spot_usdt,
            "futures_usdt": futures_usdt,
            "total_usdt": total_usdt,
            "snapshot_date": snapshot_date,
            "spot_balances": spot_balances,
            "futures_assets": futures_assets,
        }
    
    async def _save_initial_capital(
        self,
        snapshot_result: dict[str, Any],
    ) -> dict[str, Any]:
        """초기 자산 정보를 config_store에 저장"""
        initial_capital = {
            "USDT": str(snapshot_result["total_usdt"]),
            "SPOT_USDT": str(snapshot_result["spot_usdt"]),
            "FUTURES_USDT": str(snapshot_result["futures_usdt"]),
            "epoch_date": snapshot_result["snapshot_date"],
            "initialized": True,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        
        await self.config_store.set("initial_capital", initial_capital)
        
        return initial_capital
    
    async def _create_event(self, snapshot_result: dict[str, Any]) -> Event:
        """InitialCapitalEstablished 이벤트 생성 및 저장
        
        Note: 이벤트 ts는 snapshot_date의 UTC 00:00:00으로 설정됩니다.
        이렇게 하면 백필된 이벤트보다 InitialCapitalEstablished가 먼저 처리되어
        Ledger에서 음수 잔고가 발생하지 않습니다.
        """
        dedup_key = make_initial_capital_dedup_key(
            mode=self.scope.mode,
            snapshot_date=snapshot_result["snapshot_date"],
        )
        
        payload = {
            "spot_usdt": str(snapshot_result["spot_usdt"]),
            "futures_usdt": str(snapshot_result["futures_usdt"]),
            "total_usdt": str(snapshot_result["total_usdt"]),
            "snapshot_date": snapshot_result["snapshot_date"],
            "method": "daily_snapshot",
            "confidence": "exact",
            "spot_balances": snapshot_result["spot_balances"],
            "futures_assets": snapshot_result["futures_assets"],
        }
        
        event = Event.create(
            event_type=EventTypes.INITIAL_CAPITAL_ESTABLISHED,
            source="BOT",
            entity_kind="CAPITAL",
            entity_id=f"initial_{self.scope.mode}",
            scope=self.scope,
            dedup_key=dedup_key,
            payload=payload,
        )
        
        # ts를 snapshot_date의 UTC 00:00:00으로 설정
        # 백필된 이벤트들은 snapshot_date 이후이므로, 
        # InitialCapital이 먼저 처리되어 Ledger 음수 방지
        snapshot_date_str = snapshot_result["snapshot_date"]
        snapshot_datetime = datetime.fromisoformat(snapshot_date_str)
        snapshot_ts = datetime(
            snapshot_datetime.year,
            snapshot_datetime.month,
            snapshot_datetime.day,
            0, 0, 0,
            tzinfo=timezone.utc,
        )
        
        event = Event(
            event_id=event.event_id,
            event_type=event.event_type,
            ts=snapshot_ts,
            correlation_id=event.correlation_id,
            causation_id=event.causation_id,
            command_id=event.command_id,
            source=event.source,
            entity_kind=event.entity_kind,
            entity_id=event.entity_id,
            scope=event.scope,
            dedup_key=event.dedup_key,
            payload=event.payload,
        )
        
        saved = await self.event_store.append(event)
        
        if saved:
            logger.info(
                "InitialCapitalEstablished 이벤트 저장 완료",
                extra={"event_id": event.event_id},
            )
        else:
            logger.debug("InitialCapitalEstablished 이벤트가 이미 존재합니다 (중복)")
        
        return event
