"""
Order 관련 Command Handler

PlaceOrder, CancelOrder 등 주문 관련 Command 처리
"""

import logging
from typing import Any

from adapters.binance.rest_client import BinanceRestClient
from core.domain.commands import Command, CommandTypes
from core.domain.events import Event, EventTypes
from core.storage.event_store import EventStore
from core.types import Scope
from core.utils.dedup import make_order_dedup_key
from bot.executor.handlers.base import CommandHandler

logger = logging.getLogger(__name__)


class PlaceOrderHandler(CommandHandler):
    """PlaceOrder Command 핸들러
    
    거래소에 주문을 제출하고 결과 이벤트 생성.
    client_order_id = ae-{command_id} 규칙 사용.
    
    Args:
        rest_client: REST API 클라이언트
        event_store: 이벤트 저장소
    """
    
    def __init__(
        self,
        rest_client: BinanceRestClient,
        event_store: EventStore,
    ):
        self.rest_client = rest_client
        self.event_store = event_store
    
    @property
    def command_type(self) -> str:
        return CommandTypes.PLACE_ORDER
    
    async def execute(
        self,
        command: Command,
    ) -> tuple[bool, dict[str, Any], str | None, list[Event]]:
        """주문 제출
        
        payload:
            symbol: str
            side: str (BUY/SELL)
            order_type: str (LIMIT/MARKET/etc)
            quantity: str (Decimal string)
            price: str | None (LIMIT인 경우)
            time_in_force: str | None
            reduce_only: bool | None
            position_side: str | None
        """
        events: list[Event] = []
        
        try:
            payload = command.payload
            symbol = payload["symbol"]
            side = payload["side"]
            order_type = payload["order_type"]
            quantity = payload["quantity"]
            price = payload.get("price")
            time_in_force = payload.get("time_in_force", "GTC")
            reduce_only = payload.get("reduce_only", False)
            position_side = payload.get("position_side", "BOTH")
            
            client_order_id = command.client_order_id()
            
            # 거래소 API 호출
            order_result = await self.rest_client.place_order(
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price,
                time_in_force=time_in_force,
                reduce_only=reduce_only,
                position_side=position_side,
                client_order_id=client_order_id,
            )
            
            # 성공 이벤트 생성
            scope_with_symbol = Scope(
                exchange=command.scope.exchange,
                venue=command.scope.venue,
                account_id=command.scope.account_id,
                symbol=symbol,
                mode=command.scope.mode,
            )
            
            exchange_order_id = str(order_result.order_id)
            dedup_key = make_order_dedup_key(
                exchange=command.scope.exchange,
                venue=command.scope.venue,
                symbol=symbol,
                exchange_order_id=exchange_order_id,
            )
            
            event = Event.create(
                event_type=EventTypes.ORDER_PLACED,
                source="BOT",
                entity_kind="ORDER",
                entity_id=exchange_order_id,
                scope=scope_with_symbol,
                dedup_key=dedup_key,
                command_id=command.command_id,
                correlation_id=command.correlation_id,
                payload={
                    "exchange_order_id": exchange_order_id,
                    "client_order_id": client_order_id,
                    "symbol": symbol,
                    "side": side,
                    "order_type": order_type,
                    "original_qty": quantity,
                    "price": price,
                    "time_in_force": time_in_force,
                    "reduce_only": reduce_only,
                    "position_side": position_side,
                    "order_status": order_result.status,
                },
            )
            events.append(event)
            
            # 이벤트 저장
            await self.event_store.append(event)
            
            result = {
                "exchange_order_id": exchange_order_id,
                "client_order_id": client_order_id,
                "status": order_result.status,
            }
            
            logger.info(
                f"Order placed: {side} {quantity} {symbol}",
                extra={
                    "exchange_order_id": exchange_order_id,
                    "command_id": command.command_id,
                },
            )
            
            return True, result, None, events
            
        except Exception as e:
            error_msg = str(e)
            
            # 실패 이벤트 생성
            scope_with_symbol = Scope(
                exchange=command.scope.exchange,
                venue=command.scope.venue,
                account_id=command.scope.account_id,
                symbol=command.payload.get("symbol"),
                mode=command.scope.mode,
            )
            
            event = Event.create(
                event_type=EventTypes.ORDER_REJECTED,
                source="BOT",
                entity_kind="ORDER",
                entity_id=command.command_id,
                scope=scope_with_symbol,
                dedup_key=f"order:rejected:{command.command_id}",
                command_id=command.command_id,
                correlation_id=command.correlation_id,
                payload={
                    "command_id": command.command_id,
                    "error": error_msg,
                    "payload": command.payload,
                },
            )
            events.append(event)
            
            await self.event_store.append(event)
            
            logger.error(
                f"Order placement failed: {error_msg}",
                extra={"command_id": command.command_id},
            )
            
            return False, {}, error_msg, events


class CancelOrderHandler(CommandHandler):
    """CancelOrder Command 핸들러
    
    거래소에서 주문을 취소하고 결과 이벤트 생성.
    
    Args:
        rest_client: REST API 클라이언트
        event_store: 이벤트 저장소
    """
    
    def __init__(
        self,
        rest_client: BinanceRestClient,
        event_store: EventStore,
    ):
        self.rest_client = rest_client
        self.event_store = event_store
    
    @property
    def command_type(self) -> str:
        return CommandTypes.CANCEL_ORDER
    
    async def execute(
        self,
        command: Command,
    ) -> tuple[bool, dict[str, Any], str | None, list[Event]]:
        """주문 취소
        
        payload:
            symbol: str
            exchange_order_id: str | None
            client_order_id: str | None
        """
        events: list[Event] = []
        
        try:
            payload = command.payload
            symbol = payload["symbol"]
            exchange_order_id = payload.get("exchange_order_id")
            client_order_id = payload.get("client_order_id")
            
            if not exchange_order_id and not client_order_id:
                return False, {}, "Either exchange_order_id or client_order_id required", events
            
            # 거래소 API 호출
            cancel_result = await self.rest_client.cancel_order(
                symbol=symbol,
                order_id=int(exchange_order_id) if exchange_order_id else None,
                client_order_id=client_order_id,
            )
            
            # 성공 이벤트 생성
            scope_with_symbol = Scope(
                exchange=command.scope.exchange,
                venue=command.scope.venue,
                account_id=command.scope.account_id,
                symbol=symbol,
                mode=command.scope.mode,
            )
            
            canceled_order_id = str(cancel_result.order_id)
            dedup_key = f"{command.scope.exchange}:{command.scope.venue}:{symbol}:order:{canceled_order_id}:CANCELED"
            
            event = Event.create(
                event_type=EventTypes.ORDER_CANCELLED,
                source="BOT",
                entity_kind="ORDER",
                entity_id=canceled_order_id,
                scope=scope_with_symbol,
                dedup_key=dedup_key,
                command_id=command.command_id,
                correlation_id=command.correlation_id,
                payload={
                    "exchange_order_id": canceled_order_id,
                    "client_order_id": cancel_result.client_order_id,
                    "symbol": symbol,
                    "status": "CANCELED",
                },
            )
            events.append(event)
            
            await self.event_store.append(event)
            
            result = {
                "exchange_order_id": canceled_order_id,
                "status": "CANCELED",
            }
            
            logger.info(
                f"Order cancelled: {canceled_order_id}",
                extra={"command_id": command.command_id},
            )
            
            return True, result, None, events
            
        except Exception as e:
            error_msg = str(e)
            
            logger.error(
                f"Order cancellation failed: {error_msg}",
                extra={"command_id": command.command_id},
            )
            
            return False, {}, error_msg, events
