"""
복식부기 스키마 초기화

Bot/Web 시작 시 자동으로 Ledger 테이블과 View 생성.
CREATE IF NOT EXISTS / DROP VIEW IF EXISTS 패턴으로 안전하게 동작.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from adapters.db.sqlite_adapter import SQLiteAdapter

logger = logging.getLogger(__name__)


async def init_ledger_schema(db: "SQLiteAdapter") -> None:
    """Ledger 스키마 초기화 (테이블 + View)
    
    Bot/Web 시작 시 호출되어 필요한 모든 테이블과 View를 생성.
    이미 존재하는 경우 안전하게 건너뜀 (IF NOT EXISTS).
    
    Args:
        db: SQLiteAdapter 인스턴스
    """
    await _create_ledger_tables(db)
    await _create_ledger_views(db)
    await _insert_initial_accounts(db)
    logger.info("Ledger 스키마 초기화 완료")


async def _create_ledger_tables(db: "SQLiteAdapter") -> None:
    """Ledger 테이블 생성"""
    
    # account 테이블
    await db.execute("""
        CREATE TABLE IF NOT EXISTS account (
            account_id       TEXT PRIMARY KEY,
            account_type     TEXT NOT NULL,
            venue            TEXT NOT NULL,
            asset            TEXT,
            name             TEXT NOT NULL,
            description      TEXT,
            is_active        INTEGER DEFAULT 1,
            created_at       TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    
    # journal_entry 테이블
    await db.execute("""
        CREATE TABLE IF NOT EXISTS journal_entry (
            entry_id         TEXT PRIMARY KEY,
            ts               TEXT NOT NULL,
            transaction_type TEXT NOT NULL,
            scope_mode       TEXT NOT NULL,
            related_trade_id    TEXT,
            related_order_id    TEXT,
            related_position_id TEXT,
            symbol              TEXT,
            source_event_id  TEXT,
            source           TEXT NOT NULL,
            description      TEXT,
            memo             TEXT,
            raw_data         TEXT,
            is_balanced      INTEGER DEFAULT 1,
            created_at       TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    
    # journal_line 테이블
    await db.execute("""
        CREATE TABLE IF NOT EXISTS journal_line (
            line_id          INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id         TEXT NOT NULL,
            account_id       TEXT NOT NULL,
            side             TEXT NOT NULL,
            amount           TEXT NOT NULL,
            asset            TEXT NOT NULL,
            usdt_value       TEXT NOT NULL,
            usdt_rate        TEXT NOT NULL,
            memo             TEXT,
            line_order       INTEGER DEFAULT 0,
            FOREIGN KEY (entry_id) REFERENCES journal_entry(entry_id),
            FOREIGN KEY (account_id) REFERENCES account(account_id)
        )
    """)
    
    # account_balance 테이블 (Projection)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS account_balance (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id       TEXT NOT NULL,
            scope_mode       TEXT NOT NULL,
            balance          TEXT NOT NULL DEFAULT '0',
            last_entry_id    TEXT,
            last_entry_ts    TEXT,
            updated_at       TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(account_id, scope_mode),
            FOREIGN KEY (account_id) REFERENCES account(account_id)
        )
    """)
    
    # position_session 테이블
    await db.execute("""
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
    await db.execute("""
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
    
    # daily_snapshot 테이블
    await db.execute("""
        CREATE TABLE IF NOT EXISTS daily_snapshot (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date    TEXT NOT NULL,
            scope_mode       TEXT NOT NULL,
            scope_venue      TEXT NOT NULL,
            asset            TEXT NOT NULL,
            closing_balance  TEXT NOT NULL,
            realized_pnl     TEXT NOT NULL DEFAULT '0',
            cumulative_pnl   TEXT NOT NULL DEFAULT '0',
            trade_count      INTEGER NOT NULL DEFAULT 0,
            winning_trades   INTEGER NOT NULL DEFAULT 0,
            losing_trades    INTEGER NOT NULL DEFAULT 0,
            total_fees       TEXT NOT NULL DEFAULT '0',
            created_at       TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(snapshot_date, scope_mode, scope_venue, asset)
        )
    """)
    
    # 인덱스 생성
    await db.execute("CREATE INDEX IF NOT EXISTS idx_account_type ON account(account_type)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_account_venue ON account(venue)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_journal_entry_ts ON journal_entry(ts)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_journal_entry_type ON journal_entry(transaction_type)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_journal_entry_source_event ON journal_entry(source_event_id)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_journal_entry_symbol ON journal_entry(symbol)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_journal_entry_mode ON journal_entry(scope_mode)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_journal_line_entry ON journal_line(entry_id)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_journal_line_account ON journal_line(account_id)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_journal_line_asset ON journal_line(asset)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_account_balance_account ON account_balance(account_id)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_position_session_symbol ON position_session(symbol)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_position_session_status ON position_session(status)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_position_session_mode ON position_session(scope_mode)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_position_trade_session ON position_trade(session_id)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_position_trade_event ON position_trade(trade_event_id)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_daily_snapshot_date ON daily_snapshot(snapshot_date)")
    
    await db.commit()
    logger.debug("Ledger 테이블 생성 완료")


async def _create_ledger_views(db: "SQLiteAdapter") -> None:
    """프론트엔드 조회용 View 생성
    
    복잡한 JOIN/집계를 미리 정의하여 API 성능 향상.
    View는 항상 DROP 후 CREATE하여 스키마 변경 시에도 안전.
    """
    
    # 1. 거래 요약 View (v_trade_summary)
    await db.execute("DROP VIEW IF EXISTS v_trade_summary")
    await db.execute("""
        CREATE VIEW v_trade_summary AS
        SELECT 
            je.entry_id,
            je.ts,
            je.scope_mode,
            je.symbol,
            je.transaction_type,
            je.description,
            je.related_trade_id,
            je.related_order_id,
            -- Base Asset 매수 수량
            SUM(CASE 
                WHEN jl.side = 'DEBIT' 
                    AND jl.asset != 'USDT' 
                    AND jl.account_id LIKE 'ASSET:%'
                THEN CAST(jl.amount AS REAL) 
                ELSE 0 
            END) as bought_qty,
            -- Base Asset 매도 수량
            SUM(CASE 
                WHEN jl.side = 'CREDIT' 
                    AND jl.asset != 'USDT' 
                    AND jl.account_id LIKE 'ASSET:%'
                THEN CAST(jl.amount AS REAL) 
                ELSE 0 
            END) as sold_qty,
            -- USDT 지출 (매수 시)
            SUM(CASE 
                WHEN jl.side = 'CREDIT' 
                    AND jl.asset = 'USDT' 
                    AND jl.account_id LIKE 'ASSET:%'
                THEN CAST(jl.amount AS REAL) 
                ELSE 0 
            END) as usdt_spent,
            -- USDT 수령 (매도 시)
            SUM(CASE 
                WHEN jl.side = 'DEBIT' 
                    AND jl.asset = 'USDT' 
                    AND jl.account_id LIKE 'ASSET:%'
                THEN CAST(jl.amount AS REAL) 
                ELSE 0 
            END) as usdt_received,
            -- 수수료 (USDT 환산)
            SUM(CASE 
                WHEN jl.account_id LIKE 'EXPENSE:FEE:%'
                THEN CAST(jl.usdt_value AS REAL) 
                ELSE 0 
            END) as fee_usdt,
            -- 실현 손익
            SUM(CASE 
                WHEN jl.account_id = 'INCOME:TRADING:REALIZED_PNL' AND jl.side = 'CREDIT'
                THEN CAST(jl.amount AS REAL)
                WHEN jl.account_id = 'INCOME:TRADING:REALIZED_PNL' AND jl.side = 'DEBIT'
                THEN -CAST(jl.amount AS REAL)
                ELSE 0 
            END) as realized_pnl
        FROM journal_entry je
        JOIN journal_line jl ON je.entry_id = jl.entry_id
        WHERE je.transaction_type = 'TRADE'
        GROUP BY je.entry_id
    """)
    
    # 2. 일별 손익 View (v_daily_pnl)
    await db.execute("DROP VIEW IF EXISTS v_daily_pnl")
    await db.execute("""
        CREATE VIEW v_daily_pnl AS
        SELECT 
            DATE(je.ts) as trade_date,
            je.scope_mode,
            COUNT(DISTINCT je.entry_id) as trade_count,
            SUM(CASE 
                WHEN jl.account_id = 'INCOME:TRADING:REALIZED_PNL' AND jl.side = 'CREDIT'
                THEN CAST(jl.amount AS REAL)
                WHEN jl.account_id = 'INCOME:TRADING:REALIZED_PNL' AND jl.side = 'DEBIT'
                THEN -CAST(jl.amount AS REAL)
                ELSE 0 
            END) as daily_pnl,
            SUM(CASE 
                WHEN jl.account_id LIKE 'EXPENSE:FEE:TRADING%'
                THEN CAST(jl.usdt_value AS REAL) 
                ELSE 0 
            END) as trading_fees,
            SUM(CASE 
                WHEN jl.account_id LIKE 'EXPENSE:FEE:FUNDING%'
                THEN CAST(jl.usdt_value AS REAL) 
                ELSE 0 
            END) as funding_fees,
            SUM(CASE 
                WHEN jl.account_id LIKE 'EXPENSE:FEE:%'
                THEN CAST(jl.usdt_value AS REAL) 
                ELSE 0 
            END) as total_fees,
            COUNT(DISTINCT CASE 
                WHEN jl.account_id = 'INCOME:TRADING:REALIZED_PNL' 
                    AND jl.side = 'CREDIT' 
                    AND CAST(jl.amount AS REAL) > 0
                THEN je.entry_id 
            END) as winning_count,
            COUNT(DISTINCT CASE 
                WHEN jl.account_id = 'INCOME:TRADING:REALIZED_PNL' 
                    AND jl.side = 'DEBIT'
                THEN je.entry_id 
            END) as losing_count
        FROM journal_entry je
        JOIN journal_line jl ON je.entry_id = jl.entry_id
        GROUP BY DATE(je.ts), je.scope_mode
        ORDER BY trade_date DESC
    """)
    
    # 3. 수수료 요약 View (v_fee_summary)
    await db.execute("DROP VIEW IF EXISTS v_fee_summary")
    await db.execute("""
        CREATE VIEW v_fee_summary AS
        SELECT 
            DATE(je.ts) as fee_date,
            je.scope_mode,
            jl.account_id as fee_type,
            jl.asset as fee_asset,
            SUM(CAST(jl.amount AS REAL)) as total_amount,
            SUM(CAST(jl.usdt_value AS REAL)) as total_usdt_value,
            COUNT(*) as fee_count
        FROM journal_entry je
        JOIN journal_line jl ON je.entry_id = jl.entry_id
        WHERE jl.account_id LIKE 'EXPENSE:FEE:%'
            AND jl.side = 'DEBIT'
        GROUP BY DATE(je.ts), je.scope_mode, jl.account_id, jl.asset
        ORDER BY fee_date DESC
    """)
    
    # 4. 계정별 거래 내역 View (v_account_ledger)
    await db.execute("DROP VIEW IF EXISTS v_account_ledger")
    await db.execute("""
        CREATE VIEW v_account_ledger AS
        SELECT 
            je.ts,
            je.entry_id,
            je.scope_mode,
            jl.account_id,
            jl.asset,
            jl.side,
            CAST(jl.amount AS REAL) as amount,
            CAST(jl.usdt_value AS REAL) as usdt_value,
            CASE jl.side 
                WHEN 'DEBIT' THEN CAST(jl.amount AS REAL)
                ELSE -CAST(jl.amount AS REAL)
            END as signed_amount,
            je.transaction_type,
            je.description,
            je.symbol
        FROM journal_entry je
        JOIN journal_line jl ON je.entry_id = jl.entry_id
        ORDER BY jl.account_id, je.ts, jl.line_order
    """)
    
    # 5. 포트폴리오 현황 View (v_portfolio)
    await db.execute("DROP VIEW IF EXISTS v_portfolio")
    await db.execute("""
        CREATE VIEW v_portfolio AS
        SELECT 
            a.venue,
            a.asset,
            a.account_id,
            a.name,
            ab.scope_mode,
            CAST(COALESCE(ab.balance, '0') AS REAL) as balance,
            ab.last_entry_ts as last_updated
        FROM account a
        LEFT JOIN account_balance ab ON a.account_id = ab.account_id
        WHERE a.account_type = 'ASSET'
            AND a.is_active = 1
            AND a.venue IN ('BINANCE_SPOT', 'BINANCE_FUTURES')
        ORDER BY a.venue, a.asset
    """)
    
    # 6. 최근 거래 View (v_recent_trades)
    await db.execute("DROP VIEW IF EXISTS v_recent_trades")
    await db.execute("""
        CREATE VIEW v_recent_trades AS
        SELECT 
            je.entry_id,
            je.ts,
            je.scope_mode,
            je.symbol,
            je.description,
            je.related_trade_id,
            CASE 
                WHEN je.description LIKE 'BUY%' THEN 'BUY'
                WHEN je.description LIKE 'SELL%' THEN 'SELL'
                ELSE 'UNKNOWN'
            END as side,
            (SELECT SUM(CAST(jl2.amount AS REAL))
             FROM journal_line jl2 
             WHERE jl2.entry_id = je.entry_id 
                AND jl2.asset != 'USDT' 
                AND jl2.account_id LIKE 'ASSET:%'
                AND jl2.side IN ('DEBIT', 'CREDIT')
            ) as qty,
            (SELECT SUM(CASE 
                    WHEN jl2.side = 'CREDIT' THEN CAST(jl2.amount AS REAL)
                    ELSE -CAST(jl2.amount AS REAL)
                END)
             FROM journal_line jl2 
             WHERE jl2.entry_id = je.entry_id 
                AND jl2.account_id = 'INCOME:TRADING:REALIZED_PNL'
            ) as realized_pnl,
            (SELECT SUM(CAST(jl2.usdt_value AS REAL))
             FROM journal_line jl2 
             WHERE jl2.entry_id = je.entry_id 
                AND jl2.account_id LIKE 'EXPENSE:FEE:%'
            ) as fee_usdt
        FROM journal_entry je
        WHERE je.transaction_type = 'TRADE'
        ORDER BY je.ts DESC
        LIMIT 100
    """)
    
    # 7. 심볼별 손익 View (v_symbol_pnl)
    await db.execute("DROP VIEW IF EXISTS v_symbol_pnl")
    await db.execute("""
        CREATE VIEW v_symbol_pnl AS
        SELECT 
            je.symbol,
            je.scope_mode,
            COUNT(DISTINCT je.entry_id) as total_trades,
            SUM(CASE 
                WHEN jl.account_id = 'INCOME:TRADING:REALIZED_PNL' AND jl.side = 'CREDIT'
                THEN CAST(jl.amount AS REAL)
                WHEN jl.account_id = 'INCOME:TRADING:REALIZED_PNL' AND jl.side = 'DEBIT'
                THEN -CAST(jl.amount AS REAL)
                ELSE 0 
            END) as total_pnl,
            SUM(CASE 
                WHEN jl.account_id LIKE 'EXPENSE:FEE:%'
                THEN CAST(jl.usdt_value AS REAL) 
                ELSE 0 
            END) as total_fees,
            SUM(CASE 
                WHEN jl.account_id = 'INCOME:TRADING:REALIZED_PNL' AND jl.side = 'CREDIT'
                THEN CAST(jl.amount AS REAL)
                WHEN jl.account_id = 'INCOME:TRADING:REALIZED_PNL' AND jl.side = 'DEBIT'
                THEN -CAST(jl.amount AS REAL)
                ELSE 0 
            END) - SUM(CASE 
                WHEN jl.account_id LIKE 'EXPENSE:FEE:%'
                THEN CAST(jl.usdt_value AS REAL) 
                ELSE 0 
            END) as net_pnl,
            COUNT(DISTINCT CASE 
                WHEN jl.account_id = 'INCOME:TRADING:REALIZED_PNL' 
                    AND jl.side = 'CREDIT' 
                THEN je.entry_id 
            END) as winning_trades,
            COUNT(DISTINCT CASE 
                WHEN jl.account_id = 'INCOME:TRADING:REALIZED_PNL' 
                    AND jl.side = 'DEBIT'
                THEN je.entry_id 
            END) as losing_trades
        FROM journal_entry je
        JOIN journal_line jl ON je.entry_id = jl.entry_id
        WHERE je.transaction_type = 'TRADE'
            AND je.symbol IS NOT NULL
        GROUP BY je.symbol, je.scope_mode
        ORDER BY total_pnl DESC
    """)
    
    # 8. 펀딩 내역 View (v_funding_history)
    await db.execute("DROP VIEW IF EXISTS v_funding_history")
    await db.execute("""
        CREATE VIEW v_funding_history AS
        SELECT 
            je.ts,
            je.entry_id,
            je.scope_mode,
            je.symbol,
            je.transaction_type,
            CASE 
                WHEN je.transaction_type = 'FEE_FUNDING' THEN
                    (SELECT CAST(jl2.amount AS REAL)
                     FROM journal_line jl2 
                     WHERE jl2.entry_id = je.entry_id 
                        AND jl2.account_id LIKE 'EXPENSE:FEE:FUNDING%')
                ELSE 0
            END as funding_paid,
            CASE 
                WHEN je.transaction_type = 'FUNDING_RECEIVED' THEN
                    (SELECT CAST(jl2.amount AS REAL)
                     FROM journal_line jl2 
                     WHERE jl2.entry_id = je.entry_id 
                        AND jl2.account_id = 'INCOME:FUNDING:RECEIVED')
                ELSE 0
            END as funding_received
        FROM journal_entry je
        WHERE je.transaction_type IN ('FEE_FUNDING', 'FUNDING_RECEIVED')
        ORDER BY je.ts DESC
    """)
    
    await db.commit()
    logger.debug("Ledger View 생성 완료")


async def _insert_initial_accounts(db: "SQLiteAdapter") -> None:
    """초기 계정 삽입
    
    INITIAL_ACCOUNTS에 정의된 모든 계정을 생성.
    이미 존재하는 계정은 무시 (INSERT OR IGNORE).
    """
    from core.ledger.types import INITIAL_ACCOUNTS
    
    for account in INITIAL_ACCOUNTS:
        try:
            await db.execute(
                """
                INSERT OR IGNORE INTO account (account_id, account_type, venue, asset, name)
                VALUES (?, ?, ?, ?, ?)
                """,
                account,
            )
        except Exception as e:
            logger.warning(f"계정 삽입 실패 {account[0]}: {e}")
    
    await db.commit()
    logger.debug("초기 계정 삽입 완료")
