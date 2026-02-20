"""
core/types.py 테스트

모든 Enum이 문자열 직렬화 가능하고, Scope가 올바르게 동작하는지 확인
"""

from core.types import (
    TradingMode,
    Exchange,
    Venue,
    OrderSide,
    PositionSide,
    OrderType,
    OrderStatus,
    TimeInForce,
    EngineMode,
    CommandStatus,
    EventSource,
    EntityKind,
    ActorKind,
    WebSocketState,
    Scope,
    Actor,
)


class TestTradingMode:
    """TradingMode 테스트"""

    def test_values(self) -> None:
        """값 확인"""
        assert TradingMode.PRODUCTION.value == "production"
        assert TradingMode.TESTNET.value == "testnet"

    def test_string_serialization(self) -> None:
        """문자열 직렬화 확인"""
        # str(Enum)은 Python 버전에 따라 다르게 동작할 수 있음
        # .value를 사용하면 일관된 결과
        assert TradingMode.PRODUCTION.value == "production"
        assert TradingMode.TESTNET.value == "testnet"
        # f-string에서도 .value 사용 권장
        assert f"{TradingMode.TESTNET.value}" == "testnet"

    def test_from_string(self) -> None:
        """문자열에서 생성"""
        assert TradingMode("production") == TradingMode.PRODUCTION
        assert TradingMode("testnet") == TradingMode.TESTNET


class TestExchange:
    """Exchange 테스트"""

    def test_binance(self) -> None:
        """BINANCE 값 확인"""
        assert Exchange.BINANCE.value == "BINANCE"
        # Enum은 문자열과 == 비교 가능 (str 상속)
        assert Exchange.BINANCE == "BINANCE"


class TestVenue:
    """Venue 테스트"""

    def test_values(self) -> None:
        """값 확인"""
        assert Venue.FUTURES.value == "FUTURES"
        assert Venue.SPOT.value == "SPOT"


class TestOrderSide:
    """OrderSide 테스트"""

    def test_values(self) -> None:
        """값 확인"""
        assert OrderSide.BUY.value == "BUY"
        assert OrderSide.SELL.value == "SELL"


class TestPositionSide:
    """PositionSide 테스트"""

    def test_values(self) -> None:
        """값 확인"""
        assert PositionSide.LONG.value == "LONG"
        assert PositionSide.SHORT.value == "SHORT"
        assert PositionSide.BOTH.value == "BOTH"


class TestOrderType:
    """OrderType 테스트"""

    def test_values(self) -> None:
        """값 확인"""
        assert OrderType.MARKET.value == "MARKET"
        assert OrderType.LIMIT.value == "LIMIT"
        assert OrderType.STOP_MARKET.value == "STOP_MARKET"
        assert OrderType.TAKE_PROFIT_MARKET.value == "TAKE_PROFIT_MARKET"
        assert OrderType.STOP.value == "STOP"
        assert OrderType.TAKE_PROFIT.value == "TAKE_PROFIT"


class TestOrderStatus:
    """OrderStatus 테스트"""

    def test_values(self) -> None:
        """값 확인"""
        assert OrderStatus.NEW.value == "NEW"
        assert OrderStatus.PARTIALLY_FILLED.value == "PARTIALLY_FILLED"
        assert OrderStatus.FILLED.value == "FILLED"
        assert OrderStatus.CANCELED.value == "CANCELED"
        assert OrderStatus.REJECTED.value == "REJECTED"
        assert OrderStatus.EXPIRED.value == "EXPIRED"


class TestTimeInForce:
    """TimeInForce 테스트"""

    def test_values(self) -> None:
        """값 확인"""
        assert TimeInForce.GTC.value == "GTC"
        assert TimeInForce.IOC.value == "IOC"
        assert TimeInForce.FOK.value == "FOK"


