"""
기존 TradeExecuted 이벤트를 position_session/position_trade로 마이그레이션

사용법:
    python scripts/migrate_position_history.py --mode testnet
    python scripts/migrate_position_history.py --mode production --dry-run
"""

import argparse
import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

# 프로젝트 루트 추가
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.db.sqlite_adapter import SQLiteAdapter
from core.constants import Paths

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger(__name__)


async def get_trade_events(db: SQLiteAdapter, mode: str) -> list[dict[str, Any]]:
    """TradeExecuted 이벤트 조회 (시간순)"""
    rows = await db.fetchall(
        """
        SELECT 
            seq, event_id, ts,
            scope_venue, scope_symbol, scope_mode,
            payload_json
        FROM event_store
        WHERE event_type = 'TradeExecuted'
          AND scope_mode = ?
        ORDER BY ts ASC, seq ASC
        """,
        (mode.upper(),),
    )
    
    import json
    events = []
    for row in rows:
        payload = json.loads(row[6]) if isinstance(row[6], str) else row[6]
        events.append({
            "seq": row[0],
            "event_id": row[1],
            "ts": row[2],
            "venue": row[3],
            "symbol": row[4],
            "mode": row[5],
            "side": payload.get("side", "").upper(),
            "qty": Decimal(str(payload.get("qty", "0"))),
            "price": Decimal(str(payload.get("price", "0"))),
            "realized_pnl": Decimal(str(payload.get("realized_pnl", "0"))),
            "commission": Decimal(str(payload.get("commission", "0"))),
        })
    
    return events


async def clear_existing_data(db: SQLiteAdapter, mode: str) -> None:
    """기존 position_session/position_trade 데이터 삭제"""
    # position_trade 먼저 삭제 (FK 제약)
    await db.execute(
        """
        DELETE FROM position_trade
        WHERE session_id IN (
            SELECT session_id FROM position_session WHERE scope_mode = ?
        )
        """,
        (mode.upper(),),
    )
    
    await db.execute(
        "DELETE FROM position_session WHERE scope_mode = ?",
        (mode.upper(),),
    )
    
    await db.commit()
    logger.info(f"기존 {mode} 데이터 삭제 완료")


async def migrate_trades(
    db: SQLiteAdapter, 
    events: list[dict[str, Any]], 
    dry_run: bool = False,
) -> dict[str, int]:
    """거래 이벤트를 position_session으로 마이그레이션"""
    
    stats = {
        "sessions_created": 0,
        "sessions_closed": 0,
        "trades_recorded": 0,
    }
    
    # 심볼별 현재 세션 추적
    open_sessions: dict[str, dict[str, Any]] = {}
    
    for event in events:
        symbol = event["symbol"]
        venue = event["venue"]
        mode = event["mode"]
        key = f"{mode}:{venue}:{symbol}"
        
        side = event["side"]
        qty = event["qty"]
        price = event["price"]
        realized_pnl = event["realized_pnl"]
        commission = event["commission"]
        
        if qty <= 0:
            continue
        
        session = open_sessions.get(key)
        
        if session is None:
            # 새 세션 생성
            session_id = str(uuid4())
            position_side = "LONG" if side == "BUY" else "SHORT"
            
            session = {
                "session_id": session_id,
                "mode": mode,
                "venue": venue,
                "symbol": symbol,
                "side": position_side,
                "opened_at": event["ts"],
                "initial_qty": qty,
                "max_qty": qty,
                "current_qty": qty,
                "realized_pnl": realized_pnl,
                "total_commission": commission,
                "trade_count": 1,
                "trades": [{
                    "event_id": event["event_id"],
                    "action": "ENTRY",
                    "qty": qty,
                    "price": price,
                    "realized_pnl": realized_pnl,
                    "commission": commission,
                    "position_qty_after": qty,
                    "created_at": event["ts"],
                }],
            }
            
            open_sessions[key] = session
            stats["sessions_created"] += 1
            stats["trades_recorded"] += 1
            
            logger.debug(f"새 세션 생성: {symbol} {position_side} qty={qty}")
            
        else:
            # 기존 세션에 거래 추가
            position_side = session["side"]
            current_qty = session["current_qty"]
            
            # 진입 방향과 거래 방향 비교
            is_same_direction = (
                (position_side == "LONG" and side == "BUY") or
                (position_side == "SHORT" and side == "SELL")
            )
            
            if is_same_direction:
                # 포지션 추가
                new_qty = current_qty + qty
                action = "ADD"
            else:
                # 포지션 청산
                new_qty = current_qty - qty
                if new_qty < 0:
                    new_qty = Decimal("0")
                action = "REDUCE" if new_qty > 0 else "EXIT"
            
            # 세션 업데이트
            session["current_qty"] = new_qty
            session["max_qty"] = max(session["max_qty"], new_qty)
            session["realized_pnl"] += realized_pnl
            session["total_commission"] += commission
            session["trade_count"] += 1
            
            session["trades"].append({
                "event_id": event["event_id"],
                "action": action,
                "qty": qty,
                "price": price,
                "realized_pnl": realized_pnl,
                "commission": commission,
                "position_qty_after": new_qty,
                "created_at": event["ts"],
            })
            
            stats["trades_recorded"] += 1
            
            logger.debug(f"거래 추가: {symbol} {action} qty={qty} → {new_qty}")
            
            # 세션 종료
            if new_qty <= 0:
                session["closed_at"] = event["ts"]
                session["close_reason"] = "TRADE"
                session["status"] = "CLOSED"
                
                # DB에 저장 후 세션 제거
                if not dry_run:
                    await save_session(db, session)
                
                del open_sessions[key]
                stats["sessions_closed"] += 1
                
                logger.debug(f"세션 종료: {symbol} PnL={session['realized_pnl']}")
    
    # 아직 열린 세션 저장
    for session in open_sessions.values():
        session["status"] = "OPEN"
        if not dry_run:
            await save_session(db, session)
    
    return stats


