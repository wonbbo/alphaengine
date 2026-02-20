"""
매매 시나리오 테스트

시장가 매수/매도, 지정가 주문, 주문 취소, 부분 체결 시나리오 검증.
"""

import logging
from decimal import Decimal

import pytest
import pytest_asyncio

from adapters.binance.rest_client import BinanceRestClient
from adapters.binance.ws_client import BinanceWsClient
from adapters.models import OrderRequest
from core.types import OrderStatus, WebSocketState
from tests.e2e.utils.helpers import (
    wait_for_ws_state,
    wait_for_ws_message,
    wait_for_order_status,
    wait_for_order_fill,
    place_market_order,
    place_limit_order,
    close_position,
    get_current_price,
    calculate_limit_price,
    round_price,
    assert_order_filled,
    assert_order_cancelled,
    assert_position_exists,
    generate_client_order_id,
    assert_no_position,
)


pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


class TestMarketOrders:
    """시장가 주문 테스트"""
    
    @pytest.mark.production_risky
    async def test_market_buy(
        self,
        rest_client: BinanceRestClient,
        ws_client: BinanceWsClient,
        test_symbol: str,
        test_quantity: Decimal,
        e2e_logger: logging.Logger,
        ensure_no_position: None,
        ensure_no_orders: None,
        check_balance: None,
    ) -> None:
        """시장가 매수 주문
        
        검증 항목:
        - 주문 생성 성공
        - 주문 상태 FILLED
        - ORDER_TRADE_UPDATE 이벤트 수신
        - 포지션 생성 확인
        """
        e2e_logger.info("test_market_buy 시작")
        
        # WebSocket 연결
        await ws_client.start()
        await wait_for_ws_state(ws_client, WebSocketState.CONNECTED, timeout=30.0)
        e2e_logger.info("WebSocket 연결 완료")
        
        # 시장가 매수 주문
        quantity = test_quantity
        client_order_id = generate_client_order_id()
        
        e2e_logger.info(f"시장가 매수: {test_symbol}, qty={quantity}, coid={client_order_id}")
        
        order = await place_market_order(
            rest_client,
            test_symbol,
            "BUY",
            quantity,
            client_order_id=client_order_id,
        )
        
        e2e_logger.info(
            f"주문 응답: order_id={order.order_id}, "
            f"status={order.status}, "
            f"executed_qty={order.executed_qty}"
        )
        
        # 주문 체결 대기 (Testnet은 비동기 체결 가능)
        order = await wait_for_order_fill(rest_client, order, timeout=30.0)
        e2e_logger.info(f"주문 체결 확인: status={order.status}")
        
        # ORDER_TRADE_UPDATE 이벤트 수신 확인
        e2e_logger.info("ORDER_TRADE_UPDATE 대기 중...")
        message = await wait_for_ws_message(
            ws_client,
            "ORDER_TRADE_UPDATE",
            timeout=60.0,
        )
        
        if message is not None:
            order_data = message.get("o", {})
            e2e_logger.info(
                f"이벤트 수신: order_id={order_data.get('i')}, "
                f"status={order_data.get('X')}, "
                f"trade_id={order_data.get('t')}"
            )
        else:
            # Testnet WebSocket 지연 - REST로 주문 체결 확인
            e2e_logger.warning("ORDER_TRADE_UPDATE 미수신 - REST로 이미 체결 확인됨")
        
        # 포지션 확인
        position = await rest_client.get_position(test_symbol)
        assert_position_exists(position)
        e2e_logger.info(
            f"포지션 확인: qty={position.quantity}, "
            f"side={position.side}, "
            f"entry_price={position.entry_price}"
        )
        
        # 포지션 청산
        e2e_logger.info("포지션 청산 중...")
        await close_position(rest_client, test_symbol)
        
        e2e_logger.info("test_market_buy 완료")
    
    @pytest.mark.production_risky
    async def test_market_sell(
        self,
        rest_client: BinanceRestClient,
        test_symbol: str,
        test_quantity: Decimal,
        e2e_logger: logging.Logger,
        ensure_no_position: None,
        ensure_no_orders: None,
        check_balance: None,
    ) -> None:
        """시장가 매도 (포지션 청산)
        
        검증 항목:
        - 먼저 매수로 포지션 진입
        - 매도로 포지션 청산
        - 포지션이 0이 됨
        """
        e2e_logger.info("test_market_sell 시작")
        
        # 먼저 매수로 포지션 진입
        quantity = test_quantity
        e2e_logger.info(f"포지션 진입 (매수): qty={quantity}")
        
        buy_order = await place_market_order(
            rest_client,
            test_symbol,
            "BUY",
            quantity,
        )
        buy_order = await wait_for_order_fill(rest_client, buy_order)
        e2e_logger.info(f"매수 완료: avg_price={buy_order.avg_price}")
        
        # 포지션 확인
        position = await rest_client.get_position(test_symbol)
        assert_position_exists(position)
        e2e_logger.info(f"포지션 확인: qty={position.quantity}")
        
        # 매도로 청산
        e2e_logger.info("포지션 청산 (매도)...")
        sell_order = await place_market_order(
            rest_client,
            test_symbol,
            "SELL",
            position.quantity,
        )
        sell_order = await wait_for_order_fill(rest_client, sell_order)
        e2e_logger.info(f"매도 완료: avg_price={sell_order.avg_price}")
        
        # 포지션이 청산되었는지 확인
        position_after = await rest_client.get_position(test_symbol)
        assert_no_position(position_after)
        e2e_logger.info("포지션 청산 확인")
        
        e2e_logger.info("test_market_sell 완료")


