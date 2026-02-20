"""
이체 관리자

입출금 전체 흐름 관리 및 모니터링.
상태머신 기반으로 이체 진행 상태 추적.
"""

import asyncio
import logging
from decimal import Decimal
from typing import Any

from adapters.binance.rest_client import BinanceRestClient
from adapters.db.sqlite_adapter import SQLiteAdapter
from adapters.upbit.rest_client import UpbitRestClient
from bot.transfer.deposit_handler import DepositHandler
from bot.transfer.repository import Transfer, TransferRepository
from bot.transfer.withdraw_handler import WithdrawHandler
from core.domain.events import Event, EventTypes
from core.storage.event_store import EventStore
from core.types import TransferStatus, TransferType, Scope

logger = logging.getLogger(__name__)


class TransferManager:
    """이체 관리자
    
    입출금 전체 흐름 관리.
    
    Args:
        db: SQLiteAdapter 인스턴스
        upbit: Upbit REST 클라이언트
        binance: Binance REST 클라이언트
        event_store: 이벤트 저장소
        scope: 거래 범위
        binance_trx_address: Binance TRX 입금 주소
        upbit_trx_address: Upbit TRX 입금 주소
    """
    
    def __init__(
        self,
        db: SQLiteAdapter,
        upbit: UpbitRestClient,
        binance: BinanceRestClient,
        event_store: EventStore,
        scope: Scope,
        binance_trx_address: str,
        upbit_trx_address: str,
    ):
        self.db = db
        self.upbit = upbit
        self.binance = binance
        self.event_store = event_store
        self.scope = scope
        
        # 저장소 및 핸들러 초기화
        self.repository = TransferRepository(db)
        
        self.deposit_handler = DepositHandler(
            upbit=upbit,
            binance=binance,
            repository=self.repository,
            binance_trx_address=binance_trx_address,
        )
        
        self.withdraw_handler = WithdrawHandler(
            upbit=upbit,
            binance=binance,
            repository=self.repository,
            upbit_trx_address=upbit_trx_address,
        )
        
        # 모니터링 태스크
        self._monitor_task: asyncio.Task[None] | None = None
        self._running = False
    
    async def start_monitoring(self) -> None:
        """진행 중인 이체 모니터링 시작"""
        if self._running:
            return
        
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("TransferManager monitoring started")
    
    async def stop_monitoring(self) -> None:
        """모니터링 중지"""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None
        logger.info("TransferManager monitoring stopped")
    
    async def _monitor_loop(self) -> None:
        """진행 중인 이체 모니터링 루프"""
        while self._running:
            try:
                # 진행 중인 이체 조회
                pending_transfers = await self.repository.get_pending_transfers()
                
                for transfer in pending_transfers:
                    try:
                        await self._resume_transfer(transfer)
                    except Exception as e:
                        logger.error(
                            f"Transfer resume failed: {transfer.transfer_id}",
                            extra={"error": str(e)},
                        )
                
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
            
            # 30초마다 체크
            await asyncio.sleep(30)
    
    async def _resume_transfer(self, transfer: Transfer) -> None:
        """중단된 이체 재개"""
        if transfer.transfer_type == TransferType.DEPOSIT:
            await self.deposit_handler.execute(transfer)
        else:
            await self.withdraw_handler.execute(transfer)
    
    # =========================================================================
    # 입금
    # =========================================================================
    
    async def get_deposit_status(self) -> dict[str, Any]:
        """입금 가능 상태 조회
        
        Returns:
            입금 상태 정보
        """
        status = await self.deposit_handler.get_deposit_status()
        
        # 진행 중인 입금 확인
        pending = await self.repository.get_pending_transfers(TransferType.DEPOSIT)
        status["pending_deposit"] = len(pending) > 0
        status["pending_transfer_id"] = pending[0].transfer_id if pending else None
        
        return status
    
    async def request_deposit(
        self,
        amount_krw: Decimal,
        requested_by: str = "WEB:user",
    ) -> Transfer:
        """입금 요청
        
        Args:
            amount_krw: 입금 금액 (KRW)
            requested_by: 요청자
            
        Returns:
            생성된 Transfer 객체
        """
        # 이미 진행 중인 이체 확인
        pending = await self.repository.get_pending_transfers()
        if pending:
            raise ValueError(
                f"이미 진행 중인 이체가 있습니다: {pending[0].transfer_id}"
            )
        
        # 입금 가능 여부 확인
        status = await self.deposit_handler.get_deposit_status()
        if not status.get("can_deposit"):
            raise ValueError("입금 불가 상태입니다. 잔고를 확인해주세요.")
        
        # Transfer 생성
        transfer = await self.repository.create(
            transfer_type=TransferType.DEPOSIT,
            requested_amount=amount_krw,
            requested_by=requested_by,
            total_steps=DepositHandler.TOTAL_STEPS,
        )
        
        # 이벤트 기록
        await self._record_event(
            EventTypes.DEPOSIT_INITIATED,
            {
                "transfer_id": transfer.transfer_id,
                "amount_krw": str(amount_krw),
                "requested_by": requested_by,
            },
        )
        
        logger.info(
            f"Deposit requested: {transfer.transfer_id}",
            extra={"amount": str(amount_krw)},
        )
        
        # 비동기로 입금 실행 시작
        asyncio.create_task(self._execute_deposit(transfer))
        
        return transfer
    
    async def _execute_deposit(self, transfer: Transfer) -> None:
        """입금 실행 (백그라운드)"""
        try:
            result = await self.deposit_handler.execute(transfer)
            
            if result.status == TransferStatus.COMPLETED:
                await self._record_event(
                    EventTypes.DEPOSIT_COMPLETED,
                    {
                        "transfer_id": result.transfer_id,
                        "actual_amount": str(result.actual_amount),
                    },
                )
            
        except Exception as e:
            logger.error(f"Deposit execution failed: {e}", exc_info=True)
    
    # =========================================================================
    # 출금
    # =========================================================================
    
    async def get_withdraw_status(self) -> dict[str, Any]:
        """출금 가능 상태 조회
        
        Returns:
            출금 상태 정보
        """
        status = await self.withdraw_handler.get_withdraw_status()
        
        # 진행 중인 출금 확인
        pending = await self.repository.get_pending_transfers(TransferType.WITHDRAW)
        status["pending_withdraw"] = len(pending) > 0
        status["pending_transfer_id"] = pending[0].transfer_id if pending else None
        
        return status
    
    async def request_withdraw(
        self,
        amount_usdt: Decimal,
        requested_by: str = "WEB:user",
    ) -> Transfer:
        """출금 요청
        
        Args:
            amount_usdt: 출금 금액 (USDT)
            requested_by: 요청자
            
        Returns:
            생성된 Transfer 객체
        """
        # 이미 진행 중인 이체 확인
        pending = await self.repository.get_pending_transfers()
        if pending:
            raise ValueError(
                f"이미 진행 중인 이체가 있습니다: {pending[0].transfer_id}"
            )
        
        # 출금 가능 여부 확인
        status = await self.withdraw_handler.get_withdraw_status()
        if not status.get("can_withdraw"):
            raise ValueError("출금 불가 상태입니다. 잔고를 확인해주세요.")
        
        # Transfer 생성
        transfer = await self.repository.create(
            transfer_type=TransferType.WITHDRAW,
            requested_amount=amount_usdt,
            requested_by=requested_by,
            total_steps=WithdrawHandler.TOTAL_STEPS,
        )
        
        # 이벤트 기록
        await self._record_event(
            EventTypes.WITHDRAW_INITIATED,
            {
                "transfer_id": transfer.transfer_id,
                "amount_usdt": str(amount_usdt),
                "requested_by": requested_by,
            },
        )
        
        logger.info(
            f"Withdraw requested: {transfer.transfer_id}",
            extra={"amount": str(amount_usdt)},
        )
        
        # 비동기로 출금 실행 시작
        asyncio.create_task(self._execute_withdraw(transfer))
        
        return transfer
    
    async def _execute_withdraw(self, transfer: Transfer) -> None:
        """출금 실행 (백그라운드)"""
        try:
            result = await self.withdraw_handler.execute(transfer)
            
            if result.status == TransferStatus.COMPLETED:
                await self._record_event(
                    EventTypes.WITHDRAW_COMPLETED,
                    {
                        "transfer_id": result.transfer_id,
                        "actual_amount": str(result.actual_amount),
                    },
                )
            
        except Exception as e:
            logger.error(f"Withdraw execution failed: {e}", exc_info=True)
    
    # =========================================================================
    # 조회
    # =========================================================================
    
    async def get_transfer(self, transfer_id: str) -> Transfer | None:
        """이체 조회
        
        Args:
            transfer_id: 이체 ID
            
        Returns:
            Transfer 객체 또는 None
        """
        return await self.repository.get(transfer_id)
    
    async def get_history(
        self,
        transfer_type: TransferType | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Transfer]:
        """이체 내역 조회
        
        Args:
            transfer_type: 이체 유형 필터
            limit: 조회 개수
            offset: 시작 위치
            
        Returns:
            Transfer 목록
        """
        return await self.repository.get_history(
            transfer_type=transfer_type,
            limit=limit,
            offset=offset,
        )
    
    # =========================================================================
    # 취소 및 복구
    # =========================================================================
    
    async def cancel_transfer(self, transfer_id: str) -> Transfer:
        """이체 취소
        
        진행 중인 이체를 취소.
        블록체인 전송 이후에는 취소 불가.
        
        Args:
            transfer_id: 이체 ID
            
        Returns:
            업데이트된 Transfer 객체
        """
        transfer = await self.repository.get(transfer_id)
        if not transfer:
            raise ValueError(f"Transfer not found: {transfer_id}")
        
        # 취소 가능 상태 확인
        cancellable_statuses = [
            TransferStatus.PENDING,
            TransferStatus.PURCHASING,
        ]
        
        if transfer.status not in cancellable_statuses:
            raise ValueError(
                f"취소할 수 없는 상태입니다: {transfer.status.value}"
            )
        
        await self.repository.update_status(
            transfer_id,
            TransferStatus.CANCELLED,
            error_message="사용자 취소",
        )
        
        logger.info(f"Transfer cancelled: {transfer_id}")
        
        return await self.repository.get(transfer_id)  # type: ignore
    
    async def retry_transfer(self, transfer_id: str) -> Transfer:
        """실패한 이체 재시도
        
        FAILED 상태의 이체를 현재 단계부터 재시도.
        
        Args:
            transfer_id: 이체 ID
            
        Returns:
            업데이트된 Transfer 객체
        """
        transfer = await self.repository.get(transfer_id)
        if not transfer:
            raise ValueError(f"Transfer not found: {transfer_id}")
        
        if transfer.status != TransferStatus.FAILED:
            raise ValueError(
                f"재시도할 수 없는 상태입니다: {transfer.status.value}"
            )
        
        # PENDING으로 변경하여 재시도
        await self.repository.update_status(
            transfer_id,
            TransferStatus.PENDING,
            error_message=None,
        )
        
        transfer = await self.repository.get(transfer_id)
        
        # 재시도 실행
        if transfer.transfer_type == TransferType.DEPOSIT:
            asyncio.create_task(self._execute_deposit(transfer))
        else:
            asyncio.create_task(self._execute_withdraw(transfer))
        
        logger.info(f"Transfer retry started: {transfer_id}")
        
        return transfer
    
    # =========================================================================
    # 헬퍼
    # =========================================================================
    
    async def _record_event(
        self,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        """이벤트 기록"""
        from datetime import datetime, timezone
        import uuid
        
        event = Event.create(
            event_type=event_type,
            entity_kind="TRANSFER",
            entity_id=payload.get("transfer_id", "unknown"),
            scope=self.scope,
            source="BOT",
            payload=payload,
            dedup_key=f"transfer:{uuid.uuid4().hex}",
        )
        
        await self.event_store.append(event)
