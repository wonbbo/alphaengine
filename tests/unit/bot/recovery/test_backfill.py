"""
HistoricalDataRecovery 단위 테스트
"""

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock

import pytest

from bot.recovery.backfill import HistoricalDataRecovery
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
    client = AsyncMock()
    
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


class TestHistoricalDataRecoveryBackfill:
    """backfill() 테스트"""
    
    @pytest.mark.asyncio
    async def test_backfill_empty_history(
        self,
        mock_rest_client: AsyncMock,
        mock_event_store: AsyncMock,
        scope: Scope,
    ) -> None:
        """이력이 없을 때 0건 반환"""
        recovery = HistoricalDataRecovery(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            scope=scope,
            max_days=20,
        )
        
        result = await recovery.backfill()
        
        assert result["total"] == 0
        assert result["income"] == 0
        assert result["transfer"] == 0
        assert result["convert"] == 0
        assert result["deposit"] == 0
        assert result["withdraw"] == 0
        assert result["dust"] == 0
    
    @pytest.mark.asyncio
    async def test_backfill_income_history(
        self,
        mock_rest_client: AsyncMock,
        mock_event_store: AsyncMock,
        scope: Scope,
    ) -> None:
        """Income History 백필 테스트"""
        now = datetime.now(timezone.utc)
        
        mock_rest_client.get_income_history.side_effect = [
            [
                {
                    "symbol": "XRPUSDT",
                    "incomeType": "FUNDING_FEE",
                    "income": "-0.01",
                    "asset": "USDT",
                    "info": "",
                    "time": int(now.timestamp() * 1000) - 3600000,
                    "tranId": 123456,
                    "tradeId": "",
                },
                {
                    "symbol": "XRPUSDT",
                    "incomeType": "COMMISSION_REBATE",
                    "income": "0.005",
                    "asset": "USDT",
                    "info": "",
                    "time": int(now.timestamp() * 1000) - 1800000,
                    "tranId": 123457,
                    "tradeId": "",
                },
            ],
            [],
        ]
        
        recovery = HistoricalDataRecovery(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            scope=scope,
        )
        
        result = await recovery.backfill(days=1)
        
        assert result["income"] == 2
        assert mock_event_store.append.call_count >= 2
    
    @pytest.mark.asyncio
    async def test_backfill_transfer_history(
        self,
        mock_rest_client: AsyncMock,
        mock_event_store: AsyncMock,
        scope: Scope,
    ) -> None:
        """Transfer History 백필 테스트"""
        now = datetime.now(timezone.utc)
        
        def transfer_side_effect(transfer_type, **kwargs):
            if transfer_type == "MAIN_UMFUTURE":
                return {
                    "total": 1,
                    "rows": [
                        {
                            "asset": "USDT",
                            "amount": "100.00",
                            "type": "MAIN_UMFUTURE",
                            "status": "CONFIRMED",
                            "tranId": 11111,
                            "timestamp": int(now.timestamp() * 1000) - 7200000,
                        }
                    ]
                }
            return {"total": 0, "rows": []}
        
        mock_rest_client.get_transfer_history.side_effect = transfer_side_effect
        
        recovery = HistoricalDataRecovery(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            scope=scope,
        )
        
        result = await recovery.backfill(days=1)
        
        assert result["transfer"] == 1
    
    @pytest.mark.asyncio
    async def test_backfill_convert_history(
        self,
        mock_rest_client: AsyncMock,
        mock_event_store: AsyncMock,
        scope: Scope,
    ) -> None:
        """Convert History 백필 테스트"""
        now = datetime.now(timezone.utc)
        
        mock_rest_client.get_convert_history.return_value = {
            "list": [
                {
                    "quoteId": "abc123",
                    "orderId": 99999,
                    "orderStatus": "SUCCESS",
                    "fromAsset": "USDT",
                    "fromAmount": "50.00",
                    "toAsset": "BNB",
                    "toAmount": "0.1",
                    "ratio": "0.002",
                    "inverseRatio": "500",
                    "createTime": int(now.timestamp() * 1000) - 86400000,
                }
            ]
        }
        
        recovery = HistoricalDataRecovery(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            scope=scope,
        )
        
        result = await recovery.backfill(days=3)
        
        assert result["convert"] == 1
    
    @pytest.mark.asyncio
    async def test_backfill_deposit_withdraw(
        self,
        mock_rest_client: AsyncMock,
        mock_event_store: AsyncMock,
        scope: Scope,
    ) -> None:
        """Deposit/Withdraw History 백필 테스트"""
        now = datetime.now(timezone.utc)
        
        mock_rest_client.get_deposit_history.return_value = [
            {
                "id": "dep123",
                "amount": "100",
                "coin": "TRX",
                "network": "TRX",
                "status": 1,
                "address": "Txxx...",
                "txId": "0xabc...",
                "insertTime": int(now.timestamp() * 1000) - 172800000,
            }
        ]
        
        mock_rest_client.get_withdraw_history.return_value = [
            {
                "id": "wd456",
                "amount": "50",
                "transactionFee": "1",
                "coin": "TRX",
                "status": 6,
                "address": "Tyyy...",
                "txId": "0xdef...",
                "applyTime": "2024-01-15 12:00:00",
                "network": "TRX",
            }
        ]
        
        recovery = HistoricalDataRecovery(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            scope=scope,
        )
        
        result = await recovery.backfill(days=5)
        
        assert result["deposit"] == 1
        assert result["withdraw"] == 1
    
    @pytest.mark.asyncio
    async def test_backfill_dust_log(
        self,
        mock_rest_client: AsyncMock,
        mock_event_store: AsyncMock,
        scope: Scope,
    ) -> None:
        """Dust Log 백필 테스트"""
        now = datetime.now(timezone.utc)
        
        mock_rest_client.get_dust_log.return_value = {
            "total": 1,
            "userAssetDribblets": [
                {
                    "operateTime": int(now.timestamp() * 1000) - 259200000,
                    "totalTransferedAmount": "0.001",
                    "totalServiceChargeAmount": "0.00001",
                    "transId": 88888,
                    "userAssetDribbletDetails": [
                        {
                            "transId": 44444,
                            "serviceChargeAmount": "0.00001",
                            "amount": "0.0005",
                            "operateTime": int(now.timestamp() * 1000) - 259200000,
                            "transferedAmount": "0.001",
                            "fromAsset": "ATOM",
                        }
                    ]
                }
            ]
        }
        
        recovery = HistoricalDataRecovery(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            scope=scope,
        )
        
        result = await recovery.backfill(days=5)
        
        assert result["dust"] == 1


