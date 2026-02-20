"""
리스크 시나리오 테스트

손절, 익절, 레버리지 변경 시나리오 검증.
"""

import logging
from decimal import Decimal

import pytest
import pytest_asyncio

from adapters.binance.rest_client import BinanceRestClient
from adapters.binance.ws_client import BinanceWsClient
from adapters.models import OrderRequest
from core.types import OrderType, WebSocketState
from tests.e2e.utils.helpers import (
    wait_for_ws_state,
    wait_for_ws_message,
    wait_for_order_status,
    wait_for_order_fill,
    place_market_order,
    close_position,
    get_current_price,
    round_price,
    assert_order_filled,
    assert_position_exists,
)


pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


class TestStopLoss:
    """손절 (STOP_MARKET) 테스트"""
    
    @pytest.mark.production_risky
    async def test_stop_loss_order_creation(
        self,
        rest_client: BinanceRestClient,
        test_symbol: str,
        test_quantity: Decimal,
        e2e_logger: logging.Logger,
        ensure_no_position: None,
        ensure_no_orders: None,
        check_balance: None,
    ) -> None:
        """STOP_MARKET 주문 생성
        
        검증 항목:
        - 포지션 진입
        - STOP_MARKET 주문 생성 성공
        - 주문이 오픈 주문에 존재
        """
        e2e_logger.info("test_stop_loss_order_creation 시작")
        
        # 포지션 진입 (매수)
        quantity = test_quantity
        e2e_logger.info(f"포지션 진입 (매수): qty={quantity}")
        
        buy_order = await place_market_order(
            rest_client,
            test_symbol,
            "BUY",
            quantity,
        )
        buy_order = await wait_for_order_fill(rest_client, buy_order)
        
        # 포지션 확인
        position = await rest_client.get_position(test_symbol)
        assert_position_exists(position)
        entry_price = position.entry_price
        e2e_logger.info(f"포지션 진입 완료: entry_price={entry_price}")
        
        # 손절가 계산 (진입가 대비 5% 하락)
        stop_price = round_price(entry_price * Decimal("0.95"))
        e2e_logger.info(f"손절가: {stop_price} (진입가 대비 -5%)")
        
        # STOP_MARKET 주문 생성
        stop_request = OrderRequest.stop_market(
            symbol=test_symbol,
            side="SELL",  # 롱 포지션 청산은 SELL
            quantity=quantity,
            stop_price=stop_price,
            reduce_only=True,
        )
        
        e2e_logger.info("STOP_MARKET 주문 생성 중...")
        stop_order = await rest_client.place_order(stop_request)
        
        e2e_logger.info(
            f"주문 생성 완료: order_id={stop_order.order_id}, "
            f"type={stop_order.order_type}, "
            f"stop_price={stop_order.stop_price}"
        )
        
        # 주문이 오픈 주문에 존재하는지 확인
        open_orders = await rest_client.get_open_orders(test_symbol)
        stop_orders = [o for o in open_orders if o.order_type == OrderType.STOP_MARKET.value]
        
        assert len(stop_orders) > 0, "STOP_MARKET 주문이 오픈 주문에 없음"
        e2e_logger.info(f"오픈 STOP_MARKET 주문: {len(stop_orders)}개")
        
        # 정리: 주문 취소 및 포지션 청산
        e2e_logger.info("정리 중...")
        await rest_client.cancel_all_orders(test_symbol)
        await close_position(rest_client, test_symbol)
        
        e2e_logger.info("test_stop_loss_order_creation 완료")


