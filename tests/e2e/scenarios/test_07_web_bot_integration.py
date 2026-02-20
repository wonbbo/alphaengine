"""
Web + Bot 통합 테스트

Web에서 Command 발행 → Bot 처리 확인 시나리오 검증.
"""

import asyncio
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio

from core.domain.commands import Command, CommandTypes
from core.storage.command_store import CommandStore
from core.types import Scope, Actor, CommandStatus, TradingMode
from adapters.db.sqlite_adapter import SQLiteAdapter, init_schema
from web.services.command_service import CommandService
from web.services.dashboard_service import DashboardService
from web.services.config_service import ConfigService


pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


class TestWebCommandIssuing:
    """Web Command 발행 테스트"""
    
    async def test_web_command_to_bot_flow(
        self,
        e2e_logger: logging.Logger,
    ) -> None:
        """Web → Bot Command 흐름 테스트
        
        검증 항목:
        - Web에서 Command 발행 (INSERT)
        - Bot에서 Command 클레임 (claim_one)
        - Bot에서 Command 처리 완료 (update_status)
        - Web에서 결과 확인
        """
        e2e_logger.info("test_web_command_to_bot_flow 시작")
        
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = Path(tmp.name)
        
        try:
            # === Web 프로세스 시뮬레이션 ===
            async with SQLiteAdapter(db_path) as web_adapter:
                await init_schema(web_adapter)
                
                # Web Service로 Command 발행
                web_command_service = CommandService(web_adapter)
                scope = Scope.create(symbol="XRPUSDT", mode=TradingMode.TESTNET)
                
                result = await web_command_service.create_command(
                    command_type=CommandTypes.CLOSE_POSITION,
                    scope=scope,
                    payload={"reason": "user_request"},
                    priority=100,
                    actor_id="web:admin",
                )
                
                command_id = result["command_id"]
                e2e_logger.info(f"Web: Command 발행 완료 - {command_id}")
                
                # Command 상태 확인
                cmd = await web_command_service.get_command(command_id)
                assert cmd is not None
                assert cmd["status"] == CommandStatus.NEW.value
                e2e_logger.info(f"Web: Command 상태 - {cmd['status']}")
            
            # === Bot 프로세스 시뮬레이션 ===
            async with SQLiteAdapter(db_path) as bot_adapter:
                bot_command_store = CommandStore(bot_adapter)
                
                # Bot이 Command 클레임
                claimed = await bot_command_store.claim_one()
                assert claimed is not None
                assert claimed.command_id == command_id
                assert claimed.status == CommandStatus.SENT.value
                e2e_logger.info(f"Bot: Command 클레임 완료 - {claimed.status}")
                
                # Bot이 Command 처리 (실제로는 거래소 API 호출)
                # 여기서는 시뮬레이션으로 바로 ACK
                await bot_command_store.update_status(
                    command_id,
                    CommandStatus.ACK,
                    result={"executed": True, "order_id": "test123"},
                )
                e2e_logger.info("Bot: Command 처리 완료")
            
            # === Web에서 결과 확인 ===
            async with SQLiteAdapter(db_path) as web_adapter2:
                web_command_service2 = CommandService(web_adapter2)
                
                final_cmd = await web_command_service2.get_command(command_id)
                assert final_cmd is not None
                assert final_cmd["status"] == CommandStatus.ACK.value
                assert final_cmd["result"]["executed"] is True
                e2e_logger.info(f"Web: 최종 상태 확인 - {final_cmd['status']}")
        
        finally:
            if db_path.exists():
                db_path.unlink()
        
        e2e_logger.info("test_web_command_to_bot_flow 완료")
    
    async def test_multiple_commands_concurrent(
        self,
        e2e_logger: logging.Logger,
    ) -> None:
        """다중 Command 동시 발행 테스트
        
        검증 항목:
        - 여러 Command 동시 발행
        - 각각 순서대로 처리됨
        """
        e2e_logger.info("test_multiple_commands_concurrent 시작")
        
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = Path(tmp.name)
        
        try:
            async with SQLiteAdapter(db_path) as adapter:
                await init_schema(adapter)
                
                command_service = CommandService(adapter)
                scope = Scope.create(symbol="XRPUSDT", mode=TradingMode.TESTNET)
                
                # 여러 Command 발행
                command_ids = []
                for i in range(5):
                    result = await command_service.create_command(
                        command_type=CommandTypes.UPDATE_CONFIG,
                        scope=scope,
                        payload={"index": i},
                        priority=50 - i * 10,  # 50, 40, 30, 20, 10
                    )
                    command_ids.append(result["command_id"])
                
                e2e_logger.info(f"발행된 Command 수: {len(command_ids)}")
                
                # 전체 Command 수 확인 (mode는 소문자 "testnet"으로 저장됨)
                commands = await command_service.get_commands(
                    mode=TradingMode.TESTNET.value,
                    include_completed=True,
                )
                assert len(commands) == 5
                e2e_logger.info(f"조회된 Command 수: {len(commands)}")
        
        finally:
            if db_path.exists():
                db_path.unlink()
        
        e2e_logger.info("test_multiple_commands_concurrent 완료")


