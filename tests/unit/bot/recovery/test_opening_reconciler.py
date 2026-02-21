"""
OpeningBalanceReconciler 단위 테스트
"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from bot.recovery.opening_reconciler import OpeningBalanceReconciler
from core.types import Scope


class MockBalance:
    """get_balances() 결과 Mock"""
    def __init__(self, asset: str, wallet_balance: str):
        self.asset = asset
        self.wallet_balance = wallet_balance


@pytest.fixture
def scope():
    return Scope.create(
        exchange="BINANCE",
        venue="FUTURES",
        symbol="XRPUSDT",
        mode="production",
    )


@pytest.fixture
def mock_rest_client():
    """Binance REST 클라이언트 Mock"""
    client = MagicMock()
    
    # FUTURES 잔고 Mock
    client.get_balances = AsyncMock(return_value=[
        MockBalance("USDT", "673.52"),
        MockBalance("BNB", "0.10"),
    ])
    
    # SPOT 잔고 Mock
    client.get_spot_balances = AsyncMock(return_value={
        "USDT": {"free": "0.47", "locked": "0"},
        "BNB": {"free": "0.45", "locked": "0.05"},
    })
    
    return client


@pytest.fixture
def mock_event_store():
    """EventStore Mock"""
    store = MagicMock()
    store.append = AsyncMock(return_value=True)
    return store


class TestOpeningBalanceReconciler:
    """OpeningBalanceReconciler 테스트"""
    
    @pytest.mark.asyncio
    async def test_reconcile_with_differences(
        self,
        mock_rest_client,
        mock_event_store,
        scope,
    ):
        """차이가 있을 때 조정 이벤트 생성 확인"""
        reconciler = OpeningBalanceReconciler(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            scope=scope,
        )
        
        # Ledger 잔고 (거래소와 다름)
        ledger_balances = {
            "FUTURES": {
                "USDT": Decimal("670.00"),  # 거래소: 673.52, 차이: +3.52
                "BNB": Decimal("0.10"),     # 거래소: 0.10, 차이: 0 (무시)
            },
            "SPOT": {
                "USDT": Decimal("0.47"),    # 거래소: 0.47, 차이: 0 (무시)
                "BNB": Decimal("0.60"),     # 거래소: 0.50, 차이: -0.10
            },
        }
        
        result = await reconciler.reconcile(ledger_balances)
        
        # 2개 조정 (FUTURES USDT +3.52, SPOT BNB -0.10)
        assert result["adjusted_count"] == 2
        
        # append 호출 횟수 확인 (2회)
        assert mock_event_store.append.call_count == 2
    
    @pytest.mark.asyncio
    async def test_reconcile_no_differences(
        self,
        mock_rest_client,
        mock_event_store,
        scope,
    ):
        """차이가 없을 때 조정 이벤트 미생성"""
        reconciler = OpeningBalanceReconciler(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            scope=scope,
        )
        
        # Ledger 잔고가 거래소와 동일
        ledger_balances = {
            "FUTURES": {
                "USDT": Decimal("673.52"),
                "BNB": Decimal("0.10"),
            },
            "SPOT": {
                "USDT": Decimal("0.47"),
                "BNB": Decimal("0.50"),  # free + locked = 0.45 + 0.05 = 0.50
            },
        }
        
        result = await reconciler.reconcile(ledger_balances)
        
        # 조정 없음
        assert result["adjusted_count"] == 0
        assert mock_event_store.append.call_count == 0
    
    @pytest.mark.asyncio
    async def test_reconcile_below_threshold(
        self,
        mock_rest_client,
        mock_event_store,
        scope,
    ):
        """임계값 이하 차이는 무시"""
        reconciler = OpeningBalanceReconciler(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            scope=scope,
        )
        
        # 임계값(0.0001) 이하의 미세한 차이
        ledger_balances = {
            "FUTURES": {
                "USDT": Decimal("673.51995"),  # 차이: 0.00005 < 0.0001
                "BNB": Decimal("0.10"),
            },
            "SPOT": {
                "USDT": Decimal("0.47"),
                "BNB": Decimal("0.50"),
            },
        }
        
        result = await reconciler.reconcile(ledger_balances)
        
        # 임계값 이하는 skipped
        assert result["adjusted_count"] == 0
        assert result["skipped_count"] >= 1
    
    @pytest.mark.asyncio
    async def test_reconcile_new_asset_in_exchange(
        self,
        mock_event_store,
        scope,
    ):
        """거래소에만 있는 자산 감지"""
        rest_client = MagicMock()
        
        # 거래소에 ETH 추가
        rest_client.get_balances = AsyncMock(return_value=[
            MockBalance("USDT", "670.00"),
            MockBalance("ETH", "0.05"),  # Ledger에 없음
        ])
        rest_client.get_spot_balances = AsyncMock(return_value={})
        
        reconciler = OpeningBalanceReconciler(
            rest_client=rest_client,
            event_store=mock_event_store,
            scope=scope,
        )
        
        # Ledger에는 USDT만 있음
        ledger_balances = {
            "FUTURES": {
                "USDT": Decimal("670.00"),
            },
            "SPOT": {},
        }
        
        result = await reconciler.reconcile(ledger_balances)
        
        # ETH 추가 조정
        assert result["adjusted_count"] == 1
        assert any(
            adj["asset"] == "ETH" and adj["venue"] == "FUTURES"
            for adj in result["adjustments"]
        )
    
    @pytest.mark.asyncio
    async def test_fetch_exchange_balances(
        self,
        mock_rest_client,
        mock_event_store,
        scope,
    ):
        """거래소 잔고 조회 테스트"""
        reconciler = OpeningBalanceReconciler(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            scope=scope,
        )
        
        balances = await reconciler._fetch_exchange_balances()
        
        # FUTURES
        assert "USDT" in balances["FUTURES"]
        assert balances["FUTURES"]["USDT"] == Decimal("673.52")
        assert balances["FUTURES"]["BNB"] == Decimal("0.10")
        
        # SPOT (free + locked)
        assert balances["SPOT"]["USDT"] == Decimal("0.47")
        assert balances["SPOT"]["BNB"] == Decimal("0.50")  # 0.45 + 0.05
    
    @pytest.mark.asyncio
    async def test_calculate_adjustments(
        self,
        mock_rest_client,
        mock_event_store,
        scope,
    ):
        """차이 계산 로직 테스트"""
        reconciler = OpeningBalanceReconciler(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            scope=scope,
        )
        
        ledger = {
            "FUTURES": {"USDT": Decimal("100")},
            "SPOT": {"BNB": Decimal("1.0")},
        }
        
        exchange = {
            "FUTURES": {"USDT": Decimal("110"), "ETH": Decimal("0.5")},  # USDT +10, ETH 새로 추가
            "SPOT": {"BNB": Decimal("0.8")},  # BNB -0.2
        }
        
        adjustments = reconciler._calculate_adjustments(ledger, exchange)
        
        # 3개 조정 필요
        assert len(adjustments) == 3
        
        # FUTURES USDT: +10
        usdt_adj = next(a for a in adjustments if a["asset"] == "USDT")
        assert usdt_adj["diff"] == Decimal("10")
        
        # FUTURES ETH: +0.5 (새 자산)
        eth_adj = next(a for a in adjustments if a["asset"] == "ETH")
        assert eth_adj["diff"] == Decimal("0.5")
        
        # SPOT BNB: -0.2
        bnb_adj = next(a for a in adjustments if a["asset"] == "BNB")
        assert bnb_adj["diff"] == Decimal("-0.2")
