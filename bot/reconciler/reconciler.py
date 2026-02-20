"""
Hybrid Reconciler

REST API로 주기적으로 거래소 상태를 조회하여 WebSocket 누락 보완.
WebSocket 연결 상태에 따라 폴링 간격 조절.
"""

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from adapters.binance.rest_client import BinanceRestClient
from adapters.models import Balance, Position, Order, Trade
from core.domain.events import Event, EventTypes
from core.storage.event_store import EventStore
from core.types import Scope, WebSocketState
from core.utils.dedup import make_trade_dedup_key, make_order_dedup_key
from bot.reconciler.drift import DriftDetector, DriftInfo

logger = logging.getLogger(__name__)


class HybridReconciler:
    """Hybrid Reconciler
    
    WebSocket + REST Polling 조합으로 이벤트 누락 방지.
    
    동작 방식:
    1. WebSocket CONNECTED 상태: 30초 간격 폴링 (정합 검증)
    2. WebSocket DISCONNECTED/RECONNECTING 상태: 5초 간격 폴링 (누락 복구)
    3. 거래소 상태와 Projection 비교하여 Drift 감지
    
    Args:
        rest_client: REST API 클라이언트
        event_store: 이벤트 저장소
        scope: 거래 범위
        symbol: 타겟 심볼
        projection_getter: Projection 조회 함수 (선택)
    """
    
    # 폴링 간격 상수
    NORMAL_INTERVAL = 30  # WebSocket 정상 시 (초)
    FALLBACK_INTERVAL = 5  # WebSocket 끊김 시 (초)
    
    def __init__(
        self,
        rest_client: BinanceRestClient,
        event_store: EventStore,
        scope: Scope,
        symbol: str,
        projection_getter: Any = None,
    ):
        self.rest_client = rest_client
        self.event_store = event_store
        self.scope = scope
        self.symbol = symbol
        self.projection_getter = projection_getter
        
        self.drift_detector = DriftDetector(scope)
        
        # WebSocket 상태 (외부에서 설정)
        self._ws_state = WebSocketState.DISCONNECTED
        
        # 마지막 Reconcile 시간
        self._last_reconcile_time: float = 0
        
        # 마지막으로 조회한 체결 시간 (밀리초)
        self._last_trade_time: int = 0
        
        # 통계
        self._reconcile_count = 0
        self._drift_count = 0
        self._event_count = 0
    
    @property
    def poll_interval(self) -> int:
        """현재 폴링 간격"""
        if self._ws_state == WebSocketState.CONNECTED:
            return self.NORMAL_INTERVAL
        return self.FALLBACK_INTERVAL
    
    def set_ws_state(self, state: WebSocketState) -> None:
        """WebSocket 상태 설정
        
        Args:
            state: 현재 WebSocket 상태
        """
        old_state = self._ws_state
        self._ws_state = state
        
        if old_state != state:
            logger.info(
                f"Reconciler: WebSocket 상태 변경 {old_state.value} → {state.value}",
                extra={"poll_interval": self.poll_interval},
            )
    
    async def tick(self) -> int:
        """Reconcile tick (주기적 호출)
        
        Returns:
            생성된 이벤트 수
        """
        now = asyncio.get_event_loop().time()
        
        # 간격 체크
        if now - self._last_reconcile_time < self.poll_interval:
            return 0
        
        self._last_reconcile_time = now
        self._reconcile_count += 1
        
        logger.debug(f"Reconcile tick #{self._reconcile_count}")
        
        event_count = 0
        
        try:
            # 1. 누락된 체결 복구
            event_count += await self._reconcile_trades()
            
            # 2. 포지션 정합 검사 (Projection이 있는 경우)
            if self.projection_getter:
                event_count += await self._check_position_drift()
                event_count += await self._check_balance_drift()
            
        except Exception as e:
            logger.error(
                "Reconcile tick 에러",
                extra={"error": str(e)},
            )
        
        return event_count
    
    async def full_reconcile(self) -> int:
        """전체 정합 검사 (시작 시 호출)
        
        Returns:
            생성된 이벤트 수
        """
        logger.info("Full reconcile 시작")
        
        event_count = 0
        
        try:
            # 1. 체결 이력 동기화
            event_count += await self._sync_trades()
            
            # 2. 오픈 주문 동기화
            event_count += await self._sync_open_orders()
            
            # 3. 포지션 동기화
            event_count += await self._sync_position()
            
            # 4. 잔고 동기화
            event_count += await self._sync_balances()
            
        except Exception as e:
            logger.error(
                "Full reconcile 에러",
                extra={"error": str(e)},
            )
        
        logger.info(f"Full reconcile 완료: {event_count} events")
        return event_count
    
    async def _reconcile_trades(self) -> int:
        """누락된 체결 복구
        
        Returns:
            생성된 이벤트 수
        """
        try:
            # 마지막 체결 시간 이후의 체결 조회
            trades = await self.rest_client.get_trades(
                symbol=self.symbol,
                limit=100,
                start_time=self._last_trade_time + 1 if self._last_trade_time else None,
            )
            
            if not trades:
                return 0
            
            event_count = 0
            
            for trade in trades:
                event = self._create_trade_event(trade)
                saved = await self.event_store.append(event)
                
                if saved:
                    event_count += 1
                    self._event_count += 1
                    logger.debug(
                        f"Reconciled trade: {trade.trade_id}",
                        extra={"source": "REST"},
                    )
                
                # 마지막 체결 시간 업데이트
                if trade.trade_time > self._last_trade_time:
                    self._last_trade_time = trade.trade_time
            
            return event_count
            
        except Exception as e:
            logger.error(f"Trade reconcile 에러: {e}")
            return 0
    
    async def _sync_trades(self) -> int:
        """체결 이력 동기화 (초기화 시)"""
        try:
            trades = await self.rest_client.get_trades(
                symbol=self.symbol,
                limit=500,
            )
            
            event_count = 0
            
            for trade in trades:
                event = self._create_trade_event(trade)
                saved = await self.event_store.append(event)
                
                if saved:
                    event_count += 1
                
                if trade.trade_time > self._last_trade_time:
                    self._last_trade_time = trade.trade_time
            
            logger.info(f"Synced {event_count} trades from history")
            return event_count
            
        except Exception as e:
            logger.error(f"Trade sync 에러: {e}")
            return 0
    
    async def _sync_open_orders(self) -> int:
        """오픈 주문 동기화"""
        try:
            orders = await self.rest_client.get_open_orders(symbol=self.symbol)
            
            event_count = 0
            
            for order in orders:
                event = self._create_order_event(order)
                saved = await self.event_store.append(event)
                
                if saved:
                    event_count += 1
            
            logger.info(f"Synced {len(orders)} open orders, {event_count} new events")
            return event_count
            
        except Exception as e:
            logger.error(f"Order sync 에러: {e}")
            return 0
    
    async def _sync_position(self) -> int:
        """포지션 동기화"""
        try:
            position = await self.rest_client.get_position(symbol=self.symbol)
            
            if position:
                event = self._create_position_event(position)
                saved = await self.event_store.append(event)
                
                if saved:
                    logger.info(
                        f"Synced position: {position.side} {position.qty}",
                        extra={"symbol": self.symbol},
                    )
                    return 1
            
            return 0
            
        except Exception as e:
            logger.error(f"Position sync 에러: {e}")
            return 0
    
    async def _sync_balances(self) -> int:
        """잔고 동기화"""
        try:
            balances = await self.rest_client.get_balances()
            
            event_count = 0
            
            for balance in balances:
                event = self._create_balance_event(balance)
                saved = await self.event_store.append(event)
                
                if saved:
                    event_count += 1
            
            logger.info(f"Synced {len(balances)} balances, {event_count} new events")
            return event_count
            
        except Exception as e:
            logger.error(f"Balance sync 에러: {e}")
            return 0
    
    async def _check_position_drift(self) -> int:
        """포지션 drift 검사"""
        if not self.projection_getter:
            return 0
        
        try:
            # 거래소 포지션 조회
            exchange_position = await self.rest_client.get_position(symbol=self.symbol)
            
            # Projection 포지션 조회
            projection_position = await self.projection_getter.get_position(
                self.scope, self.symbol
            )
            
            # Drift 감지
            drift = self.drift_detector.detect_position_drift(
                exchange_position, projection_position, self.symbol
            )
            
            if drift:
                self._drift_count += 1
                event = self.drift_detector.create_drift_event(drift)
                saved = await self.event_store.append(event)
                
                if saved:
                    logger.warning(
                        f"Position drift detected: {drift.description}",
                    )
                    return 1
            
            return 0
            
        except Exception as e:
            logger.error(f"Position drift check 에러: {e}")
            return 0
    
    async def _check_balance_drift(self) -> int:
        """잔고 drift 검사"""
        if not self.projection_getter:
            return 0
        
        try:
            # 거래소 잔고 조회 (USDT만)
            balances = await self.rest_client.get_balances()
            usdt_balance = next((b for b in balances if b.asset == "USDT"), None)
            
            if not usdt_balance:
                return 0
            
            # Projection 잔고 조회
            projection_balance = await self.projection_getter.get_balance(
                self.scope, "USDT"
            )
            
            # Drift 감지
            drift = self.drift_detector.detect_balance_drift(
                usdt_balance, projection_balance
            )
            
            if drift:
                self._drift_count += 1
                event = self.drift_detector.create_drift_event(drift)
                saved = await self.event_store.append(event)
                
                if saved:
                    logger.warning(
                        f"Balance drift detected: {drift.description}",
                    )
                    return 1
            
            return 0
            
        except Exception as e:
            logger.error(f"Balance drift check 에러: {e}")
            return 0
    
    def _create_trade_event(self, trade: Trade) -> Event:
        """Trade → TradeExecuted 이벤트"""
        scope_with_symbol = Scope(
            exchange=self.scope.exchange,
            venue=self.scope.venue,
            account_id=self.scope.account_id,
            symbol=trade.symbol,
            mode=self.scope.mode,
        )
        
        dedup_key = make_trade_dedup_key(
            exchange=self.scope.exchange,
            venue=self.scope.venue,
            symbol=trade.symbol,
            exchange_trade_id=str(trade.trade_id),
        )
        
        return Event.create(
            event_type=EventTypes.TRADE_EXECUTED,
            source="REST",
            entity_kind="TRADE",
            entity_id=str(trade.trade_id),
            scope=scope_with_symbol,
            dedup_key=dedup_key,
            payload={
                "exchange_trade_id": str(trade.trade_id),
                "exchange_order_id": str(trade.order_id),
                "symbol": trade.symbol,
                "side": trade.side,
                "qty": str(trade.qty),
                "price": str(trade.price),
                "commission": str(trade.commission),
                "commission_asset": trade.commission_asset,
                "realized_pnl": str(trade.realized_pnl),
                "trade_time": trade.trade_time,
                "is_maker": trade.is_maker,
            },
        )
    
    def _create_order_event(self, order: Order) -> Event:
        """Order → OrderUpdated 이벤트"""
        scope_with_symbol = Scope(
            exchange=self.scope.exchange,
            venue=self.scope.venue,
            account_id=self.scope.account_id,
            symbol=order.symbol,
            mode=self.scope.mode,
        )
        
        # REST 조회는 현재 상태 스냅샷이므로 상태+시간으로 고유화
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        dedup_key = f"{self.scope.exchange}:{self.scope.venue}:{order.symbol}:order:{order.order_id}:{order.status}:{now_ms}"
        
        return Event.create(
            event_type=EventTypes.ORDER_UPDATED,
            source="REST",
            entity_kind="ORDER",
            entity_id=str(order.order_id),
            scope=scope_with_symbol,
            dedup_key=dedup_key,
            payload={
                "exchange_order_id": str(order.order_id),
                "client_order_id": order.client_order_id,
                "symbol": order.symbol,
                "side": order.side,
                "order_type": order.order_type,
                "order_status": order.status,
                "original_qty": str(order.original_qty),
                "executed_qty": str(order.executed_qty),
                "price": str(order.price) if order.price else None,
                "avg_price": str(order.avg_price) if order.avg_price else None,
                "stop_price": str(order.stop_price) if order.stop_price else None,
            },
        )
    
    def _create_position_event(self, position: Position) -> Event:
        """Position → PositionChanged 이벤트"""
        scope_with_symbol = Scope(
            exchange=self.scope.exchange,
            venue=self.scope.venue,
            account_id=self.scope.account_id,
            symbol=position.symbol,
            mode=self.scope.mode,
        )
        
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        dedup_key = f"{self.scope.exchange}:{self.scope.venue}:{position.symbol}:position:{now_ms}"
        
        return Event.create(
            event_type=EventTypes.POSITION_CHANGED,
            source="REST",
            entity_kind="POSITION",
            entity_id=position.symbol,
            scope=scope_with_symbol,
            dedup_key=dedup_key,
            payload={
                "symbol": position.symbol,
                "side": position.side,
                "position_amount": str(position.qty),
                "entry_price": str(position.entry_price),
                "unrealized_pnl": str(position.unrealized_pnl),
                "leverage": position.leverage,
                "margin_type": position.margin_type,
            },
        )
    
    def _create_balance_event(self, balance: Balance) -> Event:
        """Balance → BalanceChanged 이벤트"""
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        dedup_key = f"{self.scope.exchange}:{self.scope.venue}:{balance.asset}:balance:{now_ms}"
        
        return Event.create(
            event_type=EventTypes.BALANCE_CHANGED,
            source="REST",
            entity_kind="BALANCE",
            entity_id=balance.asset,
            scope=self.scope,
            dedup_key=dedup_key,
            payload={
                "asset": balance.asset,
                "wallet_balance": str(balance.total),
                "available_balance": str(balance.free),
                "cross_wallet_balance": str(balance.free),
            },
        )
    
    def get_stats(self) -> dict[str, Any]:
        """통계 반환"""
        return {
            "reconcile_count": self._reconcile_count,
            "drift_count": self._drift_count,
            "event_count": self._event_count,
            "ws_state": self._ws_state.value,
            "poll_interval": self.poll_interval,
            "last_trade_time": self._last_trade_time,
        }
