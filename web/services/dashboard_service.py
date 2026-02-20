"""
Dashboard 서비스

Projection 테이블에서 현재 상태 조회
"""

import logging
from datetime import datetime, timezone
from typing import Any

from adapters.db.sqlite_adapter import SQLiteAdapter

logger = logging.getLogger(__name__)


class DashboardService:
    """Dashboard 서비스
    
    projection_* 테이블에서 현재 상태 조회.
    Web에서 읽기 전용으로 사용.
    
    Args:
        db: SQLite 어댑터 (읽기 전용)
    """
    
    def __init__(self, db: SQLiteAdapter):
        self.db = db
    
    async def get_position(
        self,
        exchange: str,
        venue: str,
        account_id: str,
        mode: str,
        symbol: str,
    ) -> dict[str, Any] | None:
        """포지션 조회"""
        sql = """
            SELECT 
                scope_symbol, side, qty, entry_price, 
                unrealized_pnl, leverage, margin_type, updated_at
            FROM projection_position
            WHERE scope_exchange = ?
              AND scope_venue = ?
              AND scope_account_id = ?
              AND scope_mode = ?
              AND scope_symbol = ?
              AND CAST(qty AS REAL) > 0
        """
        
        try:
            row = await self.db.fetchone(sql, (
                exchange, venue, account_id, mode, symbol
            ))
            
            if row:
                return {
                    "symbol": row[0],
                    "side": row[1],
                    "qty": row[2],
                    "entry_price": row[3],
                    "unrealized_pnl": row[4],
                    "leverage": row[5],
                    "margin_type": row[6],
                    "updated_at": row[7],
                }
        except Exception as e:
            logger.debug(f"Position table not found or error: {e}")
        
        return None
    
    async def get_balances(
        self,
        exchange: str,
        venue: str,
        account_id: str,
        mode: str,
    ) -> list[dict[str, Any]]:
        """잔고 목록 조회"""
        sql = """
            SELECT asset, free, locked, updated_at
            FROM projection_balance
            WHERE scope_exchange = ?
              AND scope_venue = ?
              AND scope_account_id = ?
              AND scope_mode = ?
            ORDER BY asset
        """
        
        try:
            rows = await self.db.fetchall(sql, (
                exchange, venue, account_id, mode
            ))
            
            return [
                {
                    "asset": row[0],
                    "free": row[1],
                    "locked": row[2],
                    "updated_at": row[3],
                }
                for row in rows
            ]
        except Exception as e:
            logger.debug(f"Balance table not found or error: {e}")
            return []
    
    async def get_open_orders(
        self,
        exchange: str,
        venue: str,
        account_id: str,
        mode: str,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        """오픈 주문 목록 조회"""
        if symbol:
            sql = """
                SELECT 
                    scope_symbol, exchange_order_id, client_order_id,
                    order_state, side, order_type, original_qty, executed_qty,
                    price, stop_price, created_at
                FROM projection_order
                WHERE scope_exchange = ?
                  AND scope_venue = ?
                  AND scope_account_id = ?
                  AND scope_mode = ?
                  AND scope_symbol = ?
                ORDER BY created_at DESC
            """
            params = (exchange, venue, account_id, mode, symbol)
        else:
            sql = """
                SELECT 
                    scope_symbol, exchange_order_id, client_order_id,
                    order_state, side, order_type, original_qty, executed_qty,
                    price, stop_price, created_at
                FROM projection_order
                WHERE scope_exchange = ?
                  AND scope_venue = ?
                  AND scope_account_id = ?
                  AND scope_mode = ?
                ORDER BY created_at DESC
            """
            params = (exchange, venue, account_id, mode)
        
        try:
            rows = await self.db.fetchall(sql, params)
            
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
                }
                for row in rows
            ]
        except Exception as e:
            logger.debug(f"Order table not found or error: {e}")
            return []
    
    async def get_recent_trades(
        self,
        exchange: str,
        venue: str,
        account_id: str,
        mode: str,
        symbol: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """최근 체결 목록 조회 (event_store에서)"""
        if symbol:
            sql = """
                SELECT event_id, ts, payload_json, scope_symbol
                FROM event_store
                WHERE event_type = 'TradeExecuted'
                  AND scope_exchange = ?
                  AND scope_venue = ?
                  AND scope_account_id = ?
                  AND scope_mode = ?
                  AND scope_symbol = ?
                ORDER BY ts DESC
                LIMIT ?
            """
            params = (exchange, venue, account_id, mode, symbol, limit)
        else:
            sql = """
                SELECT event_id, ts, payload_json, scope_symbol
                FROM event_store
                WHERE event_type = 'TradeExecuted'
                  AND scope_exchange = ?
                  AND scope_venue = ?
                  AND scope_account_id = ?
                  AND scope_mode = ?
                ORDER BY ts DESC
                LIMIT ?
            """
            params = (exchange, venue, account_id, mode, limit)
        
        try:
            import json
            rows = await self.db.fetchall(sql, params)
            
            trades = []
            for row in rows:
                payload = json.loads(row[2]) if isinstance(row[2], str) else row[2]
                trades.append({
                    "event_id": row[0],
                    "symbol": row[3] or payload.get("symbol"),
                    "side": payload.get("side"),
                    "qty": payload.get("qty") or payload.get("quantity"),
                    "price": payload.get("price"),
                    "realized_pnl": payload.get("realized_pnl"),
                    "ts": row[1],
                })
            
            return trades
        except Exception as e:
            logger.debug(f"Trade query error: {e}")
            return []
    
    async def get_event_count(self, mode: str) -> int:
        """전체 이벤트 수 조회"""
        sql = """
            SELECT COUNT(*) as event_cnt
            FROM event_store
            WHERE scope_mode = ?
        """
        
        try:
            row = await self.db.fetchone(sql, (mode,))
            return row[0] if row else 0
        except Exception:
            return 0
    
    async def get_pending_command_count(self, mode: str) -> int:
        """처리 대기 Command 수 조회"""
        sql = """
            SELECT COUNT(*) as cmd_cnt
            FROM command_store
            WHERE scope_mode = ?
              AND status IN ('NEW', 'SENT')
        """
        
        try:
            row = await self.db.fetchone(sql, (mode,))
            return row[0] if row else 0
        except Exception:
            return 0
