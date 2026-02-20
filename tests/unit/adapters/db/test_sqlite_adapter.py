"""
SQLite 어댑터 테스트

SQLiteAdapter 및 관련 함수 테스트.
"""

import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

from adapters.db.sqlite_adapter import (
    SQLiteAdapter,
    get_db_path,
    create_connection,
    init_schema,
)
from core.constants import Paths
from core.types import TradingMode


class TestGetDbPath:
    """get_db_path 테스트"""
    
    def test_production_mode(self) -> None:
        """Production 모드"""
        path = get_db_path(TradingMode.PRODUCTION)
        
        assert path == Paths.PROD_DB
        assert isinstance(path, Path)
    
    def test_testnet_mode(self) -> None:
        """Testnet 모드"""
        path = get_db_path(TradingMode.TESTNET)
        
        assert path == Paths.TEST_DB
    
    def test_string_mode(self) -> None:
        """문자열 모드"""
        path = get_db_path("production")
        
        assert path == Paths.PROD_DB
    
    def test_string_mode_testnet(self) -> None:
        """문자열 Testnet 모드"""
        path = get_db_path("testnet")
        
        assert path == Paths.TEST_DB


class TestCreateConnection:
    """create_connection 테스트"""
    
    @pytest.mark.asyncio
    async def test_create_connection(self, tmp_path: Path) -> None:
        """연결 생성"""
        db_path = tmp_path / "test.db"
        
        conn = await create_connection(db_path)
        
        assert conn is not None
        
        # WAL 모드 확인
        cursor = await conn.execute("PRAGMA journal_mode")
        row = await cursor.fetchone()
        assert row[0].upper() == "WAL"
        
        await conn.close()
    
    @pytest.mark.asyncio
    async def test_creates_parent_directory(self, tmp_path: Path) -> None:
        """부모 디렉토리 생성"""
        db_path = tmp_path / "subdir" / "test.db"
        
        conn = await create_connection(db_path)
        
        assert db_path.parent.exists()
        
        await conn.close()


class TestSQLiteAdapter:
    """SQLiteAdapter 테스트"""
    
    @pytest_asyncio.fixture
    async def adapter(self, tmp_path: Path) -> SQLiteAdapter:
        """어댑터 픽스처"""
        db_path = tmp_path / "test.db"
        adapter = SQLiteAdapter(db_path)
        await adapter.connect()
        yield adapter
        await adapter.close()
    
    @pytest.mark.asyncio
    async def test_connect_and_close(self, tmp_path: Path) -> None:
        """연결 및 종료"""
        db_path = tmp_path / "test.db"
        adapter = SQLiteAdapter(db_path)
        
        assert adapter.is_connected is False
        
        await adapter.connect()
        assert adapter.is_connected is True
        
        await adapter.close()
        assert adapter.is_connected is False
    
    @pytest.mark.asyncio
    async def test_execute(self, adapter: SQLiteAdapter) -> None:
        """SQL 실행"""
        await adapter.execute(
            "CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)"
        )
        await adapter.execute(
            "INSERT INTO test (name) VALUES (?)",
            ("테스트",),
        )
        await adapter.commit()
        
        # 확인
        row = await adapter.fetchone("SELECT name FROM test WHERE id = 1")
        assert row[0] == "테스트"
    
    @pytest.mark.asyncio
    async def test_fetchall(self, adapter: SQLiteAdapter) -> None:
        """전체 조회"""
        await adapter.execute("CREATE TABLE items (value TEXT)")
        await adapter.executemany(
            "INSERT INTO items (value) VALUES (?)",
            [("A",), ("B",), ("C",)],
        )
        await adapter.commit()
        
        rows = await adapter.fetchall("SELECT value FROM items ORDER BY value")
        
        assert len(rows) == 3
        assert rows[0][0] == "A"
        assert rows[1][0] == "B"
        assert rows[2][0] == "C"
    
    @pytest.mark.asyncio
    async def test_transaction_commit(self, adapter: SQLiteAdapter) -> None:
        """트랜잭션 커밋"""
        await adapter.execute("CREATE TABLE tx_test (id INTEGER)")
        await adapter.commit()
        
        async with adapter.transaction() as conn:
            await conn.execute("INSERT INTO tx_test (id) VALUES (1)")
            await conn.execute("INSERT INTO tx_test (id) VALUES (2)")
        
        rows = await adapter.fetchall("SELECT id FROM tx_test")
        assert len(rows) == 2
    
    @pytest.mark.asyncio
    async def test_transaction_rollback(self, adapter: SQLiteAdapter) -> None:
        """트랜잭션 롤백"""
        await adapter.execute("CREATE TABLE tx_test2 (id INTEGER)")
        await adapter.commit()
        
        try:
            async with adapter.transaction() as conn:
                await conn.execute("INSERT INTO tx_test2 (id) VALUES (1)")
                raise ValueError("의도적 에러")
        except ValueError:
            pass
        
        rows = await adapter.fetchall("SELECT id FROM tx_test2")
        assert len(rows) == 0
    
    @pytest.mark.asyncio
    async def test_table_exists(self, adapter: SQLiteAdapter) -> None:
        """테이블 존재 확인"""
        assert await adapter.table_exists("nonexistent") is False
        
        await adapter.execute("CREATE TABLE existing (id INTEGER)")
        await adapter.commit()
        
        assert await adapter.table_exists("existing") is True
    
    @pytest.mark.asyncio
    async def test_context_manager(self, tmp_path: Path) -> None:
        """컨텍스트 매니저"""
        db_path = tmp_path / "ctx_test.db"
        
        async with SQLiteAdapter(db_path) as adapter:
            assert adapter.is_connected is True
            await adapter.execute("CREATE TABLE ctx (id INTEGER)")
        
        # 컨텍스트 종료 후 연결 해제 확인
        assert adapter.is_connected is False