class TestEngineMode:
    """EngineMode 테스트"""

    def test_values(self) -> None:
        """값 확인"""
        assert EngineMode.RUNNING.value == "RUNNING"
        assert EngineMode.PAUSED.value == "PAUSED"
        assert EngineMode.SAFE.value == "SAFE"


class TestCommandStatus:
    """CommandStatus 테스트"""

    def test_values(self) -> None:
        """값 확인"""
        assert CommandStatus.NEW.value == "NEW"
        assert CommandStatus.SENT.value == "SENT"
        assert CommandStatus.ACK.value == "ACK"
        assert CommandStatus.FAILED.value == "FAILED"


class TestEventSource:
    """EventSource 테스트"""

    def test_values(self) -> None:
        """값 확인"""
        assert EventSource.WEBSOCKET.value == "WEBSOCKET"
        assert EventSource.REST.value == "REST"
        assert EventSource.BOT.value == "BOT"
        assert EventSource.WEB.value == "WEB"


class TestEntityKind:
    """EntityKind 테스트"""

    def test_values(self) -> None:
        """값 확인"""
        assert EntityKind.ORDER.value == "ORDER"
        assert EntityKind.TRADE.value == "TRADE"
        assert EntityKind.POSITION.value == "POSITION"
        assert EntityKind.BALANCE.value == "BALANCE"
        assert EntityKind.TRANSFER.value == "TRANSFER"
        assert EntityKind.ENGINE.value == "ENGINE"
        assert EntityKind.CONFIG.value == "CONFIG"


class TestActorKind:
    """ActorKind 테스트"""

    def test_values(self) -> None:
        """값 확인"""
        assert ActorKind.STRATEGY.value == "STRATEGY"
        assert ActorKind.USER.value == "USER"
        assert ActorKind.SYSTEM.value == "SYSTEM"


class TestWebSocketState:
    """WebSocketState 테스트"""

    def test_values(self) -> None:
        """값 확인"""
        assert WebSocketState.DISCONNECTED.value == "DISCONNECTED"
        assert WebSocketState.CONNECTING.value == "CONNECTING"
        assert WebSocketState.CONNECTED.value == "CONNECTED"
        assert WebSocketState.RECONNECTING.value == "RECONNECTING"


class TestScope:
    """Scope 테스트"""

    def test_create_with_strings(self) -> None:
        """문자열로 생성"""
        scope = Scope(
            exchange="BINANCE",
            venue="FUTURES",
            account_id="main",
            symbol="XRPUSDT",
            mode="testnet",
        )
        assert scope.exchange == "BINANCE"
        assert scope.venue == "FUTURES"
        assert scope.account_id == "main"
        assert scope.symbol == "XRPUSDT"
        assert scope.mode == "testnet"

    def test_create_with_none_symbol(self) -> None:
        """symbol이 None인 경우"""
        scope = Scope(
            exchange="BINANCE",
            venue="FUTURES",
            account_id="main",
            symbol=None,
            mode="testnet",
        )
        assert scope.symbol is None

    def test_frozen(self) -> None:
        """불변성 확인"""
        scope = Scope(
            exchange="BINANCE",
            venue="FUTURES",
            account_id="main",
            symbol="XRPUSDT",
            mode="testnet",
        )
        try:
            scope.exchange = "OTHER"  # type: ignore
            assert False, "frozen dataclass는 수정 불가"
        except AttributeError:
            pass

    def test_equality(self) -> None:
        """동등성 확인"""
        scope1 = Scope(
            exchange="BINANCE",
            venue="FUTURES",
            account_id="main",
            symbol="XRPUSDT",
            mode="testnet",
        )
        scope2 = Scope(
            exchange="BINANCE",
            venue="FUTURES",
            account_id="main",
            symbol="XRPUSDT",
            mode="testnet",
        )
        assert scope1 == scope2

    def test_hashable(self) -> None:
        """해시 가능 확인 (dict key로 사용 가능)"""
        scope = Scope(
            exchange="BINANCE",
            venue="FUTURES",
            account_id="main",
            symbol="XRPUSDT",
            mode="testnet",
        )
        scope_dict = {scope: "value"}
        assert scope_dict[scope] == "value"

    def test_create_helper_with_enums(self) -> None:
        """create 헬퍼로 Enum 사용"""
        scope = Scope.create(
            exchange=Exchange.BINANCE,
            venue=Venue.FUTURES,
            account_id="main",
            symbol="XRPUSDT",
            mode=TradingMode.TESTNET,
        )
        assert scope.exchange == "BINANCE"
        assert scope.venue == "FUTURES"
        assert scope.mode == "testnet"

    def test_create_helper_with_strings(self) -> None:
        """create 헬퍼로 문자열 사용"""
        scope = Scope.create(
            exchange="BINANCE",
            venue="FUTURES",
            account_id="main",
            symbol="BTCUSDT",
            mode="production",
        )
        assert scope.exchange == "BINANCE"
        assert scope.mode == "production"

    def test_create_helper_defaults(self) -> None:
        """create 헬퍼 기본값"""
        scope = Scope.create()
        assert scope.exchange == "BINANCE"
        assert scope.venue == "FUTURES"
        assert scope.account_id == "main"
        assert scope.symbol is None
        assert scope.mode == "testnet"


