#!/usr/bin/env python3
"""
Thin Slice 검증 스크립트

Dev-Phase 3: 전체 시스템 흐름을 관통하는 최소 기능 검증

흐름:
1. secrets.yaml 로드
2. Binance REST 연결
3. 잔고 조회
4. BalanceChanged 이벤트 생성
5. SQLite DB 저장
6. 저장된 이벤트 조회 및 검증
"""

import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from adapters.binance.rest_client import BinanceRestClient
from adapters.db.sqlite_adapter import SQLiteAdapter, init_schema
from adapters.models import Balance
from core.config.loader import load_secrets, get_exchange_config, get_db_path
from core.constants import Defaults
from core.domain.events import Event, EventTypes
from core.storage.event_store import EventStore
from core.types import Scope, TradingMode, Exchange, Venue, EventSource, EntityKind
from core.utils.dedup import generate_balance_dedup_key

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def create_balance_changed_event(
    balance: Balance,
    scope: Scope,
    update_time: int | None = None,
) -> Event:
    """Balance 객체에서 BalanceChanged 이벤트 생성
    
    Args:
        balance: 잔고 정보
        scope: 거래 범위
        update_time: 업데이트 시간 (밀리초, None이면 현재 시간)
        
    Returns:
        BalanceChanged Event
    """
    # dedup_key 생성
    # 패턴: {exchange}:{venue}:{asset}:balance:{update_time}
    if update_time is None:
        update_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    
    dedup_key = generate_balance_dedup_key(
        exchange=scope.exchange,
        venue=scope.venue,
        asset=balance.asset,
        update_time=update_time,
    )
    
    # payload 구성
    payload = {
        "asset": balance.asset,
        "wallet_balance": str(balance.wallet_balance),
        "available_balance": str(balance.available_balance),
        "cross_wallet_balance": str(balance.cross_wallet_balance),
        "unrealized_pnl": str(balance.unrealized_pnl),
        "update_time": update_time,
    }
    
    return Event.create(
        event_type=EventTypes.BALANCE_CHANGED,
        source=EventSource.REST.value,
        entity_kind=EntityKind.BALANCE.value,
        entity_id=balance.asset,
        scope=scope,
        dedup_key=dedup_key,
        payload=payload,
    )


