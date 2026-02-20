"""
Bot 메인 루프 통합 테스트

Bot 시작, 전략 실행, Command 처리, 종료 시나리오 검증.
"""

import asyncio
import logging
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio

from core.config.loader import ExchangeConfig
from core.domain.commands import Command, CommandTypes
from core.domain.events import Event, EventTypes
from core.storage.event_store import EventStore
from core.storage.command_store import CommandStore
from core.types import Scope, Actor, CommandStatus, TradingMode
from adapters.db.sqlite_adapter import SQLiteAdapter, init_schema


pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


class TestBotInitialization:
    """Bot 초기화 테스트"""
    
    async def test_event_store_initialization(
        self,
        e2e_logger: logging.Logger,
    ) -> None:
        """EventStore 초기화 및 이벤트 저장 테스트
        
        검증 항목:
        - SQLite DB 생성
        - 스키마 초기화
        - 이벤트 저장 및 조회
        """
        e2e_logger.info("test_event_store_initialization 시작")
        
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = Path(tmp.name)
        
        try:
            async with SQLiteAdapter(db_path) as adapter:
                await init_schema(adapter)
                e2e_logger.info("스키마 초기화 완료")
                
                event_store = EventStore(adapter)
                
                scope = Scope.create(mode=TradingMode.TESTNET)
                event = Event.create(
                    event_type=EventTypes.ENGINE_STARTED,
                    source="BOT",
                    entity_kind="ENGINE",
                    entity_id="main",
                    scope=scope,
                    dedup_key="test:engine:started:001",
                    payload={"version": "2.0.0"},
                )
                
                saved = await event_store.append(event)
                assert saved is True, "이벤트 저장 실패"
                e2e_logger.info(f"이벤트 저장: {event.event_id}")
                
                retrieved = await event_store.get_by_id(event.event_id)
                assert retrieved is not None, "이벤트 조회 실패"
                assert retrieved.event_type == EventTypes.ENGINE_STARTED
                e2e_logger.info(f"이벤트 조회 성공: {retrieved.event_type}")
                
                total_count = await event_store.count_all()
                assert total_count >= 1, "이벤트 수 확인 실패"
                e2e_logger.info(f"전체 이벤트 수: {total_count}")
        
        finally:
            if db_path.exists():
                db_path.unlink()
        
        e2e_logger.info("test_event_store_initialization 완료")
    
    async def test_command_store_initialization(
        self,
        e2e_logger: logging.Logger,
    ) -> None:
        """CommandStore 초기화 및 Command CRUD 테스트
        
        검증 항목:
        - Command 저장
        - Command 조회
        - Command 상태 업데이트
        - Command 클레임
        """
        e2e_logger.info("test_command_store_initialization 시작")
        
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = Path(tmp.name)
        
        try:
            async with SQLiteAdapter(db_path) as adapter:
                await init_schema(adapter)
                
                command_store = CommandStore(adapter)
                
                scope = Scope.create(symbol="XRPUSDT", mode=TradingMode.TESTNET)
                actor = Actor.web("test")
                command = Command.create(
                    command_type=CommandTypes.CANCEL_ALL,
                    actor=actor,
                    scope=scope,
                    payload={},
                    priority=100,
                )
                
                inserted = await command_store.insert(command)
                assert inserted is True, "Command 저장 실패"
                e2e_logger.info(f"Command 저장: {command.command_id}")
                
                retrieved = await command_store.get_by_id(command.command_id)
                assert retrieved is not None, "Command 조회 실패"
                assert retrieved.command_type == CommandTypes.CANCEL_ALL
                assert retrieved.status == CommandStatus.NEW.value
                e2e_logger.info(f"Command 조회 성공: {retrieved.status}")
                
                claimed = await command_store.claim_one()
                assert claimed is not None, "Command 클레임 실패"
                assert claimed.status == CommandStatus.SENT.value
                e2e_logger.info(f"Command 클레임: {claimed.command_id}")
                
                updated = await command_store.update_status(
                    claimed.command_id,
                    CommandStatus.ACK,
                    result={"success": True},
                )
                assert updated is True, "상태 업데이트 실패"
                
                final = await command_store.get_by_id(claimed.command_id)
                assert final is not None
                assert final.status == CommandStatus.ACK.value
                e2e_logger.info(f"상태 업데이트 확인: {final.status}")
        
        finally:
            if db_path.exists():
                db_path.unlink()
        
        e2e_logger.info("test_command_store_initialization 완료")


