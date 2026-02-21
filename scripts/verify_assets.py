"""자산 서비스 검증 스크립트"""
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from adapters.db.sqlite_adapter import SQLiteAdapter
from web.services.asset_service import AssetService


async def main():
    db_path = PROJECT_ROOT / "data" / "alphaengine_prod.db"
    db = SQLiteAdapter(str(db_path))
    await db.connect()
    
    service = AssetService(db)
    
    print("=" * 60)
    print("=== Asset Service 검증 ===")
    print("=" * 60)
    
    # 포트폴리오 요약 조회
    summary = await service.get_portfolio_summary("PRODUCTION")
    
    print("\n[1] 자산 현황:")
    for asset in summary["assets"]:
        venue = asset.get("venue_display", asset.get("venue", "?"))
        asset_name = asset.get("asset", "?")
        balance = asset.get("balance", 0)
        print(f"  {venue:8} | {asset_name:6} | {balance:>15.8f}")
    
    print(f"\n[2] 합계:")
    print(f"  현물 USDT: {summary['spot_total_usdt']}")
    print(f"  선물 USDT: {summary['futures_total_usdt']}")
    print(f"  전체 USDT: {summary['total_usdt']}")
    
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