class TestActor:
    """Actor 테스트"""

    def test_create_with_strings(self) -> None:
        """문자열로 생성"""
        actor = Actor(kind="STRATEGY", id="strategy:sma_cross")
        assert actor.kind == "STRATEGY"
        assert actor.id == "strategy:sma_cross"

    def test_frozen(self) -> None:
        """불변성 확인"""
        actor = Actor(kind="USER", id="user:admin")
        try:
            actor.kind = "OTHER"  # type: ignore
            assert False, "frozen dataclass는 수정 불가"
        except AttributeError:
            pass

    def test_strategy_helper(self) -> None:
        """strategy 헬퍼"""
        actor = Actor.strategy("sma_cross")
        assert actor.kind == "STRATEGY"
        assert actor.id == "strategy:sma_cross"

    def test_user_helper(self) -> None:
        """user 헬퍼"""
        actor = Actor.user("admin")
        assert actor.kind == "USER"
        assert actor.id == "user:admin"

    def test_system_helper(self) -> None:
        """system 헬퍼"""
        actor = Actor.system("reconciler")
        assert actor.kind == "SYSTEM"
        assert actor.id == "system:reconciler"

    def test_web_helper(self) -> None:
        """web 헬퍼"""
        actor = Actor.web("dashboard")
        assert actor.kind == "USER"
        assert actor.id == "web:dashboard"

    def test_equality(self) -> None:
        """동등성 확인"""
        actor1 = Actor(kind="USER", id="user:admin")
        actor2 = Actor(kind="USER", id="user:admin")
        assert actor1 == actor2

    def test_hashable(self) -> None:
        """해시 가능 확인"""
        actor = Actor(kind="USER", id="user:admin")
        actor_dict = {actor: "value"}
        assert actor_dict[actor] == "value"


class TestEnumStringComparison:
    """Enum과 문자열 비교 테스트"""

    def test_enum_equals_string(self) -> None:
        """Enum이 문자열과 동등 비교 가능"""
        assert TradingMode.TESTNET == "testnet"
        assert Exchange.BINANCE == "BINANCE"
        assert Venue.FUTURES == "FUTURES"

    def test_enum_in_string_operations(self) -> None:
        """Enum이 문자열 연산에 사용 가능 (.value 사용)"""
        mode = TradingMode.TESTNET
        # f-string에서 Enum 사용 시 .value 권장
        assert f"mode:{mode.value}" == "mode:testnet"

    def test_enum_json_serializable(self) -> None:
        """Enum이 JSON 직렬화 가능"""
        import json

        data = {"mode": TradingMode.TESTNET.value}
        json_str = json.dumps(data)
        assert json_str == '{"mode": "testnet"}'
