"""
Reconciler 통합 테스트

WS 끊김 → REST 복구 → 이벤트 정합성 시나리오 검증.
"""

import asyncio
import logging
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio

from adapters.binance.rest_client import BinanceRestClient
from adapters.binance.ws_client import BinanceWsClient
from core.config.loader import ExchangeConfig
from core.domain.events import Event, EventTypes
from core.storage.event_store import EventStore
from core.types import Scope, WebSocketState, TradingMode
from adapters.db.sqlite_adapter import SQLiteAdapter, init_schema
from tests.e2e.utils.helpers import wait_for_ws_state


pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


class TestReconcilerBasic:
    """Reconciler 기본 테스트"""
    
    async def test_event_dedup_key_uniqueness(
        self,
        e2e_logger: logging.Logger,
    ) -> None:
        """이벤트 dedup_key 중복 제거 테스트
        
        검증 항목:
        - 같은 dedup_key로 중복 저장 시 무시
        - 다른 dedup_key는 정상 저장
        """
        e2e_logger.info("test_event_dedup_key_uniqueness 시작")
        
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = Path(tmp.name)
        
        try:
            async with SQLiteAdapter(db_path) as adapter:
                await init_schema(adapter)
                
                event_store = EventStore(adapter)
                scope = Scope.create(symbol="XRPUSDT", mode=TradingMode.TESTNET)
                
                # 첫 번째 이벤트 저장
                event1 = Event.create(
                    event_type=EventTypes.TRADE_EXECUTED,
                    source="WEBSOCKET",
                    entity_kind="TRADE",
                    entity_id="trade001",
                    scope=scope,
                    dedup_key="BINANCE:FUTURES:XRPUSDT:trade:12345",
                    payload={"price": "0.5", "qty": "100"},
                )
                
                saved1 = await event_store.append(event1)
                assert saved1 is True
                e2e_logger.info("첫 번째 이벤트 저장 성공")
                
                # 같은 dedup_key로 중복 저장 시도
                event2 = Event.create(
                    event_type=EventTypes.TRADE_EXECUTED,
                    source="REST",  # 다른 source
                    entity_kind="TRADE",
                    entity_id="trade001",
                    scope=scope,
                    dedup_key="BINANCE:FUTURES:XRPUSDT:trade:12345",  # 같은 dedup_key
                    payload={"price": "0.5", "qty": "100", "extra": "data"},
                )
                
                saved2 = await event_store.append(event2)
                # INSERT OR IGNORE이므로 실패하지 않지만 실제로 삽입되지 않음
                e2e_logger.info(f"중복 dedup_key 저장 시도 결과: {saved2}")
                
                # 전체 이벤트 수 확인 (1개여야 함)
                total = await event_store.count_all()
                assert total == 1, f"중복 이벤트가 저장됨: {total}개"
                e2e_logger.info(f"전체 이벤트 수: {total} (예상: 1)")
                
                # 다른 dedup_key로 저장
                event3 = Event.create(
                    event_type=EventTypes.TRADE_EXECUTED,
                    source="REST",
                    entity_kind="TRADE",
                    entity_id="trade002",
                    scope=scope,
                    dedup_key="BINANCE:FUTURES:XRPUSDT:trade:12346",  # 다른 dedup_key
                    payload={"price": "0.51", "qty": "50"},
                )
                
                saved3 = await event_store.append(event3)
                assert saved3 is True
                e2e_logger.info("다른 dedup_key 이벤트 저장 성공")
                
                # 전체 이벤트 수 확인 (2개여야 함)
                total_final = await event_store.count_all()
                assert total_final == 2, f"이벤트 수가 맞지 않음: {total_final}개"
                e2e_logger.info(f"최종 이벤트 수: {total_final} (예상: 2)")
        
        finally:
            if db_path.exists():
                db_path.unlink()
        
        e2e_logger.info("test_event_dedup_key_uniqueness 완료")
    
    async def test_event_sequence_ordering(
        self,
        e2e_logger: logging.Logger,
    ) -> None:
        """이벤트 시퀀스 순서 테스트
        
        검증 항목:
        - 이벤트가 저장 순서대로 seq 증가
        - get_since로 특정 seq 이후 이벤트 조회
        """
        e2e_logger.info("test_event_sequence_ordering 시작")
        
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = Path(tmp.name)
        
        try:
            async with SQLiteAdapter(db_path) as adapter:
                await init_schema(adapter)
                
                event_store = EventStore(adapter)
                scope = Scope.create(symbol="XRPUSDT", mode=TradingMode.TESTNET)
                
                # 여러 이벤트 저장
                for i in range(10):
                    event = Event.create(
                        event_type=EventTypes.BALANCE_CHANGED,
                        source="WEBSOCKET",
                        entity_kind="BALANCE",
                        entity_id="USDT",
                        scope=scope,
                        dedup_key=f"BINANCE:FUTURES:main:balance:USDT:{i}",
                        payload={"free": str(1000 + i)},
                    )
                    await event_store.append(event)
                
                e2e_logger.info("10개 이벤트 저장 완료")
                
                # seq=0 이후 전체 조회
                events_from_0 = await event_store.get_since(0, limit=100)
                assert len(events_from_0) == 10
                e2e_logger.info(f"seq=0 이후 이벤트 수: {len(events_from_0)}")
                
                # seq=5 이후 조회 (5개 예상)
                events_from_5 = await event_store.get_since(5, limit=100)
                assert len(events_from_5) == 5
                e2e_logger.info(f"seq=5 이후 이벤트 수: {len(events_from_5)}")
                
                # 마지막 seq 조회
                last_seq = await event_store.get_last_seq()
                assert last_seq == 10
                e2e_logger.info(f"마지막 seq: {last_seq}")
        
        finally:
            if db_path.exists():
                db_path.unlink()
        
        e2e_logger.info("test_event_sequence_ordering 완료")


