"""
Strategy Context Builder

전략 실행을 위한 StrategyTickContext 구성
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from core.types import Scope
from strategies.base import (
    StrategyTickContext,
    Position,
    Balance,
    OpenOrder,
    Bar,
)

logger = logging.getLogger(__name__)


class ContextBuilder:
    """Context Builder
    
    Projection 및 설정에서 StrategyTickContext를 구성.
    
    Args:
        scope: 거래 범위
    """
    
    def __init__(self, scope: Scope):
        self.scope = scope
    
    async def build(
        self,
        projector: Any,
        market_data_provider: Any = None,
        engine_mode: str = "RUNNING",
        strategy_state: dict[str, Any] | None = None,
        risk_config: dict[str, Any] | None = None,
    ) -> StrategyTickContext:
        """컨텍스트 구성
        
        Args:
            projector: EventProjector 인스턴스
            market_data_provider: 시장 데이터 제공자 (선택)
            engine_mode: 엔진 모드
            strategy_state: 전략 상태 (유지됨)
            risk_config: 리스크/리워드 설정 (config_store의 "risk" 키)
            
        Returns:
            StrategyTickContext
        """
        now = datetime.now(timezone.utc)
        
        position = await self._get_position(projector)
        balances = await self._get_balances(projector)
        open_orders = await self._get_open_orders(projector)
        bars = await self._get_bars(market_data_provider)
        current_price = bars[-1].close if bars else None
        
        return StrategyTickContext(
            scope=self.scope,
            now=now,
            position=position,
            balances=balances,
            open_orders=open_orders,
            bars=bars,
            current_price=current_price,
            strategy_state=strategy_state or {},
            engine_mode=engine_mode,
            market_data=market_data_provider,
            risk_config=risk_config,
        )
    
    async def _get_position(self, projector: Any) -> Position | None:
        """포지션 조회"""
        if not projector or not self.scope.symbol:
            return None
        
        try:
            pos_data = await projector.get_position(
                exchange=self.scope.exchange,
                venue=self.scope.venue,
                account_id=self.scope.account_id,
                mode=self.scope.mode,
                symbol=self.scope.symbol,
            )
            
            if not pos_data:
                return None
            
            qty = Decimal(pos_data.get("qty", "0"))
            if qty == 0:
                return None
            
            return Position(
                symbol=pos_data.get("symbol", self.scope.symbol),
                side=pos_data.get("side"),
                qty=qty,
                entry_price=Decimal(pos_data.get("entry_price", "0")),
                unrealized_pnl=Decimal(pos_data.get("unrealized_pnl", "0")),
                leverage=int(pos_data.get("leverage", 1)),
                margin_type=pos_data.get("margin_type", "ISOLATED"),
            )
            
        except Exception as e:
            logger.warning(f"Failed to get position: {e}")
            return None
    
    async def _get_balances(self, projector: Any) -> dict[str, Balance]:
        """잔고 조회"""
        balances: dict[str, Balance] = {}
        
        if not projector:
            return balances
        
        try:
            balance_data = await projector.get_balance(
                exchange=self.scope.exchange,
                venue=self.scope.venue,
                account_id=self.scope.account_id,
                mode=self.scope.mode,
                asset="USDT",
            )
            
            if balance_data:
                balances["USDT"] = Balance(
                    asset="USDT",
                    free=Decimal(balance_data.get("free", "0")),
                    locked=Decimal(balance_data.get("locked", "0")),
                )
            
        except Exception as e:
            logger.warning(f"Failed to get balances: {e}")
        
        return balances
    
    async def _get_open_orders(self, projector: Any) -> list[OpenOrder]:
        """오픈 주문 조회"""
        if not projector:
            return []
        
        try:
            orders_data = await projector.get_open_orders(
                exchange=self.scope.exchange,
                venue=self.scope.venue,
                account_id=self.scope.account_id,
                mode=self.scope.mode,
                symbol=self.scope.symbol,
            )
            
            orders = []
            for od in orders_data:
                orders.append(OpenOrder(
                    exchange_order_id=od.get("exchange_order_id", ""),
                    client_order_id=od.get("client_order_id"),
                    symbol=od.get("symbol", ""),
                    side=od.get("side", ""),
                    order_type=od.get("order_type", ""),
                    original_qty=Decimal(od.get("original_qty", "0")),
                    executed_qty=Decimal(od.get("executed_qty", "0")),
                    price=Decimal(od["price"]) if od.get("price") else None,
                    stop_price=Decimal(od["stop_price"]) if od.get("stop_price") else None,
                    status=od.get("order_state", ""),
                ))
            
            return orders
            
        except Exception as e:
            logger.warning(f"Failed to get open orders: {e}")
            return []
    
    async def _get_bars(self, market_data_provider: Any) -> list[Bar]:
        """캔들 데이터 조회"""
        if not market_data_provider:
            return []
        
        try:
            bars_data = await market_data_provider.get_bars(
                symbol=self.scope.symbol,
                timeframe="5m",
                limit=100,
            )
            
            bars = []
            for bd in bars_data:
                ts = bd.get("ts")
                if isinstance(ts, str):
                    ts = datetime.fromisoformat(ts)
                
                bars.append(Bar(
                    ts=ts,
                    open=Decimal(str(bd.get("open", "0"))),
                    high=Decimal(str(bd.get("high", "0"))),
                    low=Decimal(str(bd.get("low", "0"))),
                    close=Decimal(str(bd.get("close", "0"))),
                    volume=Decimal(str(bd.get("volume", "0"))),
                ))
            
            return bars
            
        except Exception as e:
            logger.warning(f"Failed to get bars: {e}")
            return []
