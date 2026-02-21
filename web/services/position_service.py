"""
포지션 서비스

포지션 세션 조회
"""

import logging
from decimal import Decimal
from typing import Any

from adapters.db.sqlite_adapter import SQLiteAdapter

logger = logging.getLogger(__name__)


class PositionService:
    """포지션 서비스
    
    position_session 및 position_trade 테이블 조회.
    """
    
    def __init__(self, db: SQLiteAdapter):
        self.db = db
    
    async def get_positions(
        self,
        mode: str,
        status: str | None = None,
        symbol: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """포지션 목록 조회
        
        Args:
            mode: TESTNET 또는 PRODUCTION
            status: OPEN 또는 CLOSED (선택)
            symbol: 심볼 필터 (선택)
            limit: 조회 개수 제한
            offset: 시작 위치
            
        Returns:
            positions, total_count, limit, offset 포함 응답
        """
        conditions = ["scope_mode = ?"]
        params: list[Any] = [mode]
        
        if status:
            conditions.append("status = ?")
            params.append(status)
        
        if symbol:
            conditions.append("symbol = ?")
            params.append(symbol)
        
        where_clause = " AND ".join(conditions)
        
        # 목록 조회
        sql = f"""
            SELECT 
                session_id, symbol, side, status,
                opened_at, closed_at,
                initial_qty, max_qty,
                realized_pnl, total_commission, trade_count, close_reason
            FROM position_session
            WHERE {where_clause}
            ORDER BY opened_at DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])
        
        rows = await self.db.fetchall(sql, tuple(params))
        
        # 누적 PnL 계산 (시간순 정렬 후)
        positions = []
        cumulative_pnl = Decimal("0")
        
        for row in reversed(rows):
            pnl = Decimal(str(row[8])) if row[8] else Decimal("0")
            cumulative_pnl += pnl
            
            positions.insert(0, {
                "session_id": row[0],
                "symbol": row[1],
                "side": row[2],
                "status": row[3],
                "opened_at": row[4],
                "closed_at": row[5],
                "initial_qty": row[6],
                "max_qty": row[7],
                "realized_pnl": str(pnl),
                "total_commission": row[9],
                "trade_count": row[10],
                "close_reason": row[11],
                "cumulative_pnl": str(cumulative_pnl),
            })
        
        # 총 개수 (페이지네이션용)
        count_conditions = ["scope_mode = ?"]
        count_params: list[Any] = [mode]
        if status:
            count_conditions.append("status = ?")
            count_params.append(status)
        if symbol:
            count_conditions.append("symbol = ?")
            count_params.append(symbol)
        
        count_sql = f"""
            SELECT COUNT(*) FROM position_session
            WHERE {' AND '.join(count_conditions)}
        """
        count_row = await self.db.fetchone(count_sql, tuple(count_params))
        total_count = count_row[0] if count_row else 0
        
        return {
            "positions": positions,
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
        }
    
    async def get_position_detail(self, session_id: str) -> dict[str, Any] | None:
        """포지션 상세 조회
        
        Args:
            session_id: 포지션 세션 ID
            
        Returns:
            포지션 상세 정보 또는 None
        """
        sql = """
            SELECT 
                session_id, scope_mode, scope_venue, symbol, side, status,
                opened_at, closed_at,
                initial_qty, max_qty,
                realized_pnl, total_commission, trade_count, close_reason
            FROM position_session
            WHERE session_id = ?
        """
        row = await self.db.fetchone(sql, (session_id,))
        
        if not row:
            return None
        
        return {
            "session_id": row[0],
            "scope_mode": row[1],
            "scope_venue": row[2],
            "symbol": row[3],
            "side": row[4],
            "status": row[5],
            "opened_at": row[6],
            "closed_at": row[7],
            "initial_qty": row[8],
            "max_qty": row[9],
            "realized_pnl": row[10],
            "total_commission": row[11],
            "trade_count": row[12],
            "close_reason": row[13],
        }
    
    async def get_position_trades(self, session_id: str) -> list[dict[str, Any]]:
        """포지션 내 거래 목록 조회
        
        Args:
            session_id: 포지션 세션 ID
            
        Returns:
            거래 목록
        """
        sql = """
            SELECT 
                id, trade_event_id, journal_entry_id,
                action, qty, price,
                realized_pnl, commission, position_qty_after,
                created_at
            FROM position_trade
            WHERE session_id = ?
            ORDER BY created_at
        """
        rows = await self.db.fetchall(sql, (session_id,))
        
        return [
            {
                "id": row[0],
                "trade_event_id": row[1],
                "journal_entry_id": row[2],
                "action": row[3],
                "qty": row[4],
                "price": row[5],
                "realized_pnl": row[6],
                "commission": row[7],
                "position_qty_after": row[8],
                "created_at": row[9],
            }
            for row in rows
        ]
    
    async def get_closed_positions(
        self,
        mode: str,
        limit: int = 60,
    ) -> list[dict[str, Any]]:
        """청산된 포지션 목록 조회 (시간순)
        
        Trading Edge 계산용으로 청산된 포지션만 시간순 조회.
        
        Args:
            mode: TESTNET 또는 PRODUCTION
            limit: 조회 개수 제한
            
        Returns:
            청산된 포지션 목록 (오래된 것부터)
        """
        sql = """
            SELECT 
                session_id, symbol, side, 
                closed_at, realized_pnl
            FROM position_session
            WHERE scope_mode = ? AND status = 'CLOSED'
            ORDER BY closed_at DESC
            LIMIT ?
        """
        rows = await self.db.fetchall(sql, (mode, limit))
        
        # 시간순 정렬 (오래된 것부터)
        return [
            {
                "session_id": row[0],
                "symbol": row[1],
                "side": row[2],
                "closed_at": row[3],
                "realized_pnl": float(row[4]) if row[4] else 0.0,
            }
            for row in reversed(rows)
        ]
