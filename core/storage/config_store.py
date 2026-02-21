"""
ConfigStore - 런타임 설정 저장소

config_store 테이블을 통해 런타임 설정 관리.
Bot과 Web이 공유하는 설정을 저장/조회.

설정 키 구조:
- "engine": 엔진 설정 (mode, poll_interval_sec)
- "risk": 리스크 설정 (max_position_size, daily_loss_limit 등)
- "strategy": 전략 설정 (name, params)
"""

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from adapters.db.sqlite_adapter import SQLiteAdapter

logger = logging.getLogger(__name__)


# 기본 설정값
DEFAULT_CONFIGS: dict[str, dict[str, Any]] = {
    "engine": {
        "mode": "RUNNING",
        "poll_interval_sec": 30,
    },
    "risk": {
        # RiskGuard 규칙용 (0이면 비활성화)
        "max_position_size": "0",
        "daily_loss_limit": "0",
        "max_open_orders": 0,
        "min_balance": "0",
        # 전략 공통 리스크/리워드 설정 (손절 방식과 무관)
        "risk_per_trade": "0.02",  # 거래당 리스크 비율 (2%)
        "reward_ratio": "1.5",  # R:R = 1:1.5
        "partial_tp_ratio": "0.5",  # 부분 익절 비율 (50%)
        "equity_reset_trades": 50,  # 자산 재평가 주기 (거래 수)
        # 주의: atr_multiplier 등 손절 방식별 파라미터는 전략 params에서 관리
    },
    "strategy": {
        # 전략 설정 (secrets.yaml 대신 config_store에서 관리)
        "name": None,  # 전략 이름
        "module": None,  # 전략 모듈 경로
        "class": None,  # 전략 클래스명
        "params": {},  # 전략 파라미터
        "auto_start": False,  # 봇 시작 시 자동 시작
    },
    "strategy_state": {
        # Bot 재시작 시에도 유지되어야 하는 전략 상태
        "account_equity": "0",  # 50거래 재평가용 기준 자산
        "trade_count_since_reset": 0,  # 마지막 재평가 이후 거래 수
        "total_trade_count": 0,  # 총 거래 수
    },
    "bot_status": {
        # Bot 프로세스 상태 (Web에서 조회용)
        "is_running": False,  # Bot 실행 중 여부
        "strategy_name": None,  # 현재 전략 이름
        "strategy_running": False,  # 전략 실행 중 여부
        "last_heartbeat": None,  # 마지막 heartbeat 시간 (ISO 형식)
        "tick_count": 0,  # 누적 tick 수
        "started_at": None,  # Bot 시작 시간 (ISO 형식)
    },
    "transfer": {
        # 이체 관련 설정
        "min_deposit_krw": 5000,  # 최소 입금 금액 (KRW)
        "min_withdraw_usdt": 10,  # 최소 출금 금액 (USDT)
        "trx_fee": 1,  # TRX 출금 수수료
        "daily_withdraw_limit_usdt": 0,  # 일일 출금 한도 (0 = 무제한)
        "krw_deposit_hold_hours": 24,  # KRW 입금 후 대기 시간 (시간)
    },
    "bnb_fee": {
        # BNB 수수료 할인을 위한 자동 충전 설정
        "enabled": True,  # 자동 충전 활성화
        "min_bnb_ratio": "0.01",  # 최소 BNB 비율 (총 자산의 1%)
        "target_bnb_ratio": "0.02",  # 충전 목표 비율 (2%)
        "min_trigger_usdt": "10",  # 최소 트리거 금액 (USDT 환산)
        "check_interval_sec": 3600,  # 체크 주기 (1시간)
    },
}