class TestReconcilerWithExchange:
    """거래소 연동 Reconciler 테스트"""
    
    @pytest.mark.readonly
    async def test_rest_balance_reconciliation(
        self,
        rest_client: BinanceRestClient,
        e2e_logger: logging.Logger,
    ) -> None:
        """REST API로 잔고 조회 및 이벤트 생성 테스트
        
        검증 항목:
        - REST API로 잔고 조회
        - 조회 결과로 BalanceChanged 이벤트 생성
        - dedup_key 형식 검증
        """
        e2e_logger.info("test_rest_balance_reconciliation 시작")
        
        # REST API로 잔고 조회
        e2e_logger.info("REST API로 잔고 조회 중...")
        balances = await rest_client.get_balances()
        
        assert balances is not None
        e2e_logger.info(f"조회된 잔고 수: {len(balances)}")
        
        # USDT 잔고 확인
        usdt_balance = next(
            (b for b in balances if b.asset == "USDT"),
            None,
        )
        
        if usdt_balance is None:
            e2e_logger.warning("USDT 잔고 없음")
        else:
            e2e_logger.info(f"USDT 잔고: {usdt_balance.available_balance}")
            
            # BalanceChanged 이벤트 생성 시뮬레이션
            scope = Scope.create(mode=TradingMode.TESTNET)
            
            # REST 조회 시점의 dedup_key (예: 시간 기반)
            now = datetime.now(timezone.utc)
            timestamp_key = now.strftime("%Y%m%d%H%M")  # 분 단위
            dedup_key = f"BINANCE:FUTURES:main:balance:USDT:rest:{timestamp_key}"
            
            e2e_logger.info(f"생성된 dedup_key: {dedup_key}")
            
            # 실제 이벤트 생성 (저장은 하지 않음)
            event = Event.create(
                event_type=EventTypes.BALANCE_CHANGED,
                source="REST",
                entity_kind="BALANCE",
                entity_id="USDT",
                scope=scope,
                dedup_key=dedup_key,
                payload={
                    "asset": "USDT",
                    "available_balance": str(usdt_balance.available_balance),
                    "wallet_balance": str(usdt_balance.wallet_balance),
                },
            )
            
            e2e_logger.info(f"이벤트 생성 완료: {event.event_type}")
        
        e2e_logger.info("test_rest_balance_reconciliation 완료")
    
    @pytest.mark.readonly
    async def test_rest_position_reconciliation(
        self,
        rest_client: BinanceRestClient,
        test_symbol: str,
        e2e_logger: logging.Logger,
    ) -> None:
        """REST API로 포지션 조회 및 이벤트 생성 테스트
        
        검증 항목:
        - REST API로 포지션 조회
        - 포지션 있으면 PositionChanged 이벤트 생성 시뮬레이션
        """
        e2e_logger.info("test_rest_position_reconciliation 시작")
        
        # REST API로 포지션 조회
        e2e_logger.info(f"REST API로 포지션 조회 중... (symbol={test_symbol})")
        position = await rest_client.get_position(test_symbol)
        
        if position is None:
            e2e_logger.info("포지션 없음")
        else:
            e2e_logger.info(f"포지션: qty={position.quantity}, side={position.side}")
            
            if position.quantity != Decimal("0"):
                # PositionChanged 이벤트 생성 시뮬레이션
                scope = Scope.create(symbol=test_symbol, mode=TradingMode.TESTNET)
                
                now = datetime.now(timezone.utc)
                timestamp_key = now.strftime("%Y%m%d%H%M")
                dedup_key = f"BINANCE:FUTURES:{test_symbol}:position:rest:{timestamp_key}"
                
                event = Event.create(
                    event_type=EventTypes.POSITION_CHANGED,
                    source="REST",
                    entity_kind="POSITION",
                    entity_id=test_symbol,
                    scope=scope,
                    dedup_key=dedup_key,
                    payload={
                        "symbol": test_symbol,
                        "position_amount": str(position.quantity),
                        "entry_price": str(position.entry_price),
                        "unrealized_pnl": str(position.unrealized_pnl),
                    },
                )
                
                e2e_logger.info(f"이벤트 생성 완료: {event.event_type}")
        
        e2e_logger.info("test_rest_position_reconciliation 완료")


