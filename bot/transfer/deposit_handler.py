"""
입금 핸들러

Upbit KRW -> Binance Futures USDT 입금 흐름 처리.

입금 단계:
1. Upbit에서 TRX 매수 (KRW -> TRX)
2. Upbit에서 Binance로 TRX 출금
3. Binance Spot에서 TRX 입금 확인
4. Binance Spot에서 TRX -> USDT 환전
5. Binance Spot -> Futures USDT 내부 이체
"""

import asyncio
import logging
from decimal import Decimal
from typing import Any

from adapters.binance.rest_client import BinanceRestClient
from adapters.upbit.rest_client import UpbitRestClient
from bot.transfer.repository import Transfer, TransferRepository
from core.types import TransferStatus

logger = logging.getLogger(__name__)


class DepositHandler:
    """입금 핸들러
    
    Upbit KRW -> Binance Futures USDT 입금 처리.
    
    Args:
        upbit: Upbit REST 클라이언트
        binance: Binance REST 클라이언트
        repository: Transfer 저장소
        binance_trx_address: Binance TRX 입금 주소
    """
    
    TOTAL_STEPS = 6
    
    def __init__(
        self,
        upbit: UpbitRestClient,
        binance: BinanceRestClient,
        repository: TransferRepository,
        binance_trx_address: str,
    ):
        self.upbit = upbit
        self.binance = binance
        self.repository = repository
        self.binance_trx_address = binance_trx_address
    
    async def execute(self, transfer: Transfer) -> Transfer:
        """입금 실행
        
        현재 단계부터 순차적으로 처리.
        실패 시 해당 단계에서 중단하고 에러 기록.
        
        Args:
            transfer: Transfer 객체
            
        Returns:
            업데이트된 Transfer 객체
        """
        try:
            # 단계별 처리
            if transfer.current_step < 1:
                transfer = await self._step1_buy_trx(transfer)
            
            if transfer.current_step < 2:
                transfer = await self._step2_send_to_binance(transfer)
            
            if transfer.current_step < 3:
                transfer = await self._step3_wait_binance_deposit(transfer)
            
            if transfer.current_step < 4:
                transfer = await self._step4_sell_trx_to_usdt(transfer)
            
            if transfer.current_step < 5:
                transfer = await self._step5_transfer_to_futures(transfer)
            
            if transfer.current_step < 6:
                transfer = await self._step6_complete(transfer)
            
            return transfer
            
        except Exception as e:
            logger.error(
                f"Deposit failed: {transfer.transfer_id}",
                extra={"error": str(e), "step": transfer.current_step},
                exc_info=True,
            )
            await self.repository.update_status(
                transfer.transfer_id,
                TransferStatus.FAILED,
                error_message=str(e),
            )
            return await self.repository.get(transfer.transfer_id)  # type: ignore
    
    async def _step1_buy_trx(self, transfer: Transfer) -> Transfer:
        """Step 1: Upbit에서 TRX 매수"""
        logger.info(f"[Deposit Step 1] Buying TRX on Upbit: {transfer.transfer_id}")
        
        await self.repository.update_status(
            transfer.transfer_id,
            TransferStatus.PURCHASING,
            current_step=0,
        )
        
        # KRW로 TRX 시장가 매수
        # 수수료 1 TRX를 고려하여 약간 더 매수
        buy_amount = transfer.requested_amount
        
        order = await self.upbit.place_market_buy_order(
            market="KRW-TRX",
            price=buy_amount,
        )
        
        # 주문 체결 대기
        filled_order = await self.upbit.wait_order_filled(
            order.uuid,
            timeout=60.0,
        )
        
        await self.repository.update_order_ids(
            transfer.transfer_id,
            upbit_order_id=filled_order.uuid,
        )
        
        await self.repository.update_status(
            transfer.transfer_id,
            TransferStatus.PURCHASING,
            current_step=1,
        )
        
        logger.info(
            f"[Deposit Step 1] TRX purchased: {filled_order.executed_volume} TRX",
            extra={"order_id": filled_order.uuid},
        )
        
        return await self.repository.get(transfer.transfer_id)  # type: ignore
    
    async def _step2_send_to_binance(self, transfer: Transfer) -> Transfer:
        """Step 2: Upbit에서 Binance로 TRX 출금"""
        logger.info(f"[Deposit Step 2] Sending TRX to Binance: {transfer.transfer_id}")
        
        await self.repository.update_status(
            transfer.transfer_id,
            TransferStatus.SENDING,
            current_step=1,
        )
        
        # 현재 TRX 잔고 확인
        trx_account = await self.upbit.get_account("TRX")
        if not trx_account or trx_account.balance <= Decimal("1"):
            raise ValueError(f"Insufficient TRX balance: {trx_account}")
        
        # 수수료 1 TRX 제외하고 출금
        withdraw_amount = trx_account.balance - Decimal("1")
        
        # Binance로 출금
        withdraw = await self.upbit.withdraw_coin(
            currency="TRX",
            amount=withdraw_amount,
            address=self.binance_trx_address,
        )
        
        await self.repository.update_order_ids(
            transfer.transfer_id,
            blockchain_txid=withdraw.txid,
        )
        
        # 출금 완료 대기 (최대 10분)
        completed_withdraw = await self.upbit.wait_withdraw_done(
            withdraw.uuid,
            timeout=600.0,
            poll_interval=10.0,
        )
        
        await self.repository.update_order_ids(
            transfer.transfer_id,
            blockchain_txid=completed_withdraw.txid,
        )
        
        await self.repository.update_status(
            transfer.transfer_id,
            TransferStatus.SENDING,
            current_step=2,
        )
        
        logger.info(
            f"[Deposit Step 2] TRX sent: {withdraw_amount} TRX",
            extra={"txid": completed_withdraw.txid},
        )
        
        return await self.repository.get(transfer.transfer_id)  # type: ignore
    
    async def _step3_wait_binance_deposit(self, transfer: Transfer) -> Transfer:
        """Step 3: Binance Spot TRX 입금 확인"""
        logger.info(
            f"[Deposit Step 3] Waiting for Binance deposit: {transfer.transfer_id}"
        )
        
        await self.repository.update_status(
            transfer.transfer_id,
            TransferStatus.CONFIRMING,
            current_step=2,
        )
        
        # Binance 입금 확인 (최대 10분)
        deposit = await self.binance.wait_deposit_confirmed(
            coin="TRX",
            min_amount=1.0,  # 최소 1 TRX 이상
            timeout=600.0,
            poll_interval=30.0,
        )
        
        if not deposit:
            raise TimeoutError("Binance TRX deposit not confirmed within timeout")
        
        await self.repository.update_status(
            transfer.transfer_id,
            TransferStatus.CONFIRMING,
            current_step=3,
        )
        
        logger.info(
            f"[Deposit Step 3] Binance deposit confirmed: {deposit.get('amount')} TRX"
        )
        
        return await self.repository.get(transfer.transfer_id)  # type: ignore
    
    async def _step4_sell_trx_to_usdt(self, transfer: Transfer) -> Transfer:
        """Step 4: Binance Spot에서 TRX -> USDT 환전"""
        logger.info(f"[Deposit Step 4] Converting TRX to USDT: {transfer.transfer_id}")
        
        await self.repository.update_status(
            transfer.transfer_id,
            TransferStatus.CONVERTING,
            current_step=3,
        )
        
        # TRX 잔고 확인
        trx_balance = await self.binance.get_spot_balance("TRX")
        trx_amount = trx_balance.get("free", "0")
        
        if float(trx_amount) <= 0:
            raise ValueError(f"No TRX balance to convert: {trx_amount}")
        
        # TRX -> USDT 시장가 매도
        order = await self.binance.spot_market_sell(
            symbol="TRXUSDT",
            quantity=trx_amount,
        )
        
        await self.repository.update_order_ids(
            transfer.transfer_id,
            binance_order_id=str(order.get("orderId")),
        )
        
        await self.repository.update_status(
            transfer.transfer_id,
            TransferStatus.CONVERTING,
            current_step=4,
        )
        
        logger.info(
            f"[Deposit Step 4] TRX sold: {trx_amount} TRX -> USDT",
            extra={"order_id": order.get("orderId")},
        )
        
        return await self.repository.get(transfer.transfer_id)  # type: ignore
    
    async def _step5_transfer_to_futures(self, transfer: Transfer) -> Transfer:
        """Step 5: Binance Spot -> Futures USDT 내부 이체"""
        logger.info(
            f"[Deposit Step 5] Transferring USDT to Futures: {transfer.transfer_id}"
        )
        
        await self.repository.update_status(
            transfer.transfer_id,
            TransferStatus.TRANSFERRING,
            current_step=4,
        )
        
        # USDT 잔고 확인
        usdt_balance = await self.binance.get_spot_balance("USDT")
        usdt_amount = usdt_balance.get("free", "0")
        
        if float(usdt_amount) <= 0:
            raise ValueError(f"No USDT balance to transfer: {usdt_amount}")
        
        # Spot -> Futures 내부 이체
        result = await self.binance.internal_transfer(
            asset="USDT",
            amount=usdt_amount,
            from_account="SPOT",
            to_account="FUTURES",
        )
        
        # 실제 도착 금액 기록
        await self.repository.update_amounts(
            transfer.transfer_id,
            actual_amount=Decimal(usdt_amount),
        )
        
        await self.repository.update_status(
            transfer.transfer_id,
            TransferStatus.TRANSFERRING,
            current_step=5,
        )
        
        logger.info(
            f"[Deposit Step 5] USDT transferred to Futures: {usdt_amount} USDT",
            extra={"tran_id": result.get("tranId")},
        )
        
        return await self.repository.get(transfer.transfer_id)  # type: ignore
    
    async def _step6_complete(self, transfer: Transfer) -> Transfer:
        """Step 6: 입금 완료"""
        logger.info(f"[Deposit Step 6] Completing deposit: {transfer.transfer_id}")
        
        # 수수료 계산 (요청 금액 - 실제 도착 금액)
        actual = transfer.actual_amount or Decimal("0")
        
        # KRW -> USDT 대략적인 환율 (요청 금액은 KRW)
        # 정확한 수수료는 환율 변동으로 계산 어려움
        
        await self.repository.update_status(
            transfer.transfer_id,
            TransferStatus.COMPLETED,
            current_step=6,
        )
        
        logger.info(
            f"[Deposit] Completed: {transfer.transfer_id}",
            extra={"actual_amount": str(actual)},
        )
        
        return await self.repository.get(transfer.transfer_id)  # type: ignore
    
    async def get_deposit_status(self) -> dict[str, Any]:
        """입금 가능 상태 조회
        
        Upbit 잔고와 TRX 시세를 조합하여 입금 가능 여부 판단.
        
        Returns:
            입금 상태 정보
        """
        return await self.upbit.get_deposit_status()
