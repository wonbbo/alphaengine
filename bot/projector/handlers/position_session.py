"""
Position Session Handler

TradeExecuted 이벤트를 처리하여 position_session/position_trade 테이블 관리.
포지션 진입/추가/청산을 추적하여 세션 단위로 손익을 집계.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from adapters.db.sqlite_adapter import SQLiteAdapter
from core.domain.events import Event, EventTypes
from bot.projector.handlers.base import ProjectionHandler

logger = logging.getLogger(__name__)


class PositionSessionHandler(ProjectionHandler):
    """Position Session 핸들러
    
    TradeExecuted 이벤트를 받아 position_session/position_trade 테이블 업데이트.
    
    동작 방식:
    1. 거래 발생 시 현재 OPEN 세션 조회
    2. 진입(ENTRY) 거래: 세션 없으면 새로 생성, 있으면 추가
    3. 청산(EXIT) 거래: 포지션 수량 감소, 0이 되면 세션 종료
    """
    
    @property
    def handled_event_types(self) -> list[str]:
        return [EventTypes.TRADE_EXECUTED]
    
    async def initialize(self) -> None:
        """테이블 초기화"""
        await self._ensure_tables_exist()
    
    async def handle(self, event: Event) -> bool:
        """TradeExecuted 이벤트 처리"""
        if event.event_type != EventTypes.TRADE_EXECUTED:
            return False
        
        try:
            payload = event.payload
            symbol = event.scope.symbol or payload.get("symbol")
            
            if not symbol:
                logger.warning(f"TradeExecuted event missing symbol: {event.event_id}")
                return False
            
            # 거래 정보 추출
            trade_side = payload.get("side", "").upper()  # BUY or SELL
            qty = Decimal(str(payload.get("qty", "0")))
            price = Decimal(str(payload.get("price", "0")))
            realized_pnl = Decimal(str(payload.get("realized_pnl", "0")))
            commission = Decimal(str(payload.get("commission", "0")))
            
            if qty <= 0:
                return False
            
            mode = event.scope.mode
            venue = event.scope.venue
            
            # 현재 OPEN 세션 조회
            session = await self._get_open_session(mode, venue, symbol)
            
            # 세션 상태에 따른 처리
            if session is None:
                # 새 포지션 진입
                await self._create_session(
                    event, symbol, trade_side, qty, price, 
                    realized_pnl, commission, mode, venue
                )
            else:
                # 기존 세션에 거래 추가
                await self._update_session(
                    event, session, trade_side, qty, price,
                    realized_pnl, commission
                )
            
            return True
            
        except Exception as e:
            logger.error(
                f"Position session update failed: {e}",
                extra={"event_id": event.event_id},
            )
            return False
    
    async def _get_open_session(
        self, mode: str, venue: str, symbol: str
    ) -> dict[str, Any] | None:
        """현재 OPEN 상태 세션 조회"""
        row = await self.adapter.fetchone(
            """
            SELECT session_id, side, initial_qty, max_qty, 
                   realized_pnl, total_commission, trade_count
            FROM position_session
            WHERE scope_mode = ? AND scope_venue = ? AND symbol = ? AND status = 'OPEN'
            ORDER BY opened_at DESC
            LIMIT 1
            """,
            (mode, venue, symbol),
        )
        
        if row is None:
            return None
        
        return {
            "session_id": row[0],
            "side": row[1],
            "initial_qty": Decimal(str(row[2])),
            "max_qty": Decimal(str(row[3])),
            "realized_pnl": Decimal(str(row[4])),
            "total_commission": Decimal(str(row[5])),
            "trade_count": row[6],
        }
    
    async def _get_current_position_qty(self, session_id: str) -> Decimal:
        """세션의 현재 포지션 수량 계산"""
        row = await self.adapter.fetchone(
            """
            SELECT position_qty_after
            FROM position_trade
            WHERE session_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (session_id,),
        )
        
        if row is None:
            return Decimal("0")
        
        return Decimal(str(row[0]))
    
    async def _create_session(
        self,
        event: Event,
        symbol: str,
        side: str,
        qty: Decimal,
        price: Decimal,
        realized_pnl: Decimal,
        commission: Decimal,
        mode: str,
        venue: str,
    ) -> None:
        """새 세션 생성"""
        session_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        
        # 포지션 방향 결정 (BUY → LONG, SELL → SHORT)
        position_side = "LONG" if side == "BUY" else "SHORT"
        
        # 세션 생성
        await self.adapter.execute(
            """
            INSERT INTO position_session (
                session_id, scope_mode, scope_venue, symbol, side, status,
                opened_at, initial_qty, max_qty, realized_pnl, total_commission,
                trade_count, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'OPEN', ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                session_id, mode, venue, symbol, position_side,
                now, str(qty), str(qty), str(realized_pnl), str(commission),
                now, now,
            ),
        )
        
        # 거래 기록
        await self._record_trade(
            session_id, event.event_id, "ENTRY", qty, price,
            realized_pnl, commission, qty
        )
        
        await self.adapter.commit()
        
        logger.debug(
            f"Position session created: {session_id}",
            extra={
                "symbol": symbol,
                "side": position_side,
                "qty": str(qty),
            },
        )
    
    async def _update_session(
        self,
        event: Event,
        session: dict[str, Any],
        trade_side: str,
        qty: Decimal,
        price: Decimal,
        realized_pnl: Decimal,
        commission: Decimal,
    ) -> None:
        """기존 세션 업데이트"""
        session_id = session["session_id"]
        position_side = session["side"]
        current_qty = await self._get_current_position_qty(session_id)
        
        # 진입 방향과 거래 방향 비교
        # LONG 포지션: BUY = 추가, SELL = 청산
        # SHORT 포지션: SELL = 추가, BUY = 청산
        is_same_direction = (
            (position_side == "LONG" and trade_side == "BUY") or
            (position_side == "SHORT" and trade_side == "SELL")
        )
        
        if is_same_direction:
            # 포지션 추가 (ADD)
            new_qty = current_qty + qty
            action = "ADD"
        else:
            # 포지션 청산 (REDUCE or EXIT)
            new_qty = current_qty - qty
            if new_qty < 0:
                new_qty = Decimal("0")
            action = "REDUCE" if new_qty > 0 else "EXIT"
        
        # 최대 수량 업데이트
        new_max_qty = max(session["max_qty"], new_qty)
        
        # 누적 손익/수수료
        new_realized_pnl = session["realized_pnl"] + realized_pnl
        new_total_commission = session["total_commission"] + commission
        new_trade_count = session["trade_count"] + 1
        
        now = datetime.now(timezone.utc).isoformat()
        
        # 세션 업데이트
        if new_qty <= 0:
            # 포지션 종료
            await self.adapter.execute(
                """
                UPDATE position_session
                SET status = 'CLOSED', closed_at = ?, close_reason = 'TRADE',
                    max_qty = ?, realized_pnl = ?, total_commission = ?,
                    trade_count = ?, updated_at = ?
                WHERE session_id = ?
                """,
                (
                    now, str(new_max_qty), str(new_realized_pnl),
                    str(new_total_commission), new_trade_count, now, session_id,
                ),
            )
        else:
            # 포지션 유지
            await self.adapter.execute(
                """
                UPDATE position_session
                SET max_qty = ?, realized_pnl = ?, total_commission = ?,
                    trade_count = ?, updated_at = ?
                WHERE session_id = ?
                """,
                (
                    str(new_max_qty), str(new_realized_pnl),
                    str(new_total_commission), new_trade_count, now, session_id,
                ),
            )
        
        # 거래 기록
        await self._record_trade(
            session_id, event.event_id, action, qty, price,
            realized_pnl, commission, new_qty
        )
        
        await self.adapter.commit()
        
        logger.debug(
            f"Position session updated: {session_id}",
            extra={
                "action": action,
                "qty": str(qty),
                "position_qty_after": str(new_qty),
            },
        )
    
    async def _record_trade(
        self,
        session_id: str,
        event_id: str,
        action: str,
        qty: Decimal,
        price: Decimal,
        realized_pnl: Decimal,
        commission: Decimal,
        position_qty_after: Decimal,
    ) -> None:
        """거래 기록 추가"""
        now = datetime.now(timezone.utc).isoformat()
        
        await self.adapter.execute(
            """
            INSERT INTO position_trade (
                session_id, trade_event_id, action, qty, price,
                realized_pnl, commission, position_qty_after, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id, event_id, action, str(qty), str(price),
                str(realized_pnl), str(commission), str(position_qty_after), now,
            ),
        )
    
    async def _ensure_tables_exist(self) -> None:
        """테이블 존재 확인 및 생성"""
        # position_session 테이블
        await self.adapter.execute("""
            CREATE TABLE IF NOT EXISTS position_session (
                session_id       TEXT PRIMARY KEY,
                scope_mode       TEXT NOT NULL,
                scope_venue      TEXT NOT NULL,
                symbol           TEXT NOT NULL,
                side             TEXT NOT NULL,
                status           TEXT NOT NULL DEFAULT 'OPEN',
                opened_at        TEXT NOT NULL,
                closed_at        TEXT,
                initial_qty      TEXT NOT NULL,
                max_qty          TEXT NOT NULL,
                realized_pnl     TEXT NOT NULL DEFAULT '0',
                total_commission TEXT NOT NULL DEFAULT '0',
                trade_count      INTEGER NOT NULL DEFAULT 0,
                close_reason     TEXT,
                created_at       TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        
        # position_trade 테이블
        await self.adapter.execute("""
            CREATE TABLE IF NOT EXISTS position_trade (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id       TEXT NOT NULL,
                trade_event_id   TEXT NOT NULL,
                journal_entry_id TEXT,
                action           TEXT NOT NULL,
                qty              TEXT NOT NULL,
                price            TEXT NOT NULL,
                realized_pnl     TEXT,
                commission       TEXT,
                position_qty_after TEXT NOT NULL,
                created_at       TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (session_id) REFERENCES position_session(session_id)
            )
        """)
        
        # 인덱스
        await self.adapter.execute("""
            CREATE INDEX IF NOT EXISTS idx_position_session_open
            ON position_session(scope_mode, scope_venue, symbol, status)
        """)
        
        await self.adapter.execute("""
            CREATE INDEX IF NOT EXISTS idx_position_trade_session
            ON position_trade(session_id)
        """)
        
        await self.adapter.commit()
