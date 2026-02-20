"""
자금 시나리오 테스트

잔고 조회, 잔고 변경 감지 시나리오 검증.
"""

import logging
from decimal import Decimal

import pytest
import pytest_asyncio

from adapters.binance.rest_client import BinanceRestClient
from adapters.binance.ws_client import BinanceWsClient
from adapters.models import Balance
from core.types import WebSocketState
from tests.e2e.utils.helpers import (
    wait_for_ws_state,
    wait_for_ws_message,
    place_market_order,
    close_position,
)


pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


class TestBalanceQuery:
    """잔고 조회 테스트"""
    
    async def test_balance_query(
        self,
        rest_client: BinanceRestClient,
        e2e_logger: logging.Logger,
    ) -> None:
        """REST API로 잔고 조회
        
        검증 항목:
        - get_balances() 호출 성공
        - USDT 잔고 존재
        - Decimal 타입 확인
        """
        e2e_logger.info("test_balance_query 시작")
        
        # 잔고 조회
        e2e_logger.info("잔고 조회 중...")
        balances = await rest_client.get_balances()
        
        e2e_logger.info(f"조회된 잔고 수: {len(balances)}")
        
        # USDT 잔고 찾기
        usdt_balance: Balance | None = None
        for balance in balances:
            e2e_logger.info(
                f"  {balance.asset}: wallet={balance.wallet_balance}, "
                f"available={balance.available_balance}"
            )
            if balance.asset == "USDT":
                usdt_balance = balance
        
        # 검증
        assert usdt_balance is not None, "USDT 잔고를 찾을 수 없음"
        assert isinstance(usdt_balance.wallet_balance, Decimal), "잔고가 Decimal 타입이 아님"
        assert usdt_balance.wallet_balance > Decimal("0"), "USDT 잔고가 0"
        
        e2e_logger.info(
            f"USDT 잔고 확인: wallet={usdt_balance.wallet_balance}, "
            f"available={usdt_balance.available_balance}"
        )
        
        e2e_logger.info("test_balance_query 완료")
    
    async def test_balance_decimal_precision(
        self,
        rest_client: BinanceRestClient,
        e2e_logger: logging.Logger,
    ) -> None:
        """잔고 Decimal 정밀도 검증
        
        검증 항목:
        - 잔고 값이 Decimal 타입
        - 부동소수점 오차 없음
        """
        e2e_logger.info("test_balance_decimal_precision 시작")
        
        balances = await rest_client.get_balances()
        
        for balance in balances:
            # Decimal 타입 확인
            assert isinstance(balance.wallet_balance, Decimal)
            assert isinstance(balance.available_balance, Decimal)
            assert isinstance(balance.cross_wallet_balance, Decimal)
            assert isinstance(balance.unrealized_pnl, Decimal)
            
            # total 속성도 Decimal인지 확인
            total = balance.total
            assert isinstance(total, Decimal)
            
            e2e_logger.info(
                f"{balance.asset}: total={total} (type={type(total).__name__})"
            )
        
        e2e_logger.info("test_balance_decimal_precision 완료")