class ConfigStore:
    """설정 저장소
    
    config_store 테이블을 읽고 쓰는 클래스.
    Bot에서 리스크 설정 등을 조회할 때 사용.
    
    Args:
        db: SQLiteAdapter 인스턴스
        
    사용 예시:
    ```python
    async with SQLiteAdapter(db_path) as db:
        config_store = ConfigStore(db)
        
        # 리스크 설정 조회
        risk_config = await config_store.get("risk")
        max_size = risk_config.get("max_position_size", "0")
        
        # 설정 업데이트
        await config_store.set("risk", {"max_position_size": "1000"})
    ```
    """
    
    def __init__(self, db: SQLiteAdapter):
        self.db = db
        self._cache: dict[str, dict[str, Any]] = {}
        self._cache_version: dict[str, int] = {}
    
    async def get(self, key: str, use_cache: bool = True) -> dict[str, Any]:
        """설정 조회
        
        Args:
            key: 설정 키 (engine, risk, strategy 등)
            use_cache: 캐시 사용 여부 (기본 True)
            
        Returns:
            설정 값 (dict). 없으면 기본값 반환.
        """
        # 캐시 확인
        if use_cache and key in self._cache:
            return self._cache[key]
        
        try:
            row = await self.db.fetchone(
                """
                SELECT value_json, version
                FROM config_store
                WHERE config_key = ?
                """,
                (key,),
            )
            
            if row:
                value = json.loads(row[0]) if isinstance(row[0], str) else row[0]
                version = row[1]
                
                # 캐시 갱신
                self._cache[key] = value
                self._cache_version[key] = version
                
                return value
            
        except Exception as e:
            logger.warning(f"Failed to get config '{key}': {e}")
        
        # 기본값 반환
        return DEFAULT_CONFIGS.get(key, {})
    
    async def get_value(
        self,
        key: str,
        field: str,
        default: Any = None,
    ) -> Any:
        """설정의 특정 필드 조회
        
        Args:
            key: 설정 키
            field: 필드 이름
            default: 기본값
            
        Returns:
            필드 값 또는 기본값
        """
        config = await self.get(key)
        return config.get(field, default)
    
    async def set(
        self,
        key: str,
        value: dict[str, Any],
        updated_by: str = "bot:system",
    ) -> bool:
        """설정 저장 (UPSERT)
        
        Args:
            key: 설정 키
            value: 설정 값
            updated_by: 업데이트 주체
            
        Returns:
            성공 여부
        """
        now = datetime.now(timezone.utc).isoformat()
        value_json = json.dumps(value, ensure_ascii=False)
        
        try:
            await self.db.execute(
                """
                INSERT INTO config_store (config_key, value_json, version, updated_by, created_at, updated_at)
                VALUES (?, ?, 1, ?, ?, ?)
                ON CONFLICT(config_key) DO UPDATE SET
                    value_json = excluded.value_json,
                    version = config_store.version + 1,
                    updated_by = excluded.updated_by,
                    updated_at = excluded.updated_at
                """,
                (key, value_json, updated_by, now, now),
            )
            await self.db.commit()
            
            # 캐시 무효화
            self._cache.pop(key, None)
            self._cache_version.pop(key, None)
            
            # heartbeat 로그는 너무 자주 발생하므로 표시하지 않음
            if updated_by != "bot:heartbeat":
                logger.info(f"Config '{key}' updated by {updated_by}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to set config '{key}': {e}")
            return False
    
    async def update_field(
        self,
        key: str,
        field: str,
        value: Any,
        updated_by: str = "bot:system",
    ) -> bool:
        """설정의 특정 필드만 업데이트
        
        Args:
            key: 설정 키
            field: 필드 이름
            value: 새 값
            updated_by: 업데이트 주체
            
        Returns:
            성공 여부
        """
        config = await self.get(key, use_cache=False)
        config[field] = value
        return await self.set(key, config, updated_by)
    
    async def get_all(self) -> dict[str, dict[str, Any]]:
        """모든 설정 조회
        
        Returns:
            {키: 값} 딕셔너리
        """
        result: dict[str, dict[str, Any]] = {}
        
        try:
            rows = await self.db.fetchall(
                """
                SELECT config_key, value_json
                FROM config_store
                ORDER BY config_key
                """
            )
            
            for row in rows:
                key = row[0]
                value = json.loads(row[1]) if isinstance(row[1], str) else row[1]
                result[key] = value
                
        except Exception as e:
            logger.warning(f"Failed to get all configs: {e}")
        
        return result
    
    async def ensure_defaults(self) -> None:
        """기본 설정이 없으면 생성
        
        봇 시작 시 호출하여 필수 설정이 존재하도록 보장.
        """
        for key, default_value in DEFAULT_CONFIGS.items():
            existing = await self.get(key, use_cache=False)
            
            # 기본값이 반환되었으면 (DB에 없음) 생성
            if existing == default_value:
                # DB에서 실제로 없는지 확인
                row = await self.db.fetchone(
                    "SELECT 1 FROM config_store WHERE config_key = ?",
                    (key,),
                )
                if not row:
                    await self.set(key, default_value, updated_by="bot:init")
                    logger.info(f"Created default config: {key}")
    
    def clear_cache(self) -> None:
        """캐시 초기화"""
        self._cache.clear()
        self._cache_version.clear()
    
    async def get_risk_config(self) -> dict[str, Any]:
        """리스크 설정 조회 (RiskGuard용)
        
        RiskGuard.config_getter로 사용할 수 있는 형태로 반환.
        
        Returns:
            리스크 설정 딕셔너리
        """
        return await self.get("risk")
    
    async def get_engine_mode(self) -> str:
        """엔진 모드 조회 (RiskGuard용)
        
        Returns:
            엔진 모드 문자열 (RUNNING, PAUSED, SAFE)
        """
        engine_config = await self.get("engine")
        return engine_config.get("mode", "RUNNING")
    
    # =========================================================================
    # 전략 상태 저장/복원 (Bot 재시작 시 유지)
    # =========================================================================
    
    async def get_strategy_state(self) -> dict[str, Any]:
        """저장된 전략 상태 조회
        
        Bot 시작 시 호출하여 이전 상태를 복원.
        
        Returns:
            전략 상태 딕셔너리 (account_equity, trade_count_since_reset 등)
        """
        return await self.get("strategy_state")
    
    async def save_strategy_state(
        self,
        account_equity: str,
        trade_count_since_reset: int,
        total_trade_count: int,
    ) -> bool:
        """전략 상태 저장
        
        50거래 재평가 시 또는 주기적으로 호출하여 상태 보존.
        
        Args:
            account_equity: 기준 자산 (문자열)
            trade_count_since_reset: 마지막 재평가 이후 거래 수
            total_trade_count: 총 거래 수
            
        Returns:
            성공 여부
        """
        state = {
            "account_equity": account_equity,
            "trade_count_since_reset": trade_count_since_reset,
            "total_trade_count": total_trade_count,
        }
        return await self.set("strategy_state", state, updated_by="bot:strategy")
    
    async def reset_strategy_state(self, initial_equity: str = "0") -> bool:
        """전략 상태 리셋
        
        새 전략 시작 또는 수동 리셋 시 호출.
        
        Args:
            initial_equity: 초기 자산 (기본값 "0", 실제 잔고로 설정 권장)
            
        Returns:
            성공 여부
        """
        return await self.save_strategy_state(
            account_equity=initial_equity,
            trade_count_since_reset=0,
            total_trade_count=0,
        )
    
    # =========================================================================
    # Bot 상태 저장/조회 (Web에서 전략 운용 여부 확인용)
    # =========================================================================
    
    async def get_bot_status(self) -> dict[str, Any]:
        """Bot 상태 조회
        
        Web에서 Bot 실행 여부, 전략 상태를 확인할 때 사용.
        
        Returns:
            Bot 상태 딕셔너리:
            - is_running: Bot 실행 중 여부
            - strategy_name: 현재 전략 이름 (없으면 None)
            - strategy_running: 전략 실행 중 여부
            - last_heartbeat: 마지막 heartbeat 시간
            - tick_count: 누적 tick 수
            - started_at: Bot 시작 시간
        """
        return await self.get("bot_status")
    
    async def update_bot_status(
        self,
        is_running: bool,
        strategy_name: str | None = None,
        strategy_running: bool = False,
        tick_count: int = 0,
        started_at: str | None = None,
    ) -> bool:
        """Bot 상태 업데이트 (heartbeat 포함)
        
        Bot 메인 루프에서 주기적으로 호출하여 상태 갱신.
        
        Args:
            is_running: Bot 실행 중 여부
            strategy_name: 현재 전략 이름
            strategy_running: 전략 실행 중 여부
            tick_count: 누적 tick 수
            started_at: Bot 시작 시간 (첫 호출 시에만 설정)
            
        Returns:
            성공 여부
        """
        now = datetime.now(timezone.utc).isoformat()
        
        status = {
            "is_running": is_running,
            "strategy_name": strategy_name,
            "strategy_running": strategy_running,
            "last_heartbeat": now,
            "tick_count": tick_count,
            "started_at": started_at,
        }
        return await self.set("bot_status", status, updated_by="bot:heartbeat")
    
    async def clear_bot_status(self) -> bool:
        """Bot 상태 초기화 (Bot 종료 시 호출)
        
        Bot 프로세스 종료 시 is_running을 False로 설정.
        
        Returns:
            성공 여부
        """
        current = await self.get("bot_status")
        current["is_running"] = False
        current["strategy_running"] = False
        current["last_heartbeat"] = datetime.now(timezone.utc).isoformat()
        return await self.set("bot_status", current, updated_by="bot:shutdown")


async def init_default_configs(db: SQLiteAdapter) -> None:
    """기본 설정 초기화
    
    봇/웹 시작 시 호출하여 기본 설정이 존재하도록 보장.
    
    Args:
        db: SQLiteAdapter 인스턴스
    """
    config_store = ConfigStore(db)
    await config_store.ensure_defaults()
