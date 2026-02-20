"""
Balance Projection Handler

BalanceChanged 이벤트를 처리하여 projection_balance 테이블 업데이트
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from adapters.db.sqlite_adapter import SQLiteAdapter
from core.domain.events import Event, EventTypes
from bot.projector.handlers.base import ProjectionHandler

logger = logging.getLogger(__name__)


class BalanceProjectionHandler(ProjectionHandler):
    """Balance Projection 핸들러
    
    BalanceChanged 이벤트를 받아 projection_balance 테이블 업데이트.
    
    Args:
        adapter: SQLite 어댑터
    """
    
    @property
    def handled_event_types(self) -> list[str]:
        return [EventTypes.BALANCE_CHANGED]
    
    async def handle(self, event: Event) -> bool:
        """BalanceChanged 이벤트 처리"""
        if event.event_type != EventTypes.BALANCE_CHANGED:
            return False
        
        try:
            payload = event.payload
            asset = payload.get("asset")
            
            if not asset:
                logger.warning(f"BalanceChanged event missing asset: {event.event_id}")
                return False
            
            # 잔고 계산 (WebSocket/REST에서 오는 필드명이 다를 수 있음)
            wallet_balance = payload.get("wallet_balance")
            available_balance = payload.get("available_balance")
            cross_wallet = payload.get("cross_wallet_balance")
            
            # 사용 가능 잔고 결정
            free = available_balance or cross_wallet or wallet_balance or "0"
            
            # locked 계산 (total - free)
            if wallet_balance and free:
                total = Decimal(wallet_balance)
                free_dec = Decimal(free)
                locked = str(total - free_dec) if total > free_dec else "0"
            else:
                locked = "0"
            
            # UPSERT 쿼리
            sql = """
                INSERT INTO projection_balance (
                    scope_exchange, scope_venue, scope_account_id, scope_mode,
                    asset, free, locked, last_event_seq, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scope_exchange, scope_venue, scope_account_id, asset, scope_mode)
                DO UPDATE SET
                    free = excluded.free,
                    locked = excluded.locked,
                    last_event_seq = excluded.last_event_seq,
                    updated_at = excluded.updated_at
            """
            
            now = datetime.now(timezone.utc).isoformat()
            
            await self.adapter.execute(sql, (
                event.scope.exchange,
                event.scope.venue,
                event.scope.account_id,
                event.scope.mode,
                asset,
                str(free),
                str(locked),
                event.seq,
                now,
            ))
            await self.adapter.commit()
            
            logger.debug(
                f"Balance projection updated: {asset}",
                extra={
                    "event_id": event.event_id,
                    "free": free,
                    "locked": locked,
                },
            )
            
            return True
            
        except Exception as e:
            logger.error(
                f"Balance projection update failed: {e}",
                extra={"event_id": event.event_id},
            )
            return False
    
    async def get_balance(
        self,
        exchange: str,
        venue: str,
        account_id: str,
        mode: str,
        asset: str,
    ) -> dict[str, Any] | None:
        """잔고 조회
        
        Args:
            exchange: 거래소
            venue: 거래 장소
            account_id: 계좌 ID
            mode: 거래 모드
            asset: 자산
            
        Returns:
            잔고 정보 또는 None
        """
        sql = """
            SELECT asset, free, locked, last_event_seq, updated_at
            FROM projection_balance
            WHERE scope_exchange = ?
              AND scope_venue = ?
              AND scope_account_id = ?
              AND scope_mode = ?
              AND asset = ?
        """
        
        row = await self.adapter.fetchone(sql, (
            exchange, venue, account_id, mode, asset
        ))
        
        if row:
            return {
                "asset": row[0],
                "free": row[1],
                "locked": row[2],
                "last_event_seq": row[3],
                "updated_at": row[4],
            }
        
        return None
    
    async def get_all_balances(
        self,
        exchange: str,
        venue: str,
        account_id: str,
        mode: str,
    ) -> list[dict[str, Any]]:
        """모든 잔고 조회
        
        Args:
            exchange: 거래소
            venue: 거래 장소
            account_id: 계좌 ID
            mode: 거래 모드
            
        Returns:
            잔고 목록
        """
        sql = """
            SELECT asset, free, locked, last_event_seq, updated_at
            FROM projection_balance
            WHERE scope_exchange = ?
              AND scope_venue = ?
              AND scope_account_id = ?
              AND scope_mode = ?
            ORDER BY asset
        """
        
        rows = await self.adapter.fetchall(sql, (
            exchange, venue, account_id, mode
        ))
        
        return [
            {
                "asset": row[0],
                "free": row[1],
                "locked": row[2],
                "last_event_seq": row[3],
                "updated_at": row[4],
            }
            for row in rows
        ]