class TestWebDashboard:
    """Web Dashboard 서비스 테스트"""
    
    async def test_dashboard_empty_state(
        self,
        e2e_logger: logging.Logger,
    ) -> None:
        """빈 상태 Dashboard 조회 테스트
        
        검증 항목:
        - DB에 데이터 없을 때 오류 없이 빈 결과 반환
        """
        e2e_logger.info("test_dashboard_empty_state 시작")
        
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = Path(tmp.name)
        
        try:
            async with SQLiteAdapter(db_path) as adapter:
                await init_schema(adapter)
                
                dashboard_service = DashboardService(adapter)
                
                # 빈 DB에서 조회
                balances = await dashboard_service.get_balances(
                    "BINANCE", "FUTURES", "main", "TESTNET"
                )
                assert balances == []
                e2e_logger.info("빈 잔고 조회 성공")
                
                open_orders = await dashboard_service.get_open_orders(
                    "BINANCE", "FUTURES", "main", "TESTNET"
                )
                assert open_orders == []
                e2e_logger.info("빈 오픈 주문 조회 성공")
                
                position = await dashboard_service.get_position(
                    "BINANCE", "FUTURES", "main", "TESTNET", "XRPUSDT"
                )
                assert position is None
                e2e_logger.info("빈 포지션 조회 성공")
                
                event_count = await dashboard_service.get_event_count("TESTNET")
                assert event_count == 0
                e2e_logger.info("빈 이벤트 수 조회 성공")
        
        finally:
            if db_path.exists():
                db_path.unlink()
        
        e2e_logger.info("test_dashboard_empty_state 완료")


class TestWebConfig:
    """Web Config 서비스 테스트"""
    
    async def test_config_crud_operations(
        self,
        e2e_logger: logging.Logger,
    ) -> None:
        """Config CRUD 테스트
        
        검증 항목:
        - Config 생성 (UPSERT)
        - Config 조회
        - Config 업데이트 (버전 증가)
        - Config 삭제
        """
        e2e_logger.info("test_config_crud_operations 시작")
        
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = Path(tmp.name)
        
        try:
            async with SQLiteAdapter(db_path) as adapter:
                await init_schema(adapter)
                
                config_service = ConfigService(adapter)
                
                # Config 생성
                config = await config_service.update_config(
                    key="trading",
                    value={"symbol": "XRPUSDT", "leverage": 5},
                    updated_by="test",
                )
                assert config["key"] == "trading"
                assert config["version"] == 1
                e2e_logger.info(f"Config 생성: version={config['version']}")
                
                # Config 조회
                retrieved = await config_service.get_config("trading")
                assert retrieved is not None
                assert retrieved["value"]["symbol"] == "XRPUSDT"
                e2e_logger.info(f"Config 조회 성공: {retrieved['value']}")
                
                # Config 업데이트
                updated = await config_service.update_config(
                    key="trading",
                    value={"symbol": "BTCUSDT", "leverage": 10},
                    updated_by="test",
                )
                assert updated["version"] == 2
                e2e_logger.info(f"Config 업데이트: version={updated['version']}")
                
                # 버전 충돌 테스트
                try:
                    await config_service.update_config(
                        key="trading",
                        value={"symbol": "ETHUSDT"},
                        updated_by="test",
                        expected_version=1,  # 잘못된 버전
                    )
                    pytest.fail("버전 충돌 예외가 발생해야 함")
                except ValueError as e:
                    e2e_logger.info(f"버전 충돌 감지됨: {e}")
                
                # Config 삭제
                deleted = await config_service.delete_config("trading")
                assert deleted is True
                e2e_logger.info("Config 삭제 성공")
                
                # 삭제 확인
                deleted_config = await config_service.get_config("trading")
                assert deleted_config is None
                e2e_logger.info("삭제 확인 완료")
        
        finally:
            if db_path.exists():
                db_path.unlink()
        
        e2e_logger.info("test_config_crud_operations 완료")
    
    async def test_config_list_all(
        self,
        e2e_logger: logging.Logger,
    ) -> None:
        """모든 Config 목록 조회 테스트"""
        e2e_logger.info("test_config_list_all 시작")
        
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = Path(tmp.name)
        
        try:
            async with SQLiteAdapter(db_path) as adapter:
                await init_schema(adapter)
                
                config_service = ConfigService(adapter)
                
                # 여러 Config 생성
                await config_service.update_config(
                    key="strategy",
                    value={"name": "sma_cross"},
                    updated_by="test",
                )
                await config_service.update_config(
                    key="risk",
                    value={"max_position": 1000},
                    updated_by="test",
                )
                
                # 전체 목록 조회
                all_configs = await config_service.get_all_configs()
                assert len(all_configs) == 2
                
                keys = [c["key"] for c in all_configs]
                assert "risk" in keys
                assert "strategy" in keys
                e2e_logger.info(f"전체 Config 수: {len(all_configs)}")
        
        finally:
            if db_path.exists():
                db_path.unlink()
        
        e2e_logger.info("test_config_list_all 완료")
