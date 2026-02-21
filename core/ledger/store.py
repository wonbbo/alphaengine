"""
Ledger 저장소

복식부기 분개 저장 및 조회
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from core.ledger.entry_builder import JournalEntry, JournalLine
from core.ledger.types import JournalSide

if TYPE_CHECKING:
    from adapters.db.sqlite_adapter import SQLiteAdapter

logger = logging.getLogger(__name__)


class LedgerStore:
    """Ledger 저장소
    
    복식부기 분개를 저장하고 조회하는 클래스.
    account_balance는 Projection으로 관리됨.
    
    Args:
        db: SQLite 어댑터
    """
    
    def __init__(self, db: SQLiteAdapter):
        self.db = db
    
    async def save_entry(self, entry: JournalEntry) -> str:
        """분개 저장
        
        트랜잭션 내에서 journal_entry + journal_line 저장
        account_balance 업데이트
        
        Args:
            entry: 저장할 분개
            
        Returns:
            저장된 entry_id
            
        Raises:
            ValueError: 불균형 분개인 경우
        """
        # 균형 검증
        if not entry.is_balanced():
            raise ValueError(f"Unbalanced entry: {entry.entry_id}")
        
        async with self.db.transaction():
            # journal_entry 저장
            await self.db.execute(
                """
                INSERT INTO journal_entry (
                    entry_id, ts, transaction_type, scope_mode,
                    related_trade_id, related_order_id, related_position_id, symbol,
                    source_event_id, source,
                    description, memo, raw_data, is_balanced
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.entry_id,
                    entry.ts.isoformat(),
                    entry.transaction_type,
                    entry.scope_mode,
                    entry.related_trade_id,
                    entry.related_order_id,
                    entry.related_position_id,
                    entry.symbol,
                    entry.source_event_id,
                    entry.source,
                    entry.description,
                    entry.memo,
                    json.dumps(entry.raw_data) if entry.raw_data else None,
                    1,  # is_balanced
                ),
            )
            
            # journal_line 저장
            for i, line in enumerate(entry.lines):
                await self.db.execute(
                    """
                    INSERT INTO journal_line (
                        entry_id, account_id, side, amount, asset,
                        usdt_value, usdt_rate, memo, line_order
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry.entry_id,
                        line.account_id,
                        line.side,
                        str(line.amount),
                        line.asset,
                        str(line.usdt_value),
                        str(line.usdt_rate),
                        line.memo,
                        i,
                    ),
                )
                
                # account_balance 업데이트
                await self._update_account_balance(
                    account_id=line.account_id,
                    amount=line.amount,
                    side=line.side,
                    scope_mode=entry.scope_mode,
                    entry_id=entry.entry_id,
                    entry_ts=entry.ts.isoformat(),
                )
        
        logger.debug(f"Saved journal entry: {entry.entry_id}")
        return entry.entry_id
    
    async def _update_account_balance(
        self,
        account_id: str,
        amount: Decimal,
        side: str,
        scope_mode: str,
        entry_id: str,
        entry_ts: str,
    ) -> None:
        """계정 잔액 업데이트
        
        ASSET: Debit 증가, Credit 감소
        EXPENSE: Debit 증가
        INCOME: Credit 증가
        """
        # 현재 잔액 조회
        row = await self.db.fetchone(
            """
            SELECT balance FROM account_balance
            WHERE account_id = ? AND scope_mode = ?
            """,
            (account_id, scope_mode),
        )
        
        current_balance = Decimal(row[0]) if row else Decimal("0")
        
        # 계정 유형에 따른 잔액 계산
        # 단순화: Debit + / Credit -
        if side == JournalSide.DEBIT.value:
            new_balance = current_balance + amount
        else:
            new_balance = current_balance - amount
        
        # Upsert
        await self.db.execute(
            """
            INSERT INTO account_balance (account_id, scope_mode, balance, last_entry_id, last_entry_ts)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(account_id, scope_mode) DO UPDATE SET
                balance = excluded.balance,
                last_entry_id = excluded.last_entry_id,
                last_entry_ts = excluded.last_entry_ts,
                updated_at = datetime('now')
            """,
            (account_id, scope_mode, str(new_balance), entry_id, entry_ts),
        )
    
    async def ensure_asset_account(
        self,
        venue: str,
        asset: str,
    ) -> str:
        """Asset 계정이 존재하지 않으면 자동 생성.
        
        Args:
            venue: BINANCE_SPOT, BINANCE_FUTURES, EXTERNAL
            asset: USDT, BTC, ETH, ...
        
        Returns:
            생성되거나 기존에 있는 account_id
        """
        account_id = f"ASSET:{venue}:{asset}"
        
        # INSERT OR IGNORE - 이미 있으면 무시
        await self.db.execute(
            """
            INSERT OR IGNORE INTO account (
                account_id, account_type, venue, asset, name
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                account_id,
                "ASSET",
                venue,
                asset,
                f"{venue} {asset}",
            )
        )
        await self.db.commit()
        
        return account_id
    
    async def get_account_balance(
        self,
        account_id: str,
        scope_mode: str,
    ) -> Decimal:
        """계정 잔액 조회
        
        Args:
            account_id: 계정 ID
            scope_mode: TESTNET 또는 production
            
        Returns:
            잔액 (없으면 0)
        """
        row = await self.db.fetchone(
            """
            SELECT balance FROM account_balance
            WHERE account_id = ? AND scope_mode = ?
            """,
            (account_id, scope_mode),
        )
        return Decimal(row[0]) if row else Decimal("0")
    
    async def get_trial_balance(
        self,
        scope_mode: str,
    ) -> list[dict[str, Any]]:
        """시산표 조회
        
        모든 계정의 잔액 요약.
        
        Args:
            scope_mode: TESTNET 또는 production
            
        Returns:
            계정별 잔액 목록
        """
        rows = await self.db.fetchall(
            """
            SELECT 
                a.account_id,
                a.account_type,
                a.venue,
                a.asset,
                a.name,
                COALESCE(ab.balance, '0') as balance
            FROM account a
            LEFT JOIN account_balance ab 
                ON a.account_id = ab.account_id AND ab.scope_mode = ?
            WHERE a.is_active = 1
            ORDER BY a.account_type, a.venue, a.asset
            """,
            (scope_mode,),
        )
        
        return [
            {
                "account_id": row[0],
                "account_type": row[1],
                "venue": row[2],
                "asset": row[3],
                "name": row[4],
                "balance": row[5],
            }
            for row in rows
        ]
    
    async def get_entries_by_account(
        self,
        account_id: str,
        scope_mode: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """계정별 분개 조회
        
        특정 계정에 관련된 모든 분개 항목 조회.
        
        Args:
            account_id: 계정 ID
            scope_mode: TESTNET 또는 production
            limit: 조회 개수 제한
            offset: 시작 위치
            
        Returns:
            분개 항목 목록
        """
        rows = await self.db.fetchall(
            """
            SELECT 
                je.entry_id,
                je.ts,
                je.transaction_type,
                je.description,
                jl.amount,
                jl.side,
                jl.asset,
                jl.usdt_value
            FROM journal_entry je
            JOIN journal_line jl ON je.entry_id = jl.entry_id
            WHERE jl.account_id = ? AND je.scope_mode = ?
            ORDER BY je.ts DESC
            LIMIT ? OFFSET ?
            """,
            (account_id, scope_mode, limit, offset),
        )
        
        return [
            {
                "entry_id": row[0],
                "ts": row[1],
                "transaction_type": row[2],
                "description": row[3],
                "amount": row[4],
                "side": row[5],
                "asset": row[6],
                "usdt_value": row[7],
            }
            for row in rows
        ]
    
    async def get_entry(self, entry_id: str) -> dict[str, Any] | None:
        """분개 단건 조회
        
        Args:
            entry_id: 분개 ID
            
        Returns:
            분개 정보 (없으면 None)
        """
        # 분개 헤더 조회
        row = await self.db.fetchone(
            """
            SELECT 
                entry_id, ts, transaction_type, scope_mode,
                related_trade_id, related_order_id, related_position_id, symbol,
                source_event_id, source, description, memo, raw_data, is_balanced
            FROM journal_entry
            WHERE entry_id = ?
            """,
            (entry_id,),
        )
        
        if not row:
            return None
        
        entry = {
            "entry_id": row[0],
            "ts": row[1],
            "transaction_type": row[2],
            "scope_mode": row[3],
            "related_trade_id": row[4],
            "related_order_id": row[5],
            "related_position_id": row[6],
            "symbol": row[7],
            "source_event_id": row[8],
            "source": row[9],
            "description": row[10],
            "memo": row[11],
            "raw_data": json.loads(row[12]) if row[12] else None,
            "is_balanced": bool(row[13]),
            "lines": [],
        }
        
        # 분개 항목 조회
        lines = await self.db.fetchall(
            """
            SELECT 
                line_id, account_id, side, amount, asset,
                usdt_value, usdt_rate, memo, line_order
            FROM journal_line
            WHERE entry_id = ?
            ORDER BY line_order
            """,
            (entry_id,),
        )
        
        entry["lines"] = [
            {
                "line_id": line[0],
                "account_id": line[1],
                "side": line[2],
                "amount": line[3],
                "asset": line[4],
                "usdt_value": line[5],
                "usdt_rate": line[6],
                "memo": line[7],
                "line_order": line[8],
            }
            for line in lines
        ]
        
        return entry
    
    async def get_entries_by_type(
        self,
        transaction_type: str,
        scope_mode: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """거래 타입별 분개 조회
        
        Args:
            transaction_type: 거래 타입 (TRADE, DEPOSIT 등)
            scope_mode: TESTNET 또는 production
            limit: 조회 개수 제한
            offset: 시작 위치
            
        Returns:
            분개 목록
        """
        rows = await self.db.fetchall(
            """
            SELECT 
                entry_id, ts, transaction_type, scope_mode,
                symbol, source, description
            FROM journal_entry
            WHERE transaction_type = ? AND scope_mode = ?
            ORDER BY ts DESC
            LIMIT ? OFFSET ?
            """,
            (transaction_type, scope_mode, limit, offset),
        )
        
        return [
            {
                "entry_id": row[0],
                "ts": row[1],
                "transaction_type": row[2],
                "scope_mode": row[3],
                "symbol": row[4],
                "source": row[5],
                "description": row[6],
            }
            for row in rows
        ]
    
    async def get_suspense_entries(
        self,
        scope_mode: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """SUSPENSE 계정 항목 조회
        
        미결 항목 모니터링용.
        
        Args:
            scope_mode: TESTNET 또는 production
            limit: 조회 개수 제한
            
        Returns:
            SUSPENSE 계정 관련 분개 목록
        """
        rows = await self.db.fetchall(
            """
            SELECT 
                je.entry_id,
                je.ts,
                je.transaction_type,
                je.description,
                je.memo,
                je.source_event_id,
                jl.amount,
                jl.side,
                jl.asset
            FROM journal_entry je
            JOIN journal_line jl ON je.entry_id = jl.entry_id
            WHERE jl.account_id = 'EQUITY:SUSPENSE'
              AND je.scope_mode = ?
            ORDER BY je.ts DESC
            LIMIT ?
            """,
            (scope_mode, limit),
        )
        
        return [
            {
                "entry_id": row[0],
                "ts": row[1],
                "transaction_type": row[2],
                "description": row[3],
                "memo": row[4],
                "source_event_id": row[5],
                "amount": row[6],
                "side": row[7],
                "asset": row[8],
            }
            for row in rows
        ]
    
    async def get_account(self, account_id: str) -> dict[str, Any] | None:
        """계정 정보 조회
        
        Args:
            account_id: 계정 ID
            
        Returns:
            계정 정보 (없으면 None)
        """
        row = await self.db.fetchone(
            """
            SELECT 
                account_id, account_type, venue, asset, name, description, is_active
            FROM account
            WHERE account_id = ?
            """,
            (account_id,),
        )
        
        if not row:
            return None
        
        return {
            "account_id": row[0],
            "account_type": row[1],
            "venue": row[2],
            "asset": row[3],
            "name": row[4],
            "description": row[5],
            "is_active": bool(row[6]),
        }
    
    async def list_accounts(
        self,
        account_type: str | None = None,
        venue: str | None = None,
    ) -> list[dict[str, Any]]:
        """계정 목록 조회
        
        Args:
            account_type: 필터링할 계정 유형 (선택)
            venue: 필터링할 Venue (선택)
            
        Returns:
            계정 목록
        """
        sql = "SELECT account_id, account_type, venue, asset, name, is_active FROM account WHERE is_active = 1"
        params: list[Any] = []
        
        if account_type:
            sql += " AND account_type = ?"
            params.append(account_type)
        
        if venue:
            sql += " AND venue = ?"
            params.append(venue)
        
        sql += " ORDER BY account_type, venue, asset"
        
        rows = await self.db.fetchall(sql, tuple(params))
        
        return [
            {
                "account_id": row[0],
                "account_type": row[1],
                "venue": row[2],
                "asset": row[3],
                "name": row[4],
                "is_active": bool(row[5]),
            }
            for row in rows
        ]
    
    # =====================================
    # View 기반 조회 메서드 (프론트엔드용)
    # =====================================
    
    async def get_trade_summary(
        self,
        scope_mode: str,
        symbol: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """거래 요약 조회 (v_trade_summary View 사용)
        
        대시보드/거래 내역 페이지용.
        
        Args:
            scope_mode: TESTNET 또는 PRODUCTION
            symbol: 필터링할 심볼 (선택)
            limit: 조회 개수 제한
            offset: 시작 위치
            
        Returns:
            거래 요약 목록
        """
        sql = """
            SELECT 
                entry_id, ts, scope_mode, symbol, transaction_type,
                description, related_trade_id, related_order_id,
                bought_qty, sold_qty, usdt_spent, usdt_received,
                fee_usdt, realized_pnl
            FROM v_trade_summary
            WHERE scope_mode = ?
        """
        params: list[Any] = [scope_mode]
        
        if symbol:
            sql += " AND symbol = ?"
            params.append(symbol)
        
        sql += " ORDER BY ts DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        rows = await self.db.fetchall(sql, tuple(params))
        
        return [
            {
                "entry_id": row[0],
                "ts": row[1],
                "scope_mode": row[2],
                "symbol": row[3],
                "transaction_type": row[4],
                "description": row[5],
                "related_trade_id": row[6],
                "related_order_id": row[7],
                "bought_qty": row[8],
                "sold_qty": row[9],
                "usdt_spent": row[10],
                "usdt_received": row[11],
                "fee_usdt": row[12],
                "realized_pnl": row[13],
            }
            for row in rows
        ]
    
    async def get_daily_pnl(
        self,
        scope_mode: str,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        """일별 손익 조회 (v_daily_pnl View 사용)
        
        대시보드 차트용.
        
        Args:
            scope_mode: TESTNET 또는 PRODUCTION
            start_date: 시작일 (YYYY-MM-DD)
            end_date: 종료일 (YYYY-MM-DD)
            limit: 조회 일수 제한
            
        Returns:
            일별 손익 목록
        """
        sql = """
            SELECT 
                trade_date, scope_mode, trade_count,
                daily_pnl, trading_fees, funding_fees, total_fees,
                winning_count, losing_count
            FROM v_daily_pnl
            WHERE scope_mode = ?
        """
        params: list[Any] = [scope_mode]
        
        if start_date:
            sql += " AND trade_date >= ?"
            params.append(start_date)
        
        if end_date:
            sql += " AND trade_date <= ?"
            params.append(end_date)
        
        sql += " ORDER BY trade_date DESC LIMIT ?"
        params.append(limit)
        
        rows = await self.db.fetchall(sql, tuple(params))
        
        return [
            {
                "trade_date": row[0],
                "scope_mode": row[1],
                "trade_count": row[2],
                "daily_pnl": row[3],
                "trading_fees": row[4],
                "funding_fees": row[5],
                "total_fees": row[6],
                "winning_count": row[7],
                "losing_count": row[8],
            }
            for row in rows
        ]
    
    async def get_daily_pnl_series(
        self,
        scope_mode: str,
        days: int = 30,
    ) -> dict[str, Any]:
        """일별 손익 시계열 (차트 데이터용)
        
        Args:
            scope_mode: TESTNET 또는 PRODUCTION
            days: 조회 일수
            
        Returns:
            labels, values, cumulative 포함 차트 데이터
        """
        rows = await self.get_daily_pnl(scope_mode, limit=days)
        
        # 시간순 정렬 (오래된 것부터)
        rows = list(reversed(rows))
        
        labels = [row["trade_date"] for row in rows]
        values = [row["daily_pnl"] or 0 for row in rows]
        
        # 누적 계산
        cumulative = []
        total = 0
        for v in values:
            total += v
            cumulative.append(total)
        
        return {
            "labels": labels,
            "values": values,
            "cumulative": cumulative,
        }
    
    async def get_fee_summary(
        self,
        scope_mode: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """수수료 요약 조회 (v_fee_summary View 사용)
        
        Args:
            scope_mode: TESTNET 또는 PRODUCTION
            start_date: 시작일 (YYYY-MM-DD)
            end_date: 종료일 (YYYY-MM-DD)
            
        Returns:
            수수료 타입/자산별 요약
        """
        sql = """
            SELECT 
                fee_date, scope_mode, fee_type, fee_asset,
                total_amount, total_usdt_value, fee_count
            FROM v_fee_summary
            WHERE scope_mode = ?
        """
        params: list[Any] = [scope_mode]
        
        if start_date:
            sql += " AND fee_date >= ?"
            params.append(start_date)
        
        if end_date:
            sql += " AND fee_date <= ?"
            params.append(end_date)
        
        sql += " ORDER BY fee_date DESC"
        
        rows = await self.db.fetchall(sql, tuple(params))
        
        return [
            {
                "fee_date": row[0],
                "scope_mode": row[1],
                "fee_type": row[2],
                "fee_asset": row[3],
                "total_amount": row[4],
                "total_usdt_value": row[5],
                "fee_count": row[6],
            }
            for row in rows
        ]
    
    async def get_account_ledger(
        self,
        account_id: str,
        scope_mode: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """계정별 원장 조회 (v_account_ledger View 사용)
        
        Args:
            account_id: 계정 ID
            scope_mode: TESTNET 또는 PRODUCTION
            limit: 조회 개수 제한
            offset: 시작 위치
            
        Returns:
            계정별 거래 내역
        """
        rows = await self.db.fetchall(
            """
            SELECT 
                ts, entry_id, scope_mode, account_id, asset,
                side, amount, usdt_value, signed_amount,
                transaction_type, description, symbol
            FROM v_account_ledger
            WHERE account_id = ? AND scope_mode = ?
            ORDER BY ts DESC
            LIMIT ? OFFSET ?
            """,
            (account_id, scope_mode, limit, offset),
        )
        
        return [
            {
                "ts": row[0],
                "entry_id": row[1],
                "scope_mode": row[2],
                "account_id": row[3],
                "asset": row[4],
                "side": row[5],
                "amount": row[6],
                "usdt_value": row[7],
                "signed_amount": row[8],
                "transaction_type": row[9],
                "description": row[10],
                "symbol": row[11],
            }
            for row in rows
        ]
    
    async def get_portfolio(
        self,
        scope_mode: str,
    ) -> list[dict[str, Any]]:
        """포트폴리오 현황 조회 (v_portfolio View 사용)
        
        Args:
            scope_mode: TESTNET 또는 PRODUCTION
            
        Returns:
            Venue/Asset별 잔액 현황
        """
        rows = await self.db.fetchall(
            """
            SELECT 
                venue, asset, account_id, name, scope_mode, balance, last_updated
            FROM v_portfolio
            WHERE scope_mode = ? OR scope_mode IS NULL
            ORDER BY venue, asset
            """,
            (scope_mode,),
        )
        
        return [
            {
                "venue": row[0],
                "asset": row[1],
                "account_id": row[2],
                "name": row[3],
                "scope_mode": row[4],
                "balance": row[5] or 0,
                "last_updated": row[6],
            }
            for row in rows
        ]
    
    async def get_recent_trades(
        self,
        scope_mode: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """최근 거래 조회 (v_recent_trades View 사용)
        
        대시보드 '최근 체결' 위젯용.
        
        Args:
            scope_mode: TESTNET 또는 PRODUCTION
            limit: 조회 개수 제한
            
        Returns:
            최근 거래 목록
        """
        rows = await self.db.fetchall(
            """
            SELECT 
                entry_id, ts, scope_mode, symbol, description,
                related_trade_id, side, qty, realized_pnl, fee_usdt
            FROM v_recent_trades
            WHERE scope_mode = ?
            ORDER BY ts DESC
            LIMIT ?
            """,
            (scope_mode, limit),
        )
        
        return [
            {
                "entry_id": row[0],
                "ts": row[1],
                "scope_mode": row[2],
                "symbol": row[3],
                "description": row[4],
                "related_trade_id": row[5],
                "side": row[6],
                "qty": row[7],
                "realized_pnl": row[8],
                "fee_usdt": row[9],
            }
            for row in rows
        ]
    
    async def get_symbol_pnl(
        self,
        scope_mode: str,
    ) -> list[dict[str, Any]]:
        """심볼별 손익 조회 (v_symbol_pnl View 사용)
        
        Trading Edge 페이지용.
        
        Args:
            scope_mode: TESTNET 또는 PRODUCTION
            
        Returns:
            심볼별 성과 분석 데이터
        """
        rows = await self.db.fetchall(
            """
            SELECT 
                symbol, scope_mode, total_trades,
                total_pnl, total_fees, net_pnl,
                winning_trades, losing_trades
            FROM v_symbol_pnl
            WHERE scope_mode = ?
            ORDER BY net_pnl DESC
            """,
            (scope_mode,),
        )
        
        results = []
        for row in rows:
            total_trades = row[2]
            winning_trades = row[6]
            losing_trades = row[7]
            
            # 심볼별 Trading Edge 계산 (position_session 기준으로 통일)
            # Edge = (승률 × 평균수익) - (패률 × 평균손실)
            edge = 0.0
            
            # position_session에서 직접 승/패 및 평균 계산
            pnl_row = await self.db.fetchone(
                """
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN CAST(realized_pnl AS REAL) > 0 THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN CAST(realized_pnl AS REAL) < 0 THEN 1 ELSE 0 END) as losses,
                    AVG(CASE WHEN CAST(realized_pnl AS REAL) > 0 THEN CAST(realized_pnl AS REAL) ELSE NULL END) as avg_win,
                    AVG(CASE WHEN CAST(realized_pnl AS REAL) < 0 THEN ABS(CAST(realized_pnl AS REAL)) ELSE NULL END) as avg_loss
                FROM position_session
                WHERE scope_mode = ? AND symbol = ? AND status = 'CLOSED'
                """,
                (scope_mode, row[0]),
            )
            
            if pnl_row and pnl_row[0] > 0:
                ps_total = pnl_row[0]
                ps_wins = pnl_row[1] or 0
                ps_losses = pnl_row[2] or 0
                avg_win = pnl_row[3] or 0
                avg_loss = pnl_row[4] or 0
                
                win_rate = ps_wins / ps_total
                loss_rate = ps_losses / ps_total
                edge = (win_rate * avg_win) - (loss_rate * avg_loss)
            
            results.append({
                "symbol": row[0],
                "scope_mode": row[1],
                "total_trades": total_trades,
                "total_pnl": row[3],
                "total_fees": row[4],
                "net_pnl": row[5],
                "winning_trades": winning_trades,
                "losing_trades": losing_trades,
                "win_rate": round(winning_trades / total_trades * 100, 2) if total_trades > 0 else 0,
                "trading_edge": round(edge, 4),
            })
        
        return results
    
    async def get_funding_history(
        self,
        scope_mode: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """펀딩 내역 조회 (v_funding_history View 사용)
        
        Args:
            scope_mode: TESTNET 또는 PRODUCTION
            limit: 조회 개수 제한
            offset: 시작 위치
            
        Returns:
            펀딩 내역 목록
        """
        rows = await self.db.fetchall(
            """
            SELECT 
                ts, entry_id, scope_mode, symbol, transaction_type,
                funding_paid, funding_received
            FROM v_funding_history
            WHERE scope_mode = ?
            ORDER BY ts DESC
            LIMIT ? OFFSET ?
            """,
            (scope_mode, limit, offset),
        )
        
        return [
            {
                "ts": row[0],
                "entry_id": row[1],
                "scope_mode": row[2],
                "symbol": row[3],
                "transaction_type": row[4],
                "funding_paid": row[5],
                "funding_received": row[6],
            }
            for row in rows
        ]
    
    async def get_pnl_statistics(
        self,
        scope_mode: str,
    ) -> dict[str, Any]:
        """PnL 통계 요약 (대시보드 카드용)
        
        Args:
            scope_mode: TESTNET 또는 PRODUCTION
            
        Returns:
            일일/주간/월간/전체 PnL 및 승률
        """
        # 전체 통계
        total_row = await self.db.fetchone(
            """
            SELECT 
                SUM(daily_pnl) as total_pnl,
                SUM(trade_count) as total_trades,
                SUM(winning_count) as total_wins,
                SUM(losing_count) as total_losses,
                SUM(total_fees) as total_fees
            FROM v_daily_pnl
            WHERE scope_mode = ?
            """,
            (scope_mode,),
        )
        
        # 일일 통계
        daily_row = await self.db.fetchone(
            """
            SELECT 
                daily_pnl, trade_count, winning_count, losing_count, total_fees
            FROM v_daily_pnl
            WHERE scope_mode = ? AND trade_date = DATE('now')
            """,
            (scope_mode,),
        )
        
        # 주간 통계
        weekly_row = await self.db.fetchone(
            """
            SELECT 
                SUM(daily_pnl), SUM(trade_count), SUM(winning_count), 
                SUM(losing_count), SUM(total_fees)
            FROM v_daily_pnl
            WHERE scope_mode = ? AND trade_date >= DATE('now', '-7 days')
            """,
            (scope_mode,),
        )
        
        # 월간 통계
        monthly_row = await self.db.fetchone(
            """
            SELECT 
                SUM(daily_pnl), SUM(trade_count), SUM(winning_count), 
                SUM(losing_count), SUM(total_fees)
            FROM v_daily_pnl
            WHERE scope_mode = ? AND trade_date >= DATE('now', '-30 days')
            """,
            (scope_mode,),
        )
        
        def calc_win_rate(wins: int | None, losses: int | None) -> float:
            w = wins or 0
            l = losses or 0
            total = w + l
            return round(w / total * 100, 2) if total > 0 else 0.0
        
        return {
            "total": {
                "pnl": total_row[0] if total_row else 0,
                "trades": total_row[1] if total_row else 0,
                "wins": total_row[2] if total_row else 0,
                "losses": total_row[3] if total_row else 0,
                "fees": total_row[4] if total_row else 0,
                "win_rate": calc_win_rate(total_row[2] if total_row else 0, total_row[3] if total_row else 0),
            },
            "daily": {
                "pnl": daily_row[0] if daily_row else 0,
                "trades": daily_row[1] if daily_row else 0,
                "wins": daily_row[2] if daily_row else 0,
                "losses": daily_row[3] if daily_row else 0,
                "fees": daily_row[4] if daily_row else 0,
                "win_rate": calc_win_rate(daily_row[2] if daily_row else 0, daily_row[3] if daily_row else 0),
            },
            "weekly": {
                "pnl": weekly_row[0] if weekly_row else 0,
                "trades": weekly_row[1] if weekly_row else 0,
                "wins": weekly_row[2] if weekly_row else 0,
                "losses": weekly_row[3] if weekly_row else 0,
                "fees": weekly_row[4] if weekly_row else 0,
                "win_rate": calc_win_rate(weekly_row[2] if weekly_row else 0, weekly_row[3] if weekly_row else 0),
            },
            "monthly": {
                "pnl": monthly_row[0] if monthly_row else 0,
                "trades": monthly_row[1] if monthly_row else 0,
                "wins": monthly_row[2] if monthly_row else 0,
                "losses": monthly_row[3] if monthly_row else 0,
                "fees": monthly_row[4] if monthly_row else 0,
                "win_rate": calc_win_rate(monthly_row[2] if monthly_row else 0, monthly_row[3] if monthly_row else 0),
            },
        }
