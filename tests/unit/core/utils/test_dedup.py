"""
core/utils/dedup.py 테스트

dedup_key 생성 함수들의 출력 형식 검증
"""

from core.utils.dedup import (
    make_trade_dedup_key,
    make_order_dedup_key,
    make_order_status_dedup_key,
    make_position_dedup_key,
    make_balance_dedup_key,
    make_ws_event_dedup_key,
    make_config_dedup_key,
    make_drift_dedup_key,
    make_reconciliation_dedup_key,
    make_transfer_dedup_key,
    make_deposit_dedup_key,
    make_withdraw_dedup_key,
    make_funding_dedup_key,
    make_fee_dedup_key,
    make_engine_event_dedup_key,
)


class TestMakeTradeDedup:
    """make_trade_dedup_key 테스트"""

    def test_basic_format(self) -> None:
        """기본 형식 확인"""
        result = make_trade_dedup_key("BINANCE", "FUTURES", "XRPUSDT", "123456789")
        assert result == "BINANCE:FUTURES:XRPUSDT:trade:123456789"

    def test_different_venues(self) -> None:
        """다른 venue로 생성"""
        futures = make_trade_dedup_key("BINANCE", "FUTURES", "BTCUSDT", "111")
        spot = make_trade_dedup_key("BINANCE", "SPOT", "BTCUSDT", "111")
        assert futures != spot
        assert "FUTURES" in futures
        assert "SPOT" in spot

    def test_contains_trade_keyword(self) -> None:
        """trade 키워드 포함"""
        result = make_trade_dedup_key("BINANCE", "FUTURES", "XRPUSDT", "123")
        assert ":trade:" in result


class TestMakeOrderDedup:
    """make_order_dedup_key 테스트"""

    def test_basic_format(self) -> None:
        """기본 형식 확인"""
        result = make_order_dedup_key("BINANCE", "FUTURES", "XRPUSDT", "987654321")
        assert result == "BINANCE:FUTURES:XRPUSDT:order:987654321"

    def test_contains_order_keyword(self) -> None:
        """order 키워드 포함"""
        result = make_order_dedup_key("BINANCE", "FUTURES", "XRPUSDT", "123")
        assert ":order:" in result


class TestMakeOrderStatusDedup:
    """make_order_status_dedup_key 테스트"""

    def test_basic_format(self) -> None:
        """기본 형식 확인"""
        result = make_order_status_dedup_key(
            "BINANCE", "FUTURES", "XRPUSDT", "123", "FILLED"
        )
        assert result == "BINANCE:FUTURES:XRPUSDT:order:123:FILLED"

    def test_different_status(self) -> None:
        """다른 상태로 생성"""
        filled = make_order_status_dedup_key(
            "BINANCE", "FUTURES", "XRPUSDT", "123", "FILLED"
        )
        cancelled = make_order_status_dedup_key(
            "BINANCE", "FUTURES", "XRPUSDT", "123", "CANCELLED"
        )
        assert filled != cancelled


class TestMakePositionDedup:
    """make_position_dedup_key 테스트"""

    def test_basic_format(self) -> None:
        """기본 형식 확인"""
        result = make_position_dedup_key(
            "BINANCE", "FUTURES", "XRPUSDT", "LONG", "100", "0.5123"
        )
        assert result == "BINANCE:FUTURES:XRPUSDT:position:LONG:100:0.5123"

    def test_contains_position_keyword(self) -> None:
        """position 키워드 포함"""
        result = make_position_dedup_key(
            "BINANCE", "FUTURES", "XRPUSDT", "LONG", "100", "0.5"
        )
        assert ":position:" in result

    def test_different_qty(self) -> None:
        """수량이 다르면 다른 키"""
        key1 = make_position_dedup_key(
            "BINANCE", "FUTURES", "XRPUSDT", "LONG", "100", "0.5"
        )
        key2 = make_position_dedup_key(
            "BINANCE", "FUTURES", "XRPUSDT", "LONG", "200", "0.5"
        )
        assert key1 != key2


class TestMakeBalanceDedup:
    """make_balance_dedup_key 테스트"""

    def test_basic_format(self) -> None:
        """기본 형식 확인"""
        result = make_balance_dedup_key(
            "BINANCE", "FUTURES", "main", "USDT", "1000.5", "50.0"
        )
        assert result == "BINANCE:FUTURES:main:USDT:1000.5:50.0"

    def test_different_amounts(self) -> None:
        """금액이 다르면 다른 키"""
        key1 = make_balance_dedup_key(
            "BINANCE", "FUTURES", "main", "USDT", "1000", "0"
        )
        key2 = make_balance_dedup_key(
            "BINANCE", "FUTURES", "main", "USDT", "2000", "0"
        )
        assert key1 != key2


class TestMakeWsEventDedup:
    """make_ws_event_dedup_key 테스트"""

    def test_basic_format(self) -> None:
        """기본 형식 확인"""
        result = make_ws_event_dedup_key("BINANCE", "connected", 1708408800000)
        assert result == "BINANCE:ws:connected:1708408800000"

    def test_contains_ws_keyword(self) -> None:
        """ws 키워드 포함"""
        result = make_ws_event_dedup_key("BINANCE", "disconnected", 1234567890)
        assert ":ws:" in result

    def test_different_event_types(self) -> None:
        """다른 이벤트 타입"""
        connected = make_ws_event_dedup_key("BINANCE", "connected", 123)
        disconnected = make_ws_event_dedup_key("BINANCE", "disconnected", 123)
        assert connected != disconnected


