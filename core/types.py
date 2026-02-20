"""
타입 정의 모듈

Enum, Dataclass 등 핵심 타입 정의
모든 Enum은 str을 상속하여 문자열 직렬화 가능
"""

from dataclasses import dataclass
from enum import Enum


class TradingMode(str, Enum):
    """거래 모드 (실거래 / 테스트넷)"""

    PRODUCTION = "production"
    TESTNET = "testnet"


class Exchange(str, Enum):
    """거래소"""

    BINANCE = "BINANCE"


class Venue(str, Enum):
    """거래 장소 (선물 / 현물)"""

    FUTURES = "FUTURES"
    SPOT = "SPOT"


class OrderSide(str, Enum):
    """주문 방향"""

    BUY = "BUY"
    SELL = "SELL"


class PositionSide(str, Enum):
    """포지션 방향 (Hedge Mode용)"""

    LONG = "LONG"
    SHORT = "SHORT"
    BOTH = "BOTH"


class OrderType(str, Enum):
    """주문 유형"""

    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_MARKET = "STOP_MARKET"
    TAKE_PROFIT_MARKET = "TAKE_PROFIT_MARKET"
    STOP = "STOP"
    TAKE_PROFIT = "TAKE_PROFIT"


class OrderStatus(str, Enum):
    """주문 상태"""

    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"  # Binance API 사용 (미국식 철자)
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class TimeInForce(str, Enum):
    """주문 유효 기간"""

    GTC = "GTC"  # Good Till Cancel
    IOC = "IOC"  # Immediate Or Cancel
    FOK = "FOK"  # Fill Or Kill


class EngineMode(str, Enum):
    """엔진 모드"""

    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    SAFE = "SAFE"


class CommandStatus(str, Enum):
    """Command 상태"""

    NEW = "NEW"
    SENT = "SENT"
    ACK = "ACK"
    FAILED = "FAILED"


class EventSource(str, Enum):
    """Event 출처"""

    WEBSOCKET = "WEBSOCKET"
    REST = "REST"
    BOT = "BOT"
    WEB = "WEB"


class EntityKind(str, Enum):
    """Entity 종류"""

    ORDER = "ORDER"
    TRADE = "TRADE"
    POSITION = "POSITION"
    BALANCE = "BALANCE"
    TRANSFER = "TRANSFER"
    ENGINE = "ENGINE"
    CONFIG = "CONFIG"


class ActorKind(str, Enum):
    """행위자 종류"""

    STRATEGY = "STRATEGY"
    USER = "USER"
    SYSTEM = "SYSTEM"


class WebSocketState(str, Enum):
    """WebSocket 연결 상태"""

    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"


@dataclass(frozen=True)
class Scope:
    """거래 범위 (불변)

    모든 Event와 Command에 포함되어 거래 컨텍스트를 정의
    """

    exchange: str
    venue: str
    account_id: str
    symbol: str | None
    mode: str

    @classmethod
    def create(
        cls,
        exchange: str | Exchange = Exchange.BINANCE,
        venue: str | Venue = Venue.FUTURES,
        account_id: str = "main",
        symbol: str | None = None,
        mode: str | TradingMode = TradingMode.TESTNET,
    ) -> "Scope":
        """Scope 생성 헬퍼

        Enum 또는 문자열 모두 허용
        """
        return cls(
            exchange=exchange.value if isinstance(exchange, Enum) else exchange,
            venue=venue.value if isinstance(venue, Enum) else venue,
            account_id=account_id,
            symbol=symbol,
            mode=mode.value if isinstance(mode, Enum) else mode,
        )


@dataclass(frozen=True)
class Actor:
    """행위자 (불변)

    Command 발행자를 식별
    """

    kind: str
    id: str

    @classmethod
    def strategy(cls, strategy_name: str) -> "Actor":
        """전략 Actor 생성"""
        return cls(kind=ActorKind.STRATEGY.value, id=f"strategy:{strategy_name}")

    @classmethod
    def user(cls, user_id: str) -> "Actor":
        """사용자 Actor 생성"""
        return cls(kind=ActorKind.USER.value, id=f"user:{user_id}")

    @classmethod
    def system(cls, system_name: str) -> "Actor":
        """시스템 Actor 생성"""
        return cls(kind=ActorKind.SYSTEM.value, id=f"system:{system_name}")

    @classmethod
    def web(cls, component: str) -> "Actor":
        """Web Actor 생성"""
        return cls(kind=ActorKind.USER.value, id=f"web:{component}")
