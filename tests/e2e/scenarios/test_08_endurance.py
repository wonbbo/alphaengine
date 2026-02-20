"""
장시간 내구성 테스트

24시간 무중단 운영 시나리오 검증을 위한 짧은 내구성 테스트.
(실제 24시간 테스트는 별도 스크립트로 실행)
"""

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pytest
import pytest_asyncio

from adapters.binance.rest_client import BinanceRestClient
from adapters.binance.ws_client import BinanceWsClient
from core.config.loader import ExchangeConfig
from core.types import WebSocketState
from tests.e2e.utils.helpers import wait_for_ws_state


pytestmark = [pytest.mark.e2e, pytest.mark.asyncio, pytest.mark.slow]


class TestShortEndurance:
    """짧은 내구성 테스트 (CI용)"""
    
    async def test_websocket_stable_connection_5min(
        self,
        ws_client: BinanceWsClient,
        rest_client: BinanceRestClient,
        e2e_logger: logging.Logger,
    ) -> None:
        """WebSocket 5분 안정 연결 테스트
        
        검증 항목:
        - 5분간 WebSocket 연결 유지
        - 연결 끊김 없음 (또는 자동 재연결 성공)
        - listenKey 갱신 정상 (필요 시)
        
        주의: 이 테스트는 --slow 마커로 실행해야 함
        """
        from adapters.binance.rate_limiter import BinanceApiError
        
        e2e_logger.info("test_websocket_stable_connection_5min 시작")
        
        # listenKey 생성 가능 여부 확인
        try:
            await rest_client.create_listen_key()
            await rest_client.delete_listen_key()
        except BinanceApiError as e:
            if e.code == -2015:
                pytest.skip(f"API 키 권한 오류: {e}")
            raise
        
        # WebSocket 연결
        e2e_logger.info("WebSocket 연결 시작...")
        try:
            await ws_client.start()
        except Exception as e:
            pytest.skip(f"WebSocket 연결 실패: {e}")
        
        # 연결 상태 확인
        connected = await wait_for_ws_state(
            ws_client, WebSocketState.CONNECTED, timeout=30.0
        )
        if not connected and ws_client.state != WebSocketState.CONNECTED:
            pytest.skip(f"WebSocket 연결 실패 (상태: {ws_client.state.value})")
        
        e2e_logger.info(f"WebSocket 연결 완료 - 상태: {ws_client.state.value}")
        
        # 5분간 연결 유지 테스트 (30초 간격 체크)
        test_duration = 5 * 60  # 5분
        check_interval = 30  # 30초
        checks = test_duration // check_interval
        
        disconnection_count = 0
        reconnection_count = 0
        states: list[WebSocketState] = getattr(ws_client, "_test_states", [])
        
        for i in range(checks):
            e2e_logger.info(f"체크 {i + 1}/{checks}: 상태={ws_client.state.value}")
            
            if ws_client.state != WebSocketState.CONNECTED:
                disconnection_count += 1
                e2e_logger.warning(f"연결 끊김 감지: {ws_client.state.value}")
                
                # 재연결 대기
                reconnected = await wait_for_ws_state(
                    ws_client, WebSocketState.CONNECTED, timeout=60.0
                )
                if reconnected or ws_client.state == WebSocketState.CONNECTED:
                    reconnection_count += 1
                    e2e_logger.info("재연결 성공")
                else:
                    e2e_logger.error("재연결 실패")
            
            await asyncio.sleep(check_interval)
        
        # 결과 보고
        e2e_logger.info(f"테스트 완료:")
        e2e_logger.info(f"  - 연결 끊김 횟수: {disconnection_count}")
        e2e_logger.info(f"  - 재연결 성공 횟수: {reconnection_count}")
        e2e_logger.info(f"  - 최종 상태: {ws_client.state.value}")
        e2e_logger.info(f"  - 상태 변경 이력: {[s.value for s in states[-10:]]}")
        
        # 최종 상태는 CONNECTED여야 함
        assert ws_client.state == WebSocketState.CONNECTED, \
            f"최종 상태가 CONNECTED가 아님: {ws_client.state.value}"
        
        e2e_logger.info("test_websocket_stable_connection_5min 완료")
    
    async def test_rest_api_repeated_calls(
        self,
        rest_client: BinanceRestClient,
        test_symbol: str,
        e2e_logger: logging.Logger,
    ) -> None:
        """REST API 반복 호출 테스트
        
        검증 항목:
        - 100회 반복 호출 성공
        - Rate Limit 처리 정상
        """
        e2e_logger.info("test_rest_api_repeated_calls 시작")
        
        call_count = 100
        success_count = 0
        error_count = 0
        rate_limited_count = 0
        
        for i in range(call_count):
            try:
                # 서버 시간 조회 (가벼운 API)
                await rest_client.get_server_time()
                success_count += 1
                
                # 진행 상황 로깅 (10회마다)
                if (i + 1) % 10 == 0:
                    e2e_logger.info(f"진행: {i + 1}/{call_count}")
                
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "rate" in error_str.lower():
                    rate_limited_count += 1
                    e2e_logger.warning(f"Rate Limit 발생: {e}")
                    await asyncio.sleep(1)
                else:
                    error_count += 1
                    e2e_logger.error(f"API 호출 실패: {e}")
            
            # Rate Limit 방지를 위한 짧은 대기
            await asyncio.sleep(0.1)
        
        # 결과 보고
        e2e_logger.info(f"테스트 완료:")
        e2e_logger.info(f"  - 총 호출 수: {call_count}")
        e2e_logger.info(f"  - 성공 수: {success_count}")
        e2e_logger.info(f"  - 에러 수: {error_count}")
        e2e_logger.info(f"  - Rate Limit 발생 수: {rate_limited_count}")
        
        # 90% 이상 성공해야 함
        success_rate = success_count / call_count
        assert success_rate >= 0.9, f"성공률이 90% 미만: {success_rate * 100:.1f}%"
        
        e2e_logger.info("test_rest_api_repeated_calls 완료")