class TestMakeConfigDedup:
    """make_config_dedup_key 테스트"""

    def test_basic_format(self) -> None:
        """기본 형식 확인"""
        result = make_config_dedup_key("strategy_params", 5)
        assert result == "config:strategy_params:5"

    def test_starts_with_config(self) -> None:
        """config으로 시작"""
        result = make_config_dedup_key("any_key", 1)
        assert result.startswith("config:")

    def test_different_versions(self) -> None:
        """다른 버전"""
        v1 = make_config_dedup_key("key", 1)
        v2 = make_config_dedup_key("key", 2)
        assert v1 != v2


class TestMakeDriftDedup:
    """make_drift_dedup_key 테스트"""

    def test_basic_format(self) -> None:
        """기본 형식 확인"""
        result = make_drift_dedup_key(
            "BINANCE", "FUTURES", "XRPUSDT", "position", "2026-02-20T12:00"
        )
        assert result == "BINANCE:FUTURES:XRPUSDT:drift:position:2026-02-20T12:00"

    def test_contains_drift_keyword(self) -> None:
        """drift 키워드 포함"""
        result = make_drift_dedup_key(
            "BINANCE", "FUTURES", "XRPUSDT", "balance", "2026-02-20"
        )
        assert ":drift:" in result


class TestMakeReconciliationDedup:
    """make_reconciliation_dedup_key 테스트"""

    def test_basic_format(self) -> None:
        """기본 형식 확인"""
        result = make_reconciliation_dedup_key("BINANCE", "FUTURES", "XRPUSDT", 12345)
        assert result == "BINANCE:FUTURES:XRPUSDT:recon:12345"

    def test_contains_recon_keyword(self) -> None:
        """recon 키워드 포함"""
        result = make_reconciliation_dedup_key("BINANCE", "FUTURES", "BTCUSDT", 999)
        assert ":recon:" in result


class TestMakeTransferDedup:
    """make_transfer_dedup_key 테스트"""

    def test_basic_format(self) -> None:
        """기본 형식 확인"""
        result = make_transfer_dedup_key("BINANCE", "txn_123456")
        assert result == "BINANCE:transfer:txn_123456"

    def test_contains_transfer_keyword(self) -> None:
        """transfer 키워드 포함"""
        result = make_transfer_dedup_key("BINANCE", "any_id")
        assert ":transfer:" in result


class TestMakeDepositDedup:
    """make_deposit_dedup_key 테스트"""

    def test_basic_format(self) -> None:
        """기본 형식 확인"""
        result = make_deposit_dedup_key("BINANCE", "0xabc123")
        assert result == "BINANCE:deposit:0xabc123"

    def test_contains_deposit_keyword(self) -> None:
        """deposit 키워드 포함"""
        result = make_deposit_dedup_key("BINANCE", "any_id")
        assert ":deposit:" in result


class TestMakeWithdrawDedup:
    """make_withdraw_dedup_key 테스트"""

    def test_basic_format(self) -> None:
        """기본 형식 확인"""
        result = make_withdraw_dedup_key("BINANCE", "wd_987654")
        assert result == "BINANCE:withdraw:wd_987654"

    def test_contains_withdraw_keyword(self) -> None:
        """withdraw 키워드 포함"""
        result = make_withdraw_dedup_key("BINANCE", "any_id")
        assert ":withdraw:" in result


class TestMakeFundingDedup:
    """make_funding_dedup_key 테스트"""

    def test_basic_format(self) -> None:
        """기본 형식 확인"""
        result = make_funding_dedup_key("BINANCE", "XRPUSDT", 1708408800000)
        assert result == "BINANCE:XRPUSDT:funding:1708408800000"

    def test_contains_funding_keyword(self) -> None:
        """funding 키워드 포함"""
        result = make_funding_dedup_key("BINANCE", "BTCUSDT", 123)
        assert ":funding:" in result


class TestMakeFeeDedup:
    """make_fee_dedup_key 테스트"""

    def test_basic_format(self) -> None:
        """기본 형식 확인"""
        result = make_fee_dedup_key("BINANCE", "FUTURES", "XRPUSDT", "123456789")
        assert result == "BINANCE:FUTURES:XRPUSDT:fee:123456789"

    def test_contains_fee_keyword(self) -> None:
        """fee 키워드 포함"""
        result = make_fee_dedup_key("BINANCE", "SPOT", "BTCUSDT", "111")
        assert ":fee:" in result


class TestMakeEngineEventDedup:
    """make_engine_event_dedup_key 테스트"""

    def test_basic_format(self) -> None:
        """기본 형식 확인"""
        result = make_engine_event_dedup_key("started", 1708408800000)
        assert result == "engine:started:1708408800000"

    def test_starts_with_engine(self) -> None:
        """engine으로 시작"""
        result = make_engine_event_dedup_key("stopped", 123)
        assert result.startswith("engine:")


class TestDedupKeyUniqueness:
    """dedup_key 고유성 테스트"""

    def test_trade_and_order_different(self) -> None:
        """trade와 order 키가 다름"""
        trade = make_trade_dedup_key("BINANCE", "FUTURES", "XRPUSDT", "123")
        order = make_order_dedup_key("BINANCE", "FUTURES", "XRPUSDT", "123")
        assert trade != order

    def test_same_id_different_types(self) -> None:
        """같은 ID라도 타입이 다르면 다른 키"""
        deposit = make_deposit_dedup_key("BINANCE", "123")
        withdraw = make_withdraw_dedup_key("BINANCE", "123")
        assert deposit != withdraw

    def test_deterministic(self) -> None:
        """동일 입력 → 동일 출력"""
        key1 = make_trade_dedup_key("BINANCE", "FUTURES", "XRPUSDT", "123")
        key2 = make_trade_dedup_key("BINANCE", "FUTURES", "XRPUSDT", "123")
        assert key1 == key2
