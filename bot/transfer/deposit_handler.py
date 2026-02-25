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
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from adapters.binance.rest_client import BinanceRestClient
from adapters.db.sqlite_adapter import SQLiteAdapter
from adapters.upbit.rest_client import UpbitApiError, UpbitRestClient
from bot.transfer.repository import Transfer, TransferRepository
from core.domain.events import Event, EventTypes
from core.storage.config_store import ConfigStore
from core.storage.event_store import EventStore
from core.types import Scope, TransferStatus

logger = logging.getLogger(__name__)


class DepositHandler:
    """입금 핸들러
    
    Upbit KRW -> Binance Futures USDT 입금 처리.
    
    Args:
        upbit: Upbit REST 클라이언트
        binance: Binance REST 클라이언트
        repository: Transfer 저장소
        binance_trx_address: Binance TRX 입금 주소
        db: DB 어댑터 (ConfigStore용, 24시간 입금 제한 설정 조회)
        event_store: 이벤트 저장소 (Ledger 기록용)
        scope: 거래 범위
    """
    
    TOTAL_STEPS = 6
    
    # 수수료 비율 (출금과 동일)
    UPBIT_TRADE_FEE_RATE = Decimal("0.0005")  # Upbit 거래 수수료 0.05%
    BINANCE_TRADE_FEE_RATE = Decimal("0.001")  # Binance 거래 수수료 0.1%
    NETWORK_FEE_TRX = Decimal("1")  # TRX 출금 수수료
    
    def __init__(
        self,
        upbit: UpbitRestClient,
        binance: BinanceRestClient,
        repository: TransferRepository,
        binance_trx_address: str,
        db: SQLiteAdapter | None = None,
        event_store: EventStore | None = None,
        scope: Scope | None = None,
    ):
        self.upbit = upbit
        self.binance = binance
        self.repository = repository
        self.binance_trx_address = binance_trx_address
        self.db = db
        self.event_store = event_store
        self.scope = scope
    
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
            error_msg = str(e)
            if isinstance(e, UpbitApiError) and e.error_code == "WITHDRAW_TIMEOUT":
                error_msg = (
                    "출금 확인이 지연되었습니다. 블록체인 전송이 완료되었다면 재시도해 주세요. "
                    f"(원인: {error_msg})"
                )
            await self.repository.update_status(
                transfer.transfer_id,
                TransferStatus.FAILED,
                error_message=error_msg,
            )
            return await self.repository.get(transfer.transfer_id)  # type: ignore
    
    async def _step1_buy_trx(self, transfer: Transfer) -> Transfer:
        """Step 1: Upbit에서 TRX 매수 (필요 시)
        
        requested_amount는 KRW+TRX 합산. TRX로 충당 가능하면 매수 생략.
        """
        logger.info(f"[Deposit Step 1] Buying TRX on Upbit: {transfer.transfer_id}")
        
        await self.repository.update_status(
            transfer.transfer_id,
            TransferStatus.PURCHASING,
            current_step=0,
        )
        
        # TRX 잔고 확인: 이미 충분하면 매수 생략
        trx_account = await self.upbit.get_account("TRX")
        trx_balance = trx_account.balance if trx_account else Decimal("0")
        trx_sendable = max(Decimal("0"), trx_balance - self.NETWORK_FEE_TRX)
        ticker = await self.upbit.get_ticker("KRW-TRX")
        trx_krw_price = Decimal(str(ticker.trade_price)) if ticker else Decimal("0")
        trx_value_krw = trx_sendable * trx_krw_price if trx_krw_price > 0 else Decimal("0")
        
        if trx_value_krw >= transfer.requested_amount:
            logger.info(
                f"[Deposit Step 1] TRX 잔고 충분 ({trx_sendable} TRX), 매수 생략"
            )
            await self.repository.update_status(
                transfer.transfer_id,
                TransferStatus.PURCHASING,
                current_step=1,
            )
            return await self.repository.get(transfer.transfer_id)  # type: ignore
        
        # 부족분만 KRW로 TRX 시장가 매수
        buy_amount_krw = transfer.requested_amount - trx_value_krw
        if buy_amount_krw < Decimal("1000"):  # Upbit 최소 주문
            buy_amount_krw = Decimal("0")
        if buy_amount_krw <= 0:
            await self.repository.update_status(
                transfer.transfer_id,
                TransferStatus.PURCHASING,
                current_step=1,
            )
            return await self.repository.get(transfer.transfer_id)  # type: ignore
        
        order = await self.upbit.place_market_buy_order(
            market="KRW-TRX",
            price=buy_amount_krw,
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
        
        # 주의: Binance Spot TRX 확인으로 Step 2 건너뛰기 금지.
        # 다른 출처(이전 이체 잔여 등)의 TRX를 이번 이체로 오인할 수 있음.
        
        # 현재 TRX 잔고 확인
        trx_account = await self.upbit.get_account("TRX")
        if not trx_account:
            raise ValueError(f"TRX 계좌 조회 실패")

        # balance 부족하지만 locked 있음 → 진행 중인 출금이 있을 수 있음
        if trx_account.balance <= Decimal("1") and trx_account.locked > Decimal("1"):
            pending = await self.upbit.get_withdraws(currency="TRX")
            for w in pending:
                if not w.is_done and not w.is_failed:
                    logger.info(
                        f"[Deposit Step 2] 진행 중 출금 대기: {w.uuid} state={w.state}"
                    )
                    try:
                        completed_withdraw = await self.upbit.wait_withdraw_done(
                            w.uuid,
                            timeout=900.0,  # 15분 (TRX 네트워크 지연 대비)
                            poll_interval=10.0,
                        )
                    except UpbitApiError as e:
                        if e.error_code == "WITHDRAW_TIMEOUT":
                            binance_trx = await self.binance.get_spot_balance("TRX")
                            if float(binance_trx.get("free", "0")) >= 1.0:
                                logger.info(
                                    "[Deposit Step 2] 출금 타임아웃 but TRX 이미 Binance 도착 (복구)"
                                )
                                await self.repository.update_status(
                                    transfer.transfer_id,
                                    TransferStatus.CONFIRMING,
                                    current_step=3,
                                )
                                return await self.repository.get(transfer.transfer_id)  # type: ignore
                        raise
                    if completed_withdraw.txid:
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
                        f"[Deposit Step 2] 기존 출금 완료, Step 3로 진행"
                    )
                    return await self.repository.get(transfer.transfer_id)  # type: ignore
            raise ValueError(
                f"TRX 잔고 부족 (사용가능={trx_account.balance}, 잠김={trx_account.locked}). "
                f"Upbit에서 진행 중인 출금이 완료될 때까지 대기 후 재시도하세요."
            )

        if trx_account.balance <= Decimal("1"):
            # 복구: 이전 출금 시도로 TRX가 이미 Binance에 도착했을 수 있음 (재시도 시)
            binance_trx = await self.binance.get_spot_balance("TRX")
            if float(binance_trx.get("free", "0")) >= 1.0:
                logger.info(
                    "[Deposit Step 2] Upbit TRX 부족 but Binance에 이미 도착 (이전 출금 완료, 복구)"
                )
                await self.repository.update_status(
                    transfer.transfer_id,
                    TransferStatus.CONFIRMING,
                    current_step=3,
                )
                return await self.repository.get(transfer.transfer_id)  # type: ignore
            raise ValueError(
                f"TRX 잔고 부족 (사용가능={trx_account.balance}, 잠김={trx_account.locked}). "
                f"입금 요청 금액에 맞는 TRX가 필요합니다. KRW로 TRX를 매수한 후 재시도하세요."
            )

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
        
        # 출금 완료 대기 (최대 15분, TRX 네트워크 지연 대비)
        try:
            completed_withdraw = await self.upbit.wait_withdraw_done(
                withdraw.uuid,
                timeout=900.0,
                poll_interval=10.0,
            )
        except UpbitApiError as e:
            if e.error_code == "WITHDRAW_TIMEOUT":
                binance_trx = await self.binance.get_spot_balance("TRX")
                if float(binance_trx.get("free", "0")) >= 1.0:
                    logger.info(
                        "[Deposit Step 2] 출금 타임아웃 but TRX 이미 Binance 도착 (복구)"
                    )
                    await self.repository.update_status(
                        transfer.transfer_id,
                        TransferStatus.CONFIRMING,
                        current_step=3,
                    )
                    return await self.repository.get(transfer.transfer_id)  # type: ignore
            raise
        
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
        
        # 이미 Spot에 TRX가 있으면 즉시 확인
        trx_bal = await self.binance.get_spot_balance("TRX")
        if float(trx_bal.get("free", "0")) >= 1.0:
            await self.repository.update_status(
                transfer.transfer_id, TransferStatus.CONFIRMING, current_step=3
            )
            return await self.repository.get(transfer.transfer_id)  # type: ignore
        since_ms = int(transfer.requested_at.timestamp() * 1000) - 60000
        deposit = await self.binance.wait_deposit_confirmed(
            coin="TRX",
            min_amount=1.0,  # 최소 1 TRX 이상
            timeout=600.0,
            poll_interval=30.0,
            since_time_ms=since_ms,
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
        
        # 실제 수령 USDT (이번 입금만, Spot 전체 잔고 아님)
        actual_usdt = self._parse_usdt_from_sell_order(order)
        await self.repository.update_amounts(
            transfer.transfer_id,
            actual_amount=actual_usdt,
        )
        
        # SPOT 거래 이벤트 기록 (TRX 매도 -> USDT 수령)
        trx_qty = Decimal(str(order.get("executedQty", "0")))
        avg_price = Decimal(str(order.get("cummulativeQuoteQty", "0"))) / trx_qty if trx_qty > 0 else Decimal("0")
        commission = Decimal("0")
        commission_asset = "USDT"
        for fill in order.get("fills", []):
            commission += Decimal(str(fill.get("commission", "0")))
            commission_asset = fill.get("commissionAsset", "USDT")
        
        await self._record_spot_trade_event(
            transfer_id=transfer.transfer_id,
            side="SELL",
            symbol="TRXUSDT",
            qty=trx_qty,
            price=avg_price,
            quote_qty=actual_usdt,
            commission=commission,
            commission_asset=commission_asset,
            order_id=str(order.get("orderId")),
        )
        
        await self.repository.update_status(
            transfer.transfer_id,
            TransferStatus.CONVERTING,
            current_step=4,
        )
        
        logger.info(
            f"[Deposit Step 4] TRX sold: {trx_amount} TRX -> {actual_usdt} USDT",
            extra={"order_id": order.get("orderId")},
        )
        
        return await self.repository.get(transfer.transfer_id)  # type: ignore
    
    def _parse_usdt_from_sell_order(self, order: dict[str, Any]) -> Decimal:
        """TRX 매도 주문 결과에서 실제 수령 USDT 추출 (이번 입금분만)
        
        cummulativeQuoteQty - USDT 수수료 = 실제 Spot에 입금된 금액.
        전체 Spot 잔고가 아닌 이번 거래분만 기록해야 예상 금액과 일치.
        """
        gross = Decimal(str(order.get("cummulativeQuoteQty", "0")))
        commission_usdt = Decimal("0")
        for fill in order.get("fills", []):
            if fill.get("commissionAsset") == "USDT":
                commission_usdt += Decimal(str(fill.get("commission", "0")))
        return max(Decimal("0"), gross - commission_usdt)
    
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
        
        # 내부 이체 이벤트 기록 (SPOT -> FUTURES)
        await self._record_internal_transfer_event(
            transfer_id=transfer.transfer_id,
            asset="USDT",
            amount=Decimal(str(usdt_amount)),
            from_venue="SPOT",
            to_venue="FUTURES",
            tran_id=str(result.get("tranId")),
        )
        
        # actual_amount는 Step 4에서 TRX 매도 결과로 이미 기록됨 (전체 Spot 잔고 아님)
        
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
        24시간 이내 KRW 입금은 출금 불가이므로 인출 가능 금액만 입금에 사용.
        예상 FUTURES USDT 입금액 계산용 시세 정보 포함.
        
        Returns:
            입금 상태 정보
        """
        base_status = await self.upbit.get_deposit_status()
        
        # 24시간 이내 KRW 입금 조회 및 인출 가능 금액 계산
        krw_locked_24h, krw_locked_detail = await self._get_krw_locked_within_hold_period()
        krw_balance = Decimal(base_status["krw_balance"])
        krw_withdrawable = max(Decimal("0"), krw_balance - krw_locked_24h)
        fee_krw = Decimal(base_status["fee_krw"])
        min_deposit_krw = Decimal(base_status["min_deposit_krw"])
        
        # 예상 FUTURES USDT 입금액 계산용 시세 정보
        price_info = await self._get_price_info()
        trx_balance = Decimal(base_status["trx_balance"])
        trx_krw_price = Decimal(price_info["trx_krw_price"] or "0")
        
        # 최대 입금 가능 금액 = KRW(인출가능-수수료) + TRX(네트워크수수료 1 제외 후 KRW 환산)
        # TRX도 직접 전송 가능하므로 합산
        krw_part = max(Decimal("0"), krw_withdrawable - fee_krw)
        trx_sendable = max(Decimal("0"), trx_balance - self.NETWORK_FEE_TRX)
        trx_part_krw = trx_sendable * trx_krw_price if trx_krw_price > 0 else Decimal("0")
        max_deposit_krw = krw_part + trx_part_krw
        
        # 입금 가능: 수수료 커버 가능 + 최대 입금액 >= 최소 입금액
        can_deposit = (
            base_status["can_deposit"]
            and max_deposit_krw >= min_deposit_krw
        )
        
        base_status.update({
            "can_deposit": can_deposit,
            "krw_withdrawable": str(krw_withdrawable),
            "krw_locked_24h": str(krw_locked_24h),
            "krw_locked_24h_detail": krw_locked_detail,
            "max_deposit_krw": str(max_deposit_krw),
            # 예상 입금 계산용 시세 정보
            "trx_usdt_price": price_info["trx_usdt_price"],
            "trx_krw_price": price_info["trx_krw_price"],
            "network_fee_trx": str(self.NETWORK_FEE_TRX),
            "binance_trade_fee_rate": str(self.BINANCE_TRADE_FEE_RATE),
            "upbit_trade_fee_rate": str(self.UPBIT_TRADE_FEE_RATE),
        })
        
        return base_status
    
    async def _get_krw_locked_within_hold_period(
        self,
    ) -> tuple[Decimal, list[dict[str, Any]]]:
        """24시간(설정값) 이내 KRW 입금 합계 조회
        
        Upbit 정책: KRW 입금 후 일정 시간 이내에는 출금 불가.
        
        Returns:
            (잠긴 금액 합계, 입금 내역 목록)
        """
        hold_hours = 24
        if self.db:
            try:
                config_store = ConfigStore(self.db)
                transfer_config = await config_store.get("transfer")
                hold_hours = int(transfer_config.get("krw_deposit_hold_hours", 24))
            except Exception as e:
                logger.warning(f"ConfigStore 조회 실패, 기본값 24시간 사용: {e}")
        
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hold_hours)
        krw_locked = Decimal("0")
        detail: list[dict[str, Any]] = []
        
        try:
            deposits = await self.upbit.get_deposits(currency="KRW", limit=100)
            for d in deposits:
                # 완료된 입금만 (Upbit API: ACCEPTED)
                if d.state.upper() != "ACCEPTED":
                    continue
                deposit_time = d.done_at if d.done_at else d.created_at
                if deposit_time.tzinfo is None:
                    deposit_time = deposit_time.replace(tzinfo=timezone.utc)
                if deposit_time >= cutoff:
                    krw_locked += d.amount
                    detail.append({
                        "amount": str(d.amount),
                        "done_at": deposit_time.isoformat(),
                    })
        except Exception as e:
            logger.warning(f"Upbit KRW 입금 내역 조회 실패: {e}")
        
        return krw_locked, detail
    
    async def _get_price_info(self) -> dict[str, str]:
        """TRX 시세 정보 조회 (예상 입금 USDT 계산용)
        
        Returns:
            trx_usdt_price, trx_krw_price
        """
        trx_usdt_price = "0"
        trx_krw_price = "0"
        
        try:
            ticker = await self.binance.get_ticker_price("TRXUSDT")
            trx_usdt_price = ticker.get("price", "0")
        except Exception as e:
            logger.warning(f"TRX/USDT 시세 조회 실패: {e}")
        
        try:
            ticker = await self.upbit.get_ticker("KRW-TRX")
            if ticker:
                trx_krw_price = str(ticker.trade_price)
        except Exception as e:
            logger.warning(f"TRX/KRW 시세 조회 실패: {e}")
        
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
        
        # SPOT scope 생성
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
        logger.debug(f"[Deposit] SPOT 거래 이벤트 기록: {side} {qty} {symbol}")
    
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
        logger.debug(f"[Deposit] 내부 이체 이벤트 기록: {amount} {asset} {from_venue} -> {to_venue}")
