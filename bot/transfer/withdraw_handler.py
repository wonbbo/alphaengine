"""
출금 핸들러

Binance Futures USDT -> Upbit KRW 출금 흐름 처리.

출금 단계:
1. Binance Futures -> Spot USDT 내부 이체
2. Binance Spot에서 USDT -> TRX 환전
3. Binance에서 Upbit으로 TRX 출금
4. Upbit TRX 입금 확인
5. Upbit에서 TRX -> KRW 환전
6. 출금 완료
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


class WithdrawHandler:
    """출금 핸들러
    
    Binance Futures USDT -> Upbit KRW 출금 처리.
    
    Args:
        upbit: Upbit REST 클라이언트
        binance: Binance REST 클라이언트
        repository: Transfer 저장소
        upbit_trx_address: Upbit TRX 입금 주소
    """
    
    TOTAL_STEPS = 7
    
    def __init__(
        self,
        upbit: UpbitRestClient,
        binance: BinanceRestClient,
        repository: TransferRepository,
        upbit_trx_address: str,
    ):
        self.upbit = upbit
        self.binance = binance
        self.repository = repository
        self.upbit_trx_address = upbit_trx_address
    
    async def execute(self, transfer: Transfer) -> Transfer:
        """출금 실행
        
        현재 단계부터 순차적으로 처리.
        실패 시 해당 단계에서 중단하고 에러 기록.
        
        Args:
            transfer: Transfer 객체
            
        Returns:
            업데이트된 Transfer 객체
        """
        try:
            if transfer.current_step < 1:
                transfer = await self._step1_transfer_to_spot(transfer)
            
            if transfer.current_step < 2:
                transfer = await self._step2_buy_trx(transfer)
            
            if transfer.current_step < 3:
                transfer = await self._step3_send_to_upbit(transfer)
            
            if transfer.current_step < 4:
                transfer = await self._step4_wait_upbit_deposit(transfer)
            
            if transfer.current_step < 5:
                transfer = await self._step5_sell_trx_to_krw(transfer)
            
            if transfer.current_step < 6:
                transfer = await self._step6_complete(transfer)
            
            return transfer
            
        except Exception as e:
            logger.error(
                f"Withdraw failed: {transfer.transfer_id}",
                extra={"error": str(e), "step": transfer.current_step},
                exc_info=True,
            )
            await self.repository.update_status(
                transfer.transfer_id,
                TransferStatus.FAILED,
                error_message=str(e),
            )
            return await self.repository.get(transfer.transfer_id)  # type: ignore
    
    async def _step1_transfer_to_spot(self, transfer: Transfer) -> Transfer:
        """Step 1: Binance Futures -> Spot USDT 내부 이체"""
        logger.info(
            f"[Withdraw Step 1] Transferring USDT to Spot: {transfer.transfer_id}"
        )
        
        await self.repository.update_status(
            transfer.transfer_id,
            TransferStatus.TRANSFERRING,
            current_step=0,
        )
        
        # Futures -> Spot 내부 이체
        usdt_amount = str(transfer.requested_amount)
        
        result = await self.binance.internal_transfer(
            asset="USDT",
            amount=usdt_amount,
            from_account="FUTURES",
            to_account="SPOT",
        )
        
        await self.repository.update_status(
            transfer.transfer_id,
            TransferStatus.TRANSFERRING,
            current_step=1,
        )
        
        logger.info(
            f"[Withdraw Step 1] USDT transferred to Spot: {usdt_amount} USDT",
            extra={"tran_id": result.get("tranId")},
        )
        
        return await self.repository.get(transfer.transfer_id)  # type: ignore
    
    async def _step2_buy_trx(self, transfer: Transfer) -> Transfer:
        """Step 2: Binance Spot에서 USDT -> TRX 환전"""
        logger.info(f"[Withdraw Step 2] Buying TRX on Binance: {transfer.transfer_id}")
        
        await self.repository.update_status(
            transfer.transfer_id,
            TransferStatus.PURCHASING,
            current_step=1,
        )
        
        # USDT 잔고 확인
        usdt_balance = await self.binance.get_spot_balance("USDT")
        usdt_amount = usdt_balance.get("free", "0")
        
        if float(usdt_amount) <= 0:
            raise ValueError(f"No USDT balance to convert: {usdt_amount}")
        
        # USDT -> TRX 시장가 매수
        order = await self.binance.spot_market_buy(
            symbol="TRXUSDT",
            quote_qty=usdt_amount,
        )
        
        await self.repository.update_order_ids(
            transfer.transfer_id,
            binance_order_id=str(order.get("orderId")),
        )
        
        await self.repository.update_status(
            transfer.transfer_id,
            TransferStatus.PURCHASING,
            current_step=2,
        )
        
        logger.info(
            f"[Withdraw Step 2] TRX purchased: {order.get('executedQty')} TRX",
            extra={"order_id": order.get("orderId")},
        )
        
        return await self.repository.get(transfer.transfer_id)  # type: ignore
    
    async def _step3_send_to_upbit(self, transfer: Transfer) -> Transfer:
        """Step 3: Binance에서 Upbit으로 TRX 출금"""
        logger.info(f"[Withdraw Step 3] Sending TRX to Upbit: {transfer.transfer_id}")
        
        await self.repository.update_status(
            transfer.transfer_id,
            TransferStatus.SENDING,
            current_step=2,
        )
        
        # TRX 잔고 확인
        trx_balance = await self.binance.get_spot_balance("TRX")
        trx_amount = trx_balance.get("free", "0")
        
        if float(trx_amount) <= 1:  # 수수료 고려
            raise ValueError(f"Insufficient TRX balance: {trx_amount}")
        
        # Binance TRX 출금 수수료 (약 1 TRX)
        # 실제 출금 금액 = 잔고 - 수수료
        withdraw_amount = str(float(trx_amount) - 1)
        
        # Upbit으로 출금
        result = await self.binance.withdraw_coin(
            coin="TRX",
            address=self.upbit_trx_address,
            amount=withdraw_amount,
            network="TRX",  # TRC20 네트워크
        )
        
        await self.repository.update_order_ids(
            transfer.transfer_id,
            blockchain_txid=result.get("id"),
        )
        
        await self.repository.update_status(
            transfer.transfer_id,
            TransferStatus.SENDING,
            current_step=3,
        )
        
        logger.info(
            f"[Withdraw Step 3] TRX sent to Upbit: {withdraw_amount} TRX",
            extra={"withdraw_id": result.get("id")},
        )
        
        return await self.repository.get(transfer.transfer_id)  # type: ignore
    
    async def _step4_wait_upbit_deposit(self, transfer: Transfer) -> Transfer:
        """Step 4: Upbit TRX 입금 확인"""
        logger.info(
            f"[Withdraw Step 4] Waiting for Upbit deposit: {transfer.transfer_id}"
        )
        
        await self.repository.update_status(
            transfer.transfer_id,
            TransferStatus.CONFIRMING,
            current_step=3,
        )
        
        # Upbit 입금 확인 (폴링)
        # Upbit API는 입금 완료 대기 메서드가 없으므로 직접 구현
        timeout = 600.0  # 10분
        poll_interval = 30.0
        elapsed = 0.0
        
        while elapsed < timeout:
            # TRX 잔고 확인
            trx_account = await self.upbit.get_account("TRX")
            if trx_account and trx_account.balance > Decimal("1"):
                logger.info(
                    f"[Withdraw Step 4] Upbit TRX deposit confirmed: "
                    f"{trx_account.balance} TRX"
                )
                break
            
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
        else:
            raise TimeoutError("Upbit TRX deposit not confirmed within timeout")
        
        await self.repository.update_status(
            transfer.transfer_id,
            TransferStatus.CONFIRMING,
            current_step=4,
        )
        
        return await self.repository.get(transfer.transfer_id)  # type: ignore
    
    async def _step5_sell_trx_to_krw(self, transfer: Transfer) -> Transfer:
        """Step 5: Upbit에서 TRX -> KRW 환전"""
        logger.info(f"[Withdraw Step 5] Selling TRX on Upbit: {transfer.transfer_id}")
        
        await self.repository.update_status(
            transfer.transfer_id,
            TransferStatus.CONVERTING,
            current_step=4,
        )
        
        # TRX 잔고 확인
        trx_account = await self.upbit.get_account("TRX")
        if not trx_account or trx_account.balance <= 0:
            raise ValueError(f"No TRX balance to sell: {trx_account}")
        
        # TRX -> KRW 시장가 매도
        order = await self.upbit.place_market_sell_order(
            market="KRW-TRX",
            volume=trx_account.balance,
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
            TransferStatus.CONVERTING,
            current_step=5,
        )
        
        logger.info(
            f"[Withdraw Step 5] TRX sold: {filled_order.executed_volume} TRX",
            extra={"order_id": filled_order.uuid},
        )
        
        return await self.repository.get(transfer.transfer_id)  # type: ignore
    
    async def _step6_complete(self, transfer: Transfer) -> Transfer:
        """Step 6: 출금 완료"""
        logger.info(f"[Withdraw Step 6] Completing withdraw: {transfer.transfer_id}")
        
        # KRW 잔고 확인하여 실제 도착 금액 기록
        krw_account = await self.upbit.get_account("KRW")
        actual_krw = krw_account.balance if krw_account else Decimal("0")
        
        await self.repository.update_amounts(
            transfer.transfer_id,
            actual_amount=actual_krw,
        )
        
        await self.repository.update_status(
            transfer.transfer_id,
            TransferStatus.COMPLETED,
            current_step=6,
        )
        
        logger.info(
            f"[Withdraw] Completed: {transfer.transfer_id}",
            extra={"actual_amount": str(actual_krw)},
        )
        
        return await self.repository.get(transfer.transfer_id)  # type: ignore
    
    async def get_withdraw_status(self) -> dict[str, Any]:
        """출금 가능 상태 조회
        
        Binance Futures 잔고 및 포지션 확인.
        
        Returns:
            출금 상태 정보
        """
        # Futures USDT 잔고 조회
        balances = await self.binance.get_balances()
        
        usdt_balance = Decimal("0")
        for balance in balances:
            if balance.asset == "USDT":
                usdt_balance = balance.free
                break
        
        # 포지션 확인
        positions = await self.binance.get_all_positions()
        has_position = len(positions) > 0
        
        # 최소 출금 금액
        min_withdraw = Decimal("10")  # 최소 10 USDT
        
        can_withdraw = usdt_balance >= min_withdraw
        
        return {
            "can_withdraw": can_withdraw,
            "usdt_balance": str(usdt_balance),
            "has_position": has_position,
            "position_count": len(positions),
            "min_withdraw_usdt": str(min_withdraw),
            "warning": "포지션이 있으면 출금 시 주의가 필요합니다." if has_position else None,
        }
