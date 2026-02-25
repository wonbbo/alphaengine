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
from decimal import Decimal, ROUND_DOWN
from typing import Any

from adapters.binance.rate_limiter import BinanceApiError
from adapters.binance.rest_client import BinanceRestClient
from adapters.upbit.rest_client import UpbitRestClient
from bot.transfer.repository import Transfer, TransferRepository
from core.domain.events import Event, EventTypes
from core.storage.event_store import EventStore
from core.types import Scope, TransferStatus

logger = logging.getLogger(__name__)


class WithdrawHandler:
    """출금 핸들러
    
    Binance Futures USDT -> Upbit KRW 출금 처리.
    
    Args:
        upbit: Upbit REST 클라이언트
        binance: Binance REST 클라이언트
        repository: Transfer 저장소
        upbit_trx_address: Upbit TRX 입금 주소
        event_store: 이벤트 저장소 (Ledger 기록용)
        scope: 거래 범위
    """
    
    TOTAL_STEPS = 7
    
    def __init__(
        self,
        upbit: UpbitRestClient,
        binance: BinanceRestClient,
        repository: TransferRepository,
        upbit_trx_address: str,
        event_store: EventStore | None = None,
        scope: Scope | None = None,
    ):
        self.upbit = upbit
        self.binance = binance
        self.repository = repository
        self.upbit_trx_address = upbit_trx_address
        self.event_store = event_store
        self.scope = scope
    
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
            # 에러 유형별 친절한 메시지
            error_message = str(e)
            if isinstance(e, TimeoutError):
                error_message = (
                    f"{e} TRON 네트워크 지연으로 인한 타임아웃입니다. "
                    "이체가 완료되었을 수 있으니 잠시 후 재시도하세요."
                )
            elif isinstance(e, BinanceApiError) and e.code == -4026:
                error_message = (
                    "Binance 잔고 부족: 출금 가능 TRX가 부족합니다. "
                    "TRX 매수 후 24시간 출금 제한, 수수료 변동, 또는 잔고 정산 지연일 수 있습니다. "
                    "잠시 후 재시도하세요."
                )
            await self.repository.update_status(
                transfer.transfer_id,
                TransferStatus.FAILED,
                error_message=error_message,
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
        
        # 내부 이체 이벤트 기록 (FUTURES -> SPOT)
        await self._record_internal_transfer_event(
            transfer_id=transfer.transfer_id,
            asset="USDT",
            amount=Decimal(usdt_amount),
            from_venue="FUTURES",
            to_venue="SPOT",
            tran_id=str(result.get("tranId")),
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
        
        # SPOT 거래 이벤트 기록 (USDT 소비 -> TRX 수령)
        trx_qty = Decimal(str(order.get("executedQty", "0")))
        quote_qty = Decimal(str(order.get("cummulativeQuoteQty", "0")))
        avg_price = quote_qty / trx_qty if trx_qty > 0 else Decimal("0")
        commission = Decimal("0")
        commission_asset = "TRX"
        for fill in order.get("fills", []):
            commission += Decimal(str(fill.get("commission", "0")))
            commission_asset = fill.get("commissionAsset", "TRX")
        
        await self._record_spot_trade_event(
            transfer_id=transfer.transfer_id,
            side="BUY",
            symbol="TRXUSDT",
            qty=trx_qty,
            price=avg_price,
            quote_qty=quote_qty,
            commission=commission,
            commission_asset=commission_asset,
            order_id=str(order.get("orderId")),
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
        trx_amount = Decimal(trx_balance.get("free", "0"))
        
        # Binance 출금 수수료 동적 조회 (API 실패 시 1 TRX fallback)
        withdraw_fee = Decimal("1")
        asset_detail = await self.binance.get_asset_detail("TRX")
        if asset_detail is not None:
            fee_val = asset_detail.get("withdrawFee")
            if fee_val is not None:
                withdraw_fee = Decimal(str(fee_val))
                logger.debug(
                    f"[Withdraw Step 3] Binance TRX 출금 수수료: {withdraw_fee} TRX"
                )
        
        # 안전 마진: 수수료 변동·라운딩 오차 대비 (0.1 TRX)
        safety_margin = Decimal("0.1")
        min_required = withdraw_fee + safety_margin
        
        if trx_amount <= min_required:
            # 복구: 이전 시도로 이미 Upbit에 TRX가 도착했을 수 있음 (재시도 시)
            upbit_trx = await self.upbit.get_account("TRX")
            if upbit_trx and upbit_trx.balance > Decimal("1"):
                logger.info(
                    "[Withdraw Step 3] Binance TRX 부족 but Upbit에 이미 도착 (복구)"
                )
                await self.repository.update_status(
                    transfer.transfer_id,
                    TransferStatus.CONFIRMING,
                    current_step=4,
                )
                return await self.repository.get(transfer.transfer_id)  # type: ignore
            raise ValueError(
                f"Binance TRX 잔고 부족: {trx_amount} TRX "
                f"(수수료 {withdraw_fee} + 마진 {safety_margin} 필요)"
            )
        
        # 실제 출금 금액 = 잔고 - 수수료 - 안전 마진, 소수점 6자리로 내림
        withdraw_amount = (trx_amount - withdraw_fee - safety_margin).quantize(
            Decimal("0.000001"), rounding=ROUND_DOWN
        )
        
        if withdraw_amount <= Decimal("0"):
            raise ValueError(
                f"출금 가능 금액 없음: 잔고 {trx_amount} TRX, "
                f"수수료 {withdraw_fee} + 마진 {safety_margin}"
            )
        
        # Upbit으로 출금
        result = await self.binance.withdraw_coin(
            coin="TRX",
            address=self.upbit_trx_address,
            amount=str(withdraw_amount),
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
        
        # 복구: 이미 Upbit에 TRX가 도착해 있으면 바로 진행
        trx_account = await self.upbit.get_account("TRX")
        if trx_account and trx_account.balance > Decimal("1"):
            logger.info(
                f"[Withdraw Step 4] Upbit TRX 이미 도착 (복구): {trx_account.balance} TRX"
            )
            await self.repository.update_status(
                transfer.transfer_id,
                TransferStatus.CONFIRMING,
                current_step=4,
            )
            return await self.repository.get(transfer.transfer_id)  # type: ignore
        
        # Upbit 입금 확인 (폴링)
        # Upbit API는 입금 완료 대기 메서드가 없으므로 직접 구현
        timeout = 900.0  # 15분 (TRON 네트워크 지연 고려)
        poll_interval = 30.0
        elapsed = 0.0
        
        while elapsed < timeout:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            
            # TRX 잔고 확인
            trx_account = await self.upbit.get_account("TRX")
            if trx_account and trx_account.balance > Decimal("1"):
                logger.info(
                    f"[Withdraw Step 4] Upbit TRX deposit confirmed: "
                    f"{trx_account.balance} TRX"
                )
                break
        else:
            raise TimeoutError(
                f"Upbit TRX 입금이 {int(timeout/60)}분 내에 확인되지 않음"
            )
        
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
        
        # 실제 수령 KRW 금액 계산 후 저장 (전체 잔고가 아닌 이번 거래분만)
        actual_krw = self._parse_krw_from_sell_order(filled_order)
        await self.repository.update_amounts(
            transfer.transfer_id,
            actual_amount=actual_krw,
        )
        
        await self.repository.update_status(
            transfer.transfer_id,
            TransferStatus.CONVERTING,
            current_step=5,
        )
        
        logger.info(
            f"[Withdraw Step 5] TRX sold: {filled_order.executed_volume} TRX -> {actual_krw} KRW",
            extra={"order_id": filled_order.uuid},
        )
        
        return await self.repository.get(transfer.transfer_id)  # type: ignore
    
    def _parse_krw_from_sell_order(self, order: Any) -> Decimal:
        """TRX 매도 주문 결과에서 실제 수령 KRW 추출 (이번 출금분만)
        
        Upbit 시장가 매도 시: executed_funds - paid_fee = 실제 KRW
        
        Args:
            order: UpbitOrder 객체 (wait_order_filled 결과)
            
        Returns:
            실제 수령 KRW 금액
        """
        # UpbitOrder 객체에서 executed_funds, paid_fee 사용
        gross_krw = order.executed_funds
        paid_fee = order.paid_fee
        
        return max(Decimal("0"), gross_krw - paid_fee)
    
    async def _step6_complete(self, transfer: Transfer) -> Transfer:
        """Step 6: 출금 완료"""
        logger.info(f"[Withdraw Step 6] Completing withdraw: {transfer.transfer_id}")
        
        # actual_amount는 Step 5에서 이미 저장됨 (이번 거래분만)
        # 여기서는 최종 상태만 업데이트
        await self.repository.update_status(
            transfer.transfer_id,
            TransferStatus.COMPLETED,
            current_step=6,
        )
        
        # 저장된 actual_amount 로깅용으로 조회
        updated_transfer = await self.repository.get(transfer.transfer_id)
        
        logger.info(
            f"[Withdraw] Completed: {transfer.transfer_id}",
            extra={"actual_amount": str(updated_transfer.actual_amount if updated_transfer else "N/A")},
        )
        
        return updated_transfer  # type: ignore
    
    async def get_withdraw_status(self) -> dict[str, Any]:
        """출금 가능 상태 조회
        
        Binance Futures 잔고 및 포지션 확인.
        예상 수수료 및 수령 금액 정보 포함.
        
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
        
        # 시세 정보 조회 (예상 금액 계산용)
        price_info = await self._get_price_info()
        
        return {
            "can_withdraw": can_withdraw,
            "usdt_balance": str(usdt_balance),
            "has_position": has_position,
            "position_count": len(positions),
            "min_withdraw_usdt": str(min_withdraw),
            "warning": "포지션이 있으면 출금 시 주의가 필요합니다." if has_position else None,
            # 예상 출금 계산용 시세 정보
            "trx_usdt_price": price_info["trx_usdt_price"],
            "trx_krw_price": price_info["trx_krw_price"],
            "network_fee_trx": "1",  # Binance TRX 출금 수수료
            "binance_trade_fee_rate": "0.001",  # Binance 거래 수수료 0.1%
            "upbit_trade_fee_rate": "0.0005",  # Upbit 거래 수수료 0.05%
        }
    
    async def _get_price_info(self) -> dict[str, str]:
        """TRX 시세 정보 조회
        
        Returns:
            TRX/USDT, TRX/KRW 가격 정보
        """
        trx_usdt_price = "0"
        trx_krw_price = "0"
        
        try:
            # Binance TRX/USDT 가격
            ticker = await self.binance.get_ticker_price("TRXUSDT")
            trx_usdt_price = ticker.get("price", "0")
        except Exception as e:
            logger.warning(f"Failed to get TRX/USDT price: {e}")
        
        try:
            # Upbit TRX/KRW 가격
            ticker = await self.upbit.get_ticker("KRW-TRX")
            if ticker:
                trx_krw_price = str(ticker.trade_price)
        except Exception as e:
            logger.warning(f"Failed to get TRX/KRW price: {e}")
        
        return {
            "trx_usdt_price": trx_usdt_price,
            "trx_krw_price": trx_krw_price,
        }
    
    async def _record_spot_trade_event(
        self,
        transfer_id: str,
        side: str,
        symbol: str,
        qty: Decimal,
        price: Decimal,
        quote_qty: Decimal,
        commission: Decimal,
        commission_asset: str,
        order_id: str,
    ) -> None:
        """SPOT 거래 이벤트 기록 (Ledger 분개용)
        
        TradeExecuted 이벤트로 SPOT 자산 변동을 Ledger에 기록.
        """
        if not self.event_store or not self.scope:
            return
        
        spot_scope = Scope.create(
            exchange=self.scope.exchange,
            venue="SPOT",
            symbol=symbol,
            mode=self.scope.mode,
        )
        
        payload = {
            "symbol": symbol,
            "side": side,
            "qty": str(qty),
            "price": str(price),
            "quote_qty": str(quote_qty),
            "commission": str(commission),
            "commission_asset": commission_asset,
            "order_id": order_id,
            "is_maker": False,
            "realized_pnl": "0",
            "transfer_id": transfer_id,
        }
        
        dedup_key = f"spot_trade:{order_id}"
        
        event = Event.create(
            event_type=EventTypes.TRADE_EXECUTED,
            entity_kind="TRADE",
            entity_id=order_id,
            scope=spot_scope,
            source="BOT",
            payload=payload,
            dedup_key=dedup_key,
        )
        
        await self.event_store.append(event)
        logger.debug(f"[Withdraw] SPOT 거래 이벤트 기록: {side} {qty} {symbol}")
    
    async def _record_internal_transfer_event(
        self,
        transfer_id: str,
        asset: str,
        amount: Decimal,
        from_venue: str,
        to_venue: str,
        tran_id: str,
    ) -> None:
        """내부 이체 이벤트 기록 (Ledger 분개용)
        
        InternalTransferCompleted 이벤트로 Ledger에 기록.
        """
        if not self.event_store or not self.scope:
            return
        
        payload = {
            "asset": asset,
            "amount": str(amount),
            "from_venue": f"BINANCE_{from_venue}",
            "to_venue": f"BINANCE_{to_venue}",
            "tran_id": tran_id,
            "transfer_id": transfer_id,
        }
        
        dedup_key = f"internal_transfer:{tran_id}"
        
        event = Event.create(
            event_type=EventTypes.INTERNAL_TRANSFER_COMPLETED,
            entity_kind="TRANSFER",
            entity_id=tran_id,
            scope=self.scope,
            source="BOT",
            payload=payload,
            dedup_key=dedup_key,
        )
        
        await self.event_store.append(event)
        logger.debug(f"[Withdraw] 내부 이체 이벤트 기록: {amount} {asset} {from_venue} -> {to_venue}")
