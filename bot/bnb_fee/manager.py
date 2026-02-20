"""
BNB 수수료 자동 충전 관리자

Futures에서 BNB 수수료 할인을 위해 BNB 잔고를 자동으로 유지.
BNB 비율이 임계치 이하로 떨어지면 Spot에서 구매/이체.

3단계 폴백 로직:
1. Spot BNB 충분 → Spot→Futures BNB 이체
2. Spot USDT 충분 → USDT로 BNB 구매 후 Futures 이체
3. Spot USDT 부족 → Futures→Spot USDT 이체 후 BNB 구매 후 Futures 이체
"""

import asyncio
import logging
from decimal import Decimal
from typing import Any, Callable, Awaitable
from uuid import uuid4

from adapters.binance.rest_client import BinanceRestClient
from core.domain.events import Event, EventTypes
from core.storage.event_store import EventStore
from core.storage.config_store import ConfigStore
from core.types import Scope

logger = logging.getLogger(__name__)

# BNB 최소 주문 수량 (Binance 기준)
MIN_BNB_ORDER_QTY = Decimal("0.01")
# 구매 시 추가 버퍼 (슬리피지, 수수료 고려)
BUY_BUFFER_RATIO = Decimal("1.02")


class BnbFeeManager:
    """BNB 수수료 자동 충전 관리자
    
    Futures 계좌의 BNB 비율이 설정된 임계치 이하로 떨어지면
    자동으로 Spot에서 BNB를 구매하거나 이체하여 충전.
    
    Args:
        binance: Binance REST 클라이언트
        config_store: 설정 저장소
        event_store: 이벤트 저장소
        scope: 거래 범위
        notifier_callback: 알림 전송 콜백 (선택)
    """
    
    def __init__(
        self,
        binance: BinanceRestClient,
        config_store: ConfigStore,
        event_store: EventStore,
        scope: Scope,
        notifier_callback: Callable[[str, str, dict[str, Any] | None], Awaitable[None]] | None = None,
    ):
        self.binance = binance
        self.config_store = config_store
        self.event_store = event_store
        self.scope = scope
        self._notifier_callback = notifier_callback
        
        # 중복 실행 방지 플래그
        self._replenish_in_progress = False
        
        # 마지막 체크 시간
        self._last_check_time: float = 0.0
    
    async def _send_notification(
        self,
        message: str,
        level: str = "INFO",
        extra: dict[str, Any] | None = None,
    ) -> None:
        """알림 전송 (콜백이 있는 경우에만)"""
        if self._notifier_callback:
            try:
                await self._notifier_callback(message, level, extra)
            except Exception as e:
                logger.warning(f"알림 전송 실패: {e}")
    
    async def _record_event(
        self,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        """이벤트 기록"""
        event = Event.create(
            event_type=event_type,
            entity_kind="BNB_FEE",
            entity_id="auto_replenish",
            scope=self.scope,
            source="BOT",
            payload=payload,
            dedup_key=f"bnb_fee:{uuid4().hex}",
        )
        await self.event_store.append(event)
    
    async def should_check(self) -> bool:
        """체크 시점인지 확인
        
        설정된 체크 주기(check_interval_sec)에 따라 체크 여부 결정.
        
        Returns:
            체크해야 하면 True
        """
        config = await self.config_store.get("bnb_fee")
        
        if not config.get("enabled", True):
            return False
        
        check_interval = config.get("check_interval_sec", 3600)
        now = asyncio.get_event_loop().time()
        
        if now - self._last_check_time >= check_interval:
            return True
        
        return False
    
    async def check_and_replenish(self) -> bool:
        """BNB 비율 체크 및 필요시 충전
        
        Returns:
            충전이 실행되었으면 True (성공/실패 무관)
        """
        # 중복 실행 방지
        if self._replenish_in_progress:
            logger.debug("BNB 충전 이미 진행 중")
            return False
        
        config = await self.config_store.get("bnb_fee")
        
        # 기능 비활성화 확인
        if not config.get("enabled", True):
            return False
        
        # 마지막 체크 시간 갱신
        self._last_check_time = asyncio.get_event_loop().time()
        
        try:
            # 1. Futures 잔고 확인
            futures_balances = await self.binance.get_balances()
            
            bnb_balance = Decimal("0")
            usdt_balance = Decimal("0")
            
            for balance in futures_balances:
                if balance.asset == "BNB":
                    bnb_balance = balance.wallet_balance
                elif balance.asset == "USDT":
                    usdt_balance = balance.wallet_balance
            
            # 2. BNB 가격 조회
            bnb_price = await self._get_bnb_price()
            if bnb_price <= 0:
                logger.warning("BNB 가격 조회 실패")
                return False
            
            # 3. BNB를 USDT로 환산하여 총 자산 계산
            bnb_value_usdt = bnb_balance * bnb_price
            total_value_usdt = bnb_value_usdt + usdt_balance
            
            if total_value_usdt <= 0:
                logger.debug("Futures 잔고 없음, BNB 충전 건너뜀")
                return False
            
            # 4. 현재 BNB 비율 계산
            current_ratio = bnb_value_usdt / total_value_usdt
            
            min_ratio = Decimal(config.get("min_bnb_ratio", "0.01"))
            min_trigger_usdt = Decimal(config.get("min_trigger_usdt", "10"))
            
            # 5. 비율 충분하면 종료
            if current_ratio >= min_ratio:
                logger.debug(
                    f"BNB 비율 충분: {current_ratio:.4f} >= {min_ratio}",
                )
                return False
            
            # 6. 필요 BNB 계산
            target_ratio = Decimal(config.get("target_bnb_ratio", "0.02"))
            target_bnb_value = target_ratio * total_value_usdt
            needed_bnb_value = target_bnb_value - bnb_value_usdt
            
            # 최소 트리거 금액 미만이면 건너뜀
            if needed_bnb_value < min_trigger_usdt:
                logger.debug(
                    f"필요 BNB 금액이 최소 트리거 미만: {needed_bnb_value:.2f} < {min_trigger_usdt}"
                )
                return False
            
            needed_bnb = needed_bnb_value / bnb_price
            
            # 최소 주문 수량 미만이면 건너뜀
            if needed_bnb < MIN_BNB_ORDER_QTY:
                logger.debug(f"필요 BNB가 최소 주문 수량 미만: {needed_bnb:.4f}")
                return False
            
            # 7. BNB 부족 이벤트 기록
            await self._record_event(
                EventTypes.BNB_BALANCE_LOW,
                {
                    "current_bnb": str(bnb_balance),
                    "current_ratio": str(current_ratio),
                    "min_ratio": str(min_ratio),
                    "needed_bnb": str(needed_bnb),
                    "needed_usdt": str(needed_bnb_value),
                },
            )
            
            logger.info(
                f"BNB 부족 감지: 현재 {current_ratio:.4f} < 최소 {min_ratio}, "
                f"필요 BNB: {needed_bnb:.4f} ({needed_bnb_value:.2f} USDT)"
            )
            
            # 8. 충전 실행
            self._replenish_in_progress = True
            try:
                await self._replenish_bnb(needed_bnb, bnb_price, usdt_balance)
                return True
            finally:
                self._replenish_in_progress = False
                
        except Exception as e:
            logger.error(f"BNB 체크/충전 실패: {e}", exc_info=True)
            return False
    
    async def _get_bnb_price(self) -> Decimal:
        """BNB 현재가 조회 (USDT 기준)
        
        Returns:
            BNB 가격 (Decimal), 실패 시 0
        """
        try:
            ticker = await self.binance.get_ticker_price(symbol="BNBUSDT")
            return Decimal(ticker["price"])
        except Exception as e:
            logger.error(f"BNB 가격 조회 실패: {e}")
            return Decimal("0")
    
    async def _replenish_bnb(
        self,
        needed_bnb: Decimal,
        bnb_price: Decimal,
        futures_usdt: Decimal,
    ) -> None:
        """BNB 충전 실행 (3단계 폴백)
        
        Args:
            needed_bnb: 필요한 BNB 수량
            bnb_price: 현재 BNB 가격 (USDT)
            futures_usdt: Futures USDT 잔고 (폴백용)
        """
        # 충전 시작 이벤트
        await self._record_event(
            EventTypes.BNB_REPLENISH_STARTED,
            {
                "needed_bnb": str(needed_bnb),
                "bnb_price": str(bnb_price),
            },
        )
        
        await self._send_notification(
            f"BNB 자동 충전 시작: {needed_bnb:.4f} BNB 필요",
            level="INFO",
        )
        
        try:
            # Spot 잔고 확인
            spot_balances = await self.binance.get_spot_balances()
            spot_bnb = Decimal(spot_balances.get("BNB", {}).get("free", "0"))
            spot_usdt = Decimal(spot_balances.get("USDT", {}).get("free", "0"))
            
            remaining_bnb = needed_bnb
            
            # Step 1: Spot에 BNB가 있으면 먼저 이체
            if spot_bnb >= MIN_BNB_ORDER_QTY:
                transfer_bnb = min(spot_bnb, remaining_bnb)
                
                if transfer_bnb >= MIN_BNB_ORDER_QTY:
                    logger.info(f"Step 1: Spot BNB {transfer_bnb:.4f} -> Futures 이체")
                    
                    await self.binance.internal_transfer(
                        asset="BNB",
                        amount=str(transfer_bnb.quantize(Decimal("0.0001"))),
                        from_account="SPOT",
                        to_account="FUTURES",
                    )
                    
                    remaining_bnb -= transfer_bnb
                    
                    if remaining_bnb < MIN_BNB_ORDER_QTY:
                        # 충전 완료
                        await self._complete_replenish(needed_bnb, "spot_transfer")
                        return
            
            # Step 2: BNB 구매 필요
            needed_usdt_for_buy = remaining_bnb * bnb_price * BUY_BUFFER_RATIO
            
            # Step 2a: Spot USDT 부족하면 Futures에서 가져오기
            if spot_usdt < needed_usdt_for_buy:
                transfer_usdt = needed_usdt_for_buy - spot_usdt + Decimal("5")  # 여유분
                
                # Futures에 USDT가 충분한지 확인
                if futures_usdt < transfer_usdt:
                    raise ValueError(
                        f"Futures USDT 부족: {futures_usdt:.2f} < {transfer_usdt:.2f}"
                    )
                
                logger.info(f"Step 2a: Futures USDT {transfer_usdt:.2f} -> Spot 이체")
                
                await self.binance.internal_transfer(
                    asset="USDT",
                    amount=str(transfer_usdt.quantize(Decimal("0.01"))),
                    from_account="FUTURES",
                    to_account="SPOT",
                )
                
                spot_usdt += transfer_usdt
            
            # Step 2b: Spot에서 BNB 구매
            logger.info(f"Step 2b: USDT {needed_usdt_for_buy:.2f}로 BNB 구매")
            
            buy_result = await self.binance.spot_market_buy(
                symbol="BNBUSDT",
                quote_qty=str(needed_usdt_for_buy.quantize(Decimal("0.01"))),
            )
            
            bought_bnb = Decimal(buy_result.get("executedQty", "0"))
            logger.info(f"BNB 구매 완료: {bought_bnb:.4f} BNB")
            
            # Step 3: 구매한 BNB를 Futures로 이체
            if bought_bnb >= MIN_BNB_ORDER_QTY:
                logger.info(f"Step 3: 구매한 BNB {bought_bnb:.4f} -> Futures 이체")
                
                await self.binance.internal_transfer(
                    asset="BNB",
                    amount=str(bought_bnb.quantize(Decimal("0.0001"))),
                    from_account="SPOT",
                    to_account="FUTURES",
                )
            
            await self._complete_replenish(needed_bnb, "spot_buy_transfer")
            
        except Exception as e:
            logger.error(f"BNB 충전 실패: {e}", exc_info=True)
            
            await self._record_event(
                EventTypes.BNB_REPLENISH_FAILED,
                {
                    "needed_bnb": str(needed_bnb),
                    "error": str(e),
                },
            )
            
            await self._send_notification(
                f"BNB 자동 충전 실패: {e}",
                level="ERROR",
                extra={"needed_bnb": str(needed_bnb)},
            )
            
            raise
    
    async def _complete_replenish(self, amount: Decimal, method: str) -> None:
        """충전 완료 처리
        
        Args:
            amount: 충전된 BNB 양
            method: 충전 방법 (spot_transfer, spot_buy_transfer)
        """
        await self._record_event(
            EventTypes.BNB_REPLENISH_COMPLETED,
            {
                "amount": str(amount),
                "method": method,
            },
        )
        
        logger.info(f"BNB 충전 완료: {amount:.4f} BNB (방법: {method})")
        
        await self._send_notification(
            f"BNB 자동 충전 완료: {amount:.4f} BNB",
            level="INFO",
            extra={"method": method},
        )
    
    async def force_check(self) -> bool:
        """강제 체크 실행 (체크 주기 무시)
        
        Returns:
            충전이 실행되었으면 True
        """
        self._last_check_time = 0.0
        return await self.check_and_replenish()
    
    def get_status(self) -> dict[str, Any]:
        """현재 상태 반환
        
        Returns:
            상태 정보 딕셔너리
        """
        return {
            "replenish_in_progress": self._replenish_in_progress,
            "last_check_time": self._last_check_time,
        }