class TestRecoveryScenario:
    """복구 시나리오 테스트"""
    
    async def test_websocket_recovery_after_disconnect(
        self,
        ws_client: BinanceWsClient,
        rest_client: BinanceRestClient,
        e2e_logger: logging.Logger,
    ) -> None:
        """WebSocket 끊김 후 복구 테스트
        
        검증 항목:
        - 강제 끊김 후 자동 재연결
        - 재연결 후 정상 동작
        """
        from adapters.binance.rate_limiter import BinanceApiError
        
        e2e_logger.info("test_websocket_recovery_after_disconnect 시작")
        
        # listenKey 확인
        try:
            await rest_client.create_listen_key()
            await rest_client.delete_listen_key()
        except BinanceApiError as e:
            if e.code == -2015:
                pytest.skip(f"API 키 권한 오류: {e}")
            raise
        
        # 연결
        try:
            await ws_client.start()
        except Exception as e:
            pytest.skip(f"WebSocket 연결 실패: {e}")
        
        connected = await wait_for_ws_state(
            ws_client, WebSocketState.CONNECTED, timeout=30.0
        )
        if not connected and ws_client.state != WebSocketState.CONNECTED:
            pytest.skip(f"초기 연결 실패 (상태: {ws_client.state.value})")
        
        e2e_logger.info("초기 연결 완료")
        
        # 3회 강제 끊김 및 복구 테스트
        recovery_success = 0
        
        for i in range(3):
            e2e_logger.info(f"끊김/복구 테스트 {i + 1}/3")
            
            # 상태 기록 초기화
            states: list[WebSocketState] = getattr(ws_client, "_test_states", [])
            states.clear()
            
            # 강제 끊김
            if ws_client._ws is not None:
                await ws_client._ws.close()
                e2e_logger.info("  강제 끊김 실행")
            
            # 재연결 대기
            await asyncio.sleep(2)
            
            reconnected = await wait_for_ws_state(
                ws_client, WebSocketState.CONNECTED, timeout=60.0
            )
            
            if reconnected or ws_client.state == WebSocketState.CONNECTED:
                recovery_success += 1
                e2e_logger.info(f"  복구 성공 (상태: {ws_client.state.value})")
            else:
                e2e_logger.error(f"  복구 실패 (상태: {ws_client.state.value})")
            
            # 안정화 대기
            await asyncio.sleep(3)
        
        # 결과 확인
        e2e_logger.info(f"복구 성공률: {recovery_success}/3")
        
        # 최소 2회 이상 성공해야 함
        assert recovery_success >= 2, f"복구 성공률 부족: {recovery_success}/3"
        
        e2e_logger.info("test_websocket_recovery_after_disconnect 완료")
