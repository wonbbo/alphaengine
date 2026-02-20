"""
Transfer 서비스

입출금 관련 비즈니스 로직.
Web에서 Bot의 TransferManager를 직접 사용하지 않고,
DB 조회 및 Command 발행으로 통신.
"""

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from adapters.db.sqlite_adapter import SQLiteAdapter
from bot.transfer.repository import Transfer, TransferRepository
from core.types import TransferStatus, TransferType

logger = logging.getLogger(__name__)


@dataclass
class DepositStatusResponse:
    """입금 가능 상태 응답"""
    
    can_deposit: bool
    krw_balance: str
    trx_balance: str
    trx_price_krw: str
    trx_value_krw: str
    fee_trx: str
    fee_krw: str
    min_deposit_krw: str
    pending_deposit: bool
    pending_transfer_id: str | None
    
    def to_dict(self) -> dict[str, Any]:
        """딕셔너리 변환"""
        return {
            "can_deposit": self.can_deposit,
            "krw_balance": self.krw_balance,
            "trx_balance": self.trx_balance,
            "trx_price_krw": self.trx_price_krw,
            "trx_value_krw": self.trx_value_krw,
            "fee_trx": self.fee_trx,
            "fee_krw": self.fee_krw,
            "min_deposit_krw": self.min_deposit_krw,
            "pending_deposit": self.pending_deposit,
            "pending_transfer_id": self.pending_transfer_id,
        }


@dataclass
class WithdrawStatusResponse:
    """출금 가능 상태 응답"""
    
    can_withdraw: bool
    usdt_balance: str
    has_position: bool
    position_count: int
    min_withdraw_usdt: str
    warning: str | None
    pending_withdraw: bool
    pending_transfer_id: str | None
    
    def to_dict(self) -> dict[str, Any]:
        """딕셔너리 변환"""
        return {
            "can_withdraw": self.can_withdraw,
            "usdt_balance": self.usdt_balance,
            "has_position": self.has_position,
            "position_count": self.position_count,
            "min_withdraw_usdt": self.min_withdraw_usdt,
            "warning": self.warning,
            "pending_withdraw": self.pending_withdraw,
            "pending_transfer_id": self.pending_transfer_id,
        }


@dataclass
class TransferResponse:
    """이체 응답"""
    
    transfer_id: str
    transfer_type: str
    status: str
    requested_amount: str
    requested_at: str
    current_step: int
    total_steps: int
    actual_amount: str | None
    error_message: str | None
    completed_at: str | None
    
    @classmethod
    def from_transfer(cls, transfer: Transfer) -> "TransferResponse":
        """Transfer에서 생성"""
        return cls(
            transfer_id=transfer.transfer_id,
            transfer_type=transfer.transfer_type.value,
            status=transfer.status.value,
            requested_amount=str(transfer.requested_amount),
            requested_at=transfer.requested_at.isoformat(),
            current_step=transfer.current_step,
            total_steps=transfer.total_steps,
            actual_amount=(
                str(transfer.actual_amount) if transfer.actual_amount else None
            ),
            error_message=transfer.error_message,
            completed_at=(
                transfer.completed_at.isoformat() if transfer.completed_at else None
            ),
        )
    
    def to_dict(self) -> dict[str, Any]:
        """딕셔너리 변환"""
        return {
            "transfer_id": self.transfer_id,
            "transfer_type": self.transfer_type,
            "status": self.status,
            "requested_amount": self.requested_amount,
            "requested_at": self.requested_at,
            "current_step": self.current_step,
            "total_steps": self.total_steps,
            "actual_amount": self.actual_amount,
            "error_message": self.error_message,
            "completed_at": self.completed_at,
        }


class TransferService:
    """Transfer 서비스
    
    Web에서 이체 관련 조회 및 요청 처리.
    
    Args:
        db: SQLiteAdapter 인스턴스
    """
    
    def __init__(self, db: SQLiteAdapter):
        self.db = db
        self.repository = TransferRepository(db)
    
    async def get_transfer(self, transfer_id: str) -> TransferResponse | None:
        """이체 조회
        
        Args:
            transfer_id: 이체 ID
            
        Returns:
            TransferResponse 또는 None
        """
        transfer = await self.repository.get(transfer_id)
        if not transfer:
            return None
        return TransferResponse.from_transfer(transfer)
    
    async def get_history(
        self,
        transfer_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[TransferResponse]:
        """이체 내역 조회
        
        Args:
            transfer_type: 이체 유형 필터 (DEPOSIT/WITHDRAW)
            limit: 조회 개수
            offset: 시작 위치
            
        Returns:
            TransferResponse 목록
        """
        type_enum = None
        if transfer_type:
            type_enum = TransferType(transfer_type.upper())
        
        transfers = await self.repository.get_history(
            transfer_type=type_enum,
            limit=limit,
            offset=offset,
        )
        
        return [TransferResponse.from_transfer(t) for t in transfers]
    
    async def get_pending_transfers(self) -> list[TransferResponse]:
        """진행 중인 이체 목록
        
        Returns:
            TransferResponse 목록
        """
        transfers = await self.repository.get_pending_transfers()
        return [TransferResponse.from_transfer(t) for t in transfers]
    
    async def has_pending_transfer(self) -> bool:
        """진행 중인 이체 존재 여부
        
        Returns:
            진행 중인 이체가 있으면 True
        """
        pending = await self.repository.get_pending_transfers()
        return len(pending) > 0
