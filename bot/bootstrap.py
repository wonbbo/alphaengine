"""
Bot Bootstrap

설정 로드, 의존성 주입, 메인 루프 관리.
EngineStarted/EngineStopped 이벤트로 생명주기 관리.

Dev-Phase 5: 코어 로직 통합
- WebSocket Listener
- Reconciler
- Command Processor
- Projector
- Strategy Runner
"""

import asyncio
import logging
import sys
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from adapters.binance.rest_client import BinanceRestClient
from adapters.db.sqlite_adapter import SQLiteAdapter, init_schema
from core.config.loader import get_settings
from core.constants import BinanceUrls, Defaults
from core.domain.events import Event
from core.domain.state_machines import EngineStateMachine, EngineState
from core.storage.command_store import CommandStore
from core.storage.event_store import EventStore
from core.types import Scope, WebSocketState

from bot.websocket.listener import WebSocketListener
from bot.reconciler.reconciler import HybridReconciler
from bot.command.processor import CommandProcessor
from bot.executor.executor import CommandExecutor
from bot.projector.projector import EventProjector
from bot.risk.guard import RiskGuard
from bot.strategy.runner import StrategyRunner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("bot")


class BotEngine:
    """Bot 엔진
    
    모든 컴포넌트를 초기화하고 메인 루프 실행.
    
    Args:
        settings: 설정 객체
        db: SQLite 어댑터
    """
    
    def __init__(self, settings: Any, db: SQLiteAdapter):
        self.settings = settings
        self.db = db
        
        # 상태 머신
        self.state_machine = EngineStateMachine(EngineState.BOOTING)
        
        # Scope 생성
        self.scope = self._create_scope()
        
        # 스토리지
        self.event_store = EventStore(db)
        self.command_store = CommandStore(db)
        
        # REST 클라이언트
        self.rest_client = self._create_rest_client()
        
        # 컴포넌트들 (초기화 시 생성)
        self.projector: EventProjector | None = None
        self.risk_guard: RiskGuard | None = None
        self.executor: CommandExecutor | None = None
        self.command_processor: CommandProcessor | None = None
        self.ws_listener: WebSocketListener | None = None
        self.reconciler: HybridReconciler | None = None
        self.strategy_runner: StrategyRunner | None = None
        
        # 설정
        self.target_symbol = settings.target_symbol if hasattr(settings, 'target_symbol') else "XRPUSDT"
        self.tick_interval = 0.1  # 100ms
        self.strategy_tick_interval = 5.0  # 5초 (5분봉 기준)
        
        # 통계
        self._tick_count = 0
        self._last_strategy_tick = 0.0
    
    def _create_scope(self) -> Scope:
        """기본 Scope 생성"""
        return Scope(
            exchange=Defaults.EXCHANGE,
            venue=Defaults.VENUE,
            account_id=Defaults.ACCOUNT_ID,
            symbol=None,
            mode=self.settings.mode.value.upper(),
        )
    
    def _scope_with_symbol(self) -> Scope:
        """심볼이 포함된 Scope 생성"""
        return Scope(
            exchange=self.scope.exchange,
            venue=self.scope.venue,
            account_id=self.scope.account_id,
            symbol=self.target_symbol,
            mode=self.scope.mode,
        )
    
    def _create_rest_client(self) -> BinanceRestClient:
        """REST 클라이언트 생성"""
        if self.settings.mode.value == "testnet":
            base_url = BinanceUrls.TESTNET_REST
        else:
            base_url = BinanceUrls.PROD_REST
        
        return BinanceRestClient(
            base_url=base_url,
            api_key=self.settings.api_key,
            api_secret=self.settings.api_secret,
        )
    
    async def initialize(self) -> None:
        """컴포넌트 초기화"""
        logger.info("Bot 컴포넌트 초기화 시작...")
        
        scope_with_symbol = self._scope_with_symbol()
        
        # 1. Projector
        self.projector = EventProjector(self.db, self.event_store)
        logger.info("  - Projector 초기화 완료")
        
        # 2. Risk Guard
        self.risk_guard = RiskGuard(
            event_store=self.event_store,
            projector=self.projector,
            engine_mode_getter=self._get_engine_mode,
        )
        logger.info("  - RiskGuard 초기화 완료")
        
        # 3. Executor
        self.executor = CommandExecutor(
            rest_client=self.rest_client,
            event_store=self.event_store,
            engine_state_setter=self._set_engine_mode,
        )
        logger.info("  - CommandExecutor 초기화 완료")
        
        # 4. Command Processor
        self.command_processor = CommandProcessor(
            command_store=self.command_store,
            executor=self.executor,
            risk_guard=self.risk_guard,
        )
        logger.info("  - CommandProcessor 초기화 완료")
        
        # 5. WebSocket Listener
        if self.settings.mode.value == "testnet":
            ws_url = BinanceUrls.TESTNET_WS
        else:
            ws_url = BinanceUrls.PROD_WS
        
        self.ws_listener = WebSocketListener(
            ws_base_url=ws_url,
            rest_client=self.rest_client,
            event_store=self.event_store,
            scope=self.scope,
            target_symbol=self.target_symbol,
        )
        self.ws_listener.set_state_callback(self._on_ws_state_change)
        logger.info("  - WebSocketListener 초기화 완료")
        
        # 6. Reconciler
        self.reconciler = HybridReconciler(
            rest_client=self.rest_client,
            event_store=self.event_store,
            scope=self.scope,
            symbol=self.target_symbol,
            projection_getter=self.projector,
        )
        logger.info("  - HybridReconciler 초기화 완료")
        
        # 7. Strategy Runner
        self.strategy_runner = StrategyRunner(
            event_store=self.event_store,
            command_store=self.command_store,
            scope=scope_with_symbol,
            projector=self.projector,
            risk_guard=self.risk_guard,
            engine_mode_getter=self._get_engine_mode,
        )
        logger.info("  - StrategyRunner 초기화 완료")
        
        logger.info("Bot 컴포넌트 초기화 완료")
    
    async def _get_engine_mode(self) -> str:
        """엔진 모드 조회"""
        return self.state_machine.state
    
    async def _set_engine_mode(self, mode: str) -> None:
        """엔진 모드 설정"""
        try:
            self.state_machine.transition(mode)
            logger.info(f"Engine mode changed to {mode}")
        except Exception as e:
            logger.warning(f"Failed to change engine mode: {e}")
    
    async def _on_ws_state_change(self, new_state: WebSocketState) -> None:
        """WebSocket 상태 변경 콜백"""
        if self.reconciler:
            self.reconciler.set_ws_state(new_state)
    
    async def start(self) -> None:
        """엔진 시작"""
        # EngineStarted 이벤트
        started_event = self._create_engine_started_event()
        await self.event_store.append(started_event)
        logger.info("EngineStarted 이벤트 저장 완료")
        
        # 초기 상태 동기화
        if self.reconciler:
            await self.reconciler.full_reconcile()
        
        # 초기 Projection 적용
        if self.projector:
            await self.projector.apply_all_pending()
        
        # WebSocket 연결 시작
        if self.ws_listener:
            await self.ws_listener.start()
        
        # 엔진 상태 전환
        self.state_machine.transition(EngineState.RUNNING)
        logger.info("Bot Engine RUNNING")
    
    async def stop(self) -> None:
        """엔진 종료"""
        logger.info("Bot Engine 종료 중...")
        
        # 전략 종료
        if self.strategy_runner and self.strategy_runner.is_running:
            await self.strategy_runner.stop()
        
        # WebSocket 종료
        if self.ws_listener:
            await self.ws_listener.stop()
        
        # REST 클라이언트 종료
        await self.rest_client.close()
        
        # EngineStopped 이벤트
        stopped_event = self._create_engine_stopped_event()
        await self.event_store.append(stopped_event)
        logger.info("EngineStopped 이벤트 저장 완료")
    
    async def run_main_loop(self, shutdown_event: asyncio.Event) -> None:
        """메인 루프
        
        매 tick마다 다음을 수행:
        1. Projector: 새 이벤트 처리 → Projection 업데이트
        2. Command Processor: 대기 중인 Command 처리
        3. Reconciler: 주기적으로 거래소 상태 동기화
        4. Strategy Runner: 전략 tick 실행
        """
        logger.info("메인 루프 시작")
        
        while not shutdown_event.is_set():
            self._tick_count += 1
            
            try:
                # 1. Projector: 새 이벤트 → Projection 업데이트
                if self.projector:
                    await self.projector.apply_pending_events()
                
                # 2. Command Processor: 대기 Command 처리
                if self.command_processor:
                    await self.command_processor.process_batch(max_count=5)
                
                # 3. Reconciler: 주기적 동기화
                if self.reconciler:
                    await self.reconciler.tick()
                
                # 4. Strategy Runner: 전략 tick (주기적)
                now = asyncio.get_event_loop().time()
                if now - self._last_strategy_tick >= self.strategy_tick_interval:
                    self._last_strategy_tick = now
                    if self.strategy_runner and self.strategy_runner.is_running:
                        await self.strategy_runner.tick()
                
                # 5. Heartbeat 로그 (10초마다)
                if self._tick_count % 100 == 0:
                    self._log_heartbeat()
                    
            except Exception as e:
                logger.error(f"메인 루프 에러: {e}")
            
            await asyncio.sleep(self.tick_interval)
        
        logger.info("메인 루프 종료")
    
    def _log_heartbeat(self) -> None:
        """Heartbeat 로그"""
        stats = {
            "tick": self._tick_count,
            "engine_mode": self.state_machine.state,
            "ws_connected": self.ws_listener.is_connected if self.ws_listener else False,
        }
        
        if self.command_processor:
            pending = asyncio.get_event_loop().run_until_complete(
                self.command_processor.get_pending_count()
            ) if asyncio.get_event_loop().is_running() else 0
            stats["pending_commands"] = pending
        
        if self.strategy_runner:
            stats["strategy"] = self.strategy_runner.strategy.name if self.strategy_runner.strategy else None
        
        logger.debug(f"Heartbeat: {stats}")
    
    async def load_strategy(
        self,
        module_path: str,
        class_name: str,
        params: dict[str, Any] | None = None,
    ) -> bool:
        """전략 로드 및 시작
        
        Args:
            module_path: 모듈 경로 (예: strategies.examples.sma_cross)
            class_name: 클래스 이름 (예: SmaCrossStrategy)
            params: 전략 파라미터
            
        Returns:
            로드 성공 여부
        """
        if not self.strategy_runner:
            logger.error("StrategyRunner not initialized")
            return False
        
        success = await self.strategy_runner.load_strategy(
            module_path=module_path,
            class_name=class_name,
            params=params,
        )
        
        if success:
            await self.strategy_runner.start()
        
        return success
    
    def _create_engine_started_event(self) -> Event:
        """EngineStarted 이벤트 생성"""
        now = datetime.now(timezone.utc)
        event_id = str(uuid4())
        
        return Event(
            event_id=event_id,
            event_type="EngineStarted",
            ts=now,
            correlation_id=event_id,
            causation_id=None,
            command_id=None,
            source="BOT",
            entity_kind="ENGINE",
            entity_id="main",
            scope=self.scope,
            dedup_key=f"engine:started:{now.isoformat()}",
            payload={
                "version": "2.0.0",
                "mode": self.settings.mode.value,
                "target_symbol": self.target_symbol,
                "started_at": now.isoformat(),
            },
        )
    
    def _create_engine_stopped_event(self, reason: str = "graceful") -> Event:
        """EngineStopped 이벤트 생성"""
        now = datetime.now(timezone.utc)
        event_id = str(uuid4())
        
        return Event(
            event_id=event_id,
            event_type="EngineStopped",
            ts=now,
            correlation_id=event_id,
            causation_id=None,
            command_id=None,
            source="BOT",
            entity_kind="ENGINE",
            entity_id="main",
            scope=self.scope,
            dedup_key=f"engine:stopped:{now.isoformat()}",
            payload={
                "reason": reason,
                "tick_count": self._tick_count,
                "stopped_at": now.isoformat(),
            },
        )


