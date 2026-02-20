"""
Transfer Repository

transfers 테이블 CRUD 처리.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from adapters.db.sqlite_adapter import SQLiteAdapter
from core.types import TransferStatus, TransferType

logger = logging.getLogger(__name__)


@dataclass
class Transfer:
    """이체 정보
    
    Attributes:
        transfer_id: 이체 ID
        transfer_type: 이체 유형 (DEPOSIT/WITHDRAW)
        status: 현재 상태
        requested_amount: 요청 금액
        requested_at: 요청 시각
        requested_by: 요청자
        current_step: 현재 단계
        total_steps: 전체 단계 수
        actual_amount: 실제 도착 금액
        fee_amount: 총 수수료
        upbit_order_id: Upbit 주문 ID
        binance_order_id: Binance 주문 ID
        blockchain_txid: 블록체인 트랜잭션 ID
        completed_at: 완료 시각
        error_message: 에러 메시지
        created_at: 생성 시각
        updated_at: 수정 시각
    """
    
    transfer_id: str
    transfer_type: TransferType
    status: TransferStatus
    requested_amount: Decimal
    requested_at: datetime
    requested_by: str
    current_step: int
    total_steps: int
    actual_amount: Decimal | None = None
    fee_amount: Decimal | None = None
    upbit_order_id: str | None = None
    binance_order_id: str | None = None
    blockchain_txid: str | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    
    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Transfer":
        """DB 행에서 생성"""
        return cls(
            transfer_id=row["transfer_id"],
            transfer_type=TransferType(row["transfer_type"]),
            status=TransferStatus(row["status"]),
            requested_amount=Decimal(str(row["requested_amount"])),
            requested_at=datetime.fromisoformat(row["requested_at"]),
            requested_by=row["requested_by"],
            current_step=row["current_step"],
            total_steps=row["total_steps"],
            actual_amount=(
                Decimal(str(row["actual_amount"]))
                if row.get("actual_amount")
                else None
            ),
            fee_amount=(
                Decimal(str(row["fee_amount"]))
                if row.get("fee_amount")
                else None
            ),
            upbit_order_id=row.get("upbit_order_id"),
            binance_order_id=row.get("binance_order_id"),
            blockchain_txid=row.get("blockchain_txid"),
            completed_at=(
                datetime.fromisoformat(row["completed_at"])
                if row.get("completed_at")
                else None
            ),
            error_message=row.get("error_message"),
            created_at=(
                datetime.fromisoformat(row["created_at"])
                if row.get("created_at")
                else None
            ),
            updated_at=(
                datetime.fromisoformat(row["updated_at"])
                if row.get("updated_at")
                else None
            ),
        )


class TransferRepository:
    """Transfer Repository
    
    transfers 테이블 CRUD 처리.
    
    Args:
        db: SQLiteAdapter 인스턴스
    """
    
    def __init__(self, db: SQLiteAdapter):
        self.db = db
    
    async def create(
        self,
        transfer_type: TransferType,
        requested_amount: Decimal,
        requested_by: str,
        total_steps: int,
    ) -> Transfer:
        """새 이체 생성
        
        Args:
            transfer_type: 이체 유형
            requested_amount: 요청 금액
            requested_by: 요청자 (예: "WEB:user_id")
            total_steps: 전체 단계 수
            
        Returns:
            생성된 Transfer 객체
        """
        transfer_id = f"tf-{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        
        await self.db.execute(
            """
            INSERT INTO transfers (
                transfer_id, transfer_type, status,
                requested_amount, requested_at, requested_by,
                current_step, total_steps,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                transfer_id,
                transfer_type.value,
                TransferStatus.PENDING.value,
                str(requested_amount),
                now,
                requested_by,
                0,
                total_steps,
                now,
                now,
            ),
        )
        await self.db.commit()
        
        logger.info(
            f"Transfer created: {transfer_id}",
            extra={
                "transfer_type": transfer_type.value,
                "amount": str(requested_amount),
            },
        )
        
        return await self.get(transfer_id)  # type: ignore
    
    async def get(self, transfer_id: str) -> Transfer | None:
        """이체 조회
        
        Args:
            transfer_id: 이체 ID
            
        Returns:
            Transfer 객체 또는 None
        """
        cursor = await self.db.execute(
            "SELECT * FROM transfers WHERE transfer_id = ?",
            (transfer_id,),
        )
        row = await cursor.fetchone()
        
        if not row:
            return None
        
        # row를 dict로 변환
        columns = [desc[0] for desc in cursor.description]
        row_dict = dict(zip(columns, row))
        
        return Transfer.from_row(row_dict)
    
    async def update_status(
        self,
        transfer_id: str,
        status: TransferStatus,
        current_step: int | None = None,
        error_message: str | None = None,
    ) -> bool:
        """상태 업데이트
        
        Args:
            transfer_id: 이체 ID
            status: 새 상태
            current_step: 현재 단계
            error_message: 에러 메시지
            
        Returns:
            성공 여부
        """
        now = datetime.now(timezone.utc).isoformat()
        
        update_parts = ["status = ?", "updated_at = ?"]
        params: list[Any] = [status.value, now]
        
        if current_step is not None:
            update_parts.append("current_step = ?")
            params.append(current_step)
        
        if error_message is not None:
            update_parts.append("error_message = ?")
            params.append(error_message)
        
        if status == TransferStatus.COMPLETED:
            update_parts.append("completed_at = ?")
            params.append(now)
        
        params.append(transfer_id)
        
        await self.db.execute(
            f"""
            UPDATE transfers
            SET {", ".join(update_parts)}
            WHERE transfer_id = ?
            """,
            tuple(params),
        )
        await self.db.commit()
        
        logger.info(
            f"Transfer status updated: {transfer_id} -> {status.value}",
            extra={"current_step": current_step},
        )
        
        return True
    
    async def update_order_ids(
        self,
        transfer_id: str,
        upbit_order_id: str | None = None,
        binance_order_id: str | None = None,
        blockchain_txid: str | None = None,
    ) -> bool:
        """주문 ID 업데이트
        
        Args:
            transfer_id: 이체 ID
            upbit_order_id: Upbit 주문 ID
            binance_order_id: Binance 주문 ID
            blockchain_txid: 블록체인 트랜잭션 ID
            
        Returns:
            성공 여부
        """
        now = datetime.now(timezone.utc).isoformat()
        
        update_parts = ["updated_at = ?"]
        params: list[Any] = [now]
        
        if upbit_order_id:
            update_parts.append("upbit_order_id = ?")
            params.append(upbit_order_id)
        
        if binance_order_id:
            update_parts.append("binance_order_id = ?")
            params.append(binance_order_id)
        
        if blockchain_txid:
            update_parts.append("blockchain_txid = ?")
            params.append(blockchain_txid)
        
        params.append(transfer_id)
        
        await self.db.execute(
            f"""
            UPDATE transfers
            SET {", ".join(update_parts)}
            WHERE transfer_id = ?
            """,
            tuple(params),
        )
        await self.db.commit()
        
        return True
    
    async def update_amounts(
        self,
        transfer_id: str,
        actual_amount: Decimal | None = None,
        fee_amount: Decimal | None = None,
    ) -> bool:
        """금액 업데이트
        
        Args:
            transfer_id: 이체 ID
            actual_amount: 실제 도착 금액
            fee_amount: 총 수수료
            
        Returns:
            성공 여부
        """
        now = datetime.now(timezone.utc).isoformat()
        
        update_parts = ["updated_at = ?"]
        params: list[Any] = [now]
        
        if actual_amount is not None:
            update_parts.append("actual_amount = ?")
            params.append(str(actual_amount))
        
        if fee_amount is not None:
            update_parts.append("fee_amount = ?")
            params.append(str(fee_amount))
        
        params.append(transfer_id)
        
        await self.db.execute(
            f"""
            UPDATE transfers
            SET {", ".join(update_parts)}
            WHERE transfer_id = ?
            """,
            tuple(params),
        )
        await self.db.commit()
        
        return True
    
    async def get_pending_transfers(
        self,
        transfer_type: TransferType | None = None,
    ) -> list[Transfer]:
        """진행 중인 이체 목록 조회
        
        Args:
            transfer_type: 이체 유형 필터 (선택)
            
        Returns:
            Transfer 목록
        """
        pending_statuses = [
            TransferStatus.PENDING.value,
            TransferStatus.PURCHASING.value,
            TransferStatus.SENDING.value,
            TransferStatus.CONFIRMING.value,
            TransferStatus.CONVERTING.value,
            TransferStatus.TRANSFERRING.value,
        ]
        
        placeholders = ", ".join(["?"] * len(pending_statuses))
        params: list[Any] = pending_statuses
        
        query = f"""
            SELECT * FROM transfers
            WHERE status IN ({placeholders})
        """
        
        if transfer_type:
            query += " AND transfer_type = ?"
            params.append(transfer_type.value)
        
        query += " ORDER BY requested_at ASC"
        
        cursor = await self.db.execute(query, tuple(params))
        rows = await cursor.fetchall()
        
        if not rows:
            return []
        
        columns = [desc[0] for desc in cursor.description]
        transfers = []
        for row in rows:
            row_dict = dict(zip(columns, row))
            transfers.append(Transfer.from_row(row_dict))
        
        return transfers
    
    async def get_history(
        self,
        transfer_type: TransferType | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Transfer]:
        """이체 내역 조회
        
        Args:
            transfer_type: 이체 유형 필터 (선택)
            limit: 조회 개수
            offset: 시작 위치
            
        Returns:
            Transfer 목록
        """
        params: list[Any] = []
        
        query = "SELECT * FROM transfers"
        
        if transfer_type:
            query += " WHERE transfer_type = ?"
            params.append(transfer_type.value)
        
        query += " ORDER BY requested_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor = await self.db.execute(query, tuple(params))
        rows = await cursor.fetchall()
        
        if not rows:
            return []
        
        columns = [desc[0] for desc in cursor.description]
        transfers = []
        for row in rows:
            row_dict = dict(zip(columns, row))
            transfers.append(Transfer.from_row(row_dict))
        
        return transfers
