"""
Strategy Runner

전략 로드, 실행, 상태 관리
"""

import importlib
import logging
from datetime import datetime, timezone
from typing import Any

from core.domain.events import Event, EventTypes
from core.storage.event_store import EventStore
from core.storage.command_store import CommandStore
from core.types import Scope
from strategies.base import Strategy, StrategyTickContext, TradeEvent, OrderEvent
from bot.strategy.context import ContextBuilder
from bot.strategy.emitter import CommandEmitterImpl

logger = logging.getLogger(__name__)


class StrategyRunner:
    """Strategy Runner
    
    전략을 로드하고 주기적으로 on_tick() 호출.
    전략 상태 관리 및 에러 핸들링.
    
    Args:
        event_store: 이벤트 저장소
        command_store: Command 저장소
        scope: 거래 범위
        projector: EventProjector (선택)
        risk_guard: RiskGuard (선택)
        market_data_provider: 시장 데이터 제공자 (선택)
        engine_mode_getter: 엔진 모드 조회 함수 (선택)
        
    사용 예시:
    ```python
    runner = StrategyRunner(
        event_store=event_store,
        command_store=command_store,
        scope=scope,
        projector=projector,
    )
    
    # 전략 로드
    await runner.load_strategy("strategies.examples.sma_cross", "SmaCrossStrategy")
    
    # 메인 루프에서 틱 호출
    while running:
        await runner.tick()
        await asyncio.sleep(interval)
    
    # 종료
    await runner.stop()
    ```
    """
    
    def __init__(
        self,
        event_store: EventStore,
        command_store: CommandStore,
        scope: Scope,
        projector: Any = None,
        risk_guard: Any = None,
        market_data_provider: Any = None,
        engine_mode_getter: Any = None,
        risk_config_getter: Any = None,
        config_store: Any = None,
    ):
        self.event_store = event_store
        self.command_store = command_store
        self.scope = scope
        self.projector = projector
        self.risk_guard = risk_guard
        self.market_data_provider = market_data_provider
        self.engine_mode_getter = engine_mode_getter
        self.risk_config_getter = risk_config_getter
        self.config_store = config_store
        
        # 전략 인스턴스
        self._strategy: Strategy | None = None
        
        # Context Builder
        self._context_builder = ContextBuilder(scope)
        
        # Command Emitter (전략 로드 후 생성)
        self._emitter: CommandEmitterImpl | None = None
        
        # 전략 상태 (on_tick 간 유지)
        self._strategy_state: dict[str, Any] = {}
        
        # 전략 파라미터
        self._strategy_params: dict[str, Any] = {}
        
        # 실행 상태
        self._is_running = False
        self._tick_count = 0
        self._error_count = 0
        self._last_tick_time: datetime | None = None
        
        # 이벤트 콜백 통계
        self._trade_event_count = 0
        self._order_event_count = 0
        
        # 상태 저장 추적 (마지막 저장된 거래 수)
        self._last_saved_trade_count = 0
        
        # 상태 변경 콜백 (BotEngine에서 등록하여 config_store에 즉시 반영)
        self._on_status_change_callback: Any = None
    
    def set_status_change_callback(self, callback: Any) -> None:
        """상태 변경 콜백 등록
        
        전략 시작/중지/로드 시 호출되는 콜백 함수.
        BotEngine에서 config_store.update_bot_status() 연결에 사용.
        
        Args:
            callback: async def callback(strategy_name: str | None, is_running: bool, action: str)
                - action: "loaded", "started", "stopped"
        """
        self._on_status_change_callback = callback
    
    async def _notify_status_change(self, action: str) -> None:
        """상태 변경 알림 (콜백 호출)
        
        Args:
            action: 액션 타입 ("loaded", "started", "stopped")
        """
        if self._on_status_change_callback:
            strategy_name = self._strategy.name if self._strategy else None
            try:
                await self._on_status_change_callback(strategy_name, self._is_running, action)
            except Exception as e:
                logger.warning(f"상태 변경 콜백 호출 실패: {e}")
    
    async def load_strategy(
        self,
        module_path: str,
        class_name: str,
        params: dict[str, Any] | None = None,
    ) -> bool:
        """전략 로드
        
        Args:
            module_path: 모듈 경로 (예: strategies.examples.sma_cross)
            class_name: 클래스 이름 (예: SmaCrossStrategy)
            params: 전략 파라미터 (default_params 오버라이드)
            
        Returns:
            로드 성공 여부
        """
        try:
            # 모듈 임포트
            module = importlib.import_module(module_path)
            
            # 클래스 가져오기
            strategy_class = getattr(module, class_name)
            
            # 인스턴스 생성
            self._strategy = strategy_class()
            
            # 파라미터 병합
            self._strategy_params = {
                **self._strategy.default_params,
                **(params or {}),
            }
            
            # Emitter 생성
            self._emitter = CommandEmitterImpl(
                command_store=self.command_store,
                scope=self.scope,
                strategy_name=self._strategy.name,
                risk_guard=self.risk_guard,
            )
            
            # 초기화 콜백
            await self._strategy.on_init(self._strategy_params)
            
            # 로드 이벤트 기록
            await self._record_strategy_event("loaded")
            
            # 상태 변경 즉시 알림 (전략 로드됨, 아직 실행 전)
            await self._notify_status_change("loaded")
            
            logger.info(
                f"Strategy loaded: {self._strategy.name} v{self._strategy.version}",
                extra={"params": self._strategy_params},
            )
            
            return True
            
        except Exception as e:
            logger.error(
                f"Failed to load strategy: {module_path}.{class_name}",
                extra={"error": str(e)},
            )
            return False
    
    async def load_strategy_instance(
        self,
        strategy: Strategy,
        params: dict[str, Any] | None = None,
    ) -> bool:
        """전략 인스턴스 직접 로드
        
        Args:
            strategy: Strategy 인스턴스
            params: 전략 파라미터
            
        Returns:
            로드 성공 여부
        """
        try:
            self._strategy = strategy
            
            self._strategy_params = {
                **strategy.default_params,
                **(params or {}),
            }
            
            self._emitter = CommandEmitterImpl(
                command_store=self.command_store,
                scope=self.scope,
                strategy_name=strategy.name,
                risk_guard=self.risk_guard,
            )
            
            await strategy.on_init(self._strategy_params)
            
            await self._record_strategy_event("loaded")
            
            # 상태 변경 즉시 알림 (전략 로드됨, 아직 실행 전)
            await self._notify_status_change("loaded")
            
            logger.info(
                f"Strategy loaded: {strategy.name} v{strategy.version}",
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to load strategy instance: {e}")
            return False
    
    async def start(self) -> None:
        """전략 실행 시작"""
        if not self._strategy:
            raise RuntimeError("No strategy loaded")
        
        if self._is_running:
            return
        
        self._is_running = True
        
        # DB에서 저장된 전략 상태 복원
        await self._restore_strategy_state()
        
        # 시작 컨텍스트 구성
        ctx = await self._build_context()
        
        # on_start 콜백
        await self._strategy.on_start(ctx)
        
        await self._record_strategy_event("started")
        
        # 상태 변경 즉시 알림 (Web에서 확인 가능)
        await self._notify_status_change("started")
        
        logger.info(f"Strategy started: {self._strategy.name}")
    
    async def stop(self) -> None:
        """전략 실행 종료"""
        if not self._strategy or not self._is_running:
            return
        
        self._is_running = False
        
        # 종료 컨텍스트 구성
        ctx = await self._build_context()
        
        # on_stop 콜백
        await self._strategy.on_stop(ctx)
        
        # 전략 상태 DB에 저장 (종료 시 반드시)
        await self._save_strategy_state()
        
        await self._record_strategy_event("stopped")
        
        # 상태 변경 즉시 알림 (Web에서 확인 가능)
        await self._notify_status_change("stopped")
        
        logger.info(f"Strategy stopped: {self._strategy.name}")
    
    async def tick(self) -> bool:
        """전략 틱 실행
        
        Returns:
            True: 정상 실행
            False: 에러 발생 또는 미실행
        """
        if not self._strategy or not self._is_running or not self._emitter:
            return False
        
        self._tick_count += 1
        self._last_tick_time = datetime.now(timezone.utc)
        
        try:
            # 컨텍스트 구성
            ctx = await self._build_context()
            
            # on_tick 호출
            await self._strategy.on_tick(ctx, self._emitter)
            
            return True
            
        except Exception as e:
            self._error_count += 1
            
            logger.error(
                f"Strategy tick error: {self._strategy.name}",
                extra={"error": str(e), "tick": self._tick_count},
            )
            
            # on_error 콜백
            try:
                ctx = await self._build_context()
                
                should_continue = await self._strategy.on_error(e, ctx)
                
                if not should_continue:
                    logger.warning(f"Strategy stopped due to error: {self._strategy.name}")
                    self._is_running = False
                    
            except Exception as inner_e:
                logger.error(f"Strategy on_error failed: {inner_e}")
            
            return False
    
    async def _get_engine_mode(self) -> str:
        """엔진 모드 조회"""
        if self.engine_mode_getter:
            try:
                return await self.engine_mode_getter()
            except Exception:
                pass
        return "RUNNING"
    
    async def _get_risk_config(self) -> dict[str, Any] | None:
        """리스크/리워드 설정 조회"""
        if self.risk_config_getter:
            try:
                return await self.risk_config_getter()
            except Exception:
                pass
        return None
    
    async def _build_context(self) -> StrategyTickContext:
        """표준 컨텍스트 구성 (중복 제거용)"""
        engine_mode = await self._get_engine_mode()
        risk_config = await self._get_risk_config()
        
        return await self._context_builder.build(
            projector=self.projector,
            market_data_provider=self.market_data_provider,
            engine_mode=engine_mode,
            strategy_state=self._strategy_state,
            risk_config=risk_config,
        )
    
    async def _record_strategy_event(self, action: str) -> None:
        """전략 이벤트 기록"""
        if not self._strategy:
            return
        
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        
        event = Event.create(
            event_type=EventTypes.STRATEGY_LOADED if action == "loaded" else EventTypes.ENGINE_MODE_CHANGED,
            source="BOT",
            entity_kind="STRATEGY",
            entity_id=self._strategy.name,
            scope=self.scope,
            dedup_key=f"strategy:{self._strategy.name}:{action}:{now_ms}",
            payload={
                "strategy_name": self._strategy.name,
                "strategy_version": self._strategy.version,
                "action": action,
                "params": self._strategy_params,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        
        await self.event_store.append(event)
    
    @property
    def strategy(self) -> Strategy | None:
        """현재 전략"""
        return self._strategy
    
    @property
    def is_running(self) -> bool:
        """실행 중 여부"""
        return self._is_running
    
    @property
    def strategy_state(self) -> dict[str, Any]:
        """전략 상태 (읽기 전용 복사본)"""
        return self._strategy_state.copy()
    
    def get_stats(self) -> dict[str, Any]:
        """통계 반환"""
        return {
            "strategy_name": self._strategy.name if self._strategy else None,
            "is_running": self._is_running,
            "tick_count": self._tick_count,
            "error_count": self._error_count,
            "trade_event_count": self._trade_event_count,
            "order_event_count": self._order_event_count,
            "last_tick_time": self._last_tick_time.isoformat() if self._last_tick_time else None,
        }
    
    def reset_stats(self) -> None:
        """통계 초기화"""
        self._tick_count = 0
        self._error_count = 0
        self._last_tick_time = None
        self._trade_event_count = 0
    
    # =========================================================================
    # 전략 상태 저장/복원 (Bot 재시작 시 유지)
    # =========================================================================
    
    async def _restore_strategy_state(self) -> None:
        """DB에서 저장된 전략 상태 복원
        
        Bot 재시작 시 호출되어 account_equity, trade_count 등을 복원.
        """
        if not self.config_store:
            logger.debug("ConfigStore not available, skipping state restore")
            return
        
        try:
            saved_state = await self.config_store.get_strategy_state()
            
            # 저장된 값이 있으면 strategy_state에 설정
            if saved_state:
                account_equity = saved_state.get("account_equity", "0")
                trade_count = saved_state.get("trade_count_since_reset", 0)
                total_count = saved_state.get("total_trade_count", 0)
                
                # "0"이 아닌 유효한 값이 있으면 복원
                if account_equity != "0":
                    self._strategy_state["account_equity"] = account_equity
                    self._strategy_state["trade_count_since_reset"] = trade_count
                    self._strategy_state["total_trade_count"] = total_count
                    self._last_saved_trade_count = total_count
                    
                    logger.info(
                        f"Restored strategy state: "
                        f"equity={account_equity}, "
                        f"trades_since_reset={trade_count}, "
                        f"total_trades={total_count}"
                    )
                    
        except Exception as e:
            logger.warning(f"Failed to restore strategy state: {e}")
    
    async def _save_strategy_state(self) -> None:
        """현재 전략 상태를 DB에 저장
        
        거래 종료 시 또는 종료 시 호출하여 상태 보존.
        """
        if not self.config_store:
            return
        
        try:
            account_equity = self._strategy_state.get("account_equity")
            trade_count = self._strategy_state.get("trade_count_since_reset", 0)
            total_count = self._strategy_state.get("total_trade_count", 0)
            
            if account_equity is not None:
                await self.config_store.save_strategy_state(
                    account_equity=str(account_equity),
                    trade_count_since_reset=trade_count,
                    total_trade_count=total_count,
                )
                self._last_saved_trade_count = total_count
                
                logger.debug(
                    f"Saved strategy state: "
                    f"equity={account_equity}, "
                    f"total_trades={total_count}"
                )
                
        except Exception as e:
            logger.warning(f"Failed to save strategy state: {e}")
    
    async def _maybe_save_strategy_state(self) -> None:
        """거래 수 변경 시 상태 저장 (매 거래 후)
        
        total_trade_count가 변경되었으면 저장.
        """
        total_count = self._strategy_state.get("total_trade_count", 0)
        
        if total_count != self._last_saved_trade_count:
            await self._save_strategy_state()
        self._order_event_count = 0
    
    # =========================================================================
    # 이벤트 기반 콜백 핸들러
    # 
    # WebSocket에서 실시간 이벤트 발생 시 BotEngine을 통해 호출됨.
    # 전략의 on_trade(), on_order_update() 콜백을 즉시 실행.
    # =========================================================================
    
    async def handle_trade_event(self, trade: TradeEvent) -> bool:
        """체결 이벤트 처리
        
        WebSocket ORDER_TRADE_UPDATE에서 체결 발생 시 호출.
        전략의 on_trade() 콜백을 즉시 실행.
        
        Args:
            trade: 체결 이벤트
            
        Returns:
            True: 정상 처리
            False: 에러 또는 미처리
        """
        if not self._strategy or not self._is_running or not self._emitter:
            return False
        
        # 심볼 필터링
        if trade.symbol != self.scope.symbol:
            return False
        
        self._trade_event_count += 1
        
        try:
            # 컨텍스트 구성 (실시간)
            ctx = await self._build_context()
            
            # on_trade 콜백 호출
            await self._strategy.on_trade(trade, ctx, self._emitter)
            
            logger.debug(
                f"Strategy on_trade executed",
                extra={
                    "strategy": self._strategy.name,
                    "trade_id": trade.trade_id,
                    "side": trade.side,
                    "qty": str(trade.quantity),
                    "price": str(trade.price),
                },
            )
            
            return True
            
        except Exception as e:
            self._error_count += 1
            
            logger.error(
                f"Strategy on_trade error: {self._strategy.name}",
                extra={"error": str(e), "trade_id": trade.trade_id},
            )
            
            # on_error 콜백
            try:
                ctx = await self._build_context()
                
                should_continue = await self._strategy.on_error(e, ctx)
                
                if not should_continue:
                    logger.warning(
                        f"Strategy stopped due to on_trade error: {self._strategy.name}"
                    )
                    self._is_running = False
                    
            except Exception as inner_e:
                logger.error(f"Strategy on_error failed: {inner_e}")
            
            return False
    
    async def handle_order_event(self, order: OrderEvent) -> bool:
        """주문 상태 변경 이벤트 처리
        
        WebSocket ORDER_TRADE_UPDATE에서 주문 상태 변경 시 호출.
        전략의 on_order_update() 콜백을 즉시 실행.
        
        Args:
            order: 주문 이벤트
            
        Returns:
            True: 정상 처리
            False: 에러 또는 미처리
        """
        if not self._strategy or not self._is_running or not self._emitter:
            return False
        
        # 심볼 필터링
        if order.symbol != self.scope.symbol:
            return False
        
        self._order_event_count += 1
        
        try:
            # 컨텍스트 구성 (실시간)
            ctx = await self._build_context()
            
            # on_order_update 콜백 호출
            await self._strategy.on_order_update(order, ctx, self._emitter)
            
            # 거래 수 변경 시 상태 저장 (손절/익절 체결 등)
            await self._maybe_save_strategy_state()
            
            logger.debug(
                f"Strategy on_order_update executed",
                extra={
                    "strategy": self._strategy.name,
                    "order_id": order.order_id,
                    "status": order.status,
                    "type": order.order_type,
                },
            )
            
            return True
            
        except Exception as e:
            self._error_count += 1
            
            logger.error(
                f"Strategy on_order_update error: {self._strategy.name}",
                extra={"error": str(e), "order_id": order.order_id},
            )
            
            # on_error 콜백
            try:
                ctx = await self._build_context()
                
                should_continue = await self._strategy.on_error(e, ctx)
                
                if not should_continue:
                    logger.warning(
                        f"Strategy stopped due to on_order_update error: {self._strategy.name}"
                    )
                    self._is_running = False
                    
            except Exception as inner_e:
                logger.error(f"Strategy on_error failed: {inner_e}")
            
            return False