class TestHistoricalDataRecoveryDedup:
    """중복 방지 테스트"""
    
    @pytest.mark.asyncio
    async def test_dedup_prevents_duplicates(
        self,
        mock_rest_client: AsyncMock,
        mock_event_store: AsyncMock,
        scope: Scope,
    ) -> None:
        """dedup_key로 중복 이벤트 방지"""
        now = datetime.now(timezone.utc)
        
        mock_rest_client.get_income_history.side_effect = [
            [
                {
                    "symbol": "XRPUSDT",
                    "incomeType": "FUNDING_FEE",
                    "income": "-0.01",
                    "asset": "USDT",
                    "info": "",
                    "time": int(now.timestamp() * 1000) - 3600000,
                    "tranId": 123456,
                    "tradeId": "",
                },
            ],
            [],
        ]
        
        mock_event_store.append.return_value = False
        
        recovery = HistoricalDataRecovery(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            scope=scope,
        )
        
        result = await recovery.backfill(days=1)
        
        assert result["income"] == 0
        mock_event_store.append.assert_called()


class TestHistoricalDataRecoveryEventPayload:
    """이벤트 페이로드 테스트"""
    
    @pytest.mark.asyncio
    async def test_income_event_has_correct_payload(
        self,
        mock_rest_client: AsyncMock,
        mock_event_store: AsyncMock,
        scope: Scope,
    ) -> None:
        """Income 이벤트 페이로드 검증"""
        now = datetime.now(timezone.utc)
        
        mock_rest_client.get_income_history.side_effect = [
            [
                {
                    "symbol": "XRPUSDT",
                    "incomeType": "FUNDING_FEE",
                    "income": "-0.01234567",
                    "asset": "USDT",
                    "info": "test info",
                    "time": int(now.timestamp() * 1000) - 3600000,
                    "tranId": 999999,
                    "tradeId": "",
                },
            ],
            [],
        ]
        
        recovery = HistoricalDataRecovery(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            scope=scope,
        )
        
        await recovery.backfill(days=1)
        
        event = mock_event_store.append.call_args[0][0]
        
        assert event.event_type == "FundingApplied"
        assert event.payload["symbol"] == "XRPUSDT"
        assert event.payload["income_type"] == "FUNDING_FEE"
        assert event.payload["income"] == "-0.01234567"
        assert event.payload["source"] == "backfill"
