"""
자산 서비스

projection_balance 기반 자산 조회.
가격 캐시: Bot이 주기적으로 config_store에 저장한 가격 사용 (Hybrid 방식).
"""

import logging
from decimal import Decimal
from typing import Any

from adapters.db.sqlite_adapter import SQLiteAdapter
from core.ledger.store import LedgerStore
from core.storage.config_store import ConfigStore

logger = logging.getLogger(__name__)

# 하드코딩된 기본 환율 (캐시 실패 시 최후의 폴백)
_DEFAULT_RATES = {
    "BNB": Decimal("650"),
    "BTC": Decimal("100000"),
    "ETH": Decimal("3500"),
    "XRP": Decimal("1.5"),
    "USDC": Decimal("1"),
}


async def get_usdt_rate_from_cache(
    config_store: ConfigStore,
    asset: str,
) -> Decimal:
    """자산의 USDT 환율 조회 (config_store 캐시 사용)
    
    Bot의 PriceCachePoller가 주기적으로 저장한 가격을 사용.
    캐시에 없으면 기본값 사용.
    
    Args:
        config_store: 설정 저장소
        asset: 자산 코드 (예: BNB, BTC)
        
    Returns:
        1 ASSET = ? USDT
    """
    if asset == "USDT":
        return Decimal("1")
    
    symbol = f"{asset}USDT"
    
    # config_store에서 캐시된 가격 조회
    cached_price = await config_store.get_price(symbol)
    if cached_price:
        try:
            return Decimal(cached_price)
        except Exception:
            pass
    
    # 캐시에 없으면 기본값 사용 (정확도 낮음)
    default_rate = _DEFAULT_RATES.get(asset, Decimal("1"))
    logger.debug(
        f"가격 캐시 없음, 기본값 사용: {asset} = {default_rate} USDT"
    )
    return default_rate


def get_usdt_rate(asset: str) -> Decimal:
    """자산의 USDT 환율 조회 (동기 버전 - 기본값만 반환)
    
    비동기 컨텍스트에서는 get_usdt_rate_from_cache() 사용 권장.
    
    Args:
        asset: 자산 코드 (예: BNB, BTC)
        
    Returns:
        1 ASSET = ? USDT
    """
    if asset == "USDT":
        return Decimal("1")
    
    return _DEFAULT_RATES.get(asset, Decimal("1"))


