"""
InitialCapitalRecorder 단위 테스트
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.recovery.initial_capital import InitialCapitalRecorder
from core.types import Scope


@pytest.fixture
def scope() -> Scope:
    """테스트용 Scope"""
    return Scope(
        exchange="BINANCE",
        venue="FUTURES",
        account_id="test_account",
        symbol="XRPUSDT",
        mode="testnet",
    )


@pytest.fixture
def mock_rest_client() -> AsyncMock:
    """Mock REST 클라이언트"""
    return AsyncMock()


@pytest.fixture
def mock_event_store() -> AsyncMock:
    """Mock 이벤트 저장소"""
    store = AsyncMock()
    store.append.return_value = True
    return store


@pytest.fixture
def mock_config_store() -> AsyncMock:
    """Mock 설정 저장소"""
    store = AsyncMock()
    store.get.return_value = None
    return store


class TestInitialCapitalRecorderIsInitialized:
    """is_initialized() 테스트"""
    
    @pytest.mark.asyncio
    async def test_returns_false_when_no_config(
        self,
        mock_rest_client: AsyncMock,
        mock_event_store: AsyncMock,
        mock_config_store: AsyncMock,
        scope: Scope,
    ) -> None:
        """config_store에 initial_capital이 없으면 False 반환"""
        mock_config_store.get.return_value = None
        
        recorder = InitialCapitalRecorder(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            config_store=mock_config_store,
            scope=scope,
        )
        
        result = await recorder.is_initialized()
        
        assert result is False
        mock_config_store.get.assert_called_once_with("initial_capital")
    
    @pytest.mark.asyncio
    async def test_returns_false_when_not_initialized(
        self,
        mock_rest_client: AsyncMock,
        mock_event_store: AsyncMock,
        mock_config_store: AsyncMock,
        scope: Scope,
    ) -> None:
        """initialized 플래그가 False면 False 반환"""
        mock_config_store.get.return_value = {"initialized": False}
        
        recorder = InitialCapitalRecorder(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            config_store=mock_config_store,
            scope=scope,
        )
        
        result = await recorder.is_initialized()
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_returns_true_when_initialized(
        self,
        mock_rest_client: AsyncMock,
        mock_event_store: AsyncMock,
        mock_config_store: AsyncMock,
        scope: Scope,
    ) -> None:
        """initialized 플래그가 True면 True 반환"""
        mock_config_store.get.return_value = {
            "initialized": True,
            "USDT": "500.00",
        }
        
        recorder = InitialCapitalRecorder(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            config_store=mock_config_store,
            scope=scope,
        )
        
        result = await recorder.is_initialized()
        
        assert result is True


class TestInitialCapitalRecorderRecord:
    """record() 테스트"""
    
    @pytest.mark.asyncio
    async def test_skip_if_already_initialized(
        self,
        mock_rest_client: AsyncMock,
        mock_event_store: AsyncMock,
        mock_config_store: AsyncMock,
        scope: Scope,
    ) -> None:
        """이미 초기화되었으면 건너뛴다"""
        existing_capital = {
            "initialized": True,
            "USDT": "500.00",
        }
        mock_config_store.get.return_value = existing_capital
        
        recorder = InitialCapitalRecorder(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            config_store=mock_config_store,
            scope=scope,
        )
        
        result = await recorder.record()
        
        assert result == existing_capital
        mock_rest_client.get_account_snapshot.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_record_initial_capital_success(
        self,
        mock_rest_client: AsyncMock,
        mock_event_store: AsyncMock,
        mock_config_store: AsyncMock,
        scope: Scope,
    ) -> None:
        """초기 자산 기록 성공"""
        mock_config_store.get.return_value = None
        
        mock_rest_client.get_account_snapshot.side_effect = [
            {
                "code": 200,
                "msg": "",
                "snapshotVos": [
                    {
                        "type": "spot",
                        "updateTime": 1708408800000,
                        "data": {
                            "balances": [
                                {"asset": "USDT", "free": "100.50", "locked": "0"},
                                {"asset": "BNB", "free": "1.5", "locked": "0"},
                            ]
                        }
                    }
                ]
            },
            {
                "code": 200,
                "msg": "",
                "snapshotVos": [
                    {
                        "type": "futures",
                        "updateTime": 1708408800000,
                        "data": {
                            "assets": [
                                {"asset": "USDT", "walletBalance": "400.00"},
                            ]
                        }
                    }
                ]
            },
        ]
        
        recorder = InitialCapitalRecorder(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            config_store=mock_config_store,
            scope=scope,
        )
        
        result = await recorder.record()
        
        assert result["initialized"] is True
        assert result["SPOT_USDT"] == "100.50"
        assert result["FUTURES_USDT"] == "400"
        
        mock_config_store.set.assert_called_once()
        mock_event_store.append.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_record_handles_empty_snapshot(
        self,
        mock_rest_client: AsyncMock,
        mock_event_store: AsyncMock,
        mock_config_store: AsyncMock,
        scope: Scope,
    ) -> None:
        """스냅샷이 비어있을 때 0으로 처리"""
        mock_config_store.get.return_value = None
        
        mock_rest_client.get_account_snapshot.side_effect = [
            {"code": 200, "msg": "", "snapshotVos": []},
            {"code": 200, "msg": "", "snapshotVos": []},
        ]
        
        recorder = InitialCapitalRecorder(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            config_store=mock_config_store,
            scope=scope,
        )
        
        result = await recorder.record()
        
        assert result["initialized"] is True
        assert result["SPOT_USDT"] == "0"
        assert result["FUTURES_USDT"] == "0"
        assert result["USDT"] == "0"


class TestInitialCapitalRecorderEvent:
    """이벤트 생성 테스트"""
    
    @pytest.mark.asyncio
    async def test_creates_event_with_correct_type(
        self,
        mock_rest_client: AsyncMock,
        mock_event_store: AsyncMock,
        mock_config_store: AsyncMock,
        scope: Scope,
    ) -> None:
        """올바른 이벤트 타입으로 생성"""
        mock_config_store.get.return_value = None
        
        mock_rest_client.get_account_snapshot.side_effect = [
            {"code": 200, "msg": "", "snapshotVos": []},
            {"code": 200, "msg": "", "snapshotVos": []},
        ]
        
        recorder = InitialCapitalRecorder(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            config_store=mock_config_store,
            scope=scope,
        )
        
        await recorder.record()
        
        mock_event_store.append.assert_called_once()
        event = mock_event_store.append.call_args[0][0]
        
        assert event.event_type == "InitialCapitalEstablished"
        assert event.source == "BOT"
        assert event.entity_kind == "CAPITAL"
        assert "spot_usdt" in event.payload
        assert "futures_usdt" in event.payload
        assert "total_usdt" in event.payload
