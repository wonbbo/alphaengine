"""
SQLite 어댑터

WAL 모드로 SQLite 연결 관리.
Bot과 Web이 동시에 접근 가능하도록 설정.

주의: SQLite alias로 time, count 사용 금지 (예약어)
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

import aiosqlite

from core.constants import Paths
from core.types import TradingMode

logger = logging.getLogger(__name__)


def get_db_path(mode: TradingMode | str) -> Path:
    """모드에 따른 DB 경로 반환
    
    Args:
        mode: 거래 모드 (PRODUCTION/TESTNET)
        
    Returns:
        DB 파일 경로 (Path 타입)
    """
    if isinstance(mode, str):
        mode = TradingMode(mode.lower())
    
    if mode == TradingMode.PRODUCTION:
        return Paths.PROD_DB
    return Paths.TEST_DB


async def create_connection(
    db_path: Path | str,
    readonly: bool = False,
) -> aiosqlite.Connection:
    """SQLite 연결 생성 (WAL 모드)
    
    Args:
        db_path: DB 파일 경로
        readonly: 읽기 전용 여부
        
    Returns:
        aiosqlite 연결 객체
    """
    # pathlib.Path를 문자열로 변환
    db_path_str = str(db_path)
    
    # 디렉토리가 없으면 생성
    db_dir = Path(db_path).parent
    db_dir.mkdir(parents=True, exist_ok=True)
    
    # 연결 생성
    if readonly:
        # 읽기 전용 모드
        conn = await aiosqlite.connect(f"file:{db_path_str}?mode=ro", uri=True)
    else:
        conn = await aiosqlite.connect(db_path_str)
    
    # WAL 모드 설정
    await conn.execute("PRAGMA journal_mode=WAL")
    
    # 동시 접근 설정
    await conn.execute("PRAGMA busy_timeout=30000")  # 30초 대기
    
    # 외래 키 제약 활성화
    await conn.execute("PRAGMA foreign_keys=ON")
    
    logger.info(
        "SQLite 연결 생성",
        extra={"db_path": db_path_str, "readonly": readonly},
    )
    
    return conn


class SQLiteAdapter:
    """SQLite 어댑터
    
    WAL 모드로 SQLite 연결 관리.
    트랜잭션 컨텍스트 매니저 제공.
    
    Args:
        db_path: DB 파일 경로
        readonly: 읽기 전용 여부 (Web 조회용)
    
    사용 예시:
    ```python
    adapter = SQLiteAdapter(db_path)
    await adapter.connect()
    
    async with adapter.transaction() as conn:
        await conn.execute("INSERT INTO ...")
    
    await adapter.close()
    ```
    """
    
    def __init__(self, db_path: Path | str, readonly: bool = False):
        self.db_path = Path(db_path)
        self.readonly = readonly
        self._conn: aiosqlite.Connection | None = None
    
    @property
    def is_connected(self) -> bool:
        """연결 상태 확인"""
        return self._conn is not None
    
    async def connect(self) -> None:
        """연결 생성"""
        if self._conn is not None:
            return
        
        self._conn = await create_connection(self.db_path, self.readonly)
    
    async def close(self) -> None:
        """연결 종료"""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
            logger.info("SQLite 연결 종료")
    
    async def execute(
        self,
        sql: str,
        parameters: tuple[Any, ...] | None = None,
    ) -> aiosqlite.Cursor:
        """SQL 실행"""
        if self._conn is None:
            raise RuntimeError("Not connected to database")
        
        if parameters:
            return await self._conn.execute(sql, parameters)
        return await self._conn.execute(sql)
    
    async def executemany(
        self,
        sql: str,
        parameters: list[tuple[Any, ...]],
    ) -> aiosqlite.Cursor:
        """SQL 다중 실행"""
        if self._conn is None:
            raise RuntimeError("Not connected to database")
        
        return await self._conn.executemany(sql, parameters)
    
    async def fetchone(
        self,
        sql: str,
        parameters: tuple[Any, ...] | None = None,
    ) -> tuple[Any, ...] | None:
        """단일 행 조회"""
        cursor = await self.execute(sql, parameters)
        return await cursor.fetchone()
    
    async def fetchall(
        self,
        sql: str,
        parameters: tuple[Any, ...] | None = None,
    ) -> list[tuple[Any, ...]]:
        """전체 행 조회"""
        cursor = await self.execute(sql, parameters)
        return await cursor.fetchall()
    
    async def commit(self) -> None:
        """커밋"""
        if self._conn is not None:
            await self._conn.commit()
    
    async def rollback(self) -> None:
        """롤백"""
        if self._conn is not None:
            await self._conn.rollback()
    
    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[aiosqlite.Connection]:
        """트랜잭션 컨텍스트 매니저
        
        성공 시 자동 커밋, 예외 시 자동 롤백.
        
        사용 예시:
        ```python
        async with adapter.transaction() as conn:
            await conn.execute("INSERT INTO ...")
            # 성공 시 자동 커밋
        ```
        """
        if self._conn is None:
            raise RuntimeError("Not connected to database")
        
        try:
            yield self._conn
            await self._conn.commit()
        except Exception:
            await self._conn.rollback()
            raise
    
    async def table_exists(self, table_name: str) -> bool:
        """테이블 존재 여부 확인"""
        result = await self.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        return result is not None
    
    async def get_table_info(self, table_name: str) -> list[dict[str, Any]]:
        """테이블 정보 조회"""
        rows = await self.fetchall(f"PRAGMA table_info({table_name})")
        
        columns = []
        for row in rows:
            columns.append({
                "cid": row[0],
                "name": row[1],
                "type": row[2],
                "notnull": bool(row[3]),
                "default_value": row[4],
                "pk": bool(row[5]),
            })
        
        return columns
    
    # -------------------------------------------------------------------------
    # 컨텍스트 매니저
    # -------------------------------------------------------------------------
    
    async def __aenter__(self) -> "SQLiteAdapter":
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()


async def init_schema(adapter: SQLiteAdapter) -> None:
    """스키마 초기화 (테이블 생성)
    
    Args:
        adapter: 연결된 SQLiteAdapter
    
    주의: 별도의 마이그레이션 스크립트에서 호출.
    """
    # event_store
    await adapter.execute("""
        CREATE TABLE IF NOT EXISTS event_store (
            seq              INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id         TEXT NOT NULL UNIQUE,
            event_type       TEXT NOT NULL,
            ts               TEXT NOT NULL,
            
            correlation_id   TEXT NOT NULL,
            causation_id     TEXT,
            command_id       TEXT,
            source           TEXT NOT NULL,
            
            entity_kind      TEXT NOT NULL,
            entity_id        TEXT NOT NULL,
            
            scope_exchange   TEXT NOT NULL,
            scope_venue      TEXT NOT NULL,
            scope_account_id TEXT NOT NULL,
            scope_symbol     TEXT,
            scope_mode       TEXT NOT NULL DEFAULT 'TESTNET',
            
            dedup_key        TEXT NOT NULL UNIQUE,
            payload_json     TEXT NOT NULL,
            
            created_at       TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    
    # command_store
    await adapter.execute("""
        CREATE TABLE IF NOT EXISTS command_store (
            seq              INTEGER PRIMARY KEY AUTOINCREMENT,
            command_id       TEXT NOT NULL UNIQUE,
            command_type     TEXT NOT NULL,
            ts               TEXT NOT NULL,
            
            correlation_id   TEXT NOT NULL,
            causation_id     TEXT,
            
            actor_kind       TEXT NOT NULL,
            actor_id         TEXT NOT NULL,
            
            scope_exchange   TEXT NOT NULL,
            scope_venue      TEXT NOT NULL,
            scope_account_id TEXT NOT NULL,
            scope_symbol     TEXT,
            scope_mode       TEXT NOT NULL DEFAULT 'TESTNET',
            
            idempotency_key  TEXT NOT NULL UNIQUE,
            status           TEXT NOT NULL DEFAULT 'NEW',
            priority         INTEGER NOT NULL DEFAULT 0,
            
            payload_json     TEXT NOT NULL,
            result_json      TEXT,
            last_error       TEXT,
            
            created_at       TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at       TEXT NOT NULL DEFAULT (datetime('now')),
            claimed_at       TEXT,
            completed_at     TEXT
        )
    """)
    
    # config_store
    await adapter.execute("""
        CREATE TABLE IF NOT EXISTS config_store (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            config_key   TEXT NOT NULL UNIQUE,
            value_json   TEXT NOT NULL,
            version      INTEGER NOT NULL DEFAULT 1,
            
            updated_by   TEXT NOT NULL,
            created_at   TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    
    # checkpoint_store
    await adapter.execute("""
        CREATE TABLE IF NOT EXISTS checkpoint_store (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            checkpoint_type  TEXT NOT NULL UNIQUE,
            last_seq         INTEGER NOT NULL DEFAULT 0,
            last_ts          TEXT,
            metadata_json    TEXT,
            updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    
    # projection_balance (현재 잔고 Projection)
    await adapter.execute("""
        CREATE TABLE IF NOT EXISTS projection_balance (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            scope_exchange   TEXT NOT NULL,
            scope_venue      TEXT NOT NULL,
            scope_account_id TEXT NOT NULL,
            scope_mode       TEXT NOT NULL DEFAULT 'TESTNET',
            
            asset            TEXT NOT NULL,
            free             TEXT NOT NULL DEFAULT '0',
            locked           TEXT NOT NULL DEFAULT '0',
            
            last_event_seq   INTEGER NOT NULL,
            updated_at       TEXT NOT NULL DEFAULT (datetime('now')),
            
            UNIQUE(scope_exchange, scope_venue, scope_account_id, asset, scope_mode)
        )
    """)
    
    # transfers (입출금 이체 테이블)
    await adapter.execute("""
        CREATE TABLE IF NOT EXISTS transfers (
            transfer_id      TEXT PRIMARY KEY,
            transfer_type    TEXT NOT NULL,
            status           TEXT NOT NULL,
            
            requested_amount TEXT NOT NULL,
            requested_at     TEXT NOT NULL,
            requested_by     TEXT NOT NULL,
            
            current_step     INTEGER DEFAULT 0,
            total_steps      INTEGER NOT NULL,
            
            actual_amount    TEXT,
            fee_amount       TEXT,
            
            upbit_order_id   TEXT,
            binance_order_id TEXT,
            blockchain_txid  TEXT,
            
            completed_at     TEXT,
            error_message    TEXT,
            
            created_at       TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # 인덱스 생성
    await adapter.execute("""
        CREATE INDEX IF NOT EXISTS ix_event_store_ts 
        ON event_store(ts)
    """)
    
    await adapter.execute("""
        CREATE INDEX IF NOT EXISTS ix_event_store_entity 
        ON event_store(entity_kind, entity_id)
    """)
    
    await adapter.execute("""
        CREATE INDEX IF NOT EXISTS ix_event_store_type 
        ON event_store(event_type)
    """)
    
    await adapter.execute("""
        CREATE INDEX IF NOT EXISTS ix_command_store_status 
        ON command_store(status, priority DESC, ts)
    """)

    # transfers 인덱스
    await adapter.execute("""
        CREATE INDEX IF NOT EXISTS ix_transfers_status 
        ON transfers(status)
    """)

    await adapter.execute("""
        CREATE INDEX IF NOT EXISTS ix_transfers_type 
        ON transfers(transfer_type)
    """)

    await adapter.execute("""
        CREATE INDEX IF NOT EXISTS ix_transfers_requested_at 
        ON transfers(requested_at)
    """)
    
    await adapter.commit()
    
    logger.info("스키마 초기화 완료")