class AssetService:
    """자산 현황 서비스
    
    실시간 잔고는 projection_balance 테이블 사용.
    Ledger 관련 조회는 LedgerStore 활용.
    가격 조회는 config_store 캐시 사용 (Bot이 주기적으로 업데이트).
    """
    
    def __init__(self, db: SQLiteAdapter):
        self.db = db
        self.ledger_store = LedgerStore(db)
        self.config_store = ConfigStore(db)
    
    async def get_portfolio(self, mode: str) -> list[dict[str, Any]]:
        """포트폴리오 현황 조회
        
        projection_balance 테이블에서 실시간 잔고 조회.
        SPOT 데이터가 없으면 Ledger(account_balance)에서 보완.
        
        Args:
            mode: TESTNET 또는 PRODUCTION
            
        Returns:
            Venue/Asset별 잔액 현황
        """
        # 1. projection_balance에서 조회 (실시간 동기화된 데이터)
        rows = await self.db.fetchall(
            """
            SELECT 
                scope_venue as venue,
                asset,
                CAST(free AS REAL) + CAST(locked AS REAL) as balance,
                CAST(free AS REAL) as free,
                CAST(locked AS REAL) as locked,
                updated_at as last_updated
            FROM projection_balance
            WHERE scope_mode = ?
            ORDER BY scope_venue, asset
            """,
            (mode,),
        )
        
        portfolio = [
            {
                "venue": row[0],
                "asset": row[1],
                "balance": row[2] or 0,
                "free": row[3] or 0,
                "locked": row[4] or 0,
                "last_updated": row[5],
                "source": "projection",
            }
            for row in rows
        ]
        
        # 2. SPOT 데이터가 없으면 Ledger에서 보완
        has_spot = any(p.get("venue") == "SPOT" for p in portfolio)
        if not has_spot:
            ledger_spot = await self._get_spot_from_ledger(mode)
            portfolio.extend(ledger_spot)
        
        return portfolio
    
    async def _get_spot_from_ledger(self, mode: str) -> list[dict[str, Any]]:
        """Ledger에서 SPOT 잔고 조회
        
        projection_balance에 SPOT 데이터가 없을 때 account_balance에서 조회.
        ASSET:BINANCE_SPOT:* 계정의 잔고를 반환.
        """
        rows = await self.db.fetchall(
            """
            SELECT 
                account_id,
                CAST(balance AS REAL) as balance
            FROM account_balance
            WHERE scope_mode = ?
              AND account_id LIKE 'ASSET:BINANCE_SPOT:%'
              AND balance != '0'
            """,
            (mode,),
        )
        
        result = []
        for row in rows:
            account_id = row[0]
            balance = row[1] or 0
            
            # ASSET:BINANCE_SPOT:USDT -> USDT
            asset = account_id.replace("ASSET:BINANCE_SPOT:", "")
            
            result.append({
                "venue": "SPOT",
                "asset": asset,
                "balance": balance,
                "free": balance,
                "locked": 0,
                "last_updated": None,
                "source": "ledger",
            })
        
        return result
    
    async def get_portfolio_summary(self, mode: str) -> dict[str, Any]:
        """포트폴리오 요약
        
        projection_balance에서 Venue별 자산 합계.
        모든 자산을 USDT로 환산하여 합산.
        가격은 Bot이 config_store에 캐시한 값 사용 (Hybrid 방식).
        
        Args:
            mode: TESTNET 또는 PRODUCTION
            
        Returns:
            assets, spot_total_usdt, futures_total_usdt, total_usdt 포함 응답
        """
        portfolio = await self.get_portfolio(mode)
        
        # 잔액이 0인 자산 필터링
        portfolio = [
            p for p in portfolio
            if (p.get("balance") or 0) != 0
        ]
        
        # 각 자산에 USDT 환산 값 추가 (캐시된 가격 사용)
        for p in portfolio:
            asset = p.get("asset", "USDT")
            balance = Decimal(str(p.get("balance", 0)))
            usdt_rate = await get_usdt_rate_from_cache(self.config_store, asset)
            p["usdt_value"] = float(balance * usdt_rate)
            p["usdt_rate"] = float(usdt_rate)
        
        # Venue별 USDT 환산 합계 (모든 자산 포함)
        spot_total = sum(
            p.get("usdt_value", 0)
            for p in portfolio 
            if p.get("venue") == "SPOT"
        )
        futures_total = sum(
            p.get("usdt_value", 0)
            for p in portfolio 
            if p.get("venue") == "FUTURES"
        )
        
        # 대시보드 표시용으로 venue 변환
        for p in portfolio:
            venue = p.get("venue", "")
            if venue == "FUTURES":
                p["venue_display"] = "선물"
            elif venue == "SPOT":
                p["venue_display"] = "현물"
            else:
                p["venue_display"] = venue
        
        return {
            "assets": portfolio,
            "spot_total_usdt": spot_total,
            "futures_total_usdt": futures_total,
            "total_usdt": spot_total + futures_total,
        }
    
    async def get_trial_balance(self, mode: str) -> list[dict[str, Any]]:
        """시산표 조회
        
        Args:
            mode: TESTNET 또는 PRODUCTION
            
        Returns:
            계정별 잔액 (잔액이 0인 계정 제외)
        """
        trial_balance = await self.ledger_store.get_trial_balance(mode)
        
        # 잔액이 0인 계정 필터링
        return [
            item for item in trial_balance
            if (item.get("balance") or 0) != 0
        ]