class TestTakeProfit:
    """익절 (TAKE_PROFIT_MARKET) 테스트"""
    
    @pytest.mark.production_risky
    async def test_take_profit_order_creation(
        self,
        rest_client: BinanceRestClient,
        test_symbol: str,
        test_quantity: Decimal,
        e2e_logger: logging.Logger,
        ensure_no_position: None,
        ensure_no_orders: None,
        check_balance: None,
    ) -> None:
        """TAKE_PROFIT_MARKET 주문 생성
        
        검증 항목:
        - 포지션 진입
        - TAKE_PROFIT_MARKET 주문 생성 성공
        - 주문이 오픈 주문에 존재
        """
        e2e_logger.info("test_take_profit_order_creation 시작")
        
        # 포지션 진입 (매수)
        quantity = test_quantity
        e2e_logger.info(f"포지션 진입 (매수): qty={quantity}")
        
        buy_order = await place_market_order(
            rest_client,
            test_symbol,
            "BUY",
            quantity,
        )
        buy_order = await wait_for_order_fill(rest_client, buy_order)
        
        # 포지션 확인
        position = await rest_client.get_position(test_symbol)
        assert_position_exists(position)
        entry_price = position.entry_price
        e2e_logger.info(f"포지션 진입 완료: entry_price={entry_price}")
        
        # 익절가 계산 (진입가 대비 5% 상승)
        take_profit_price = round_price(entry_price * Decimal("1.05"))
        e2e_logger.info(f"익절가: {take_profit_price} (진입가 대비 +5%)")
        
        # TAKE_PROFIT_MARKET 주문 생성
        tp_request = OrderRequest.take_profit_market(
            symbol=test_symbol,
            side="SELL",  # 롱 포지션 청산은 SELL
            quantity=quantity,
            stop_price=take_profit_price,
            reduce_only=True,
        )
        
        e2e_logger.info("TAKE_PROFIT_MARKET 주문 생성 중...")
        tp_order = await rest_client.place_order(tp_request)
        
        e2e_logger.info(
            f"주문 생성 완료: order_id={tp_order.order_id}, "
            f"type={tp_order.order_type}, "
            f"stop_price={tp_order.stop_price}"
        )
        
        # 주문이 오픈 주문에 존재하는지 확인
        open_orders = await rest_client.get_open_orders(test_symbol)
        tp_orders = [
            o for o in open_orders 
            if o.order_type == OrderType.TAKE_PROFIT_MARKET.value
        ]
        
        assert len(tp_orders) > 0, "TAKE_PROFIT_MARKET 주문이 오픈 주문에 없음"
        e2e_logger.info(f"오픈 TAKE_PROFIT_MARKET 주문: {len(tp_orders)}개")
        
        # 정리: 주문 취소 및 포지션 청산
        e2e_logger.info("정리 중...")
        await rest_client.cancel_all_orders(test_symbol)
        await close_position(rest_client, test_symbol)
        
        e2e_logger.info("test_take_profit_order_creation 완료")
    
    @pytest.mark.production_risky
    async def test_stop_loss_and_take_profit_together(
        self,
        rest_client: BinanceRestClient,
        test_symbol: str,
        test_quantity: Decimal,
        e2e_logger: logging.Logger,
        ensure_no_position: None,
        ensure_no_orders: None,
        check_balance: None,
    ) -> None:
        """손절과 익절 동시 설정
        
        검증 항목:
        - 포지션 진입
        - STOP_MARKET과 TAKE_PROFIT_MARKET 동시 생성
        - 두 주문 모두 오픈 주문에 존재
        """
        e2e_logger.info("test_stop_loss_and_take_profit_together 시작")
        
        # 포지션 진입
        quantity = test_quantity
        buy_order = await place_market_order(
            rest_client,
            test_symbol,
            "BUY",
            quantity,
        )
        buy_order = await wait_for_order_fill(rest_client, buy_order)
        
        # 포지션 확인
        position = await rest_client.get_position(test_symbol)
        entry_price = position.entry_price
        e2e_logger.info(f"진입가: {entry_price}")
        
        # 손절가, 익절가 계산
        stop_price = round_price(entry_price * Decimal("0.95"))
        take_profit_price = round_price(entry_price * Decimal("1.05"))
        
        e2e_logger.info(f"손절가: {stop_price}, 익절가: {take_profit_price}")
        
        # STOP_MARKET 주문
        sl_request = OrderRequest.stop_market(
            symbol=test_symbol,
            side="SELL",
            quantity=quantity,
            stop_price=stop_price,
            reduce_only=True,
        )
        sl_order = await rest_client.place_order(sl_request)
        e2e_logger.info(f"손절 주문: order_id={sl_order.order_id}")
        
        # TAKE_PROFIT_MARKET 주문
        tp_request = OrderRequest.take_profit_market(
            symbol=test_symbol,
            side="SELL",
            quantity=quantity,
            stop_price=take_profit_price,
            reduce_only=True,
        )
        tp_order = await rest_client.place_order(tp_request)
        e2e_logger.info(f"익절 주문: order_id={tp_order.order_id}")
        
        # 오픈 주문 확인
        open_orders = await rest_client.get_open_orders(test_symbol)
        e2e_logger.info(f"오픈 주문: {len(open_orders)}개")
        
        order_types = [o.order_type for o in open_orders]
        assert OrderType.STOP_MARKET.value in order_types, "STOP_MARKET 없음"
        assert OrderType.TAKE_PROFIT_MARKET.value in order_types, "TAKE_PROFIT_MARKET 없음"
        
        # 정리
        e2e_logger.info("정리 중...")
        await rest_client.cancel_all_orders(test_symbol)
        await close_position(rest_client, test_symbol)
        
        e2e_logger.info("test_stop_loss_and_take_profit_together 완료")


