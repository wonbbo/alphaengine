"""
TransferManager 단위 테스트

입출금 요청 시 Bot 모니터만 실행하는 구조 검증.
실행 태스크(create_task) 제거 후 request_deposit/request_withdraw는 Transfer만 반환하는지,
_resume_transfer가 Transfer를 반환하는지 검증.
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.transfer.manager import TransferManager
from bot.transfer.repository import Transfer
from core.types import TransferStatus, TransferType


def _make_transfer(
    transfer_id: str = "tf-test-001",
    transfer_type: TransferType = TransferType.DEPOSIT,
    status: TransferStatus = TransferStatus.PENDING,
    requested_amount: Decimal = Decimal("10000"),
    current_step: int = 1,
    total_steps: int = 6,
) -> Transfer:
    """테스트용 Transfer 생성"""
    return Transfer(
        transfer_id=transfer_id,
        transfer_type=transfer_type,
        status=status,
        requested_amount=requested_amount,
        requested_at=datetime.now(timezone.utc),
        requested_by="test",
        current_step=current_step,
        total_steps=total_steps,
        actual_amount=None,
        fee_amount=None,
        upbit_order_id=None,
        binance_order_id=None,
        blockchain_txid=None,
        completed_at=None,
        error_message=None,
        created_at=None,
        updated_at=None,
    )


@pytest.fixture
def mock_db() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_upbit() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_binance() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_event_store() -> AsyncMock:
    store = AsyncMock()
    store.append = AsyncMock(return_value=True)
    return store


@pytest.fixture
def mock_scope() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_repository() -> AsyncMock:
    repo = AsyncMock()
    repo.get_pending_transfers = AsyncMock(return_value=[])
    repo.get = AsyncMock(side_effect=lambda tid: _make_transfer(transfer_id=tid))
    return repo


@pytest.fixture
def transfer_manager(
    mock_db: AsyncMock,
    mock_upbit: AsyncMock,
    mock_binance: AsyncMock,
    mock_event_store: AsyncMock,
    mock_scope: MagicMock,
    mock_repository: AsyncMock,
) -> TransferManager:
    """TransferManager 인스턴스 (의존성 모킹)"""
    manager = TransferManager(
        db=mock_db,
        upbit=mock_upbit,
        binance=mock_binance,
        event_store=mock_event_store,
        scope=mock_scope,
        binance_trx_address="TBinanceTRX",
        upbit_trx_address="TUpbitTRX",
    )
    manager.repository = mock_repository
    return manager


class TestRequestDepositNoExecute:
    """request_deposit는 실행 태스크를 생성하지 않고 Transfer만 반환하는지 검증"""

    @pytest.mark.asyncio
    async def test_request_deposit_returns_transfer_without_create_task(
        self,
        transfer_manager: TransferManager,
        mock_repository: AsyncMock,
    ) -> None:
        # get_deposit_status: can_deposit True, max_deposit_krw 충분
        transfer_manager.deposit_handler.get_deposit_status = AsyncMock(
            return_value={
                "can_deposit": True,
                "max_deposit_krw": "100000",
            }
        )
        created = _make_transfer(
            transfer_id="tf-deposit-1",
            transfer_type=TransferType.DEPOSIT,
            requested_amount=Decimal("50000"),
            total_steps=6,
        )
        mock_repository.create = AsyncMock(return_value=created)

        with patch("bot.transfer.manager.asyncio.create_task") as mock_create_task:
            result = await transfer_manager.request_deposit(
                amount_krw=Decimal("50000"),
                requested_by="test",
            )

        assert result is not None
        assert result.transfer_id == "tf-deposit-1"
        assert result.transfer_type == TransferType.DEPOSIT
        # 실행 태스크가 생성되지 않음 (Bot 모니터만 실행)
        mock_create_task.assert_not_called()


class TestRequestWithdrawNoExecute:
    """request_withdraw는 실행 태스크를 생성하지 않고 Transfer만 반환하는지 검증"""

    @pytest.mark.asyncio
    async def test_request_withdraw_returns_transfer_without_create_task(
        self,
        transfer_manager: TransferManager,
        mock_repository: AsyncMock,
    ) -> None:
        transfer_manager.withdraw_handler.get_withdraw_status = AsyncMock(
            return_value={"can_withdraw": True}
        )
        created = _make_transfer(
            transfer_id="tf-withdraw-1",
            transfer_type=TransferType.WITHDRAW,
            requested_amount=Decimal("71"),
            total_steps=7,
        )
        mock_repository.create = AsyncMock(return_value=created)

        with patch("bot.transfer.manager.asyncio.create_task") as mock_create_task:
            result = await transfer_manager.request_withdraw(
                amount_usdt=Decimal("71"),
                requested_by="test",
            )

        assert result is not None
        assert result.transfer_id == "tf-withdraw-1"
        assert result.transfer_type == TransferType.WITHDRAW
        mock_create_task.assert_not_called()


class TestResumeTransferReturnsTransfer:
    """_resume_transfer가 Deposit/Withdraw 모두 Transfer를 반환하는지 검증"""

    @pytest.mark.asyncio
    async def test_resume_transfer_deposit_returns_transfer(
        self,
        transfer_manager: TransferManager,
    ) -> None:
        transfer = _make_transfer(
            transfer_id="tf-resume-dep",
            transfer_type=TransferType.DEPOSIT,
            current_step=1,
        )
        expected = _make_transfer(
            transfer_id="tf-resume-dep",
            transfer_type=TransferType.DEPOSIT,
            status=TransferStatus.COMPLETED,
            current_step=6,
        )
        transfer_manager.deposit_handler.execute = AsyncMock(return_value=expected)

        result = await transfer_manager._resume_transfer(transfer)

        assert result is expected
        assert result.transfer_id == "tf-resume-dep"
        transfer_manager.deposit_handler.execute.assert_called_once_with(transfer)

    @pytest.mark.asyncio
    async def test_resume_transfer_withdraw_returns_transfer(
        self,
        transfer_manager: TransferManager,
    ) -> None:
        transfer = _make_transfer(
            transfer_id="tf-resume-wdw",
            transfer_type=TransferType.WITHDRAW,
            current_step=1,
            total_steps=7,
        )
        expected = _make_transfer(
            transfer_id="tf-resume-wdw",
            transfer_type=TransferType.WITHDRAW,
            status=TransferStatus.COMPLETED,
            current_step=7,
            total_steps=7,
        )
        transfer_manager.withdraw_handler.execute = AsyncMock(return_value=expected)

        result = await transfer_manager._resume_transfer(transfer)

        assert result is expected
        assert result.transfer_id == "tf-resume-wdw"
        transfer_manager.withdraw_handler.execute.assert_called_once_with(transfer)


class TestExecuteMethodsRemoved:
    """_execute_deposit, _execute_withdraw가 제거되었는지 검증"""

    def test_no_execute_deposit_method(self) -> None:
        assert not hasattr(TransferManager, "_execute_deposit"), (
            "_execute_deposit should be removed; execution is done by bot monitor only."
        )

    def test_no_execute_withdraw_method(self) -> None:
        assert not hasattr(TransferManager, "_execute_withdraw"), (
            "_execute_withdraw should be removed; execution is done by bot monitor only."
        )