async def main() -> None:
    """Bot 메인 함수"""
    logger.info("=" * 60)
    logger.info("AlphaEngine Bot v2.0.0 시작")
    logger.info("=" * 60)
    
    # 1. 설정 로드
    try:
        settings = get_settings()
    except Exception as e:
        logger.error(f"설정 로드 실패: {e}")
        sys.exit(1)
    
    logger.info(f"Mode: {settings.mode.value}")
    logger.info(f"DB: {settings.db_path}")
    
    # 2. DB 연결 및 스키마 초기화
    async with SQLiteAdapter(settings.db_path) as db:
        await init_schema(db)
        
        # 3. Bot 엔진 생성 및 초기화
        engine = BotEngine(settings, db)
        await engine.initialize()
        
        # 4. 전략 로드 (설정에서 가져오거나 기본 전략)
        # await engine.load_strategy(
        #     module_path="strategies.examples.sma_cross",
        #     class_name="SmaCrossStrategy",
        #     params={"fast_period": 5, "slow_period": 20, "quantity": "10"},
        # )
        
        # 5. 종료 이벤트 설정
        shutdown_event = asyncio.Event()
        
        logger.info("Bot 메인 루프 시작 (종료: Ctrl+C)")
        
        try:
            # 6. 엔진 시작
            await engine.start()
            
            # 7. 메인 루프 실행
            await engine.run_main_loop(shutdown_event)
            
        except asyncio.CancelledError:
            logger.info("메인 루프 취소됨")
        except KeyboardInterrupt:
            logger.info("Ctrl+C 감지")
        finally:
            # 8. 엔진 종료
            await engine.stop()
    
    logger.info("=" * 60)
    logger.info("AlphaEngine Bot 정상 종료")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