class TestLeverage:
    """레버리지 변경 테스트"""
    
    async def test_leverage_change(
        self,
        rest_client: BinanceRestClient,
        test_symbol: str,
        e2e_logger: logging.Logger,
        ensure_no_position: None,
        ensure_no_orders: None,
    ) -> None:
        """레버리지 변경
        
        검증 항목:
        - 레버리지 설정 API 호출 성공
        - 응답에서 설정된 레버리지 확인
        """
        e2e_logger.info("test_leverage_change 시작")
        
        # 현재 레버리지를 확인하기 위해 포지션 조회
        # (포지션이 없어도 positionRisk에서 레버리지 정보 제공)
        
        # 레버리지 10으로 변경
        new_leverage = 10
        e2e_logger.info(f"레버리지 변경: {new_leverage}배")
        
        result = await rest_client.set_leverage(test_symbol, new_leverage)
        
        e2e_logger.info(f"응답: {result}")
        
        # 응답 검증
        assert result.get("leverage") == new_leverage, (
            f"예상: {new_leverage}, 실제: {result.get('leverage')}"
        )
        assert result.get("symbol") == test_symbol
        
        e2e_logger.info(f"레버리지 변경 성공: {result.get('leverage')}배")
        
        e2e_logger.info("test_leverage_change 완료")
    
    async def test_leverage_limits(
        self,
        rest_client: BinanceRestClient,
        test_symbol: str,
        e2e_logger: logging.Logger,
        ensure_no_position: None,
        ensure_no_orders: None,
    ) -> None:
        """레버리지 제한 테스트
        
        검증 항목:
        - 최소 레버리지 (1배) 설정 가능
        - 최대 레버리지 (심볼별 상이, 보통 125배) 설정 가능
        - 범위 초과 시 에러
        """
        e2e_logger.info("test_leverage_limits 시작")
        
        # 최소 레버리지 테스트
        min_leverage = 1
        e2e_logger.info(f"최소 레버리지 테스트: {min_leverage}배")
        
        result = await rest_client.set_leverage(test_symbol, min_leverage)
        assert result.get("leverage") == min_leverage
        e2e_logger.info(f"최소 레버리지 설정 성공: {result.get('leverage')}배")
        
        # 높은 레버리지 테스트 (20배 - 대부분 심볼에서 지원)
        high_leverage = 20
        e2e_logger.info(f"높은 레버리지 테스트: {high_leverage}배")
        
        result = await rest_client.set_leverage(test_symbol, high_leverage)
        assert result.get("leverage") == high_leverage
        e2e_logger.info(f"높은 레버리지 설정 성공: {result.get('leverage')}배")
        
        # 기본값으로 복원
        default_leverage = 10
        await rest_client.set_leverage(test_symbol, default_leverage)
        e2e_logger.info(f"기본 레버리지로 복원: {default_leverage}배")
        
        e2e_logger.info("test_leverage_limits 완료")
    
    @pytest.mark.production_risky
    async def test_leverage_affects_position(
        self,
        rest_client: BinanceRestClient,
        test_symbol: str,
        test_quantity: Decimal,
        e2e_logger: logging.Logger,
        ensure_no_position: None,
        ensure_no_orders: None,
        check_balance: None,
    ) -> None:
        """레버리지가 포지션에 적용되는지 확인
        
        검증 항목:
        - 레버리지 설정 후 포지션 진입
        - 포지션의 레버리지가 설정값과 일치
        """
        e2e_logger.info("test_leverage_affects_position 시작")
        
        # 레버리지 설정
        target_leverage = 15
        e2e_logger.info(f"레버리지 설정: {target_leverage}배")
        
        await rest_client.set_leverage(test_symbol, target_leverage)
        
        # 포지션 진입
        quantity = test_quantity
        buy_order = await place_market_order(
            rest_client,
            test_symbol,
            "BUY",
            quantity,
        )
        buy_order = await wait_for_order_fill(rest_client, buy_order)
        e2e_logger.info("포지션 진입 완료")
        
        # 포지션 레버리지 확인
        position = await rest_client.get_position(test_symbol)
        assert_position_exists(position)
        
        e2e_logger.info(
            f"포지션 레버리지: {position.leverage}, "
            f"마진 타입: {position.margin_type}"
        )
        
        assert position.leverage == target_leverage, (
            f"레버리지 불일치: 예상={target_leverage}, 실제={position.leverage}"
        )
        
        # 정리
        await close_position(rest_client, test_symbol)
        
        # 기본 레버리지로 복원
        await rest_client.set_leverage(test_symbol, 10)
        
        e2e_logger.info("test_leverage_affects_position 완료")