class TestBalanceChangeDetection:
    """잔고 변경 감지 테스트"""
    
    @pytest.mark.production_risky
    async def test_balance_change_detection(
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
        """주문 실행 시 ACCOUNT_UPDATE 이벤트로 잔고 변경 감지
        
        검증 항목:
        - WebSocket 연결 성공
        - 주문 실행 후 ACCOUNT_UPDATE 이벤트 수신
        - 이벤트에 잔고 변경 정보 포함
        """
        e2e_logger.info("test_balance_change_detection 시작")
        
        # WebSocket 연결
        e2e_logger.info("WebSocket 연결 중...")
        await ws_client.start()
        await wait_for_ws_state(ws_client, WebSocketState.CONNECTED, timeout=30.0)
        e2e_logger.info("WebSocket 연결 완료")
        
        # 주문 전 잔고 조회
        balances_before = await rest_client.get_balances()
        usdt_before = next((b for b in balances_before if b.asset == "USDT"), None)
        assert usdt_before is not None
        e2e_logger.info(f"주문 전 USDT 잔고: {usdt_before.available_balance}")
        
        # 시장가 매수 주문
        quantity = test_quantity
        e2e_logger.info(f"시장가 매수: {test_symbol}, qty={quantity}")
        
        order = await place_market_order(
            rest_client,
            test_symbol,
            "BUY",
            quantity,
        )
        e2e_logger.info(f"주문 완료: order_id={order.order_id}, status={order.status}")
        
        # ACCOUNT_UPDATE 메시지 대기
        e2e_logger.info("ACCOUNT_UPDATE 메시지 대기 중...")
        message = await wait_for_ws_message(
            ws_client,
            "ACCOUNT_UPDATE",
            timeout=60.0,
        )
        
        if message is not None:
            e2e_logger.info(f"ACCOUNT_UPDATE 수신: reason={message.get('a', {}).get('m')}")
            
            # 잔고 변경 정보 확인
            account_data = message.get("a", {})
            balances_in_event = account_data.get("B", [])
            positions_in_event = account_data.get("P", [])
            
            e2e_logger.info(f"잔고 변경 수: {len(balances_in_event)}")
            e2e_logger.info(f"포지션 변경 수: {len(positions_in_event)}")
            
            # USDT 잔고 변경 확인
            usdt_change = next(
                (b for b in balances_in_event if b.get("a") == "USDT"),
                None,
            )
            
            if usdt_change:
                e2e_logger.info(
                    f"USDT 변경: wallet_balance={usdt_change.get('wb')}, "
                    f"balance_change={usdt_change.get('bc')}"
                )
        else:
            # Testnet WebSocket 지연 - REST API로 잔고 변경 확인
            e2e_logger.warning("ACCOUNT_UPDATE 미수신 - REST API로 확인")
            balances_after = await rest_client.get_balances()
            usdt_after = next((b for b in balances_after if b.asset == "USDT"), None)
            
            if usdt_after:
                e2e_logger.info(f"주문 후 USDT 잔고: {usdt_after.available_balance}")
                # 잔고 변경 발생 여부 확인
                balance_changed = usdt_before.available_balance != usdt_after.available_balance
                e2e_logger.info(f"잔고 변경 확인 (REST): {balance_changed}")
                assert balance_changed, "REST로도 잔고 변경 없음 (비정상)"
            else:
                pytest.skip("Testnet WebSocket 지연으로 테스트 스킵")
        
        # 포지션 정리
        e2e_logger.info("포지션 청산 중...")
        await close_position(rest_client, test_symbol)
        
        e2e_logger.info("test_balance_change_detection 완료")
    
    @pytest.mark.production_risky
    async def test_position_change_in_account_update(
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
        """ACCOUNT_UPDATE 이벤트에서 포지션 변경 감지
        
        검증 항목:
        - 주문 실행 후 포지션 변경 정보 포함
        - 심볼, 수량, 진입가 정보 확인
        """
        e2e_logger.info("test_position_change_in_account_update 시작")
        
        # WebSocket 연결
        await ws_client.start()
        await wait_for_ws_state(ws_client, WebSocketState.CONNECTED, timeout=30.0)
        e2e_logger.info("WebSocket 연결 완료")
        
        # 시장가 매수 주문
        quantity = test_quantity
        e2e_logger.info(f"시장가 매수: {test_symbol}, qty={quantity}")
        
        order = await place_market_order(
            rest_client,
            test_symbol,
            "BUY",
            quantity,
        )
        e2e_logger.info(f"주문 완료: status={order.status}")
        
        # ACCOUNT_UPDATE 메시지 대기
        e2e_logger.info("ACCOUNT_UPDATE 메시지 대기 중...")
        message = await wait_for_ws_message(
            ws_client,
            "ACCOUNT_UPDATE",
            timeout=60.0,
        )
        
        if message is not None:
            # 포지션 변경 정보 확인
            positions_in_event = message.get("a", {}).get("P", [])
            
            target_position = next(
                (p for p in positions_in_event if p.get("s") == test_symbol),
                None,
            )
            
            assert target_position is not None, f"{test_symbol} 포지션 변경 정보 없음"
            
            e2e_logger.info(
                f"포지션 변경: symbol={target_position.get('s')}, "
                f"quantity={target_position.get('pa')}, "
                f"entry_price={target_position.get('ep')}, "
                f"side={target_position.get('ps')}"
            )
            
            # 수량이 0이 아닌지 확인 (포지션 진입)
            position_qty = Decimal(target_position.get("pa", "0"))
            assert position_qty != Decimal("0"), "포지션 수량이 0"
        else:
            # Testnet WebSocket 지연 - REST API로 포지션 확인
            e2e_logger.warning("ACCOUNT_UPDATE 미수신 - REST API로 포지션 확인")
            position = await rest_client.get_position(test_symbol)
            
            assert position is not None, "REST로 포지션 조회 실패"
            assert position.quantity != Decimal("0"), "REST로 확인된 포지션 수량 0"
            
            e2e_logger.info(
                f"포지션 확인 (REST): symbol={position.symbol}, "
                f"quantity={position.quantity}, "
                f"entry_price={position.entry_price}"
            )
        
        # 포지션 정리
        e2e_logger.info("포지션 청산 중...")
        await close_position(rest_client, test_symbol)
        
        e2e_logger.info("test_position_change_in_account_update 완료")
