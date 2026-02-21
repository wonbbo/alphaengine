"""
BasePoller 단위 테스트
"""

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock

import pytest

from bot.poller.base import BasePoller
from core.types import Scope


class ConcretePoller(BasePoller):
    """테스트용 구체 Poller"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.poll_count = 0
    
    @property
    def poller_name(self) -> str:
        return "test"
    
    async def _do_poll(self, since: datetime) -> int:
        self.poll_count += 1
        return 5


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


class TestBasePollerShouldPoll:
    """should_poll() 테스트"""
    
    @pytest.mark.asyncio
    async def test_should_poll_returns_true_on_first_run(
        self,
        mock_rest_client: AsyncMock,
        mock_event_store: AsyncMock,
        mock_config_store: AsyncMock,
        scope: Scope,
    ) -> None:
        """첫 실행 시 True 반환"""
        poller = ConcretePoller(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            config_store=mock_config_store,
            scope=scope,
            poll_interval_seconds=60,
        )
        
        result = await poller.should_poll()
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_should_poll_returns_false_if_interval_not_elapsed(
        self,
        mock_rest_client: AsyncMock,
        mock_event_store: AsyncMock,
        mock_config_store: AsyncMock,
        scope: Scope,
    ) -> None:
        """폴링 간격이 지나지 않았으면 False 반환"""
        poller = ConcretePoller(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            config_store=mock_config_store,
            scope=scope,
            poll_interval_seconds=300,
        )
        
        poller._last_poll_time = datetime.now(timezone.utc) - timedelta(seconds=60)
        
        result = await poller.should_poll()
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_should_poll_returns_true_if_interval_elapsed(
        self,
        mock_rest_client: AsyncMock,
        mock_event_store: AsyncMock,
        mock_config_store: AsyncMock,
        scope: Scope,
    ) -> None:
        """폴링 간격이 지났으면 True 반환"""
        poller = ConcretePoller(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            config_store=mock_config_store,
            scope=scope,
            poll_interval_seconds=60,
        )
        
        poller._last_poll_time = datetime.now(timezone.utc) - timedelta(seconds=120)
        
        result = await poller.should_poll()
        
        assert result is True


class TestBasePollerPoll:
    """poll() 테스트"""
    
    @pytest.mark.asyncio
    async def test_poll_calls_do_poll(
        self,
        mock_rest_client: AsyncMock,
        mock_event_store: AsyncMock,
        mock_config_store: AsyncMock,
        scope: Scope,
    ) -> None:
        """poll()이 _do_poll() 호출"""
        poller = ConcretePoller(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            config_store=mock_config_store,
            scope=scope,
            poll_interval_seconds=60,
        )
        
        result = await poller.poll()
        
        assert poller.poll_count == 1
        assert result["events_created"] == 5
    
    @pytest.mark.asyncio
    async def test_poll_updates_last_poll_time(
        self,
        mock_rest_client: AsyncMock,
        mock_event_store: AsyncMock,
        mock_config_store: AsyncMock,
        scope: Scope,
    ) -> None:
        """poll() 후 마지막 폴링 시간 업데이트"""
        poller = ConcretePoller(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            config_store=mock_config_store,
            scope=scope,
            poll_interval_seconds=60,
        )
        
        before_poll = datetime.now(timezone.utc)
        await poller.poll()
        after_poll = datetime.now(timezone.utc)
        
        assert poller._last_poll_time is not None
        assert before_poll <= poller._last_poll_time <= after_poll
    
    @pytest.mark.asyncio
    async def test_poll_saves_to_config_store(
        self,
        mock_rest_client: AsyncMock,
        mock_event_store: AsyncMock,
        mock_config_store: AsyncMock,
        scope: Scope,
    ) -> None:
        """poll() 후 설정 저장소에 저장"""
        poller = ConcretePoller(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            config_store=mock_config_store,
            scope=scope,
            poll_interval_seconds=60,
        )
        
        await poller.poll()
        
        mock_config_store.set.assert_called_once()
        call_args = mock_config_store.set.call_args
        assert call_args[0][0] == "poller_test_last_poll"


class TestBasePollerInitialize:
    """initialize() 테스트"""
    
    @pytest.mark.asyncio
    async def test_initialize_restores_last_poll_time(
        self,
        mock_rest_client: AsyncMock,
        mock_event_store: AsyncMock,
        mock_config_store: AsyncMock,
        scope: Scope,
    ) -> None:
        """초기화 시 마지막 폴링 시간 복구"""
        saved_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        mock_config_store.get.return_value = {"last_poll_time": saved_time}
        
        poller = ConcretePoller(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            config_store=mock_config_store,
            scope=scope,
            poll_interval_seconds=60,
        )
        
        await poller.initialize()
        
        assert poller._last_poll_time is not None
        assert poller._last_poll_time.isoformat() == saved_time
    
    @pytest.mark.asyncio
    async def test_initialize_with_no_saved_state(
        self,
        mock_rest_client: AsyncMock,
        mock_event_store: AsyncMock,
        mock_config_store: AsyncMock,
        scope: Scope,
    ) -> None:
        """저장된 상태 없을 때 초기화"""
        mock_config_store.get.return_value = None
        
        poller = ConcretePoller(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            config_store=mock_config_store,
            scope=scope,
            poll_interval_seconds=60,
        )
        
        await poller.initialize()
        
        assert poller._last_poll_time is None