async def main() -> int:
    """메인 함수
    
    Returns:
        종료 코드 (0: 성공, 1: 실패)
    """
    logger.info("=" * 60)
    logger.info("Dev-Phase 3: Thin Slice 검증 시작")
    logger.info("=" * 60)
    
    try:
        # =====================================================================
        # 1. 설정 로드
        # =====================================================================
        logger.info("")
        logger.info("[Step 1] 설정 로드")
        
        secrets = load_secrets()
        exchange_config = get_exchange_config(secrets)
        db_path = get_db_path(secrets)
        
        logger.info(f"  - mode: {secrets.mode.value}")
        logger.info(f"  - REST URL: {exchange_config.rest_url}")
        logger.info(f"  - DB 경로: {db_path}")
        
        # Scope 생성
        scope = Scope.create(
            exchange=Exchange.BINANCE,
            venue=Venue.FUTURES,
            account_id=Defaults.ACCOUNT_ID,
            symbol=None,  # 잔고는 심볼 없음
            mode=secrets.mode,
        )
        
        # =====================================================================
        # 2. DB 연결 및 스키마 초기화
        # =====================================================================
        logger.info("")
        logger.info("[Step 2] DB 연결 및 스키마 초기화")
        
        async with SQLiteAdapter(db_path) as db:
            await init_schema(db)
            event_store = EventStore(db)
            
            logger.info(f"  - DB 연결 완료")
            logger.info(f"  - 스키마 초기화 완료")
            
            # =================================================================
            # 3. REST 클라이언트 생성 및 연결
            # =================================================================
            logger.info("")
            logger.info("[Step 3] Binance REST 클라이언트 연결")
            
            async with BinanceRestClient(
                base_url=exchange_config.rest_url,
                api_key=exchange_config.api_key,
                api_secret=exchange_config.api_secret,
            ) as client:
                # 서버 시간 동기화
                offset = await client.sync_time()
                logger.info(f"  - 서버 시간 동기화 완료 (offset: {offset}ms)")
                
                # =============================================================
                # 4. 잔고 조회
                # =============================================================
                logger.info("")
                logger.info("[Step 4] 잔고 조회")
                
                balances = await client.get_balances()
                logger.info(f"  - 조회된 자산: {len(balances)}개")
                
                if not balances:
                    logger.warning("  - 잔고가 없습니다. Testnet에서 잔고를 충전해주세요.")
                    logger.warning("    https://testnet.binancefuture.com/")
                    return 1
                
                for b in balances:
                    logger.info(f"    - {b.asset}: {b.wallet_balance} (available: {b.available_balance})")
                
                # =============================================================
                # 5. BalanceChanged 이벤트 생성 및 저장
                # =============================================================
                logger.info("")
                logger.info("[Step 5] BalanceChanged 이벤트 생성 및 저장")
                
                # 현재 시간으로 update_time 통일 (중복 방지용)
                update_time = int(datetime.now(timezone.utc).timestamp() * 1000)
                
                saved_count = 0
                skipped_count = 0
                
                for balance in balances:
                    event = create_balance_changed_event(
                        balance=balance,
                        scope=scope,
                        update_time=update_time,
                    )
                    
                    saved = await event_store.append(event)
                    
                    if saved:
                        logger.info(f"  - 저장: {balance.asset} (신규)")
                        saved_count += 1
                    else:
                        logger.info(f"  - 스킵: {balance.asset} (중복)")
                        skipped_count += 1
                
                logger.info(f"  - 총 {saved_count}개 저장, {skipped_count}개 스킵")
                
                # =============================================================
                # 6. 저장된 이벤트 조회 및 검증
                # =============================================================
                logger.info("")
                logger.info("[Step 6] 저장된 이벤트 조회 및 검증")
                
                # BalanceChanged 타입 이벤트 조회
                events = await event_store.get_by_type(
                    event_type=EventTypes.BALANCE_CHANGED,
                    limit=100,
                )
                
                logger.info(f"  - 조회된 BalanceChanged 이벤트: {len(events)}개")
                
                for event in events[:5]:  # 최대 5개만 출력
                    asset = event.payload.get("asset", "N/A")
                    wallet = event.payload.get("wallet_balance", "N/A")
                    logger.info(f"    - event_id: {event.event_id[:8]}..., asset: {asset}, wallet: {wallet}")
                
                if len(events) > 5:
                    logger.info(f"    ... 외 {len(events) - 5}개")
                
                # 전체 이벤트 통계
                total_events = await event_store.count_all()
                last_seq = await event_store.get_last_seq()
                
                logger.info(f"  - 전체 이벤트 수: {total_events}")
                logger.info(f"  - 마지막 seq: {last_seq}")
        
        # =====================================================================
        # 검증 완료
        # =====================================================================
        logger.info("")
        logger.info("=" * 60)
        logger.info("Thin Slice 검증 완료!")
        logger.info("=" * 60)
        logger.info("")
        logger.info("검증 체크리스트:")
        logger.info("  [OK] secrets.yaml 로드 성공")
        logger.info("  [OK] Binance Testnet REST 연결 성공")
        logger.info("  [OK] 잔고 조회 성공")
        logger.info("  [OK] BalanceChanged 이벤트 생성")
        logger.info("  [OK] event_store 테이블에 저장 성공")
        logger.info("  [OK] 저장된 이벤트 조회 성공")
        logger.info("")
        logger.info("다음 단계: Dev-Phase 4 (스켈레톤 구축)")
        
        return 0
        
    except FileNotFoundError as e:
        logger.error(f"파일을 찾을 수 없습니다: {e}")
        logger.error("config/secrets.yaml 파일이 존재하는지 확인해주세요.")
        return 1
        
    except Exception as e:
        logger.error(f"오류 발생: {e}")
        logger.exception("상세 오류:")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