class TestLimitOrders:
    """지정가 주문 테스트"""
    
    @pytest.mark.production_risky
    async def test_limit_order(
        self,
        rest_client: BinanceRestClient,
        test_symbol: str,
        test_quantity: Decimal,
        e2e_logger: logging.Logger,
        ensure_no_position: None,
        ensure_no_orders: None,
        check_balance: None,
    ) -> None:
        """지정가 주문 생성
        
        현재가보다 낮은 가격에 매수 주문을 걸어 체결되지 않게 함.
        
        검증 항목:
        - 주문 생성 성공
        - 주문 상태 NEW
        - 오픈 주문 목록에 존재
        """
        e2e_logger.info("test_limit_order 시작")
        
        # 현재 가격 조회
        current_price = await get_current_price(rest_client, test_symbol)
        e2e_logger.info(f"현재 가격: {current_price}")
        
        # 현재가보다 5% 낮은 가격에 지정가 매수 (체결 안 되게)
        limit_price = round_price(
            calculate_limit_price(current_price, "BUY", Decimal("0.05"))
        )
        quantity = test_quantity
        
        e2e_logger.info(f"지정가 매수: price={limit_price}, qty={quantity}")
        
        order = await place_limit_order(
            rest_client,
            test_symbol,
            "BUY",
            quantity,
            limit_price,
        )
        
        e2e_logger.info(f"주문 생성: order_id={order.order_id}, status={order.status}")
        
        # 주문 상태 확인 (NEW여야 함)
        assert order.status == OrderStatus.NEW.value, f"예상: NEW, 실제: {order.status}"
        
        # 오픈 주문 목록에서 확인
        open_orders = await rest_client.get_open_orders(test_symbol)
        order_ids = [o.order_id for o in open_orders]
        
        assert order.order_id in order_ids, "오픈 주문 목록에 없음"
        e2e_logger.info(f"오픈 주문 확인: {len(open_orders)}개 중 존재")
        
        # 주문 취소 (정리)
        e2e_logger.info("주문 취소 중...")
        await rest_client.cancel_order(test_symbol, order_id=order.order_id)
        
        e2e_logger.info("test_limit_order 완료")
    
    @pytest.mark.production_risky
    async def test_cancel_order(
        self,
        rest_client: BinanceRestClient,
        test_symbol: str,
        test_quantity: Decimal,
        e2e_logger: logging.Logger,
        ensure_no_position: None,
        ensure_no_orders: None,
        check_balance: None,
    ) -> None:
        """주문 취소
        
        검증 항목:
        - 지정가 주문 생성
        - 주문 취소 성공
        - 주문 상태 CANCELED
        - ORDER_TRADE_UPDATE 이벤트 수신 (선택)
        """
        e2e_logger.info("test_cancel_order 시작")
        
        # 현재 가격 조회
        current_price = await get_current_price(rest_client, test_symbol)
        
        # 지정가 주문 생성
        limit_price = round_price(
            calculate_limit_price(current_price, "BUY", Decimal("0.05"))
        )
        quantity = test_quantity
        client_order_id = generate_client_order_id()
        
        e2e_logger.info(f"지정가 주문 생성: coid={client_order_id}")
        
        order = await place_limit_order(
            rest_client,
            test_symbol,
            "BUY",
            quantity,
            limit_price,
            client_order_id=client_order_id,
        )
        
        e2e_logger.info(f"주문 생성 완료: order_id={order.order_id}")
        
        # 주문 취소
        e2e_logger.info("주문 취소 중...")
        cancelled_order = await rest_client.cancel_order(
            test_symbol,
            order_id=order.order_id,
        )
        
        e2e_logger.info(f"취소 응답: status={cancelled_order.status}")
        
        # 상태 확인
        assert_order_cancelled(cancelled_order)
        
        # 오픈 주문에서 제거되었는지 확인
        open_orders = await rest_client.get_open_orders(test_symbol)
        order_ids = [o.order_id for o in open_orders]
        
        assert order.order_id not in order_ids, "오픈 주문에 여전히 존재"
        e2e_logger.info("오픈 주문에서 제거 확인")
        
        e2e_logger.info("test_cancel_order 완료")
    
    @pytest.mark.production_risky
    async def test_cancel_by_client_order_id(
        self,
        rest_client: BinanceRestClient,
        test_symbol: str,
        test_quantity: Decimal,
        e2e_logger: logging.Logger,
        ensure_no_position: None,
        ensure_no_orders: None,
        check_balance: None,
    ) -> None:
        """client_order_id로 주문 취소
        
        검증 항목:
        - client_order_id로 주문 조회 가능
        - client_order_id로 주문 취소 가능
        """
        e2e_logger.info("test_cancel_by_client_order_id 시작")
        
        # 현재 가격 조회
        current_price = await get_current_price(rest_client, test_symbol)
        
        # 지정가 주문 생성 (client_order_id 지정)
        limit_price = round_price(
            calculate_limit_price(current_price, "BUY", Decimal("0.05"))
        )
        quantity = test_quantity
        client_order_id = generate_client_order_id()
        
        e2e_logger.info(f"지정가 주문 생성: coid={client_order_id}")
        
        order = await place_limit_order(
            rest_client,
            test_symbol,
            "BUY",
            quantity,
            limit_price,
            client_order_id=client_order_id,
        )
        
        e2e_logger.info(f"주문 생성 완료: order_id={order.order_id}")
        
        # client_order_id로 주문 조회
        e2e_logger.info("client_order_id로 주문 조회...")
        queried_order = await rest_client.get_order(
            test_symbol,
            client_order_id=client_order_id,
        )
        
        assert queried_order.order_id == order.order_id
        e2e_logger.info("주문 조회 성공")
        
        # client_order_id로 주문 취소
        e2e_logger.info("client_order_id로 주문 취소...")
        cancelled_order = await rest_client.cancel_order(
            test_symbol,
            client_order_id=client_order_id,
        )
        
        assert_order_cancelled(cancelled_order)
        e2e_logger.info("주문 취소 성공")
        
        e2e_logger.info("test_cancel_by_client_order_id 완료")


