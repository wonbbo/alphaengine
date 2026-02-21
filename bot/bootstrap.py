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
from core.constants import BinanceEndpoints, Defaults
from core.domain.events import Event
from core.domain.state_machines import EngineStateMachine, EngineState
from core.storage.command_store import CommandStore
from core.storage.event_store import EventStore
from core.storage.config_store import ConfigStore, init_default_configs
from core.types import Scope, WebSocketState

from bot.websocket.listener import WebSocketListener
from bot.reconciler.reconciler import HybridReconciler
from bot.command.processor import CommandProcessor
from bot.executor.executor import CommandExecutor
from bot.projector.projector import EventProjector
from bot.risk.guard import RiskGuard
from bot.strategy.runner import StrategyRunner
from bot.market_data.provider import MarketDataProvider
from bot.transfer.manager import TransferManager
from bot.bnb_fee.manager import BnbFeeManager
from adapters.slack.notifier import SlackNotifier
from adapters.upbit.rest_client import UpbitRestClient
from core.constants import Paths

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
        self.config_store = ConfigStore(db)
        
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
        self.market_data_provider: MarketDataProvider | None = None
        self.notifier: SlackNotifier | None = None
        self.transfer_manager: TransferManager | None = None
        self.upbit_client: UpbitRestClient | None = None
        self.bnb_fee_manager: BnbFeeManager | None = None
        
        # 전략 설정 (런타임에 config_store에서 로드)
        self.strategy_config: dict[str, Any] = {}
        
        # 설정
        self.target_symbol = settings.target_symbol if hasattr(settings, 'target_symbol') else "XRPUSDT"
        self.tick_interval = 0.1  # 100ms
        self.strategy_tick_interval = 5.0  # 5초 (5분봉 기준)
        
        # 통계
        self._tick_count = 0
        self._last_strategy_tick = 0.0
        self._started_at: str | None = None  # Bot 시작 시간 (ISO 형식)
    
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
            base_url = BinanceEndpoints.TEST_REST_URL
        else:
            base_url = BinanceEndpoints.PROD_REST_URL
        
        return BinanceRestClient(
            base_url=base_url,
            api_key=self.settings.api_key,
            api_secret=self.settings.api_secret,
        )
    
    async def _load_strategy_config_from_store(self) -> dict[str, Any]:
        """전략 설정 로드 (config_store 우선)
        
        Returns:
            전략 설정 딕셔너리:
            - module: 전략 모듈 경로
            - class: 전략 클래스명
            - params: 전략 파라미터
            - auto_start: 자동 시작 여부
        """
        if not self.config_store:
            logger.warning("ConfigStore가 없어 빈 전략 설정 반환")
            return {
                "name": None,
                "module": None,
                "class": None,
                "params": {},
                "auto_start": False,
            }
        
        strategy_config = await self.config_store.get("strategy")
        logger.info(f"전략 설정 로드: {strategy_config}")
        return strategy_config
    
    def _create_notifier(self) -> SlackNotifier | None:
        """Slack Notifier 생성 (설정이 있는 경우에만)"""
        import yaml
        
        try:
            if not Paths.SECRETS_FILE.exists():
                return None
            
            with open(Paths.SECRETS_FILE, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            
            slack_config = data.get("slack", {})
            webhook_url = slack_config.get("webhook_url", "")
            
            if not webhook_url:
                logger.info("Slack webhook_url이 설정되지 않아 알림 비활성화")
                return None
            
            channel = slack_config.get("channel", "")
            
            notifier = SlackNotifier(
                webhook_url=webhook_url,
                channel=channel if channel else None,
                timeout=10.0,
            )
            
            logger.info(f"SlackNotifier 생성 완료 (channel: {channel or 'default'})")
            return notifier
            
        except Exception as e:
            logger.warning(f"SlackNotifier 생성 실패: {e}")
            return None
    
    def _load_transfer_config(self) -> dict[str, Any]:
        """입출금 설정 로드 (secrets.yaml의 upbit, binance 섹션)
        
        Returns:
            입출금 설정 딕셔너리:
            - upbit_api_key, upbit_api_secret, upbit_trx_address
            - binance_trx_address
        """
        import yaml
        
        config: dict[str, Any] = {
            "upbit_api_key": "",
            "upbit_api_secret": "",
            "upbit_trx_address": "",
            "binance_trx_address": "",
        }
        
        try:
            if not Paths.SECRETS_FILE.exists():
                return config
            
            with open(Paths.SECRETS_FILE, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            
            # Upbit 설정
            upbit_config = data.get("upbit", {})
            config["upbit_api_key"] = upbit_config.get("api_key", "")
            config["upbit_api_secret"] = upbit_config.get("api_secret", "")
            config["upbit_trx_address"] = upbit_config.get("trx_deposit_address", "")
            
            # Binance TRX 주소
            binance_config = data.get("binance", {})
            config["binance_trx_address"] = binance_config.get("trx_deposit_address", "")
            
        except Exception as e:
            logger.warning(f"입출금 설정 로드 실패: {e}")
        
        return config
    
    async def _init_transfer_manager(self) -> TransferManager | None:
        """TransferManager 초기화 (Upbit/Binance 설정이 있는 경우에만)
        
        Returns:
            TransferManager 인스턴스 또는 None
        """
        config = self._load_transfer_config()
        
        # 필수 설정 확인
        if not config["upbit_api_key"] or not config["upbit_api_secret"]:
            logger.info("Upbit API 설정이 없어 입출금 기능 비활성화")
            return None
        
        if not config["upbit_trx_address"]:
            logger.info("Upbit TRX 주소가 없어 입출금 기능 비활성화")
            return None
        
        if not config["binance_trx_address"]:
            logger.info("Binance TRX 주소가 없어 입출금 기능 비활성화")
            return None
        
        try:
            # Upbit 클라이언트 생성
            self.upbit_client = UpbitRestClient(
                api_key=config["upbit_api_key"],
                api_secret=config["upbit_api_secret"],
            )
            
            # TransferManager 생성
            transfer_manager = TransferManager(
                db=self.db,
                upbit=self.upbit_client,
                binance=self.rest_client,
                event_store=self.event_store,
                scope=self.scope,
                binance_trx_address=config["binance_trx_address"],
                upbit_trx_address=config["upbit_trx_address"],
            )
            
            logger.info("TransferManager 초기화 완료")
            return transfer_manager
            
        except Exception as e:
            logger.warning(f"TransferManager 초기화 실패: {e}")
            return None
    
    async def initialize(self) -> None:
        """컴포넌트 초기화"""
        logger.info("Bot 컴포넌트 초기화 시작...")
        
        # 0. ConfigStore 기본값 초기화
        await self.config_store.ensure_defaults()
        logger.info("  - ConfigStore 기본값 확인 완료")
        
        scope_with_symbol = self._scope_with_symbol()
        
        # 1. Projector
        self.projector = EventProjector(self.db, self.event_store)
        await self.projector.initialize()
        logger.info("  - Projector 초기화 완료")
        
        # 2. Risk Guard (ConfigStore 연결)
        self.risk_guard = RiskGuard(
            event_store=self.event_store,
            projector=self.projector,
            config_getter=self.config_store.get_risk_config,
            engine_mode_getter=self._get_engine_mode,
        )
        logger.info("  - RiskGuard 초기화 완료 (ConfigStore 연결)")
        
        # 3. Executor
        self.executor = CommandExecutor(
            rest_client=self.rest_client,
            event_store=self.event_store,
            engine_state_setter=self._set_engine_mode,
            strategy_resume_callback=self._on_engine_resume,
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
            ws_url = BinanceEndpoints.TEST_WS_URL
        else:
            ws_url = BinanceEndpoints.PROD_WS_URL
        
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
        
        # 7. Market Data Provider
        self.market_data_provider = MarketDataProvider(
            rest_client=self.rest_client,
            default_timeframe="5m",
            default_limit=100,
            cache_ttl_seconds=60,
        )
        logger.info("  - MarketDataProvider 초기화 완료")
        
        # 8. Strategy Runner (ConfigStore 리스크 설정 + 상태 저장 연결)
        self.strategy_runner = StrategyRunner(
            event_store=self.event_store,
            command_store=self.command_store,
            scope=scope_with_symbol,
            projector=self.projector,
            risk_guard=self.risk_guard,
            market_data_provider=self.market_data_provider,
            engine_mode_getter=self._get_engine_mode,
            risk_config_getter=self.config_store.get_risk_config,
            config_store=self.config_store,
        )
        
        # 전략 상태 변경 시 즉시 config_store에 반영 (Web에서 조회 가능)
        self.strategy_runner.set_status_change_callback(self._on_strategy_status_change)
        
        logger.info("  - StrategyRunner 초기화 완료 (ConfigStore 연결, 상태 저장 활성화)")
        
        # 9. WebSocket ↔ StrategyRunner 이벤트 콜백 연결
        # 체결/주문 이벤트 발생 시 전략의 on_trade/on_order_update 즉시 호출
        self.ws_listener.set_trade_callback(self.strategy_runner.handle_trade_event)
        self.ws_listener.set_order_callback(self.strategy_runner.handle_order_event)
        logger.info("  - WebSocket 이벤트 콜백 연결 완료")
        
        # 10. Slack Notifier (선택)
        self.notifier = self._create_notifier()
        if self.notifier:
            logger.info("  - SlackNotifier 초기화 완료")
        
        # 11. TransferManager (입출금, 설정이 있는 경우에만)
        self.transfer_manager = await self._init_transfer_manager()
        if self.transfer_manager:
            logger.info("  - TransferManager 초기화 완료")
            # Web에서 사용할 수 있도록 등록
            from web.dependencies import set_transfer_manager
            set_transfer_manager(self.transfer_manager)
            logger.info("  - TransferManager Web 의존성 등록 완료")
        
        # 12. BnbFeeManager (production 모드에서만 활성화)
        self.bnb_fee_manager = await self._init_bnb_fee_manager()
        if self.bnb_fee_manager:
            logger.info("  - BnbFeeManager 초기화 완료")
        
        logger.info("Bot 컴포넌트 초기화 완료")
    
    async def _init_bnb_fee_manager(self) -> BnbFeeManager | None:
        """BnbFeeManager 초기화 (production 모드에서만 활성화)
        
        Testnet은 Spot API가 제한적이므로 production에서만 동작.
        
        Returns:
            BnbFeeManager 인스턴스 또는 None
        """
        # Testnet에서는 비활성화 (Spot API 제한)
        if self.settings.mode.value == "testnet":
            logger.info("Testnet 모드: BNB 자동 충전 비활성화 (Spot API 제한)")
            return None
        
        try:
            bnb_fee_manager = BnbFeeManager(
                binance=self.rest_client,
                config_store=self.config_store,
                event_store=self.event_store,
                scope=self.scope,
                notifier_callback=self._send_notification,
            )
            
            logger.info("BnbFeeManager 초기화 완료 (production 모드)")
            return bnb_fee_manager
            
        except Exception as e:
            logger.warning(f"BnbFeeManager 초기화 실패: {e}")
            return None
    
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
    
    async def _on_engine_resume(self) -> bool:
        """엔진 재개 시 전략 시작 콜백
        
        엔진이 RUNNING으로 재개될 때 호출됨.
        - 전략이 없으면: config_store에서 설정 읽어 로드 + 시작
        - 전략이 있으면: 대기 상태라면 시작
        
        주의: auto_start는 Bot 최초 시작 시에만 사용.
              엔진 재개 시에는 무조건 운용 상태로 전환.
        
        Returns:
            전략 시작 여부
        """
        if not self.strategy_runner:
            return False
        
        # 전략이 이미 실행 중이면 건너뜀
        if self.strategy_runner.is_running:
            logger.debug("전략이 이미 실행 중")
            return False
        
        # 전략이 로드되어 있으면 시작만
        if self.strategy_runner.strategy:
            await self.strategy_runner.start()
            logger.info(f"전략 시작됨 (엔진 재개): {self.strategy_runner.strategy.name}")
            
            await self._send_notification(
                f"전략 시작됨 (엔진 재개): {self.strategy_runner.strategy.name}",
                level="INFO",
                extra={"symbol": self.target_symbol},
            )
            return True
        
        # 전략이 로드되어 있지 않은 경우 → 설정에서 로드 후 시작
        strategy_config = await self._load_strategy_config_from_store()
        module_path = strategy_config.get("module")
        class_name = strategy_config.get("class")
        params = strategy_config.get("params", {})
        
        if not module_path or not class_name:
            logger.debug("전략 설정 불완전 (module/class 없음), 전략 없이 엔진만 재개")
            return False
        
        # 전략 로드
        success = await self.strategy_runner.load_strategy(
            module_path=module_path,
            class_name=class_name,
            params=params,
        )
        
        if not success:
            logger.warning("전략 로드 실패")
            return False
        
        # 전략 시작
        await self.strategy_runner.start()
        strategy_name = self.strategy_runner.strategy.name if self.strategy_runner.strategy else "Unknown"
        logger.info(f"전략 로드 및 시작됨 (엔진 재개): {strategy_name}")
        
        await self._send_notification(
            f"전략 로드 및 시작됨 (엔진 재개): {strategy_name}",
            level="INFO",
            extra={"symbol": self.target_symbol, "params": params},
        )
        return True
    
    async def _on_ws_state_change(self, new_state: WebSocketState) -> None:
        """WebSocket 상태 변경 콜백"""
        if self.reconciler:
            self.reconciler.set_ws_state(new_state)
    
    async def _send_notification(
        self,
        message: str,
        level: str = "INFO",
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Slack 알림 전송 (notifier가 있는 경우에만)"""
        if self.notifier:
            try:
                await self.notifier.send(message, level=level, extra=extra)
            except Exception as e:
                logger.warning(f"Slack 알림 전송 실패: {e}")
    
    async def send_trade_notification(
        self,
        symbol: str,
        side: str,
        quantity: str,
        price: str,
        pnl: str | None = None,
    ) -> None:
        """거래 알림 전송 (외부에서 호출 가능)"""
        if self.notifier:
            try:
                await self.notifier.send_trade_alert(
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    price=price,
                    pnl=pnl,
                )
            except Exception as e:
                logger.warning(f"거래 알림 전송 실패: {e}")
    
    async def _load_and_start_strategy(self) -> None:
        """전략 자동 로드 및 시작
        
        config_store의 strategy 섹션에서 설정을 읽어 전략을 로드.
        
        전략 운용 조건:
        - name, module, class 필드가 모두 존재하고 유효한 값이어야 함
        - auto_start가 True여야 자동 시작 (False면 로드만)
        - 조건 미충족 시 전략 로드 건너뜀
        
        config_store strategy 예시:
        ```json
        {
            "name": "SMA Cross",
            "module": "strategies.examples.sma_cross",
            "class": "SmaCrossStrategy",
            "params": {"fast_period": 5, "slow_period": 20},
            "auto_start": true
        }
        ```
        """
        if not self.strategy_runner:
            logger.warning("StrategyRunner가 없어 전략 로드 건너뜀")
            return
        
        # config_store에서 전략 설정 로드
        self.strategy_config = await self._load_strategy_config_from_store()
        
        # 필수 필드 확인 (None, 빈 문자열, 미존재 모두 체크)
        strategy_name = self.strategy_config.get("name")
        module_path = self.strategy_config.get("module")
        class_name = self.strategy_config.get("class")
        
        # name, module, class 중 하나라도 없거나 null이면 전략 로드 안 함
        if not strategy_name or not module_path or not class_name:
            missing_fields = []
            if not strategy_name:
                missing_fields.append("name")
            if not module_path:
                missing_fields.append("module")
            if not class_name:
                missing_fields.append("class")
            
            logger.info(
                f"전략 설정 미완료로 전략 로드 건너뜀 "
                f"(미설정 필드: {', '.join(missing_fields)})"
            )
            return
        
        # auto_start 확인 (기본값: False)
        auto_start = self.strategy_config.get("auto_start", False)
        params = self.strategy_config.get("params", {})
        
        logger.info(f"전략 로드 시도: {strategy_name} ({module_path}.{class_name})")
        
        # 전략 로드
        success = await self.strategy_runner.load_strategy(
            module_path=module_path,
            class_name=class_name,
            params=params,
        )
        
        if not success:
            logger.error(f"전략 로드 실패: {strategy_name} ({module_path}.{class_name})")
            await self._send_notification(
                f"전략 로드 실패: {strategy_name}",
                level="ERROR",
            )
            return
        
        logger.info(f"전략 로드 성공: {strategy_name}")
        
        # auto_start가 True일 때만 자동 시작
        if auto_start:
            await self.strategy_runner.start()
            logger.info(f"전략 시작됨: {strategy_name}")
            
            await self._send_notification(
                f"전략 시작됨: {strategy_name} (params: {params})",
                level="INFO",
            )
        else:
            logger.info(f"전략 로드됨 (auto_start=False로 대기 상태): {strategy_name}")
    
    async def start(self) -> None:
        """엔진 시작"""
        # 시작 시간 기록
        self._started_at = datetime.now(timezone.utc).isoformat()
        
        # EngineStarted 이벤트
        started_event = self._create_engine_started_event()
        await self.event_store.append(started_event)
        logger.info("EngineStarted 이벤트 저장 완료")
        
        # Bot 상태 초기 저장
        if self.config_store:
            await self.config_store.update_bot_status(
                is_running=True,
                strategy_name=None,
                strategy_running=False,
                tick_count=0,
                started_at=self._started_at,
            )
        
        # 초기 상태 동기화
        if self.reconciler:
            await self.reconciler.full_reconcile()
        
        # 초기 Projection 적용
        if self.projector:
            await self.projector.apply_all_pending()
        
        # WebSocket 연결 시작
        if self.ws_listener:
            await self.ws_listener.start()
        
        # TransferManager 모니터링 시작
        if self.transfer_manager:
            await self.transfer_manager.start_monitoring()
            logger.info("TransferManager 모니터링 시작됨")
        
        # BnbFeeManager 초기 체크
        if self.bnb_fee_manager:
            try:
                await self.bnb_fee_manager.check_and_replenish()
                logger.info("BnbFeeManager 초기 체크 완료")
            except Exception as e:
                logger.warning(f"BnbFeeManager 초기 체크 실패: {e}")
        
        # 전략 자동 로드 및 시작
        await self._load_and_start_strategy()
        
        # 엔진 상태 전환
        self.state_machine.transition(EngineState.RUNNING)
        logger.info("Bot Engine RUNNING")
        
        # 시작 알림 전송
        await self._send_notification(
            f"Bot Engine 시작됨 (mode: {self.settings.mode.value}, symbol: {self.target_symbol})",
            level="INFO",
        )
    
    async def stop(self) -> None:
        """엔진 종료"""
        logger.info("Bot Engine 종료 중...")
        
        # 종료 알림 전송
        await self._send_notification(
            f"Bot Engine 종료됨 (mode: {self.settings.mode.value})",
            level="WARNING",
        )
        
        # 전략 종료
        if self.strategy_runner and self.strategy_runner.is_running:
            await self.strategy_runner.stop()
        
        # TransferManager 모니터링 종료
        if self.transfer_manager:
            await self.transfer_manager.stop_monitoring()
            logger.info("TransferManager 모니터링 종료됨")
        
        # Upbit 클라이언트 종료
        if self.upbit_client:
            await self.upbit_client.close()
        
        # WebSocket 종료
        if self.ws_listener:
            await self.ws_listener.stop()
        
        # REST 클라이언트 종료
        await self.rest_client.close()
        
        # EngineStopped 이벤트
        stopped_event = self._create_engine_stopped_event()
        await self.event_store.append(stopped_event)
        logger.info("EngineStopped 이벤트 저장 완료")
        
        # Bot 상태 초기화 (종료 표시)
        if self.config_store:
            await self.config_store.clear_bot_status()
    
    async def run_main_loop(self, shutdown_event: asyncio.Event) -> None:
        """메인 루프
        
        매 tick마다 다음을 수행:
        1. Projector: 새 이벤트 처리 → Projection 업데이트
        2. Command Processor: 대기 중인 Command 처리
        3. Reconciler: 주기적으로 거래소 상태 동기화
        4. Strategy Runner: 전략 tick 실행
        5. BnbFeeManager: BNB 비율 체크 및 자동 충전
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
                
                # 5. BnbFeeManager: BNB 비율 체크 및 자동 충전 (주기적)
                if self.bnb_fee_manager:
                    if await self.bnb_fee_manager.should_check():
                        await self.bnb_fee_manager.check_and_replenish()
                
                # 6. Heartbeat 로그 (10초마다)
                if self._tick_count % 100 == 0:
                    await self._log_heartbeat()
                    
            except Exception as e:
                logger.error(f"메인 루프 에러: {e}")
            
            await asyncio.sleep(self.tick_interval)
        
        logger.info("메인 루프 종료")
    
    async def _on_strategy_status_change(
        self,
        strategy_name: str | None,
        is_running: bool,
        action: str,
    ) -> None:
        """전략 상태 변경 콜백 (StrategyRunner에서 호출)
        
        전략 로드/시작/중지 시 즉시 config_store에 상태 저장.
        Web에서 실시간으로 전략 운용 상태를 확인할 수 있게 함.
        Slack 알림도 함께 전송.
        
        Args:
            strategy_name: 전략 이름 (없으면 None)
            is_running: 전략 실행 중 여부
            action: 액션 타입 ("loaded", "started", "stopped")
        """
        # config_store에 상태 저장
        if self.config_store:
            try:
                await self.config_store.update_bot_status(
                    is_running=True,  # Bot은 실행 중
                    strategy_name=strategy_name,
                    strategy_running=is_running,
                    tick_count=self._tick_count,
                    started_at=self._started_at,
                )
                logger.debug(f"전략 상태 변경 저장: {strategy_name}, action={action}, running={is_running}")
            except Exception as e:
                logger.warning(f"전략 상태 변경 저장 실패: {e}")
        
        # Slack 알림 전송 (액션 타입에 따라 메시지 구분)
        if strategy_name:
            extra_info = {"symbol": self.target_symbol, "mode": self.settings.mode.value}
            
            if action == "loaded":
                await self._send_notification(
                    f"전략 로드됨: {strategy_name}",
                    level="INFO",
                    extra=extra_info,
                )
            elif action == "started":
                await self._send_notification(
                    f"전략 시작됨: {strategy_name}",
                    level="INFO",
                    extra=extra_info,
                )
            elif action == "stopped":
                await self._send_notification(
                    f"전략 중지됨: {strategy_name}",
                    level="WARNING",
                    extra=extra_info,
                )
    
    async def _log_heartbeat(self) -> None:
        """Heartbeat 로그 및 상태 저장"""
        stats = {
            "tick": self._tick_count,
            "engine_mode": self.state_machine.state,
            "ws_connected": self.ws_listener.is_connected if self.ws_listener else False,
        }
        
        if self.command_processor:
            try:
                pending = await self.command_processor.get_pending_count()
                stats["pending_commands"] = pending
            except Exception:
                stats["pending_commands"] = 0
        
        # 전략 상태 수집
        strategy_name = None
        strategy_running = False
        if self.strategy_runner:
            strategy_name = self.strategy_runner.strategy.name if self.strategy_runner.strategy else None
            strategy_running = self.strategy_runner.is_running
            stats["strategy"] = strategy_name
        
        logger.debug(f"Heartbeat: {stats}")
        
        # config_store에 Bot 상태 저장 (Web에서 조회 가능)
        if self.config_store:
            try:
                await self.config_store.update_bot_status(
                    is_running=True,
                    strategy_name=strategy_name,
                    strategy_running=strategy_running,
                    tick_count=self._tick_count,
                    started_at=self._started_at,
                )
            except Exception as e:
                logger.warning(f"Bot 상태 저장 실패: {e}")
    
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