async def save_session(db: SQLiteAdapter, session: dict[str, Any]) -> None:
    """세션 및 거래 저장"""
    now = datetime.now(timezone.utc).isoformat()
    
    # position_session 저장
    await db.execute(
        """
        INSERT INTO position_session (
            session_id, scope_mode, scope_venue, symbol, side, status,
            opened_at, closed_at, initial_qty, max_qty,
            realized_pnl, total_commission, trade_count, close_reason,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session["session_id"],
            session["mode"],
            session["venue"],
            session["symbol"],
            session["side"],
            session.get("status", "OPEN"),
            session["opened_at"],
            session.get("closed_at"),
            str(session["initial_qty"]),
            str(session["max_qty"]),
            str(session["realized_pnl"]),
            str(session["total_commission"]),
            session["trade_count"],
            session.get("close_reason"),
            now,
            now,
        ),
    )
    
    # position_trade 저장
    for trade in session["trades"]:
        await db.execute(
            """
            INSERT INTO position_trade (
                session_id, trade_event_id, action, qty, price,
                realized_pnl, commission, position_qty_after, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session["session_id"],
                trade["event_id"],
                trade["action"],
                str(trade["qty"]),
                str(trade["price"]),
                str(trade["realized_pnl"]),
                str(trade["commission"]),
                str(trade["position_qty_after"]),
                trade["created_at"],
            ),
        )
    
    await db.commit()


async def main(mode: str, dry_run: bool = False) -> None:
    """마이그레이션 실행"""
    logger.info(f"=== Position History 마이그레이션 시작 ===")
    logger.info(f"Mode: {mode.upper()}")
    logger.info(f"Dry Run: {dry_run}")
    
    # DB 경로 결정
    db_path = Paths.TEST_DB if mode.lower() == "testnet" else Paths.PROD_DB
    logger.info(f"DB: {db_path}")
    
    if not db_path.exists():
        logger.error(f"DB 파일이 존재하지 않습니다: {db_path}")
        return
    
    async with SQLiteAdapter(db_path) as db:
        # 테이블 존재 확인
        try:
            await db.fetchone("SELECT 1 FROM position_session LIMIT 1")
        except Exception:
            logger.error("position_session 테이블이 없습니다. migrate_ledger.py를 먼저 실행하세요.")
            return
        
        # 기존 TradeExecuted 이벤트 조회
        events = await get_trade_events(db, mode)
        logger.info(f"TradeExecuted 이벤트 수: {len(events)}")
        
        if not events:
            logger.info("마이그레이션할 이벤트가 없습니다.")
            return
        
        # 기존 데이터 삭제 (dry_run 아닐 때만)
        if not dry_run:
            await clear_existing_data(db, mode)
        
        # 마이그레이션 실행
        stats = await migrate_trades(db, events, dry_run)
        
        logger.info(f"=== 마이그레이션 완료 ===")
        logger.info(f"생성된 세션: {stats['sessions_created']}")
        logger.info(f"종료된 세션: {stats['sessions_closed']}")
        logger.info(f"열린 세션: {stats['sessions_created'] - stats['sessions_closed']}")
        logger.info(f"기록된 거래: {stats['trades_recorded']}")
        
        if dry_run:
            logger.info("(Dry Run - 실제 저장되지 않음)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Position History 마이그레이션")
    parser.add_argument(
        "--mode",
        choices=["testnet", "production"],
        default="testnet",
        help="거래 모드 (기본: testnet)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 저장하지 않고 시뮬레이션만 실행",
    )
    
    args = parser.parse_args()
    asyncio.run(main(args.mode, args.dry_run))
