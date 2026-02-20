#!/usr/bin/env python3
"""DB 상태 확인 스크립트"""

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from adapters.db.sqlite_adapter import SQLiteAdapter
from core.storage.event_store import EventStore


async def main():
    db_path = PROJECT_ROOT / "data" / "alphaengine_test.db"
    
    async with SQLiteAdapter(db_path) as db:
        es = EventStore(db)
        total = await es.count_all()
        last_seq = await es.get_last_seq()
        
        print(f"DB Path: {db_path}")
        print(f"Total events: {total}")
        print(f"Last seq: {last_seq}")
        
        # 최근 이벤트 5개 출력
        events = await es.get_since(0, limit=10)
        print(f"\nRecent events ({len(events)}):")
        for e in events:
            print(f"  - seq: ?, event_id: {e.event_id[:8]}, type: {e.event_type}, asset: {e.payload.get('asset', 'N/A')}")


if __name__ == "__main__":
    asyncio.run(main())
