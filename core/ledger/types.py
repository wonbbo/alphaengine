"""
복식부기 타입 정의

TransactionType 등 Ledger 시스템에서 사용하는 Enum 정의
"""

from enum import Enum


class TransactionType(str, Enum):
    """분개 거래 유형
    
    모든 금융 이벤트를 분류하는 거래 타입.
    str을 상속하여 JSON 직렬화 가능.
    """
    
    # 거래
    TRADE = "TRADE"  # 체결 (매수/매도)
    
    # 이체
    DEPOSIT = "DEPOSIT"  # 외부 입금
    WITHDRAWAL = "WITHDRAWAL"  # 외부 출금
    INTERNAL_TRANSFER = "INTERNAL_TRANSFER"  # 내부 이체 (Spot <-> Futures)
    
    # 수수료
    FEE_TRADING = "FEE_TRADING"  # 거래 수수료
    FEE_FUNDING = "FEE_FUNDING"  # 펀딩 수수료
    FEE_WITHDRAWAL = "FEE_WITHDRAWAL"  # 출금 수수료
    FEE_NETWORK = "FEE_NETWORK"  # 네트워크 수수료
    
    # 기타 수익/비용
    FUNDING_RECEIVED = "FUNDING_RECEIVED"  # 펀딩 수령
    REBATE = "REBATE"  # 리베이트
    LIQUIDATION = "LIQUIDATION"  # 강제 청산
    REALIZED_PNL = "REALIZED_PNL"  # 실현 손익 (별도 기록 시)
    
    # 확장용 (동적 처리)
    ADJUSTMENT = "ADJUSTMENT"  # 잔고 조정 (BalanceChanged 범용)
    UNKNOWN = "UNKNOWN"  # 알 수 없는 타입 (Fallback)
    CORRECTION = "CORRECTION"  # 오류 수정
    OTHER = "OTHER"  # 기타


class AccountType(str, Enum):
    """계정 유형
    
    복식부기의 5대 계정 유형 중 4가지 사용.
    (부채 계정은 현재 시스템에서 미사용)
    """
    
    ASSET = "ASSET"  # 자산 (잔고, 보유 암호화폐)
    EXPENSE = "EXPENSE"  # 비용 (수수료, 손실)
    INCOME = "INCOME"  # 수익 (실현이익, 펀딩수령)
    EQUITY = "EQUITY"  # 자본 (초기자본, 이익잉여금)


class JournalSide(str, Enum):
    """분개 방향 (차변/대변)"""
    
    DEBIT = "DEBIT"  # 차변 (자산 증가, 비용 증가)
    CREDIT = "CREDIT"  # 대변 (자산 감소, 수익 증가)


class LedgerVenue(str, Enum):
    """Ledger용 Venue 정의
    
    거래소 계정 위치를 구분.
    """
    
    BINANCE_SPOT = "BINANCE_SPOT"  # 바이낸스 현물
    BINANCE_FUTURES = "BINANCE_FUTURES"  # 바이낸스 선물
    EXTERNAL = "EXTERNAL"  # 외부 (입출금 상대방)
    SYSTEM = "SYSTEM"  # 시스템 계정 (수수료, 손익 등)


