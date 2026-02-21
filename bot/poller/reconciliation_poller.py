"""
ReconciliationPoller

일일 1회 Ledger vs 거래소 잔고 정합.
포지션이 없을 때만 수행.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from bot.poller.base import BasePoller
from bot.recovery.opening_reconciler import OpeningBalanceReconciler
from adapters.binance.rest_client import BinanceRestClient
from core.storage.event_store import EventStore
from core.storage.config_store import ConfigStore
from core.types import Scope

logger = logging.getLogger(__name__)


class ReconciliationPoller(BasePoller):
    """일일 잔고 정합 Poller
    
    24시간마다 Ledger 잔고와 거래소 실제 잔고를 비교하여 정합.
    포지션이 열려 있으면 건너뛰고 다음 주기에 재시도.
    
    Args:
        rest_client: Binance REST 클라이언트
        event_store: 이벤트 저장소
        config_store: 설정 저장소
        scope: 거래 범위
        ledger_balance_getter: Ledger 잔고 조회 함수
        target_symbol: 포지션 체크할 심볼
        poll_interval_seconds: 폴링 간격 (기본 1시간, 조건 체크용)
    """
    
    # 정합 주기: 24시간
    RECONCILIATION_INTERVAL_SECONDS = 24 * 60 * 60
    
    # 폴링 주기: 1시간 (조건 체크)
    DEFAULT_POLL_INTERVAL = 60 * 60
    
    def __init__(
        self,
        rest_client: BinanceRestClient,
        event_store: EventStore,
        config_store: ConfigStore,
        scope: Scope,
        ledger_balance_getter: Any,
        target_symbol: str,
        poll_interval_seconds: int | None = None,
    ):
        super().__init__(
            rest_client=rest_client,
            event_store=event_store,
            config_store=config_store,
            scope=scope,
            poll_interval_seconds=poll_interval_seconds or self.DEFAULT_POLL_INTERVAL,
        )
        
        self._ledger_balance_getter = ledger_balance_getter
        self._target_symbol = target_symbol
        self._last_reconciliation_time: datetime | None = None
        
        # OpeningBalanceReconciler 인스턴스
        self._reconciler = OpeningBalanceReconciler(
            rest_client=rest_client,
            event_store=event_store,
            scope=scope,
        )
    
    @property
    def poller_name(self) -> str:
        return "reconciliation"
    
    @property
    def reconciliation_config_key(self) -> str:
        """정합 시간 저장 키"""
        return f"poller_{self.poller_name}_last_reconciliation"
    
    async def initialize(self) -> None:
        """초기화: 마지막 정합 시간 복구"""
        await super().initialize()
        
        saved_state = await self.config_store.get(self.reconciliation_config_key)
        
        if saved_state and "last_reconciliation_time" in saved_state:
            last_recon_str = saved_state["last_reconciliation_time"]
            self._last_reconciliation_time = datetime.fromisoformat(last_recon_str)
            
            logger.info(
                "ReconciliationPoller: 마지막 정합 시간 복구됨",
                extra={"last_reconciliation_time": last_recon_str},
            )
        else:
            self._last_reconciliation_time = None
            logger.info("ReconciliationPoller: 첫 정합 대기")
    
    async def _do_poll(self, since: datetime) -> int:
        """정합 조건 체크 및 수행
        
        1. 24시간 경과 체크
        2. 포지션 없음 체크
        3. 조건 충족 시 정합 수행
        """
        # 1. 24시간 경과 체크
        if not self._should_reconcile():
            logger.debug("ReconciliationPoller: 정합 주기 미도래")
            return 0
        
        # 2. 포지션 체크
        has_position = await self._has_open_position()
        if has_position:
            logger.info("ReconciliationPoller: 포지션 보유 중, 정합 건너뜀")
            return 0
        
        # 3. 정합 수행
        logger.info("ReconciliationPoller: 일일 정합 시작")
        
        try:
            # Ledger 잔고 조회
            ledger_balances = await self._ledger_balance_getter()
            
            # 정합 수행
            result = await self._reconciler.reconcile(ledger_balances)
            
            # 마지막 정합 시간 저장
            self._last_reconciliation_time = datetime.now(timezone.utc)
            await self._save_last_reconciliation_time()
            
            adjusted_count = result.get("adjusted_count", 0)
            
            if adjusted_count > 0:
                logger.info(
                    "ReconciliationPoller: 정합 완료",
                    extra={
                        "adjusted_count": adjusted_count,
                        "adjustments": result.get("adjustments", []),
                    },
                )
            else:
                logger.info("ReconciliationPoller: 정합 완료 (차이 없음)")
            
            return adjusted_count
            
        except Exception as e:
            logger.error(f"ReconciliationPoller: 정합 실패 - {e}")
            return 0
    
    def _should_reconcile(self) -> bool:
        """정합 필요 여부 확인
        
        마지막 정합 후 24시간 경과했는지 확인.
        """
        if self._last_reconciliation_time is None:
            return True
        
        now = datetime.now(timezone.utc)
        elapsed = (now - self._last_reconciliation_time).total_seconds()
        
        return elapsed >= self.RECONCILIATION_INTERVAL_SECONDS
    
    async def _has_open_position(self) -> bool:
        """포지션 보유 여부 확인"""
        try:
            position = await self.rest_client.get_position(self._target_symbol)
            
            if position is None:
                return False
            
            # position_amt가 0이 아니면 포지션 있음
            position_amt = abs(float(position.position_amt))
            has_position = position_amt > 0
            
            if has_position:
                logger.debug(
                    f"ReconciliationPoller: 포지션 보유 중",
                    extra={
                        "symbol": self._target_symbol,
                        "position_amt": position.position_amt,
                    },
                )
            
            return has_position
            
        except Exception as e:
            logger.warning(f"ReconciliationPoller: 포지션 조회 실패 - {e}")
            # 조회 실패 시 안전하게 포지션 있다고 가정
            return True
    
    async def _save_last_reconciliation_time(self) -> None:
        """마지막 정합 시간 저장"""
        if self._last_reconciliation_time:
            await self.config_store.set(
                self.reconciliation_config_key,
                {"last_reconciliation_time": self._last_reconciliation_time.isoformat()},
            )
