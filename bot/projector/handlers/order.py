"""
Order Projection Handler

Order 관련 이벤트를 처리하여 projection_order 테이블 업데이트
"""

import logging
from datetime import datetime, timezone
from typing import Any

from adapters.db.sqlite_adapter import SQLiteAdapter
from core.domain.events import Event, EventTypes
from bot.projector.handlers.base import ProjectionHandler

logger = logging.getLogger(__name__)


class OrderProjectionHandler(ProjectionHandler):
    """Order Projection 핸들러
    
    Order 관련 이벤트를 받아 projection_order 테이블 업데이트.
    오픈 주문 목록 관리.
    
    Args:
        adapter: SQLite 어댑터
    """
    
    @property
    def handled_event_types(self) -> list[str]:
        return [
            EventTypes.ORDER_PLACED,
            EventTypes.ORDER_UPDATED,
            EventTypes.ORDER_CANCELLED,
            EventTypes.ORDER_REJECTED,
        ]
    
    async def handle(self, event: Event) -> bool:
        """Order 이벤트 처리"""
        if event.event_type not in self.handled_event_types:
            return False
        
        try:
            # 테이블 존재 확인 및 생성
            await self._ensure_table_exists()
            
            payload = event.payload
            exchange_order_id = payload.get("exchange_order_id")
            
            if not exchange_order_id:
                logger.warning(f"Order event missing exchange_order_id: {event.event_id}")
                return False
            
            # 이벤트 타입별 처리
            if event.event_type == EventTypes.ORDER_PLACED:
                await self._handle_order_placed(event)
            elif event.event_type == EventTypes.ORDER_UPDATED:
                await self._handle_order_updated(event)
            elif event.event_type == EventTypes.ORDER_CANCELLED:
                await self._handle_order_cancelled(event)
            elif event.event_type == EventTypes.ORDER_REJECTED:
                await self._handle_order_rejected(event)
            
            return True
            
        except Exception as e:
            logger.error(
                f"Order projection update failed: {e}",
                extra={"event_id": event.event_id},
            )
            return False
    
    async def _handle_order_placed(self, event: Event) -> None:
        """새 주문 등록"""
        payload = event.payload
        symbol = event.scope.symbol or payload.get("symbol")
        
        sql = """
            INSERT INTO projection_order (
                scope_exchange, scope_venue, scope_account_id, scope_symbol, scope_mode,
                exchange_order_id, client_order_id, order_state, side, order_type,
                original_qty, executed_qty, price, stop_price,
                last_event_seq, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(scope_exchange, scope_venue, scope_account_id, exchange_order_id, scope_mode)
            DO UPDATE SET
                order_state = excluded.order_state,
                last_event_seq = excluded.last_event_seq,
                updated_at = excluded.updated_at
        """
        
        now = datetime.now(timezone.utc).isoformat()
        
        await self.adapter.execute(sql, (
            event.scope.exchange,
            event.scope.venue,
            event.scope.account_id,
            symbol,
            event.scope.mode,
            payload.get("exchange_order_id"),
            payload.get("client_order_id"),
            payload.get("order_status", "NEW"),
            payload.get("side"),
            payload.get("order_type"),
            payload.get("original_qty"),
            payload.get("executed_qty", "0"),
            payload.get("price"),
            payload.get("stop_price"),
            event.seq,
            now,
            now,
        ))
        await self.adapter.commit()
        
        logger.debug(
            f"Order projection created: {payload.get('exchange_order_id')}",
            extra={"event_id": event.event_id},
        )
    
    async def _handle_order_updated(self, event: Event) -> None:
        """주문 상태 업데이트"""
        payload = event.payload
        exchange_order_id = payload.get("exchange_order_id")
        order_status = payload.get("order_status")
        
        # 완료된 주문은 삭제 (오픈 주문 목록에서 제거)
        if order_status in ("FILLED", "CANCELED", "EXPIRED", "REJECTED"):
            await self._delete_order(event, exchange_order_id)
            return
        
        # 상태 업데이트
        sql = """
            UPDATE projection_order
            SET order_state = ?,
                executed_qty = ?,
                last_event_seq = ?,
                updated_at = ?
            WHERE scope_exchange = ?
              AND scope_venue = ?
              AND scope_account_id = ?
              AND exchange_order_id = ?
              AND scope_mode = ?
        """
        
        now = datetime.now(timezone.utc).isoformat()
        
        await self.adapter.execute(sql, (
            order_status,
            payload.get("executed_qty", "0"),
            event.seq,
            now,
            event.scope.exchange,
            event.scope.venue,
            event.scope.account_id,
            exchange_order_id,
            event.scope.mode,
        ))
        await self.adapter.commit()
        
        logger.debug(
            f"Order projection updated: {exchange_order_id} -> {order_status}",
            extra={"event_id": event.event_id},
        )
    
    async def _handle_order_cancelled(self, event: Event) -> None:
        """주문 취소 처리 (삭제)"""
        exchange_order_id = event.payload.get("exchange_order_id")
        await self._delete_order(event, exchange_order_id)
    
    async def _handle_order_rejected(self, event: Event) -> None:
        """주문 거부 처리 (삭제)"""
        exchange_order_id = event.payload.get("exchange_order_id")
        if exchange_order_id:
            await self._delete_order(event, exchange_order_id)
    
    async def _delete_order(self, event: Event, exchange_order_id: str) -> None:
        """주문 삭제 (오픈 주문 목록에서 제거)"""
        sql = """
            DELETE FROM projection_order
            WHERE scope_exchange = ?
              AND scope_venue = ?
              AND scope_account_id = ?
              AND exchange_order_id = ?
              AND scope_mode = ?
        """
        
        await self.adapter.execute(sql, (
            event.scope.exchange,
            event.scope.venue,
            event.scope.account_id,
            exchange_order_id,
            event.scope.mode,
        ))
        await self.adapter.commit()
        
        logger.debug(
            f"Order projection deleted: {exchange_order_id}",
            extra={"event_id": event.event_id},
        )
    
    async def _ensure_table_exists(self) -> None:
        """projection_order 테이블 존재 확인 및 생성"""
        sql = """
            CREATE TABLE IF NOT EXISTS projection_order (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                scope_exchange     TEXT NOT NULL,
                scope_venue        TEXT NOT NULL,
                scope_account_id   TEXT NOT NULL,
                scope_symbol       TEXT NOT NULL,
                scope_mode         TEXT NOT NULL DEFAULT 'TESTNET',
                
                exchange_order_id  TEXT NOT NULL,
                client_order_id    TEXT,
                order_state        TEXT NOT NULL,
                side               TEXT NOT NULL,
                order_type         TEXT NOT NULL,
                original_qty       TEXT NOT NULL,
                executed_qty       TEXT NOT NULL DEFAULT '0',
                price              TEXT,
                stop_price         TEXT,
                
                last_event_seq     INTEGER NOT NULL,
                created_at         TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at         TEXT NOT NULL DEFAULT (datetime('now')),
                
                UNIQUE(scope_exchange, scope_venue, scope_account_id, exchange_order_id, scope_mode)
            )
        """
        await self.adapter.execute(sql)
        await self.adapter.commit()
    
    async def get_open_orders(
        self,
        exchange: str,
        venue: str,
        account_id: str,
        mode: str,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        """오픈 주문 조회
        
        Args:
            exchange: 거래소
            venue: 거래 장소
            account_id: 계좌 ID
            mode: 거래 모드
            symbol: 심볼 (None이면 전체)
            
        Returns:
            오픈 주문 목록
        """
        if symbol:
            sql = """
                SELECT 
                    scope_symbol, exchange_order_id, client_order_id,
                    order_state, side, order_type, original_qty, executed_qty,
                    price, stop_price, created_at, updated_at
                FROM projection_order
                WHERE scope_exchange = ?
                  AND scope_venue = ?
                  AND scope_account_id = ?
                  AND scope_mode = ?
                  AND scope_symbol = ?
                ORDER BY created_at
            """
            rows = await self.adapter.fetchall(sql, (
                exchange, venue, account_id, mode, symbol
            ))
        else:
            sql = """
                SELECT 
                    scope_symbol, exchange_order_id, client_order_id,
                    order_state, side, order_type, original_qty, executed_qty,
                    price, stop_price, created_at, updated_at
                FROM projection_order
                WHERE scope_exchange = ?
                  AND scope_venue = ?
                  AND scope_account_id = ?
                  AND scope_mode = ?
                ORDER BY created_at
            """
            rows = await self.adapter.fetchall(sql, (
                exchange, venue, account_id, mode
            ))
        
        return [
            {
                "symbol": row[0],
                "exchange_order_id": row[1],
                "client_order_id": row[2],
                "order_state": row[3],
                "side": row[4],
                "order_type": row[5],
                "original_qty": row[6],
                "executed_qty": row[7],
                "price": row[8],
                "stop_price": row[9],
                "created_at": row[10],
                "updated_at": row[11],
            }
            for row in rows
        ]
    
    async def count_open_orders(
        self,
        exchange: str,
        venue: str,
        account_id: str,
        mode: str,
        symbol: str | None = None,
    ) -> int:
        """오픈 주문 수 조회"""
        if symbol:
            sql = """
                SELECT COUNT(*) as cnt
                FROM projection_order
                WHERE scope_exchange = ?
                  AND scope_venue = ?
                  AND scope_account_id = ?
                  AND scope_mode = ?
                  AND scope_symbol = ?
            """
            row = await self.adapter.fetchone(sql, (
                exchange, venue, account_id, mode, symbol
            ))
        else:
            sql = """
                SELECT COUNT(*) as cnt
                FROM projection_order
                WHERE scope_exchange = ?
                  AND scope_venue = ?
                  AND scope_account_id = ?
                  AND scope_mode = ?
            """
            row = await self.adapter.fetchone(sql, (
                exchange, venue, account_id, mode
            ))
        
        return row[0] if row else 0