# 초기 계정 목록 (마이그레이션에서 사용)
INITIAL_ACCOUNTS: list[tuple[str, str, str, str | None, str]] = [
    # (account_id, account_type, venue, asset, name)
    
    # ASSET 계정 - BINANCE_SPOT
    ("ASSET:BINANCE_SPOT:USDT", "ASSET", "BINANCE_SPOT", "USDT", "Binance Spot USDT"),
    ("ASSET:BINANCE_SPOT:BTC", "ASSET", "BINANCE_SPOT", "BTC", "Binance Spot BTC"),
    ("ASSET:BINANCE_SPOT:BNB", "ASSET", "BINANCE_SPOT", "BNB", "Binance Spot BNB"),
    ("ASSET:BINANCE_SPOT:TRX", "ASSET", "BINANCE_SPOT", "TRX", "Binance Spot TRX"),
    
    # ASSET 계정 - BINANCE_FUTURES
    ("ASSET:BINANCE_FUTURES:USDT", "ASSET", "BINANCE_FUTURES", "USDT", "Binance Futures USDT"),
    ("ASSET:BINANCE_FUTURES:BNB", "ASSET", "BINANCE_FUTURES", "BNB", "Binance Futures BNB"),
    
    # ASSET 계정 - EXTERNAL
    ("ASSET:EXTERNAL:USDT", "ASSET", "EXTERNAL", "USDT", "External USDT"),
    ("ASSET:EXTERNAL:KRW", "ASSET", "EXTERNAL", "KRW", "External KRW"),
    
    # EXPENSE 계정 - 수수료
    ("EXPENSE:FEE:TRADING:TAKER", "EXPENSE", "SYSTEM", None, "Taker Fee"),
    ("EXPENSE:FEE:TRADING:MAKER", "EXPENSE", "SYSTEM", None, "Maker Fee"),
    ("EXPENSE:FEE:FUNDING:PAID", "EXPENSE", "SYSTEM", None, "Funding Fee Paid"),
    ("EXPENSE:FEE:WITHDRAWAL", "EXPENSE", "SYSTEM", None, "Withdrawal Fee"),
    ("EXPENSE:FEE:NETWORK", "EXPENSE", "SYSTEM", None, "Network Fee"),
    ("EXPENSE:FEE:DUST_CONVERSION", "EXPENSE", "SYSTEM", None, "Dust Conversion Fee"),
    ("EXPENSE:CONVERSION_LOSS", "EXPENSE", "SYSTEM", None, "Conversion Loss"),
    
    # INCOME 계정 - 수익
    ("INCOME:TRADING:REALIZED_PNL", "INCOME", "SYSTEM", None, "Realized PnL"),
    ("INCOME:FUNDING:RECEIVED", "INCOME", "SYSTEM", None, "Funding Fee Received"),
    ("INCOME:REBATE", "INCOME", "SYSTEM", None, "Trading Rebate"),
    ("INCOME:CONVERSION_GAIN", "INCOME", "SYSTEM", None, "Conversion Gain"),
    
    # EQUITY 계정
    ("EQUITY:INITIAL_CAPITAL", "EQUITY", "SYSTEM", None, "Initial Capital"),
    ("EQUITY:RETAINED_EARNINGS", "EQUITY", "SYSTEM", None, "Retained Earnings"),
    ("EQUITY:SUSPENSE", "EQUITY", "SYSTEM", None, "Suspense Account"),  # 미결 계정
    ("EQUITY:ADJUSTMENT", "EQUITY", "SYSTEM", None, "Adjustment Account"),  # 조정 계정
    ("EQUITY:OPENING_ADJUSTMENT", "EQUITY", "SYSTEM", None, "Opening Balance Adjustment"),  # 기초 잔액 조정
    
    # UNKNOWN 계정 - 동적 생성 전 임시 사용
    ("ASSET:BINANCE_SPOT:UNKNOWN", "ASSET", "BINANCE_SPOT", "UNKNOWN", "Unknown Spot Asset"),
    ("ASSET:BINANCE_FUTURES:UNKNOWN", "ASSET", "BINANCE_FUTURES", "UNKNOWN", "Unknown Futures Asset"),
]


# 비금융 이벤트 타입 (Ledger에서 무시)
NON_FINANCIAL_EVENT_TYPES: set[str] = {
    "OrderCreated",
    "OrderCancelled",
    "OrderUpdated",
    "OrderPlaced",
    "OrderRejected",
    "PositionUpdated",
    "PositionChanged",
    "HeartbeatReceived",
    "ConnectionEstablished",
    "StrategyStarted",
    "StrategyStopped",
    "StrategyLoaded",
    "StrategyError",
    "ConfigChanged",
    "EngineStarted",
    "EngineStopped",
    "EnginePaused",
    "EngineResumed",
    "EngineModeChanged",
    "WsConnected",
    "WsDisconnected",
    "WsReconnected",
    "WebSocketConnected",
    "WebSocketDisconnected",
    "WebSocketReconnected",
    "ManualOverrideExecuted",
    "RiskGuardRejected",
    "DriftDetected",
    "ReconciliationPerformed",
    "QuarantineStarted",
    "QuarantineCompleted",
}
