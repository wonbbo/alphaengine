"""
Position Projection Handler

PositionChanged 이벤트를 처리하여 projection_position 테이블 업데이트
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from adapters.db.sqlite_adapter import SQLiteAdapter
from core.domain.events import Event, EventTypes
from bot.projector.handlers.base import ProjectionHandler

logger = logging.getLogger(__name__)


class PositionProjectionHandler(ProjectionHandler):
    """Position Projection 핸들러
    
    PositionChanged 이벤트를 받아 projection_position 테이블 업데이트.
    
    Args:
        adapter: SQLite 어댑터
    """
    
    @property
    def handled_event_types(self) -> list[str]:
        return [EventTypes.POSITION_CHANGED]
    
    async def initialize(self) -> None:
        """테이블 초기화"""
        await self._ensure_table_exists()
    
    async def handle(self, event: Event) -> bool:
        """PositionChanged 이벤트 처리"""
        if event.event_type != EventTypes.POSITION_CHANGED:
            return False
        
        try:
            payload = event.payload
            symbol = event.scope.symbol or payload.get("symbol")
            
            if not symbol:
                logger.warning(f"PositionChanged event missing symbol: {event.event_id}")
                return False
            
            # 포지션 정보 추출
            position_amount = payload.get("position_amount", "0")
            entry_price = payload.get("entry_price", "0")
            unrealized_pnl = payload.get("unrealized_pnl", "0")
            leverage = payload.get("leverage", 1)
            margin_type = payload.get("margin_type", "ISOLATED")
            position_side = payload.get("position_side") or payload.get("side")
            
            # 포지션 방향 결정
            qty = Decimal(position_amount)
            if qty > 0:
                side = position_side if position_side in ("LONG", "SHORT") else "LONG"
            elif qty < 0:
                side = "SHORT"
                qty = abs(qty)  # 수량은 양수로 저장
            else:
                side = None  # FLAT
            
            # 테이블 존재 확인 및 생성
            await self._ensure_table_exists()
            
            # UPSERT 쿼리
            sql = """
                INSERT INTO projection_position (
                    scope_exchange, scope_venue, scope_account_id, scope_symbol, scope_mode,
                    side, qty, entry_price, unrealized_pnl, leverage, margin_type,
                    last_event_seq, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scope_exchange, scope_venue, scope_account_id, scope_symbol, scope_mode)
                DO UPDATE SET
                    side = excluded.side,
                    qty = excluded.qty,
                    entry_price = excluded.entry_price,
                    unrealized_pnl = excluded.unrealized_pnl,
                    leverage = excluded.leverage,
                    margin_type = excluded.margin_type,
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
                side,
                str(qty),
                str(entry_price),
                str(unrealized_pnl),
                leverage,
                margin_type,
                event.seq,
                now,
            ))
            await self.adapter.commit()
            
            logger.debug(
                f"Position projection updated: {symbol}",
                extra={
                    "event_id": event.event_id,
                    "side": side,
                    "qty": str(qty),
                },
            )
            
            return True
            
        except Exception as e:
            logger.error(
                f"Position projection update failed: {e}",
                extra={"event_id": event.event_id},
            )
            return False
    
    async def _ensure_table_exists(self) -> None:
        """projection_position 테이블 존재 확인 및 생성"""
        sql = """
            CREATE TABLE IF NOT EXISTS projection_position (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                scope_exchange   TEXT NOT NULL,
                scope_venue      TEXT NOT NULL,
                scope_account_id TEXT NOT NULL,
                scope_symbol     TEXT NOT NULL,
                scope_mode       TEXT NOT NULL DEFAULT 'TESTNET',
                
                side             TEXT,
                qty              TEXT NOT NULL DEFAULT '0',
                entry_price      TEXT NOT NULL DEFAULT '0',
                unrealized_pnl   TEXT NOT NULL DEFAULT '0',
                leverage         INTEGER NOT NULL DEFAULT 1,
                margin_type      TEXT NOT NULL DEFAULT 'ISOLATED',
                
                last_event_seq   INTEGER NOT NULL,
                updated_at       TEXT NOT NULL DEFAULT (datetime('now')),
                
                UNIQUE(scope_exchange, scope_venue, scope_account_id, scope_symbol, scope_mode)
            )
        """
        await self.adapter.execute(sql)
        await self.adapter.commit()
    
    async def get_position(
        self,
        exchange: str,
        venue: str,
        account_id: str,
        mode: str,
        symbol: str,
    ) -> dict[str, Any] | None:
        """포지션 조회
        
        Args:
            exchange: 거래소
            venue: 거래 장소
            account_id: 계좌 ID
            mode: 거래 모드
            symbol: 심볼
            
        Returns:
            포지션 정보 또는 None
        """
        sql = """
            SELECT 
                scope_symbol, side, qty, entry_price, 
                unrealized_pnl, leverage, margin_type,
                last_event_seq, updated_at
            FROM projection_position
            WHERE scope_exchange = ?
              AND scope_venue = ?
              AND scope_account_id = ?
              AND scope_mode = ?
              AND scope_symbol = ?
        """
        
        row = await self.adapter.fetchone(sql, (
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
                "last_event_seq": row[7],
                "updated_at": row[8],
            }
        
        return None
    
    async def get_all_positions(
        self,
        exchange: str,
        venue: str,
        account_id: str,
        mode: str,
    ) -> list[dict[str, Any]]:
        """모든 포지션 조회 (수량 > 0인 것만)
        
        Args:
            exchange: 거래소
            venue: 거래 장소
            account_id: 계좌 ID
            mode: 거래 모드
            
        Returns:
            포지션 목록
        """
        sql = """
            SELECT 
                scope_symbol, side, qty, entry_price, 
                unrealized_pnl, leverage, margin_type,
                last_event_seq, updated_at
            FROM projection_position
            WHERE scope_exchange = ?
              AND scope_venue = ?
              AND scope_account_id = ?
              AND scope_mode = ?
              AND CAST(qty AS REAL) > 0
            ORDER BY scope_symbol
        """
        
        rows = await self.adapter.fetchall(sql, (
            exchange, venue, account_id, mode
        ))
        
        return [
            {
                "symbol": row[0],
                "side": row[1],
                "qty": row[2],
                "entry_price": row[3],
                "unrealized_pnl": row[4],
                "leverage": row[5],
                "margin_type": row[6],
                "last_event_seq": row[7],
                "updated_at": row[8],
            }
            for row in rows
        ]
