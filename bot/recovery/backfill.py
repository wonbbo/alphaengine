"""
HistoricalDataRecovery

Bot 최초 실행 시 과거 데이터를 백필하는 컴포넌트.
Income History, Transfer History, Convert History, Deposit/Withdraw History 조회.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any

from adapters.binance.rest_client import BinanceRestClient
from core.domain.events import Event, EventTypes
from core.storage.event_store import EventStore
from core.types import Scope
from core.utils.dedup import (
    make_income_dedup_key,
    make_transfer_dedup_key,
    make_convert_dedup_key,
    make_dust_dedup_key,
    make_deposit_dedup_key,
    make_withdraw_dedup_key,
    make_funding_dedup_key,
    make_commission_rebate_dedup_key,
)

logger = logging.getLogger(__name__)


class HistoricalDataRecovery:
    """과거 데이터 복구기
    
    Bot 최초 실행 시 과거 이벤트들을 백필합니다.
    
    Args:
        rest_client: Binance REST 클라이언트
        event_store: 이벤트 저장소
        scope: 거래 범위
        max_days: 최대 복구 일수 (기본 20일)
    """
    
    DEFAULT_MAX_DAYS = 20
    
    def __init__(
        self,
        rest_client: BinanceRestClient,
        event_store: EventStore,
        scope: Scope,
        max_days: int = DEFAULT_MAX_DAYS,
    ):
        self.rest_client = rest_client
        self.event_store = event_store
        self.scope = scope
        self.max_days = max_days
    
    async def backfill(
        self,
        days: int | None = None,
        epoch_date: str | None = None,
    ) -> dict[str, int]:
        """과거 데이터 백필 실행
        
        Args:
            days: 백필할 일수 (None이면 max_days 사용, epoch_date와 함께 사용 시 무시)
            epoch_date: 백필 시작 날짜 (YYYY-MM-DD, InitialCapitalEstablished의 snapshot_date)
                       지정 시 이 날짜의 UTC 00:00:00부터 현재까지 백필
            
        Returns:
            백필된 이벤트 수:
            {
                "income": 150,
                "transfer": 5,
                "convert": 2,
                "deposit": 1,
                "withdraw": 0,
                "dust": 0,
                "total": 158
            }
        """
        end_time = datetime.now(timezone.utc)
        
        if epoch_date:
            # epoch_date가 제공되면 해당 날짜의 UTC 00:00:00부터 백필
            # InitialCapitalEstablished와 시간 동기화됨
            epoch_datetime = datetime.fromisoformat(epoch_date)
            start_time = datetime(
                epoch_datetime.year,
                epoch_datetime.month,
                epoch_datetime.day,
                0, 0, 0,
                tzinfo=timezone.utc,
            )
            backfill_days = (end_time - start_time).days
            logger.info(f"과거 데이터 백필 시작 (epoch_date={epoch_date}, {backfill_days}일)")
        else:
            # 기존 방식: days 파라미터 사용
            backfill_days = days or self.max_days
            start_time = end_time - timedelta(days=backfill_days)
            logger.info(f"과거 데이터 백필 시작 ({backfill_days}일)")
        
        results = {
            "income": 0,
            "transfer": 0,
            "convert": 0,
            "deposit": 0,
            "withdraw": 0,
            "dust": 0,
            "total": 0,
        }
        
        income_count = await self._backfill_income(start_time, end_time)
        results["income"] = income_count
        await asyncio.sleep(0.5)
        
        transfer_count = await self._backfill_transfers(start_time, end_time)
        results["transfer"] = transfer_count
        await asyncio.sleep(0.5)
        
        convert_count = await self._backfill_converts(start_time, end_time)
        results["convert"] = convert_count
        await asyncio.sleep(0.5)
        
        deposit_count, withdraw_count = await self._backfill_deposit_withdraw(
            start_time, end_time
        )
        results["deposit"] = deposit_count
        results["withdraw"] = withdraw_count
        await asyncio.sleep(0.5)
        
        dust_count = await self._backfill_dust()
        results["dust"] = dust_count
        
        results["total"] = sum(
            v for k, v in results.items() if k != "total"
        )
        
        logger.info(
            "과거 데이터 백필 완료",
            extra={
                "days": backfill_days,
                "total_events": results["total"],
                "breakdown": results,
            },
        )
        
        return results
    
    async def _backfill_income(
        self,
        start_time: datetime,
        end_time: datetime,
    ) -> int:
        """Income History 백필 (펀딩비, 수수료, 이체 등)"""
        logger.debug("Income History 백필 시작")
        
        event_count = 0
        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)
        current_start = start_ms
        
        while current_start < end_ms:
            try:
                income_list = await self.rest_client.get_income_history(
                    start_time=current_start,
                    end_time=end_ms,
                    limit=1000,
                )
                
                if not income_list:
                    break
                
                for income in income_list:
                    saved = await self._create_income_event(income)
                    if saved:
                        event_count += 1
                
                last_time = income_list[-1].get("time", 0)
                current_start = last_time + 1
                
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Income History 조회 실패: {e}")
                break
        
        logger.debug(f"Income History 백필 완료: {event_count}건")
        return event_count
    
    async def _create_income_event(self, income: dict[str, Any]) -> bool:
        """Income 데이터를 이벤트로 변환 및 저장"""
        income_type = income.get("incomeType", "")
        tran_id = income.get("tranId", 0)
        
        if income_type == "FUNDING_FEE":
            event_type = EventTypes.FUNDING_APPLIED
            dedup_key = make_funding_dedup_key(
                exchange=self.scope.exchange,
                symbol=income.get("symbol", ""),
                funding_ts=income.get("time", 0),
            )
            entity_kind = "FUNDING"
        elif income_type == "COMMISSION_REBATE":
            event_type = EventTypes.COMMISSION_REBATE_RECEIVED
            dedup_key = make_commission_rebate_dedup_key(
                exchange=self.scope.exchange,
                tran_id=tran_id,
            )
            entity_kind = "REBATE"
        elif income_type == "TRANSFER":
            event_type = EventTypes.INTERNAL_TRANSFER_COMPLETED
            dedup_key = make_transfer_dedup_key(
                exchange=self.scope.exchange,
                transfer_id=str(tran_id),
            )
            entity_kind = "TRANSFER"
        else:
            return False
        
        income_amount = Decimal(income.get("income", "0"))
        
        payload = {
            "symbol": income.get("symbol", ""),
            "income_type": income_type,
            "income": str(income_amount),
            "asset": income.get("asset", "USDT"),
            "info": income.get("info", ""),
            "tran_id": str(tran_id),
            "trade_id": income.get("tradeId", ""),
            "time": income.get("time", 0),
            "source": "backfill",
        }
        
        event = Event.create(
            event_type=event_type,
            source="BOT",
            entity_kind=entity_kind,
            entity_id=str(tran_id),
            scope=self.scope,
            dedup_key=dedup_key,
            payload=payload,
        )
        
        event = Event(
            event_id=event.event_id,
            event_type=event.event_type,
            ts=datetime.fromtimestamp(
                income.get("time", 0) / 1000, tz=timezone.utc
            ),
            correlation_id=event.correlation_id,
            causation_id=event.causation_id,
            command_id=event.command_id,
            source=event.source,
            entity_kind=event.entity_kind,
            entity_id=event.entity_id,
            scope=event.scope,
            dedup_key=event.dedup_key,
            payload=event.payload,
        )
        
        return await self.event_store.append(event)
    
    async def _backfill_transfers(
        self,
        start_time: datetime,
        end_time: datetime,
    ) -> int:
        """Transfer History 백필 (SPOT ↔ FUTURES 이체)"""
        logger.debug("Transfer History 백필 시작")
        
        event_count = 0
        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)
        
        for transfer_type in ["MAIN_UMFUTURE", "UMFUTURE_MAIN"]:
            try:
                current_page = 1
                
                while True:
                    result = await self.rest_client.get_transfer_history(
                        transfer_type=transfer_type,
                        start_time=start_ms,
                        end_time=end_ms,
                        current=current_page,
                        size=100,
                    )
                    
                    rows = result.get("rows", [])
                    if not rows:
                        break
                    
                    for transfer in rows:
                        saved = await self._create_transfer_event(transfer)
                        if saved:
                            event_count += 1
                    
                    if len(rows) < 100:
                        break
                    
                    current_page += 1
                    await asyncio.sleep(0.1)
                    
            except Exception as e:
                logger.error(f"Transfer History 조회 실패 ({transfer_type}): {e}")
        
        logger.debug(f"Transfer History 백필 완료: {event_count}건")
        return event_count
    
    async def _create_transfer_event(self, transfer: dict[str, Any]) -> bool:
        """Transfer 데이터를 이벤트로 변환 및 저장"""
        tran_id = str(transfer.get("tranId", 0))
        
        dedup_key = make_transfer_dedup_key(
            exchange=self.scope.exchange,
            transfer_id=tran_id,
        )
        
        payload = {
            "asset": transfer.get("asset", "USDT"),
            "amount": transfer.get("amount", "0"),
            "type": transfer.get("type", ""),
            "status": transfer.get("status", ""),
            "tran_id": tran_id,
            "timestamp": transfer.get("timestamp", 0),
            "source": "backfill",
        }
        
        event = Event.create(
            event_type=EventTypes.INTERNAL_TRANSFER_COMPLETED,
            source="BOT",
            entity_kind="TRANSFER",
            entity_id=tran_id,
            scope=self.scope,
            dedup_key=dedup_key,
            payload=payload,
        )
        
        ts_ms = transfer.get("timestamp", 0)
        if ts_ms:
            event = Event(
                event_id=event.event_id,
                event_type=event.event_type,
                ts=datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc),
                correlation_id=event.correlation_id,
                causation_id=event.causation_id,
                command_id=event.command_id,
                source=event.source,
                entity_kind=event.entity_kind,
                entity_id=event.entity_id,
                scope=event.scope,
                dedup_key=event.dedup_key,
                payload=event.payload,
            )
        
        return await self.event_store.append(event)
    
    async def _backfill_converts(
        self,
        start_time: datetime,
        end_time: datetime,
    ) -> int:
        """Convert History 백필 (간편 전환)"""
        logger.debug("Convert History 백필 시작")
        
        event_count = 0
        
        current_start = start_time
        while current_start < end_time:
            chunk_end = min(current_start + timedelta(days=30), end_time)
            
            start_ms = int(current_start.timestamp() * 1000)
            end_ms = int(chunk_end.timestamp() * 1000)
            
            try:
                result = await self.rest_client.get_convert_history(
                    start_time=start_ms,
                    end_time=end_ms,
                    limit=1000,
                )
                
                convert_list = result.get("list", [])
                
                for convert in convert_list:
                    saved = await self._create_convert_event(convert)
                    if saved:
                        event_count += 1
                
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Convert History 조회 실패: {e}")
            
            current_start = chunk_end
        
        logger.debug(f"Convert History 백필 완료: {event_count}건")
        return event_count
    
    async def _create_convert_event(self, convert: dict[str, Any]) -> bool:
        """Convert 데이터를 이벤트로 변환 및 저장"""
        order_id = str(convert.get("orderId", 0))
        
        dedup_key = make_convert_dedup_key(
            exchange=self.scope.exchange,
            order_id=order_id,
        )
        
        payload = {
            "quote_id": convert.get("quoteId", ""),
            "order_id": order_id,
            "order_status": convert.get("orderStatus", ""),
            "from_asset": convert.get("fromAsset", ""),
            "from_amount": convert.get("fromAmount", "0"),
            "to_asset": convert.get("toAsset", ""),
            "to_amount": convert.get("toAmount", "0"),
            "ratio": convert.get("ratio", ""),
            "inverse_ratio": convert.get("inverseRatio", ""),
            "create_time": convert.get("createTime", 0),
            "source": "backfill",
        }
        
        event = Event.create(
            event_type=EventTypes.CONVERT_EXECUTED,
            source="BOT",
            entity_kind="CONVERT",
            entity_id=order_id,
            scope=self.scope,
            dedup_key=dedup_key,
            payload=payload,
        )
        
        create_time = convert.get("createTime", 0)
        if create_time:
            event = Event(
                event_id=event.event_id,
                event_type=event.event_type,
                ts=datetime.fromtimestamp(create_time / 1000, tz=timezone.utc),
                correlation_id=event.correlation_id,
                causation_id=event.causation_id,
                command_id=event.command_id,
                source=event.source,
                entity_kind=event.entity_kind,
                entity_id=event.entity_id,
                scope=event.scope,
                dedup_key=event.dedup_key,
                payload=event.payload,
            )
        
        return await self.event_store.append(event)
    
    async def _backfill_deposit_withdraw(
        self,
        start_time: datetime,
        end_time: datetime,
    ) -> tuple[int, int]:
        """Deposit/Withdraw History 백필
        
        Note: 모든 상태의 입출금을 조회한 후, 완료된 것만 이벤트로 생성합니다.
        - Deposit status=1: Success (완료)
        - Withdraw status=6: Completed (완료)
        """
        logger.debug("Deposit/Withdraw History 백필 시작")
        
        deposit_count = 0
        withdraw_count = 0
        
        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)
        
        # 완료된 입금만 조회 (status=1: Success)
        # status 파라미터 없이 조회하면 모든 상태가 반환되지만,
        # 완료된 것만 Ledger에 기록해야 정합성이 맞음
        try:
            deposits = await self.rest_client.get_deposit_history(
                status=1,
                start_time=start_ms,
                end_time=end_ms,
                limit=1000,
            )
            
            for deposit in deposits:
                # 추가 안전장치: status 재확인
                if deposit.get("status") == 1:
                    saved = await self._create_deposit_event(deposit)
                    if saved:
                        deposit_count += 1
                    
        except Exception as e:
            logger.error(f"Deposit History 조회 실패: {e}")
        
        await asyncio.sleep(0.5)
        
        # 완료된 출금만 조회 (status=6: Completed)
        # Note: get_withdraw_history는 현재 start_time/end_time을 지원하지 않음
        # 필요시 REST 클라이언트 확장 필요
        try:
            withdraws = await self.rest_client.get_withdraw_history(
                status=6,
                limit=1000,
            )
            
            for withdraw in withdraws:
                # 추가 안전장치: status 재확인
                if withdraw.get("status") == 6:
                    saved = await self._create_withdraw_event(withdraw)
                    if saved:
                        withdraw_count += 1
                    
        except Exception as e:
            logger.error(f"Withdraw History 조회 실패: {e}")
        
        logger.debug(
            f"Deposit/Withdraw History 백필 완료: "
            f"입금 {deposit_count}건, 출금 {withdraw_count}건"
        )
        
        return deposit_count, withdraw_count
    
    async def _create_deposit_event(self, deposit: dict[str, Any]) -> bool:
        """Deposit 데이터를 이벤트로 변환 및 저장"""
        deposit_id = str(deposit.get("id", deposit.get("txId", "")))
        
        dedup_key = make_deposit_dedup_key(
            exchange=self.scope.exchange,
            deposit_id=deposit_id,
        )
        
        payload = {
            "id": deposit_id,
            "amount": deposit.get("amount", "0"),
            "coin": deposit.get("coin", ""),
            "network": deposit.get("network", ""),
            "status": deposit.get("status", 0),
            "address": deposit.get("address", ""),
            "tx_id": deposit.get("txId", ""),
            "insert_time": deposit.get("insertTime", 0),
            "source": "backfill",
        }
        
        event = Event.create(
            event_type=EventTypes.DEPOSIT_COMPLETED,
            source="BOT",
            entity_kind="DEPOSIT",
            entity_id=deposit_id,
            scope=self.scope,
            dedup_key=dedup_key,
            payload=payload,
        )
        
        insert_time = deposit.get("insertTime", 0)
        if insert_time:
            event = Event(
                event_id=event.event_id,
                event_type=event.event_type,
                ts=datetime.fromtimestamp(insert_time / 1000, tz=timezone.utc),
                correlation_id=event.correlation_id,
                causation_id=event.causation_id,
                command_id=event.command_id,
                source=event.source,
                entity_kind=event.entity_kind,
                entity_id=event.entity_id,
                scope=event.scope,
                dedup_key=event.dedup_key,
                payload=event.payload,
            )
        
        return await self.event_store.append(event)
    
    async def _create_withdraw_event(self, withdraw: dict[str, Any]) -> bool:
        """Withdraw 데이터를 이벤트로 변환 및 저장"""
        withdraw_id = str(withdraw.get("id", ""))
        
        dedup_key = make_withdraw_dedup_key(
            exchange=self.scope.exchange,
            withdraw_id=withdraw_id,
        )
        
        payload = {
            "id": withdraw_id,
            "amount": withdraw.get("amount", "0"),
            "transaction_fee": withdraw.get("transactionFee", "0"),
            "coin": withdraw.get("coin", ""),
            "status": withdraw.get("status", 0),
            "address": withdraw.get("address", ""),
            "tx_id": withdraw.get("txId", ""),
            "apply_time": withdraw.get("applyTime", ""),
            "network": withdraw.get("network", ""),
            "complete_time": withdraw.get("completeTime", ""),
            "source": "backfill",
        }
        
        event = Event.create(
            event_type=EventTypes.WITHDRAW_COMPLETED,
            source="BOT",
            entity_kind="WITHDRAW",
            entity_id=withdraw_id,
            scope=self.scope,
            dedup_key=dedup_key,
            payload=payload,
        )
        
        return await self.event_store.append(event)
    
    async def _backfill_dust(self) -> int:
        """Dust Log 백필 (소액 자산 전환)"""
        logger.debug("Dust Log 백필 시작")
        
        event_count = 0
        
        try:
            result = await self.rest_client.get_dust_log()
            
            dribblets = result.get("userAssetDribblets", [])
            
            for dribblet in dribblets:
                saved = await self._create_dust_event(dribblet)
                if saved:
                    event_count += 1
                    
        except Exception as e:
            logger.error(f"Dust Log 조회 실패: {e}")
        
        logger.debug(f"Dust Log 백필 완료: {event_count}건")
        return event_count
    
    async def _create_dust_event(self, dribblet: dict[str, Any]) -> bool:
        """Dust 데이터를 이벤트로 변환 및 저장"""
        trans_id = str(dribblet.get("transId", 0))
        
        dedup_key = make_dust_dedup_key(
            exchange=self.scope.exchange,
            trans_id=trans_id,
        )
        
        details = dribblet.get("userAssetDribbletDetails", [])
        from_assets = [d.get("fromAsset", "") for d in details]
        
        payload = {
            "trans_id": trans_id,
            "operate_time": dribblet.get("operateTime", 0),
            "total_transferred_amount": dribblet.get("totalTransferedAmount", "0"),
            "total_service_charge": dribblet.get("totalServiceChargeAmount", "0"),
            "from_assets": from_assets,
            "details": details,
            "source": "backfill",
        }
        
        event = Event.create(
            event_type=EventTypes.DUST_CONVERTED,
            source="BOT",
            entity_kind="DUST",
            entity_id=trans_id,
            scope=self.scope,
            dedup_key=dedup_key,
            payload=payload,
        )
        
        operate_time = dribblet.get("operateTime", 0)
        if operate_time:
            event = Event(
                event_id=event.event_id,
                event_type=event.event_type,
                ts=datetime.fromtimestamp(operate_time / 1000, tz=timezone.utc),
                correlation_id=event.correlation_id,
                causation_id=event.causation_id,
                command_id=event.command_id,
                source=event.source,
                entity_kind=event.entity_kind,
                entity_id=event.entity_id,
                scope=event.scope,
                dedup_key=event.dedup_key,
                payload=event.payload,
            )
        
        return await self.event_store.append(event)
