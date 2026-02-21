"""
이벤트 복구 및 완전 추적 시스템 통합 테스트

전체 복구 흐름을 Mock 기반으로 검증합니다.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.types import Scope
from core.domain.events import EventTypes
from bot.recovery.initial_capital import InitialCapitalRecorder
from bot.recovery.backfill import HistoricalDataRecovery
from bot.poller.income_poller import IncomePoller
from bot.poller.transfer_poller import TransferPoller
from bot.poller.convert_poller import ConvertPoller
from bot.poller.deposit_withdraw_poller import DepositWithdrawPoller


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
    client = AsyncMock()
    
    client.get_account_snapshot.return_value = {
        "code": 200,
        "msg": "",
        "snapshotVos": []
    }
    client.get_income_history.return_value = []
    client.get_transfer_history.return_value = {"total": 0, "rows": []}
    client.get_convert_history.return_value = {"list": []}
    client.get_deposit_history.return_value = []
    client.get_withdraw_history.return_value = []
    client.get_dust_log.return_value = {"userAssetDribblets": []}
    
    return client


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


class TestEventRecoveryIntegration:
    """이벤트 복구 통합 테스트"""
    
    @pytest.mark.asyncio
    async def test_first_run_recovery_flow(
        self,
        mock_rest_client: AsyncMock,
        mock_event_store: AsyncMock,
        mock_config_store: AsyncMock,
        scope: Scope,
    ) -> None:
        """최초 실행 시 전체 복구 흐름 테스트"""
        now = datetime.now(timezone.utc)
        
        mock_rest_client.get_account_snapshot.side_effect = [
            {
                "code": 200,
                "msg": "",
                "snapshotVos": [
                    {
                        "type": "spot",
                        "updateTime": int(now.timestamp() * 1000),
                        "data": {
                            "balances": [
                                {"asset": "USDT", "free": "100.00", "locked": "0"},
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
                        "updateTime": int(now.timestamp() * 1000),
                        "data": {
                            "assets": [
                                {"asset": "USDT", "walletBalance": "400.00"},
                            ]
                        }
                    }
                ]
            },
        ]
        
        mock_rest_client.get_income_history.side_effect = [
            [
                {
                    "symbol": "XRPUSDT",
                    "incomeType": "FUNDING_FEE",
                    "income": "-0.01",
                    "asset": "USDT",
                    "info": "",
                    "time": int(now.timestamp() * 1000) - 86400000,
                    "tranId": 111111,
                    "tradeId": "",
                }
            ],
            [],
        ]
        
        recorder = InitialCapitalRecorder(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            config_store=mock_config_store,
            scope=scope,
        )
        
        result = await recorder.record()
        
        assert result["initialized"] is True
        assert result["SPOT_USDT"] == "100.00"
        assert result["FUTURES_USDT"] == "400.00"
        assert result["USDT"] == "500.00"
        
        mock_event_store.append.assert_called()
        event = mock_event_store.append.call_args[0][0]
        assert event.event_type == EventTypes.INITIAL_CAPITAL_ESTABLISHED
        
        mock_event_store.reset_mock()
        
        recovery = HistoricalDataRecovery(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            scope=scope,
            max_days=20,
        )
        
        backfill_result = await recovery.backfill(days=1)
        
        assert backfill_result["income"] == 1
    
    @pytest.mark.asyncio
    async def test_skip_recovery_if_already_initialized(
        self,
        mock_rest_client: AsyncMock,
        mock_event_store: AsyncMock,
        mock_config_store: AsyncMock,
        scope: Scope,
    ) -> None:
        """이미 초기화된 경우 복구 건너뜀"""
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
        
        result = await recorder.record()
        
        assert result == {"initialized": True, "USDT": "500.00"}
        
        mock_rest_client.get_account_snapshot.assert_not_called()


class TestPollerIntegration:
    """Poller 통합 테스트"""
    
    @pytest.mark.asyncio
    async def test_income_poller_creates_funding_event(
        self,
        mock_rest_client: AsyncMock,
        mock_event_store: AsyncMock,
        mock_config_store: AsyncMock,
        scope: Scope,
    ) -> None:
        """IncomePoller가 FundingApplied 이벤트 생성"""
        now = datetime.now(timezone.utc)
        
        mock_rest_client.get_income_history.return_value = [
            {
                "symbol": "XRPUSDT",
                "incomeType": "FUNDING_FEE",
                "income": "-0.02345678",
                "asset": "USDT",
                "info": "",
                "time": int(now.timestamp() * 1000) - 300000,
                "tranId": 222222,
                "tradeId": "",
            }
        ]
        
        poller = IncomePoller(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            config_store=mock_config_store,
            scope=scope,
            poll_interval_seconds=60,
        )
        
        result = await poller.poll()
        
        assert result["events_created"] == 1
        
        event = mock_event_store.append.call_args[0][0]
        assert event.event_type == EventTypes.FUNDING_APPLIED
        assert event.payload["funding_fee"] == "-0.02345678"
    
    @pytest.mark.asyncio
    async def test_transfer_poller_creates_transfer_event(
        self,
        mock_rest_client: AsyncMock,
        mock_event_store: AsyncMock,
        mock_config_store: AsyncMock,
        scope: Scope,
    ) -> None:
        """TransferPoller가 InternalTransferCompleted 이벤트 생성"""
        now = datetime.now(timezone.utc)
        
        def transfer_side_effect(transfer_type, **kwargs):
            if transfer_type == "MAIN_UMFUTURE":
                return {
                    "total": 1,
                    "rows": [
                        {
                            "asset": "USDT",
                            "amount": "200.00",
                            "type": "MAIN_UMFUTURE",
                            "status": "CONFIRMED",
                            "tranId": 333333,
                            "timestamp": int(now.timestamp() * 1000) - 600000,
                        }
                    ]
                }
            return {"total": 0, "rows": []}
        
        mock_rest_client.get_transfer_history.side_effect = transfer_side_effect
        
        poller = TransferPoller(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            config_store=mock_config_store,
            scope=scope,
        )
        
        result = await poller.poll()
        
        assert result["events_created"] == 1
        
        event = mock_event_store.append.call_args[0][0]
        assert event.event_type == EventTypes.INTERNAL_TRANSFER_COMPLETED
        assert event.payload["amount"] == "200.00"
    
    @pytest.mark.asyncio
    async def test_convert_poller_creates_convert_event(
        self,
        mock_rest_client: AsyncMock,
        mock_event_store: AsyncMock,
        mock_config_store: AsyncMock,
        scope: Scope,
    ) -> None:
        """ConvertPoller가 ConvertExecuted 이벤트 생성"""
        now = datetime.now(timezone.utc)
        
        mock_rest_client.get_convert_history.return_value = {
            "list": [
                {
                    "quoteId": "quote123",
                    "orderId": 444444,
                    "orderStatus": "SUCCESS",
                    "fromAsset": "USDT",
                    "fromAmount": "50.00",
                    "toAsset": "BNB",
                    "toAmount": "0.1",
                    "ratio": "0.002",
                    "inverseRatio": "500",
                    "createTime": int(now.timestamp() * 1000) - 1800000,
                }
            ]
        }
        
        poller = ConvertPoller(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            config_store=mock_config_store,
            scope=scope,
        )
        
        result = await poller.poll()
        
        assert result["events_created"] == 1
        
        event = mock_event_store.append.call_args[0][0]
        assert event.event_type == EventTypes.CONVERT_EXECUTED
        assert event.payload["from_asset"] == "USDT"
        assert event.payload["to_asset"] == "BNB"
    
    @pytest.mark.asyncio
    async def test_deposit_withdraw_poller_creates_events(
        self,
        mock_rest_client: AsyncMock,
        mock_event_store: AsyncMock,
        mock_config_store: AsyncMock,
        scope: Scope,
    ) -> None:
        """DepositWithdrawPoller가 입출금 이벤트 생성"""
        now = datetime.now(timezone.utc)
        
        mock_rest_client.get_deposit_history.return_value = [
            {
                "id": "dep555",
                "amount": "100.00",
                "coin": "TRX",
                "network": "TRX",
                "status": 1,
                "address": "Txxx...",
                "txId": "0xabc...",
                "insertTime": int(now.timestamp() * 1000) - 3600000,
            }
        ]
        
        mock_rest_client.get_withdraw_history.return_value = [
            {
                "id": "wd666",
                "amount": "50.00",
                "transactionFee": "1.00",
                "coin": "TRX",
                "status": 6,
                "address": "Tyyy...",
                "txId": "0xdef...",
                "applyTime": "2024-01-15 12:00:00",
                "network": "TRX",
            }
        ]
        
        poller = DepositWithdrawPoller(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            config_store=mock_config_store,
            scope=scope,
        )
        
        result = await poller.poll()
        
        assert result["events_created"] == 2


class TestDedupPrevention:
    """중복 방지 테스트"""
    
    @pytest.mark.asyncio
    async def test_duplicate_events_not_created(
        self,
        mock_rest_client: AsyncMock,
        mock_event_store: AsyncMock,
        mock_config_store: AsyncMock,
        scope: Scope,
    ) -> None:
        """중복 이벤트가 생성되지 않음"""
        now = datetime.now(timezone.utc)
        
        mock_rest_client.get_income_history.return_value = [
            {
                "symbol": "XRPUSDT",
                "incomeType": "FUNDING_FEE",
                "income": "-0.01",
                "asset": "USDT",
                "info": "",
                "time": int(now.timestamp() * 1000) - 300000,
                "tranId": 777777,
                "tradeId": "",
            }
        ]
        
        mock_event_store.append.return_value = False
        
        poller = IncomePoller(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            config_store=mock_config_store,
            scope=scope,
        )
        
        result = await poller.poll()
        
        assert result["events_created"] == 0


class TestPollerInterval:
    """Poller 간격 테스트"""
    
    @pytest.mark.asyncio
    async def test_should_poll_respects_interval(
        self,
        mock_rest_client: AsyncMock,
        mock_event_store: AsyncMock,
        mock_config_store: AsyncMock,
        scope: Scope,
    ) -> None:
        """폴링 간격이 준수됨"""
        poller = IncomePoller(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            config_store=mock_config_store,
            scope=scope,
            poll_interval_seconds=300,
        )
        
        assert await poller.should_poll() is True
        
        await poller.poll()
        
        assert await poller.should_poll() is False
        
        poller._last_poll_time = datetime.now(timezone.utc) - timedelta(seconds=400)
        
        assert await poller.should_poll() is True