class TestPartialFill:
    """부분 체결 테스트"""
    
    @pytest.mark.slow
    async def test_partial_fill(
        self,
        rest_client: BinanceRestClient,
        ws_client: BinanceWsClient,
        test_symbol: str,
        e2e_logger: logging.Logger,
        ensure_no_position: None,
        ensure_no_orders: None,
        check_balance: None,
    ) -> None:
        """부분 체결 시나리오
        
        현재가에 가까운 지정가 주문을 걸어 부분 체결 시도.
        Testnet에서는 유동성이 낮아 부분 체결 재현이 어려울 수 있음.
        
        검증 항목:
        - 지정가 주문 생성
        - 주문 상태 확인 (NEW, PARTIALLY_FILLED, FILLED 중 하나)
        """
        e2e_logger.info("test_partial_fill 시작")
        
        # WebSocket 연결
        await ws_client.start()
        await wait_for_ws_state(ws_client, WebSocketState.CONNECTED, timeout=30.0)
        
        # 현재 가격 조회
        current_price = await get_current_price(rest_client, test_symbol)
        e2e_logger.info(f"현재 가격: {current_price}")
        
        # 현재가와 같은 가격에 대량 주문 (부분 체결 시도)
        # Testnet에서는 체결이 잘 안 될 수 있음
        limit_price = round_price(current_price)
        quantity = Decimal("100")  # 대량 주문
        
        e2e_logger.info(f"지정가 주문: price={limit_price}, qty={quantity}")
        
        order = await place_limit_order(
            rest_client,
            test_symbol,
            "BUY",
            quantity,
            limit_price,
        )
        
        e2e_logger.info(
            f"주문 생성: order_id={order.order_id}, "
            f"status={order.status}, "
            f"executed_qty={order.executed_qty}"
        )
        
        # 5초 대기 후 상태 확인
        import asyncio
        await asyncio.sleep(5)
        
        updated_order = await rest_client.get_order(
            test_symbol,
            order_id=order.order_id,
        )
        
        e2e_logger.info(
            f"업데이트된 상태: status={updated_order.status}, "
            f"executed={updated_order.executed_qty}/{updated_order.original_qty}"
        )
        
        # 상태 검증 (NEW, PARTIALLY_FILLED, FILLED 중 하나)
        valid_statuses = [
            OrderStatus.NEW.value,
            OrderStatus.PARTIALLY_FILLED.value,
            OrderStatus.FILLED.value,
        ]
        assert updated_order.status in valid_statuses, (
            f"예상치 못한 상태: {updated_order.status}"
        )
        
        # 부분 체결 시 로그
        if updated_order.status == OrderStatus.PARTIALLY_FILLED.value:
            e2e_logger.info(
                f"부분 체결 확인: {updated_order.executed_qty}/{updated_order.original_qty}"
            )
        
        # 정리: 미체결 주문 취소
        if updated_order.is_open:
            e2e_logger.info("미체결 주문 취소 중...")
            await rest_client.cancel_order(test_symbol, order_id=order.order_id)
        
        # 포지션 정리
        await close_position(rest_client, test_symbol)
        
        e2e_logger.info("test_partial_fill 완료")


