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
        logger.info(
            f"[Withdraw] execute 시작: {transfer.transfer_id} | "
            f"current_step={transfer.current_step}/{transfer.total_steps} "
            f"status={transfer.status.value} requested_amount={transfer.requested_amount}",
            extra={
                "transfer_id": transfer.transfer_id,
                "current_step": transfer.current_step,
                "total_steps": transfer.total_steps,
                "status": transfer.status.value,
                "requested_amount": str(transfer.requested_amount),
            },
        )
        try:
            # 단계별 처리 (current_step <= N: 해당 단계 진행 중 또는 미완료)
            # Step 시작 시 current_step=N 설정, 완료 후 다음 Step이 N+1로 설정
            if transfer.current_step <= 1:
                transfer = await self._step1_transfer_to_spot(transfer)
            
            if transfer.current_step <= 2:
                transfer = await self._step2_buy_trx(transfer)
            
            if transfer.current_step <= 3:
                transfer = await self._step3_send_to_upbit(transfer)
            
            if transfer.current_step <= 4:
                transfer = await self._step4_wait_upbit_deposit(transfer)
            
            if transfer.current_step <= 5:
                transfer = await self._step5_sell_trx_to_krw(transfer)
            
            if transfer.current_step <= 6:
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
                    "Binance 출금 잔고 부족(-4026). "
                    "원인: TRX 매수 직후 24~72시간 출금 락, 수수료·마진 부족, 또는 정산 지연. "
                    "락 해제 후 재시도하세요."
                )
            await self.repository.update_status(
                transfer.transfer_id,
                TransferStatus.FAILED,
                error_message=error_message,
            )
            return await self.repository.get(transfer.transfer_id)  # type: ignore
    
    async def _step1_transfer_to_spot(self, transfer: Transfer) -> Transfer:
        """Step 1: Binance Futures -> Spot USDT 내부 이체"""
        usdt_amount = str(transfer.requested_amount)
        logger.info(
            f"[Withdraw Step 1] Transferring USDT to Spot: {transfer.transfer_id} | amount={usdt_amount} USDT",
            extra={"transfer_id": transfer.transfer_id, "amount_usdt": usdt_amount},
        )
        
        await self.repository.update_status(
            transfer.transfer_id,
            TransferStatus.TRANSFERRING,
            current_step=1,  # Step 1 진행 중임을 UI에 표시 (17%)
        )
        
        # Futures -> Spot 내부 이체
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
        
        logger.info(
            f"[Withdraw Step 1] USDT transferred to Spot: {usdt_amount} USDT | tran_id={result.get('tranId')}",
            extra={"transfer_id": transfer.transfer_id, "amount_usdt": usdt_amount, "tran_id": result.get("tranId")},
        )
        
        return await self.repository.get(transfer.transfer_id)  # type: ignore
    
    async def _step2_buy_trx(self, transfer: Transfer) -> Transfer:
        """Step 2: Binance Spot에서 USDT -> TRX 환전"""
        logger.info(
            f"[Withdraw Step 2] Buying TRX on Binance: {transfer.transfer_id} | "
            f"requested_amount={transfer.requested_amount} USDT",
            extra={"transfer_id": transfer.transfer_id},
        )
        
        await self.repository.update_status(
            transfer.transfer_id,
            TransferStatus.PURCHASING,
            current_step=2,  # Step 2 진행 중임을 UI에 표시 (33%)
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
        
        trx_qty = order.get("executedQty", "0")
        logger.info(
            f"[Withdraw Step 2] TRX purchased: {trx_qty} TRX | order_id={order.get('orderId')}",
            extra={"transfer_id": transfer.transfer_id, "executed_qty": trx_qty, "order_id": str(order.get("orderId"))},
        )
        
        return await self.repository.get(transfer.transfer_id)  # type: ignore
    
    async def _step3_send_to_upbit(self, transfer: Transfer) -> Transfer:
        """Step 3: Binance에서 Upbit으로 TRX 출금"""
        logger.info(f"[Withdraw Step 3] Sending TRX to Upbit: {transfer.transfer_id}")
        
        await self.repository.update_status(
            transfer.transfer_id,
            TransferStatus.SENDING,
            current_step=3,  # Step 3 진행 중임을 UI에 표시 (50%)
        )
        
        # Binance TRX TRC20 출금 수수료·최소 출금액
        # 수수료: API 우선, 없으면 상수. 최소 출금: API 우선, 없으면 30 (Binance -4022 대응)
        TRX_TRC20_WITHDRAW_FEE = Decimal("0.062")
        TRX_TRC20_MIN_WITHDRAW_FALLBACK = Decimal("30")
        
        asset_detail = await self.binance.get_asset_detail("TRX")
        withdraw_fee = TRX_TRC20_WITHDRAW_FEE
        min_withdraw = TRX_TRC20_MIN_WITHDRAW_FALLBACK
        if asset_detail is not None:
            fee_val = asset_detail.get("withdrawFee")
            if fee_val is not None:
                api_fee = Decimal(str(fee_val))
                if api_fee > withdraw_fee:
                    withdraw_fee = api_fee
                    logger.info(
                        f"[Withdraw Step 3] Binance TRX 출금 수수료 (API): {withdraw_fee} TRX"
                    )
            min_val = asset_detail.get("minWithdrawAmount")
            if min_val is not None:
                min_withdraw = max(min_withdraw, Decimal(str(min_val)))
        
        # 안전 마진: 수수료 변동·라운딩 오차·Binance 내부 정산 지연 대비
        safety_margin = Decimal("0.15")
        min_required = withdraw_fee + safety_margin
        
        # 일부 락 가정: free 중 일부만 출금 가능하다고 보고 90%만 사용
        WITHDRAWABLE_RATIO = Decimal("0.9")
        
        # -4026 시 락 해제 대기 후 재시도 (최대 5회, 20초 간격)
        # 1차 요청 후 잔고가 요청액만큼 줄었으면 출금 진행 중으로 간주하고 Step 4로 전환
        MAX_WITHDRAW_RETRIES = 5
        RETRY_DELAY_SEC = 20
        BALANCE_DROP_THRESHOLD = Decimal("0.99")  # 잔고 감소가 요청액의 99% 이상이면 출금 진행 중 추정
        
        last_error: Exception | None = None
        balance_before_4026: Decimal | None = None
        requested_amount_4026: Decimal | None = None
        
        for attempt in range(MAX_WITHDRAW_RETRIES):
            # 매 재시도마다 잔고 재조회 (락 해제 반영)
            trx_balance = await self.binance.get_spot_balance("TRX")
            trx_amount = Decimal(trx_balance.get("free", "0"))
            
            # 이전 시도에서 -4026 난 뒤 재진입: 잔고가 요청액만큼 줄었으면 출금 진행 중 → Step 4
            if balance_before_4026 is not None and requested_amount_4026 is not None:
                balance_drop = balance_before_4026 - trx_amount
                if balance_drop >= (requested_amount_4026 * BALANCE_DROP_THRESHOLD):
                    logger.info(
                        "[Withdraw Step 3] -4026 후 잔고 감소로 출금 진행 중 추정, Step 4로 전환 | "
                        f"balance_before_4026={balance_before_4026} current_trx={trx_amount} "
                        f"balance_drop={balance_drop} requested_amount_4026={requested_amount_4026}",
                        extra={
                            "transfer_id": transfer.transfer_id,
                            "balance_before_4026": str(balance_before_4026),
                            "current_trx": str(trx_amount),
                            "balance_drop": str(balance_drop),
                            "requested_amount_4026": str(requested_amount_4026),
                        },
                    )
                    await self.repository.update_status(
                        transfer.transfer_id,
                        TransferStatus.CONFIRMING,
                        current_step=4,
                    )
                    return await self.repository.get(transfer.transfer_id)  # type: ignore
                balance_before_4026 = None
                requested_amount_4026 = None
            
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
            
            # 보수적 출금액 = (잔고 - 수수료 - 마진) * 90%, 소수점 6자리 내림
            raw_amount = trx_amount - withdraw_fee - safety_margin
            withdraw_amount = (raw_amount * WITHDRAWABLE_RATIO).quantize(
                Decimal("0.000001"), rounding=ROUND_DOWN
            )
            
            if withdraw_amount <= Decimal("0"):
                raise ValueError(
                    f"출금 가능 금액 없음: 잔고 {trx_amount} TRX, "
                    f"수수료 {withdraw_fee} + 마진 {safety_margin}"
                )
            
            # Binance 최소 출금액 미만이면 API 호출 금지 (-4022 방지)
            if withdraw_amount < min_withdraw:
                # 이전 -4026 요청으로 잔고가 줄어든 경우 출금 진행 중으로 간주 → Step 4
                if balance_before_4026 is not None and requested_amount_4026 is not None:
                    balance_drop = balance_before_4026 - trx_amount
                    if balance_drop >= (requested_amount_4026 * BALANCE_DROP_THRESHOLD):
                        logger.info(
                            "[Withdraw Step 3] 출금액이 최소 미만이지만 잔고 감소로 출금 진행 중 추정, Step 4로 전환 | "
                            f"balance_before_4026={balance_before_4026} current_trx={trx_amount} "
                            f"balance_drop={balance_drop} requested_amount_4026={requested_amount_4026}",
                            extra={
                                "transfer_id": transfer.transfer_id,
                                "balance_before_4026": str(balance_before_4026),
                                "current_trx": str(trx_amount),
                                "balance_drop": str(balance_drop),
                            },
                        )
                        await self.repository.update_status(
                            transfer.transfer_id,
                            TransferStatus.CONFIRMING,
                            current_step=4,
                        )
                        return await self.repository.get(transfer.transfer_id)  # type: ignore
                raise ValueError(
                    f"출금 금액 {withdraw_amount} TRX가 Binance 최소 출금액 {min_withdraw} TRX 미만입니다. "
                    f"잔고 부족 또는 이전 출금 처리 후 남은 잔고입니다."
                )
            
            # -4026 시 다음 루프에서 잔고 비교용으로 저장
            balance_before_4026 = trx_amount
            requested_amount_4026 = withdraw_amount

            logger.info(
                f"[Withdraw Step 3] 출금 요청 (시도 {attempt + 1}/{MAX_WITHDRAW_RETRIES}): "
                f"잔고={trx_amount} 출금액={withdraw_amount} TRX 수수료={withdraw_fee} 최소출금={min_withdraw}",
                extra={
                    "transfer_id": transfer.transfer_id,
                    "trx_balance": str(trx_amount),
                    "withdraw_amount": str(withdraw_amount),
                    "withdraw_fee": str(withdraw_fee),
                },
            )

            try:
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
                logger.info(
                    f"[Withdraw Step 3] TRX sent to Upbit: {withdraw_amount} TRX | withdraw_id={result.get('id')}",
                    extra={
                        "transfer_id": transfer.transfer_id,
                        "withdraw_amount": str(withdraw_amount),
                        "withdraw_id": str(result.get("id")),
                    },
                )
                return await self.repository.get(transfer.transfer_id)  # type: ignore
            except BinanceApiError as e:
                last_error = e
                if e.code == -4026 and attempt < MAX_WITHDRAW_RETRIES - 1:
                    logger.warning(
                        f"[Withdraw Step 3] Binance API 에러 -4026(출금 잔고 부족), "
                        f"{RETRY_DELAY_SEC}초 후 재시도 ({attempt + 1}/{MAX_WITHDRAW_RETRIES}) | "
                        f"balance_before_4026={balance_before_4026} requested_amount_4026={requested_amount_4026}",
                        extra={
                            "transfer_id": transfer.transfer_id,
                            "balance_before_4026": str(balance_before_4026),
                            "requested_amount_4026": str(requested_amount_4026),
                        },
                    )
                    await asyncio.sleep(RETRY_DELAY_SEC)
                    continue
                raise
        
        if last_error:
            raise last_error
        return await self.repository.get(transfer.transfer_id)  # type: ignore
    
    async def _step4_wait_upbit_deposit(self, transfer: Transfer) -> Transfer:
        """Step 4: Upbit TRX 입금 확인

        Step 5 Upbit 최소 주문 5000 KRW를 만족하는 TRX 이상 도착했을 때만 완료 처리.
        (기존 잔여 소액만 있을 때 즉시 완료되지 않도록)
        """
        # 방어: 이미 다른 경로로 완료됐으면 스킵 (이중 실행 대비)
        latest = await self.repository.get(transfer.transfer_id)
        if latest and latest.status == TransferStatus.COMPLETED:
            logger.info(
                f"[Withdraw Step 4] 이미 완료됨(DB 재조회), 스킵: {transfer.transfer_id}",
                extra={"transfer_id": transfer.transfer_id},
            )
            return latest  # type: ignore

        logger.info(
            f"[Withdraw Step 4] Waiting for Upbit deposit: {transfer.transfer_id}",
            extra={"transfer_id": transfer.transfer_id},
        )
        
        await self.repository.update_status(
            transfer.transfer_id,
            TransferStatus.CONFIRMING,
            current_step=4,  # Step 4 진행 중임을 UI에 표시 (67%)
        )
        
        # Upbit 시장가 매도 최소 주문 5000 KRW → 해당 TRX 수량 이상일 때만 "도착" 인정
        UPBIT_MIN_ORDER_KRW = Decimal("5000")
        MARGIN = Decimal("1.1")  # 시세 변동·매수1호가 차이 여유
        ticker = await self.upbit.get_ticker("KRW-TRX")
        trx_price = ticker.trade_price if ticker else Decimal("0")
        if trx_price <= Decimal("0"):
            min_trx = Decimal("1000")  # 시세 조회 실패 시 보수적 값
        else:
            min_trx = (UPBIT_MIN_ORDER_KRW * MARGIN / trx_price).quantize(
                Decimal("0.000001"), rounding=ROUND_DOWN
            )
        timeout = 900.0  # 15분 (TRON 네트워크 지연 고려)
        poll_interval = 10.0
        logger.info(
            f"[Withdraw Step 4] Upbit 입금 대기 시작 | min_trx={min_trx} trx_price={trx_price} "
            f"timeout={int(timeout)}s poll_interval={poll_interval}s",
            extra={"transfer_id": transfer.transfer_id, "min_trx": str(min_trx)},
        )
        
        # 복구: 이미 Upbit에 TRX가 최소 주문 가능 수량 이상 도착해 있으면 바로 진행
        trx_account = await self.upbit.get_account("TRX")
        current_balance = trx_account.balance if trx_account else Decimal("0")
        if trx_account and trx_account.balance >= min_trx:
            logger.info(
                f"[Withdraw Step 4] Upbit TRX 이미 도착 (복구): balance={trx_account.balance} TRX "
                f"min_trx={min_trx} TRX",
                extra={"transfer_id": transfer.transfer_id, "balance": str(trx_account.balance)},
            )
            return await self.repository.get(transfer.transfer_id)  # type: ignore
        
        # Upbit 입금 확인 (폴링) — 최소 주문 가능 수량 이상 도착할 때까지 대기
        elapsed = 0.0
        while elapsed < timeout:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            
            trx_account = await self.upbit.get_account("TRX")
            current_balance = trx_account.balance if trx_account else Decimal("0")
            if trx_account and trx_account.balance >= min_trx:
                logger.info(
                    f"[Withdraw Step 4] Upbit TRX deposit confirmed: balance={trx_account.balance} TRX "
                    f"(최소 {min_trx} TRX) elapsed={elapsed:.0f}s",
                    extra={
                        "transfer_id": transfer.transfer_id,
                        "balance": str(trx_account.balance),
                        "elapsed_sec": elapsed,
                    },
                )
                break
        else:
            logger.warning(
                f"[Withdraw Step 4] Upbit 입금 타임아웃 | transfer_id={transfer.transfer_id} "
                f"min_trx={min_trx} timeout={int(timeout)}s last_balance={current_balance}",
                extra={"transfer_id": transfer.transfer_id},
            )
            raise TimeoutError(
                f"Upbit TRX 입금이 {int(timeout/60)}분 내에 확인되지 않음 "
                f"(최소 {min_trx} TRX 필요, Upbit 최소 주문 5000 KRW)"
            )
        
        return await self.repository.get(transfer.transfer_id)  # type: ignore
    
    async def _step5_sell_trx_to_krw(self, transfer: Transfer) -> Transfer:
        """Step 5: Upbit에서 TRX -> KRW 환전"""
        trx_account = await self.upbit.get_account("TRX")
        trx_balance = trx_account.balance if trx_account else Decimal("0")
        logger.info(
            f"[Withdraw Step 5] Selling TRX on Upbit: {transfer.transfer_id} | TRX_balance={trx_balance}",
            extra={"transfer_id": transfer.transfer_id, "trx_balance": str(trx_balance)},
        )
        
        await self.repository.update_status(
            transfer.transfer_id,
            TransferStatus.CONVERTING,
            current_step=5,  # Step 5 진행 중임을 UI에 표시 (83%)
        )
        
        # TRX 잔고 확인 (위에서 이미 조회함)
        if not trx_account or trx_account.balance <= 0:
            raise ValueError(f"No TRX balance to sell: {trx_account}")
        
        # Upbit 시장가 매도 최소 주문 5000 KRW 검사 (under_min_total_market_ask 방지)
        UPBIT_MIN_ORDER_KRW = Decimal("5000")
        ticker = await self.upbit.get_ticker("KRW-TRX")
        trx_price = Decimal(str(ticker.trade_price)) if ticker else Decimal("0")
        estimated_krw = trx_account.balance * trx_price if trx_price > Decimal("0") else Decimal("0")
        if estimated_krw < UPBIT_MIN_ORDER_KRW:
            raise ValueError(
                f"Upbit 최소 주문 금액 5000 KRW 미만입니다. "
                f"TRX 잔고={trx_account.balance}, 예상 금액≈{estimated_krw:.0f} KRW. "
                f"TRX 입금이 더 필요하거나 잠시 후 재시도하세요."
            )
        
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
        
        logger.info(
            f"[Withdraw Step 5] TRX sold: {filled_order.executed_volume} TRX -> {actual_krw} KRW | "
            f"order_id={filled_order.uuid}",
            extra={
                "transfer_id": transfer.transfer_id,
                "executed_volume": str(filled_order.executed_volume),
                "actual_krw": str(actual_krw),
                "order_id": filled_order.uuid,
            },
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
        actual = transfer.actual_amount or Decimal("0")
        logger.info(
            f"[Withdraw Step 6] Completing withdraw: {transfer.transfer_id} | actual_amount={actual} KRW",
            extra={"transfer_id": transfer.transfer_id, "actual_amount": str(actual)},
        )
        
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
            "upbit_trx_address": self.upbit_trx_address,  # 출금 확인 모달용
            # 예상 출금 계산용 시세 정보
            "trx_usdt_price": price_info["trx_usdt_price"],
            "trx_krw_price": price_info["trx_krw_price"],
            "network_fee_trx": "0.062",  # Binance TRX TRC20 출금 수수료
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
