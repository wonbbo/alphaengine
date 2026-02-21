"""Ledger 타입 테스트"""

import pytest

from core.ledger.types import (
    INITIAL_ACCOUNTS,
    NON_FINANCIAL_EVENT_TYPES,
    AccountType,
    JournalSide,
    LedgerVenue,
    TransactionType,
)


class TestTransactionType:
    """TransactionType Enum 테스트"""
    
    def test_trade_type(self) -> None:
        """TRADE 타입 확인"""
        assert TransactionType.TRADE.value == "TRADE"
        # str(Enum)은 "EnumClass.VALUE" 형태로 반환되므로 value 사용
        assert TransactionType.TRADE == "TRADE"
    
    def test_all_types_are_strings(self) -> None:
        """모든 타입이 문자열인지 확인"""
        for t in TransactionType:
            assert isinstance(t.value, str)
            assert len(t.value) > 0
    
    def test_adjustment_types(self) -> None:
        """확장 타입 확인 (ADJUSTMENT, UNKNOWN 등)"""
        assert TransactionType.ADJUSTMENT.value == "ADJUSTMENT"
        assert TransactionType.UNKNOWN.value == "UNKNOWN"
        assert TransactionType.CORRECTION.value == "CORRECTION"


class TestAccountType:
    """AccountType Enum 테스트"""
    
    def test_account_types(self) -> None:
        """계정 유형 확인"""
        assert AccountType.ASSET.value == "ASSET"
        assert AccountType.EXPENSE.value == "EXPENSE"
        assert AccountType.INCOME.value == "INCOME"
        assert AccountType.EQUITY.value == "EQUITY"


class TestJournalSide:
    """JournalSide Enum 테스트"""
    
    def test_sides(self) -> None:
        """차변/대변 확인"""
        assert JournalSide.DEBIT.value == "DEBIT"
        assert JournalSide.CREDIT.value == "CREDIT"


class TestLedgerVenue:
    """LedgerVenue Enum 테스트"""
    
    def test_venues(self) -> None:
        """Venue 확인"""
        assert LedgerVenue.BINANCE_SPOT.value == "BINANCE_SPOT"
        assert LedgerVenue.BINANCE_FUTURES.value == "BINANCE_FUTURES"
        assert LedgerVenue.EXTERNAL.value == "EXTERNAL"
        assert LedgerVenue.SYSTEM.value == "SYSTEM"


class TestInitialAccounts:
    """초기 계정 목록 테스트"""
    
    def test_initial_accounts_not_empty(self) -> None:
        """초기 계정 목록이 비어있지 않음"""
        assert len(INITIAL_ACCOUNTS) > 0
    
    def test_initial_accounts_structure(self) -> None:
        """초기 계정 구조 확인 (5-tuple)"""
        for account in INITIAL_ACCOUNTS:
            assert len(account) == 5
            account_id, account_type, venue, asset, name = account
            assert isinstance(account_id, str)
            assert isinstance(account_type, str)
            assert isinstance(venue, str)
            assert asset is None or isinstance(asset, str)
            assert isinstance(name, str)
    
    def test_required_accounts_exist(self) -> None:
        """필수 계정 존재 확인"""
        account_ids = [a[0] for a in INITIAL_ACCOUNTS]
        
        # 필수 ASSET 계정
        assert "ASSET:BINANCE_FUTURES:USDT" in account_ids
        assert "ASSET:BINANCE_SPOT:USDT" in account_ids
        
        # 필수 EXPENSE 계정
        assert "EXPENSE:FEE:TRADING:TAKER" in account_ids
        assert "EXPENSE:FEE:TRADING:MAKER" in account_ids
        
        # 필수 INCOME 계정
        assert "INCOME:TRADING:REALIZED_PNL" in account_ids
        
        # 필수 EQUITY 계정
        assert "EQUITY:SUSPENSE" in account_ids
        assert "EQUITY:ADJUSTMENT" in account_ids


class TestNonFinancialEventTypes:
    """비금융 이벤트 타입 테스트"""
    
    def test_non_financial_events_not_empty(self) -> None:
        """비금융 이벤트 목록이 비어있지 않음"""
        assert len(NON_FINANCIAL_EVENT_TYPES) > 0
    
    def test_order_events_are_non_financial(self) -> None:
        """주문 이벤트는 비금융 이벤트"""
        assert "OrderPlaced" in NON_FINANCIAL_EVENT_TYPES
        assert "OrderCancelled" in NON_FINANCIAL_EVENT_TYPES
    
    def test_engine_events_are_non_financial(self) -> None:
        """엔진 이벤트는 비금융 이벤트"""
        assert "EngineStarted" in NON_FINANCIAL_EVENT_TYPES
        assert "EngineStopped" in NON_FINANCIAL_EVENT_TYPES
