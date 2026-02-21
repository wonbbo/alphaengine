"""
복식부기 (Double-Entry Bookkeeping) 시스템

모든 자산 이동을 정확하게 추적하는 복식부기 시스템.
기존 Event/Projection 시스템과 병행 운영.

사용 예시:
```python
from core.ledger import LedgerStore, JournalEntryBuilder

# 초기화
ledger_store = LedgerStore(db)
entry_builder = JournalEntryBuilder(ledger_store)

# 이벤트에서 분개 생성
entry = await entry_builder.from_event(event)
if entry:
    await ledger_store.save_entry(entry)

# 잔액 조회
balance = await ledger_store.get_account_balance(
    "ASSET:BINANCE_FUTURES:USDT",
    "testnet"
)

# 시산표 조회
trial_balance = await ledger_store.get_trial_balance("testnet")
```
"""

from core.ledger.entry_builder import JournalEntry, JournalEntryBuilder, JournalLine
from core.ledger.store import LedgerStore
from core.ledger.types import (
    INITIAL_ACCOUNTS,
    NON_FINANCIAL_EVENT_TYPES,
    AccountType,
    JournalSide,
    LedgerVenue,
    TransactionType,
)

__all__ = [
    # 핵심 클래스
    "LedgerStore",
    "JournalEntryBuilder",
    "JournalEntry",
    "JournalLine",
    # Enum
    "TransactionType",
    "AccountType",
    "JournalSide",
    "LedgerVenue",
    # 상수
    "INITIAL_ACCOUNTS",
    "NON_FINANCIAL_EVENT_TYPES",
]