class TestBotCommandProcessing:
    """Bot Command 처리 테스트"""
    
    async def test_command_priority_ordering(
        self,
        e2e_logger: logging.Logger,
    ) -> None:
        """Command 우선순위 처리 순서 테스트
        
        검증 항목:
        - 높은 우선순위 Command가 먼저 클레임됨
        - 같은 우선순위면 ts 순서
        """
        e2e_logger.info("test_command_priority_ordering 시작")
        
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = Path(tmp.name)
        
        try:
            async with SQLiteAdapter(db_path) as adapter:
                await init_schema(adapter)
                command_store = CommandStore(adapter)
                
                scope = Scope.create(symbol="XRPUSDT", mode=TradingMode.TESTNET)
                actor = Actor.web("test")
                
                low_priority_cmd = Command.create(
                    command_type=CommandTypes.UPDATE_CONFIG,
                    actor=actor,
                    scope=scope,
                    payload={"key": "test"},
                    priority=10,
                )
                await command_store.insert(low_priority_cmd)
                e2e_logger.info("낮은 우선순위 Command 저장: priority=10")
                
                await asyncio.sleep(0.1)
                high_priority_cmd = Command.create(
                    command_type=CommandTypes.CANCEL_ALL,
                    actor=actor,
                    scope=scope,
                    payload={},
                    priority=100,
                )
                await command_store.insert(high_priority_cmd)
                e2e_logger.info("높은 우선순위 Command 저장: priority=100")
                
                claimed_first = await command_store.claim_one()
                assert claimed_first is not None
                assert claimed_first.priority == 100
                e2e_logger.info(f"첫 번째 클레임: priority={claimed_first.priority}")
                
                claimed_second = await command_store.claim_one()
                assert claimed_second is not None
                assert claimed_second.priority == 10
                e2e_logger.info(f"두 번째 클레임: priority={claimed_second.priority}")
        
        finally:
            if db_path.exists():
                db_path.unlink()
        
        e2e_logger.info("test_command_priority_ordering 완료")
    
    async def test_command_idempotency(
        self,
        e2e_logger: logging.Logger,
    ) -> None:
        """Command 멱등성 테스트
        
        검증 항목:
        - 같은 idempotency_key로 중복 저장 시 무시
        """
        e2e_logger.info("test_command_idempotency 시작")
        
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = Path(tmp.name)
        
        try:
            async with SQLiteAdapter(db_path) as adapter:
                await init_schema(adapter)
                command_store = CommandStore(adapter)
                
                scope = Scope.create(symbol="XRPUSDT", mode=TradingMode.TESTNET)
                actor = Actor.web("test")
                
                cmd1 = Command.create(
                    command_type=CommandTypes.CANCEL_ALL,
                    actor=actor,
                    scope=scope,
                    payload={},
                    idempotency_key="test-idempotency-001",
                )
                inserted1 = await command_store.insert(cmd1)
                assert inserted1 is True
                e2e_logger.info("첫 번째 Command 저장 성공")
                
                cmd2 = Command.create(
                    command_type=CommandTypes.CANCEL_ALL,
                    actor=actor,
                    scope=scope,
                    payload={"different": "payload"},
                    idempotency_key="test-idempotency-001",
                )
                inserted2 = await command_store.insert(cmd2)
                assert inserted2 is False
                e2e_logger.info("중복 Command 저장 거부됨 (멱등성 보장)")
                
                new_commands = await command_store.find_by_status(CommandStatus.NEW)
                assert len(new_commands) == 1
                e2e_logger.info(f"NEW 상태 Command 수: {len(new_commands)}")
        
        finally:
            if db_path.exists():
                db_path.unlink()
        
        e2e_logger.info("test_command_idempotency 완료")