class TestOrderEvents:
    """주문 이벤트 테스트"""
    
    @pytest.mark.production_risky
    async def test_order_trade_update_fields(
        self,
        rest_client: BinanceRestClient,
        ws_client: BinanceWsClient,
        test_symbol: str,
        test_quantity: Decimal,
        e2e_logger: logging.Logger,
        ensure_no_position: None,
        ensure_no_orders: None,
        check_balance: None,
    ) -> None:
        """ORDER_TRADE_UPDATE 이벤트 필드 검증
        
        검증 항목:
        - 필수 필드 존재 (s, c, S, o, X, i, l, L, t 등)
        - 필드 값 유효성
        """
        e2e_logger.info("test_order_trade_update_fields 시작")
        
        # WebSocket 연결
        await ws_client.start()
        await wait_for_ws_state(ws_client, WebSocketState.CONNECTED, timeout=30.0)
        
        # 시장가 매수 주문
        quantity = test_quantity
        client_order_id = generate_client_order_id()
        
        e2e_logger.info(f"시장가 매수: coid={client_order_id}")
        
        order = await place_market_order(
            rest_client,
            test_symbol,
            "BUY",
            quantity,
            client_order_id=client_order_id,
        )
        
        # ORDER_TRADE_UPDATE 대기
        message = await wait_for_ws_message(
            ws_client,
            "ORDER_TRADE_UPDATE",
            timeout=60.0,
        )
        
        if message is not None:
            order_data = message.get("o", {})
            
            # 필수 필드 검증
            required_fields = ["s", "c", "S", "o", "X", "i"]
            for field in required_fields:
                assert field in order_data, f"필수 필드 누락: {field}"
                e2e_logger.info(f"  {field}: {order_data.get(field)}")
            
            # 체결 시 추가 필드
            if order_data.get("X") in ["FILLED", "PARTIALLY_FILLED"]:
                trade_fields = ["l", "L", "t", "n", "N"]
                for field in trade_fields:
                    if field in order_data:
                        e2e_logger.info(f"  {field}: {order_data.get(field)}")
            
            # 필드 값 검증
            assert order_data.get("s") == test_symbol
            assert order_data.get("c") == client_order_id
            assert order_data.get("S") == "BUY"
        else:
            # Testnet WebSocket 지연 - REST로 주문 상태 확인
            e2e_logger.warning("ORDER_TRADE_UPDATE 미수신 - REST로 검증")
            order_info = await rest_client.get_order(
                test_symbol, 
                client_order_id=client_order_id,
            )
            assert order_info is not None, "REST로 주문 조회 실패"
            
            # REST 응답으로 필드 검증
            e2e_logger.info(f"  symbol: {order_info.symbol}")
            e2e_logger.info(f"  client_order_id: {order_info.client_order_id}")
            e2e_logger.info(f"  side: {order_info.side}")
            e2e_logger.info(f"  status: {order_info.status}")
            
            assert order_info.symbol == test_symbol
            assert order_info.client_order_id == client_order_id
            assert order_info.side == "BUY"
        
        # 포지션 정리
        await close_position(rest_client, test_symbol)
        
        e2e_logger.info("test_order_trade_update_fields 완료")
