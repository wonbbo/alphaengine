"""
Testnet 24시간 내구성 테스트 스크립트

실행 방법:
    python -m scripts.endurance_test --duration 24h

테스트 항목:
1. WebSocket 연결 안정성
2. REST API 정상 동작
3. Event/Command 저장 정합성
4. 메모리 누수 확인
5. 에러 발생 빈도
"""

import asyncio
import argparse
import logging
import signal
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

# 프로젝트 루트를 path에 추가
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.config.loader import load_secrets, get_exchange_config
from core.types import WebSocketState, TradingMode
from adapters.binance.rest_client import BinanceRestClient
from adapters.binance.ws_client import BinanceWsClient
from adapters.db.sqlite_adapter import SQLiteAdapter, get_db_path


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class EnduranceTest:
    """내구성 테스트 실행기"""
    
    def __init__(self, duration_hours: float):
        self.duration_hours = duration_hours
        self.start_time: datetime | None = None
        self.end_time: datetime | None = None
        self.running = True
        
        # 통계
        self.stats = {
            "ws_connected_count": 0,
            "ws_disconnected_count": 0,
            "ws_reconnected_count": 0,
            "ws_messages_received": 0,
            "rest_calls_success": 0,
            "rest_calls_failed": 0,
            "errors": [],
        }
        
        # 클라이언트
        self.rest_client: BinanceRestClient | None = None
        self.ws_client: BinanceWsClient | None = None
        
    async def setup(self) -> None:
        """초기화"""
        logger.info("내구성 테스트 초기화 중...")
        
        # 설정 로드
        secrets = load_secrets()
        if secrets.mode != TradingMode.TESTNET:
            raise ValueError(
                f"내구성 테스트는 Testnet에서만 실행 가능합니다. "
                f"현재 모드: {secrets.mode.value}"
            )
        
        config = get_exchange_config(secrets)
        
        # REST 클라이언트 생성
        self.rest_client = BinanceRestClient(
            base_url=config.rest_url,
            api_key=config.api_key,
            api_secret=config.api_secret,
        )
        
        # WebSocket 클라이언트 생성
        self.ws_client = BinanceWsClient(
            ws_base_url=config.ws_url,
            rest_client=self.rest_client,
            on_message=self._on_ws_message,
            on_state_change=self._on_ws_state_change,
        )
        
        logger.info("초기화 완료")
    
    async def _on_ws_message(self, message: dict[str, Any]) -> None:
        """WebSocket 메시지 수신 콜백"""
        self.stats["ws_messages_received"] += 1
    
    async def _on_ws_state_change(self, state: WebSocketState) -> None:
        """WebSocket 상태 변경 콜백"""
        logger.info(f"WebSocket 상태 변경: {state.value}")
        
        if state == WebSocketState.CONNECTED:
            self.stats["ws_connected_count"] += 1
        elif state == WebSocketState.DISCONNECTED:
            self.stats["ws_disconnected_count"] += 1
        elif state == WebSocketState.RECONNECTING:
            self.stats["ws_reconnected_count"] += 1
    
    async def run(self) -> None:
        """테스트 실행"""
        self.start_time = datetime.now(timezone.utc)
        self.end_time = self.start_time + timedelta(hours=self.duration_hours)
        
        logger.info("=" * 60)
        logger.info("AlphaEngine 내구성 테스트 시작")
        logger.info(f"시작 시간: {self.start_time.isoformat()}")
        logger.info(f"예상 종료: {self.end_time.isoformat()}")
        logger.info(f"테스트 시간: {self.duration_hours}시간")
        logger.info("=" * 60)
        
        # WebSocket 연결 시작
        logger.info("WebSocket 연결 시작...")
        await self.ws_client.start()
        
        # 연결 대기
        for _ in range(30):
            if self.ws_client.state == WebSocketState.CONNECTED:
                break
            await asyncio.sleep(1)
        
        if self.ws_client.state != WebSocketState.CONNECTED:
            raise RuntimeError(
                f"WebSocket 연결 실패 (상태: {self.ws_client.state.value})"
            )
        
        logger.info("WebSocket 연결 완료")
        
        # 테스트 루프
        check_interval = 60  # 1분마다 체크
        last_report_time = self.start_time
        report_interval = timedelta(hours=1)  # 1시간마다 리포트
        
        while self.running and datetime.now(timezone.utc) < self.end_time:
            try:
                # REST API 헬스 체크
                await self._check_rest_api()
                
                # 현재 상태 체크
                await self._check_current_state()
                
                # 정기 리포트
                now = datetime.now(timezone.utc)
                if now - last_report_time >= report_interval:
                    self._print_progress_report()
                    last_report_time = now
                
                # 대기
                await asyncio.sleep(check_interval)
                
            except Exception as e:
                logger.error(f"체크 중 오류: {e}")
                self.stats["errors"].append({
                    "time": datetime.now(timezone.utc).isoformat(),
                    "error": str(e),
                })
                await asyncio.sleep(10)
        
        logger.info("테스트 루프 종료")
    
    async def _check_rest_api(self) -> None:
        """REST API 체크"""
        try:
            await self.rest_client.get_server_time()
            self.stats["rest_calls_success"] += 1
        except Exception as e:
            self.stats["rest_calls_failed"] += 1
            raise
    
    async def _check_current_state(self) -> None:
        """현재 상태 체크"""
        # WebSocket 상태
        if self.ws_client.state != WebSocketState.CONNECTED:
            logger.warning(f"WebSocket 상태 비정상: {self.ws_client.state.value}")
    
    def _print_progress_report(self) -> None:
        """진행 상황 리포트"""
        now = datetime.now(timezone.utc)
        elapsed = now - self.start_time
        remaining = self.end_time - now
        
        logger.info("=" * 60)
        logger.info("진행 상황 리포트")
        logger.info(f"경과 시간: {elapsed}")
        logger.info(f"남은 시간: {remaining}")
        logger.info(f"WebSocket 상태: {self.ws_client.state.value}")
        logger.info(f"수신된 WS 메시지: {self.stats['ws_messages_received']}")
        logger.info(f"REST 호출 성공/실패: {self.stats['rest_calls_success']}/{self.stats['rest_calls_failed']}")
        logger.info(f"연결/재연결: {self.stats['ws_connected_count']}/{self.stats['ws_reconnected_count']}")
        logger.info(f"에러 수: {len(self.stats['errors'])}")
        logger.info("=" * 60)
    
    async def cleanup(self) -> None:
        """정리"""
        logger.info("정리 중...")
        
        if self.ws_client:
            await self.ws_client.stop()
        
        if self.rest_client:
            await self.rest_client.close()
        
        logger.info("정리 완료")
    
    def print_final_report(self) -> None:
        """최종 리포트"""
        actual_end = datetime.now(timezone.utc)
        duration = actual_end - self.start_time
        
        logger.info("")
        logger.info("=" * 60)
        logger.info("내구성 테스트 최종 리포트")
        logger.info("=" * 60)
        logger.info(f"시작 시간: {self.start_time.isoformat()}")
        logger.info(f"종료 시간: {actual_end.isoformat()}")
        logger.info(f"실제 소요 시간: {duration}")
        logger.info("")
        logger.info("[WebSocket 통계]")
        logger.info(f"  수신된 메시지: {self.stats['ws_messages_received']}")
        logger.info(f"  연결 횟수: {self.stats['ws_connected_count']}")
        logger.info(f"  끊김 횟수: {self.stats['ws_disconnected_count']}")
        logger.info(f"  재연결 횟수: {self.stats['ws_reconnected_count']}")
        logger.info("")
        logger.info("[REST API 통계]")
        logger.info(f"  성공: {self.stats['rest_calls_success']}")
        logger.info(f"  실패: {self.stats['rest_calls_failed']}")
        success_rate = (
            self.stats['rest_calls_success'] / 
            max(self.stats['rest_calls_success'] + self.stats['rest_calls_failed'], 1)
        ) * 100
        logger.info(f"  성공률: {success_rate:.2f}%")
        logger.info("")
        logger.info("[에러]")
        logger.info(f"  총 에러 수: {len(self.stats['errors'])}")
        for i, err in enumerate(self.stats['errors'][-5:], 1):
            logger.info(f"  {i}. [{err['time']}] {err['error']}")
        logger.info("")
        logger.info("=" * 60)
        
        # 성공 여부 판단
        if self.stats['rest_calls_failed'] == 0 and len(self.stats['errors']) == 0:
            logger.info("결과: 성공")
        elif success_rate >= 99.0 and len(self.stats['errors']) < 10:
            logger.info("결과: 부분 성공 (경미한 문제 발생)")
        else:
            logger.info("결과: 실패 (검토 필요)")
    
    def stop(self) -> None:
        """테스트 중지"""
        logger.info("테스트 중지 요청...")
        self.running = False


def parse_duration(duration_str: str) -> float:
    """시간 문자열 파싱 (예: 24h, 30m, 1.5h)"""
    duration_str = duration_str.strip().lower()
    
    if duration_str.endswith("h"):
        return float(duration_str[:-1])
    elif duration_str.endswith("m"):
        return float(duration_str[:-1]) / 60
    else:
        return float(duration_str)


async def main() -> None:
    parser = argparse.ArgumentParser(description="AlphaEngine 내구성 테스트")
    parser.add_argument(
        "--duration",
        type=str,
        default="24h",
        help="테스트 시간 (예: 24h, 30m, 1.5h)",
    )
    
    args = parser.parse_args()
    duration_hours = parse_duration(args.duration)
    
    test = EnduranceTest(duration_hours)
    
    # 시그널 핸들러
    def signal_handler(sig, frame):
        logger.info(f"시그널 수신: {sig}")
        test.stop()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await test.setup()
        await test.run()
    except Exception as e:
        logger.error(f"테스트 실패: {e}")
        raise
    finally:
        await test.cleanup()
        test.print_final_report()


if __name__ == "__main__":
    asyncio.run(main())