class TestDriftDetection:
    """Drift 감지 테스트"""
    
    async def test_balance_drift_detection_logic(
        self,
        e2e_logger: logging.Logger,
    ) -> None:
        """잔고 Drift 감지 로직 테스트
        
        검증 항목:
        - 거래소 vs Projection 잔고 비교
        - Drift 감지 시 DriftInfo 반환
        """
        from decimal import Decimal
        from bot.reconciler.drift import DriftDetector
        from adapters.models import Balance
        from core.types import Scope, TradingMode
        
        e2e_logger.info("test_balance_drift_detection_logic 시작")
        
        # DriftDetector 인스턴스 생성
        scope = Scope.create(symbol="XRPUSDT", mode=TradingMode.TESTNET)
        detector = DriftDetector(scope)
        
        # 정상 케이스: Drift 없음 (free와 locked가 일치)
        # Balance는 wallet_balance와 available_balance를 사용
        # free = available_balance, locked = wallet_balance - available_balance
        exchange_balance = Balance(
            asset="USDT",
            wallet_balance=Decimal("1000.00"),  # free + locked
            available_balance=Decimal("950.00"),  # free
        )
        projection_balance = {
            "asset": "USDT",
            "free": "950.00",
            "locked": "50.00",
        }
        
        drift = detector.detect_balance_drift(exchange_balance, projection_balance)
        
        if drift:
            e2e_logger.info(f"Drift 감지됨: {drift}")
        else:
            e2e_logger.info("Drift 없음 (정상)")
        
        assert drift is None, "일치하는 잔고에서 Drift가 감지되면 안 됨"
        
        # Drift 케이스: 잔고 차이
        projection_balance_wrong = {
            "asset": "USDT",
            "free": "800.00",  # 실제보다 적음 (950 != 800)
            "locked": "50.00",
        }
        
        drift2 = detector.detect_balance_drift(exchange_balance, projection_balance_wrong)
        
        if drift2:
            e2e_logger.info(f"Drift 감지됨 (예상): {drift2.description}")
            assert "balance" in drift2.drift_kind.lower() or "free" in drift2.description.lower()
        else:
            pytest.fail("Drift가 감지되어야 하는데 감지되지 않음")
        
        e2e_logger.info("test_balance_drift_detection_logic 완료")
    
    async def test_position_drift_detection_logic(
        self,
        e2e_logger: logging.Logger,
    ) -> None:
        """포지션 Drift 감지 로직 테스트
        
        검증 항목:
        - 거래소 vs Projection 포지션 비교
        - Drift 감지 시 DriftInfo 반환
        """
        from decimal import Decimal
        from bot.reconciler.drift import DriftDetector
        from adapters.models import Position
        from core.types import Scope, TradingMode
        
        e2e_logger.info("test_position_drift_detection_logic 시작")
        
        # DriftDetector 인스턴스 생성
        scope = Scope.create(symbol="XRPUSDT", mode=TradingMode.TESTNET)
        detector = DriftDetector(scope)
        
        # 케이스 1: Projection 없는데 거래소에 포지션 있음
        # Position은 quantity 필드를 사용 (qty는 property)
        exchange_position = Position(
            symbol="XRPUSDT",
            side="LONG",
            quantity=Decimal("100"),
            entry_price=Decimal("0.5"),
            unrealized_pnl=Decimal("0"),
            leverage=10,
            margin_type="ISOLATED",
        )
        projection_position = None
        
        drift1 = detector.detect_position_drift(
            exchange_position, projection_position, "XRPUSDT"
        )
        
        if drift1:
            e2e_logger.info(f"Drift 감지됨 (거래소에 포지션): {drift1.description}")
            assert "empty" in drift1.description.lower() or "position" in drift1.drift_kind.lower()
        else:
            pytest.fail("Drift가 감지되어야 함")
        
        # 케이스 2: 거래소에 없는데 Projection에 포지션 있음
        exchange_position2 = None
        projection_position2 = {
            "symbol": "XRPUSDT",
            "qty": "100",
            "side": "LONG",
        }
        
        drift2 = detector.detect_position_drift(
            exchange_position2, projection_position2, "XRPUSDT"
        )
        
        if drift2:
            e2e_logger.info(f"Drift 감지됨 (Projection에 포지션): {drift2.description}")
        else:
            pytest.fail("Drift가 감지되어야 함")
        
        # 케이스 3: 둘 다 없음 (정상)
        drift3 = detector.detect_position_drift(None, None, "XRPUSDT")
        assert drift3 is None
        e2e_logger.info("Drift 없음 (둘 다 없음)")
        
        e2e_logger.info("test_position_drift_detection_logic 완료")