class TestInitSchema:
    """init_schema 테스트"""
    
    @pytest.mark.asyncio
    async def test_init_schema_creates_tables(self, tmp_path: Path) -> None:
        """스키마 초기화 - 테이블 생성"""
        db_path = tmp_path / "schema_test.db"
        
        async with SQLiteAdapter(db_path) as adapter:
            await init_schema(adapter)
            
            # 테이블 존재 확인
            assert await adapter.table_exists("event_store") is True
            assert await adapter.table_exists("command_store") is True
            assert await adapter.table_exists("config_store") is True
            assert await adapter.table_exists("checkpoint_store") is True
    
    @pytest.mark.asyncio
    async def test_init_schema_idempotent(self, tmp_path: Path) -> None:
        """스키마 초기화 멱등성 (여러 번 실행 가능)"""
        db_path = tmp_path / "idempotent_test.db"
        
        async with SQLiteAdapter(db_path) as adapter:
            # 두 번 실행해도 에러 없음
            await init_schema(adapter)
            await init_schema(adapter)
            
            assert await adapter.table_exists("event_store") is True
    
    @pytest.mark.asyncio
    async def test_event_store_schema(self, tmp_path: Path) -> None:
        """event_store 스키마 확인"""
        db_path = tmp_path / "event_schema_test.db"
        
        async with SQLiteAdapter(db_path) as adapter:
            await init_schema(adapter)
            
            columns = await adapter.get_table_info("event_store")
            column_names = [c["name"] for c in columns]
            
            # 필수 컬럼 확인
            assert "seq" in column_names
            assert "event_id" in column_names
            assert "event_type" in column_names
            assert "dedup_key" in column_names
            assert "payload_json" in column_names
    
    @pytest.mark.asyncio
    async def test_command_store_schema(self, tmp_path: Path) -> None:
        """command_store 스키마 확인"""
        db_path = tmp_path / "cmd_schema_test.db"
        
        async with SQLiteAdapter(db_path) as adapter:
            await init_schema(adapter)
            
            columns = await adapter.get_table_info("command_store")
            column_names = [c["name"] for c in columns]
            
            # 필수 컬럼 확인
            assert "command_id" in column_names
            assert "command_type" in column_names
            assert "idempotency_key" in column_names
            assert "status" in column_names
    
    @pytest.mark.asyncio
    async def test_dedup_key_unique(self, tmp_path: Path) -> None:
        """dedup_key UNIQUE 제약조건 테스트"""
        db_path = tmp_path / "unique_test.db"
        
        async with SQLiteAdapter(db_path) as adapter:
            await init_schema(adapter)
            
            # 첫 번째 삽입
            await adapter.execute("""
                INSERT INTO event_store (
                    event_id, event_type, ts, correlation_id, source,
                    entity_kind, entity_id, scope_exchange, scope_venue,
                    scope_account_id, scope_mode, dedup_key, payload_json
                ) VALUES (
                    'evt1', 'TEST', '2024-01-01', 'corr1', 'BOT',
                    'TEST', 'id1', 'BINANCE', 'FUTURES',
                    'main', 'TESTNET', 'unique_key_1', '{}'
                )
            """)
            await adapter.commit()
            
            # 같은 dedup_key로 삽입 시도 → 에러
            import aiosqlite
            with pytest.raises(aiosqlite.IntegrityError):
                await adapter.execute("""
                    INSERT INTO event_store (
                        event_id, event_type, ts, correlation_id, source,
                        entity_kind, entity_id, scope_exchange, scope_venue,
                        scope_account_id, scope_mode, dedup_key, payload_json
                    ) VALUES (
                        'evt2', 'TEST', '2024-01-01', 'corr2', 'BOT',
                        'TEST', 'id2', 'BINANCE', 'FUTURES',
                        'main', 'TESTNET', 'unique_key_1', '{}'
                    )
                """)
