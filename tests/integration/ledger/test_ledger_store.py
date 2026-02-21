"""LedgerStore 통합 테스트"""

import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio

from adapters.db.sqlite_adapter import SQLiteAdapter
from core.ledger.entry_builder import JournalEntry, JournalLine
from core.ledger.store import LedgerStore
from core.ledger.types import INITIAL_ACCOUNTS, JournalSide, TransactionType


@pytest_asyncio.fixture
async def db() -> SQLiteAdapter:
    """테스트용 임시 DB"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_ledger.db"
        adapter = SQLiteAdapter(db_path)
        await adapter.connect()
        
        # account 테이블 생성
        await adapter.execute("""
            CREATE TABLE account (
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
        
        # journal_entry 테이블 생성
        await adapter.execute("""
            CREATE TABLE journal_entry (
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
        
        # journal_line 테이블 생성
        await adapter.execute("""
            CREATE TABLE journal_line (
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
        
        # account_balance 테이블 생성
        await adapter.execute("""
            CREATE TABLE account_balance (
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
        
        # 기본 계정 생성
        for account in INITIAL_ACCOUNTS[:10]:  # 처음 10개만
            await adapter.execute(
                """
                INSERT OR IGNORE INTO account (account_id, account_type, venue, asset, name)
                VALUES (?, ?, ?, ?, ?)
                """,
                account,
            )
        
        await adapter.commit()
        
        yield adapter
        
        await adapter.close()


@pytest.fixture
def ledger_store(db: SQLiteAdapter) -> LedgerStore:
    """LedgerStore 인스턴스"""
    return LedgerStore(db)


class TestLedgerStoreSaveEntry:
    """분개 저장 테스트"""
    
    @pytest.mark.asyncio
    async def test_save_balanced_entry(self, ledger_store: LedgerStore) -> None:
        """균형 분개 저장"""
        entry = JournalEntry(
            entry_id="entry_001",
            ts=datetime.now(timezone.utc),
            transaction_type=TransactionType.TRADE.value,
            scope_mode="testnet",
            lines=[
                JournalLine(
                    account_id="ASSET:BINANCE_FUTURES:USDT",
                    side=JournalSide.DEBIT.value,
                    amount=Decimal("100.00"),
                    asset="USDT",
                    usdt_value=Decimal("100.00"),
                    usdt_rate=Decimal("1"),
                ),
                JournalLine(
                    account_id="ASSET:BINANCE_FUTURES:USDT",
                    side=JournalSide.CREDIT.value,
                    amount=Decimal("100.00"),
                    asset="USDT",
                    usdt_value=Decimal("100.00"),
                    usdt_rate=Decimal("1"),
                ),
            ],
            description="Test entry",
            source="TEST",
        )
        
        # 균형 확인
        assert entry.is_balanced()
        
        # 저장
        entry_id = await ledger_store.save_entry(entry)
        assert entry_id == "entry_001"
    
    @pytest.mark.asyncio
    async def test_reject_unbalanced_entry(self, ledger_store: LedgerStore) -> None:
        """불균형 분개 거부"""
        entry = JournalEntry(
            entry_id="entry_002",
            ts=datetime.now(timezone.utc),
            transaction_type=TransactionType.TRADE.value,
            scope_mode="testnet",
            lines=[
                JournalLine(
                    account_id="ASSET:BINANCE_FUTURES:USDT",
                    side=JournalSide.DEBIT.value,
                    amount=Decimal("100.00"),
                    asset="USDT",
                    usdt_value=Decimal("100.00"),
                    usdt_rate=Decimal("1"),
                ),
                # Credit이 더 적음 - 불균형
                JournalLine(
                    account_id="ASSET:BINANCE_FUTURES:USDT",
                    side=JournalSide.CREDIT.value,
                    amount=Decimal("50.00"),
                    asset="USDT",
                    usdt_value=Decimal("50.00"),
                    usdt_rate=Decimal("1"),
                ),
            ],
        )
        
        assert not entry.is_balanced()
        
        with pytest.raises(ValueError, match="Unbalanced"):
            await ledger_store.save_entry(entry)
    
    @pytest.mark.asyncio
    async def test_save_entry_updates_balance(self, ledger_store: LedgerStore) -> None:
        """분개 저장 시 잔액 업데이트"""
        # USDT 입금 분개
        entry = JournalEntry(
            entry_id="entry_003",
            ts=datetime.now(timezone.utc),
            transaction_type=TransactionType.DEPOSIT.value,
            scope_mode="testnet",
            lines=[
                JournalLine(
                    account_id="ASSET:BINANCE_FUTURES:USDT",
                    side=JournalSide.DEBIT.value,
                    amount=Decimal("1000.00"),
                    asset="USDT",
                    usdt_value=Decimal("1000.00"),
                    usdt_rate=Decimal("1"),
                ),
                JournalLine(
                    account_id="ASSET:EXTERNAL:USDT",
                    side=JournalSide.CREDIT.value,
                    amount=Decimal("1000.00"),
                    asset="USDT",
                    usdt_value=Decimal("1000.00"),
                    usdt_rate=Decimal("1"),
                ),
            ],
            source="TEST",
        )
        
        await ledger_store.save_entry(entry)
        
        # 잔액 확인
        futures_balance = await ledger_store.get_account_balance(
            "ASSET:BINANCE_FUTURES:USDT", "testnet"
        )
        assert futures_balance == Decimal("1000.00")
        
        external_balance = await ledger_store.get_account_balance(
            "ASSET:EXTERNAL:USDT", "testnet"
        )
        assert external_balance == Decimal("-1000.00")  # Credit이므로 음수


class TestLedgerStoreEnsureAssetAccount:
    """동적 계정 생성 테스트"""
    
    @pytest.mark.asyncio
    async def test_ensure_asset_account_creates_new(
        self, ledger_store: LedgerStore, db: SQLiteAdapter
    ) -> None:
        """새 Asset 계정 자동 생성"""
        # ETH 계정이 없는 상태에서 요청
        account_id = await ledger_store.ensure_asset_account("BINANCE_FUTURES", "ETH")
        
        assert account_id == "ASSET:BINANCE_FUTURES:ETH"
        
        # DB에 생성되었는지 확인
        row = await db.fetchone(
            "SELECT account_id, asset, account_type FROM account WHERE account_id = ?",
            (account_id,)
        )
        assert row is not None
        assert row[1] == "ETH"
        assert row[2] == "ASSET"
    
    @pytest.mark.asyncio
    async def test_ensure_asset_account_idempotent(
        self, ledger_store: LedgerStore
    ) -> None:
        """같은 Asset 계정 중복 생성 방지 (멱등성)"""
        # 두 번 호출
        account_id1 = await ledger_store.ensure_asset_account("BINANCE_SPOT", "SOL")
        account_id2 = await ledger_store.ensure_asset_account("BINANCE_SPOT", "SOL")
        
        # 동일한 account_id 반환
        assert account_id1 == account_id2 == "ASSET:BINANCE_SPOT:SOL"


class TestLedgerStoreQueries:
    """조회 메서드 테스트"""
    
    @pytest.mark.asyncio
    async def test_get_trial_balance(self, ledger_store: LedgerStore) -> None:
        """시산표 조회"""
        trial_balance = await ledger_store.get_trial_balance("testnet")
        
        assert len(trial_balance) > 0
        assert all("account_id" in row for row in trial_balance)
        assert all("balance" in row for row in trial_balance)
    
    @pytest.mark.asyncio
    async def test_get_entry(self, ledger_store: LedgerStore) -> None:
        """분개 단건 조회"""
        # 먼저 분개 저장
        entry = JournalEntry(
            entry_id="entry_query_001",
            ts=datetime.now(timezone.utc),
            transaction_type=TransactionType.TRADE.value,
            scope_mode="testnet",
            symbol="BTCUSDT",
            lines=[
                JournalLine(
                    account_id="ASSET:BINANCE_FUTURES:USDT",
                    side=JournalSide.DEBIT.value,
                    amount=Decimal("50.00"),
                    asset="USDT",
                    usdt_value=Decimal("50.00"),
                    usdt_rate=Decimal("1"),
                ),
                JournalLine(
                    account_id="ASSET:BINANCE_FUTURES:USDT",
                    side=JournalSide.CREDIT.value,
                    amount=Decimal("50.00"),
                    asset="USDT",
                    usdt_value=Decimal("50.00"),
                    usdt_rate=Decimal("1"),
                ),
            ],
            source="TEST",
        )
        await ledger_store.save_entry(entry)
        
        # 조회
        result = await ledger_store.get_entry("entry_query_001")
        
        assert result is not None
        assert result["entry_id"] == "entry_query_001"
        assert result["transaction_type"] == TransactionType.TRADE.value
        assert result["symbol"] == "BTCUSDT"
        assert len(result["lines"]) == 2
    
    @pytest.mark.asyncio
    async def test_get_entry_not_found(self, ledger_store: LedgerStore) -> None:
        """존재하지 않는 분개 조회"""
        result = await ledger_store.get_entry("nonexistent_entry")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_get_entries_by_account(self, ledger_store: LedgerStore) -> None:
        """계정별 분개 조회"""
        # 분개 저장
        entry = JournalEntry(
            entry_id="entry_account_001",
            ts=datetime.now(timezone.utc),
            transaction_type=TransactionType.DEPOSIT.value,
            scope_mode="testnet",
            lines=[
                JournalLine(
                    account_id="ASSET:BINANCE_FUTURES:USDT",
                    side=JournalSide.DEBIT.value,
                    amount=Decimal("200.00"),
                    asset="USDT",
                    usdt_value=Decimal("200.00"),
                    usdt_rate=Decimal("1"),
                ),
                JournalLine(
                    account_id="ASSET:EXTERNAL:USDT",
                    side=JournalSide.CREDIT.value,
                    amount=Decimal("200.00"),
                    asset="USDT",
                    usdt_value=Decimal("200.00"),
                    usdt_rate=Decimal("1"),
                ),
            ],
            source="TEST",
        )
        await ledger_store.save_entry(entry)
        
        # 계정별 조회
        entries = await ledger_store.get_entries_by_account(
            "ASSET:BINANCE_FUTURES:USDT", "testnet"
        )
        
        assert len(entries) >= 1
        assert any(e["entry_id"] == "entry_account_001" for e in entries)
    
    @pytest.mark.asyncio
    async def test_list_accounts(self, ledger_store: LedgerStore) -> None:
        """계정 목록 조회"""
        accounts = await ledger_store.list_accounts()
        
        assert len(accounts) > 0
        
        # ASSET 타입 필터링
        asset_accounts = await ledger_store.list_accounts(account_type="ASSET")
        assert all(a["account_type"] == "ASSET" for a in asset_accounts)


class TestLedgerStoreMultipleEntries:
    """복수 분개 테스트"""
    
    @pytest.mark.asyncio
    async def test_cumulative_balance(self, ledger_store: LedgerStore) -> None:
        """연속 분개 시 잔액 누적"""
        # 첫 번째 입금
        entry1 = JournalEntry(
            entry_id="entry_cumul_001",
            ts=datetime.now(timezone.utc),
            transaction_type=TransactionType.DEPOSIT.value,
            scope_mode="testnet",
            lines=[
                JournalLine(
                    account_id="ASSET:BINANCE_FUTURES:USDT",
                    side=JournalSide.DEBIT.value,
                    amount=Decimal("500.00"),
                    asset="USDT",
                    usdt_value=Decimal("500.00"),
                    usdt_rate=Decimal("1"),
                ),
                JournalLine(
                    account_id="ASSET:EXTERNAL:USDT",
                    side=JournalSide.CREDIT.value,
                    amount=Decimal("500.00"),
                    asset="USDT",
                    usdt_value=Decimal("500.00"),
                    usdt_rate=Decimal("1"),
                ),
            ],
            source="TEST",
        )
        await ledger_store.save_entry(entry1)
        
        # 두 번째 입금
        entry2 = JournalEntry(
            entry_id="entry_cumul_002",
            ts=datetime.now(timezone.utc),
            transaction_type=TransactionType.DEPOSIT.value,
            scope_mode="testnet",
            lines=[
                JournalLine(
                    account_id="ASSET:BINANCE_FUTURES:USDT",
                    side=JournalSide.DEBIT.value,
                    amount=Decimal("300.00"),
                    asset="USDT",
                    usdt_value=Decimal("300.00"),
                    usdt_rate=Decimal("1"),
                ),
                JournalLine(
                    account_id="ASSET:EXTERNAL:USDT",
                    side=JournalSide.CREDIT.value,
                    amount=Decimal("300.00"),
                    asset="USDT",
                    usdt_value=Decimal("300.00"),
                    usdt_rate=Decimal("1"),
                ),
            ],
            source="TEST",
        )
        await ledger_store.save_entry(entry2)
        
        # 잔액 확인 (누적)
        balance = await ledger_store.get_account_balance(
            "ASSET:BINANCE_FUTURES:USDT", "testnet"
        )
        assert balance == Decimal("800.00")  # 500 + 300
