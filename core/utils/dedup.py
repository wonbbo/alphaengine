"""
Dedup Key 생성 유틸리티

이벤트 중복 제거를 위한 dedup_key 생성 함수 제공
TRD 문서의 dedup_key 규칙 준수
"""


def make_trade_dedup_key(
    exchange: str,
    venue: str,
    symbol: str,
    exchange_trade_id: str,
) -> str:
    """TradeExecuted용 dedup_key 생성

    Args:
        exchange: 거래소 (예: BINANCE)
        venue: 거래 장소 (예: FUTURES, SPOT)
        symbol: 심볼 (예: XRPUSDT)
        exchange_trade_id: 거래소의 체결 ID

    Returns:
        dedup_key: {exchange}:{venue}:{symbol}:trade:{exchange_trade_id}

    Example:
        >>> make_trade_dedup_key("BINANCE", "FUTURES", "XRPUSDT", "123456789")
        'BINANCE:FUTURES:XRPUSDT:trade:123456789'
    """
    return f"{exchange}:{venue}:{symbol}:trade:{exchange_trade_id}"


def make_order_dedup_key(
    exchange: str,
    venue: str,
    symbol: str,
    exchange_order_id: str,
) -> str:
    """Order*용 dedup_key 생성 (OrderPlaced, OrderCancelled 등)

    Args:
        exchange: 거래소
        venue: 거래 장소
        symbol: 심볼
        exchange_order_id: 거래소의 주문 ID

    Returns:
        dedup_key: {exchange}:{venue}:{symbol}:order:{exchange_order_id}

    Example:
        >>> make_order_dedup_key("BINANCE", "FUTURES", "XRPUSDT", "987654321")
        'BINANCE:FUTURES:XRPUSDT:order:987654321'
    """
    return f"{exchange}:{venue}:{symbol}:order:{exchange_order_id}"


def make_order_status_dedup_key(
    exchange: str,
    venue: str,
    symbol: str,
    exchange_order_id: str,
    status: str,
) -> str:
    """OrderUpdated용 dedup_key 생성 (상태별로 구분)

    Args:
        exchange: 거래소
        venue: 거래 장소
        symbol: 심볼
        exchange_order_id: 거래소의 주문 ID
        status: 주문 상태 (NEW, FILLED, CANCELLED 등)

    Returns:
        dedup_key: {exchange}:{venue}:{symbol}:order:{exchange_order_id}:{status}

    Example:
        >>> make_order_status_dedup_key("BINANCE", "FUTURES", "XRPUSDT", "123", "FILLED")
        'BINANCE:FUTURES:XRPUSDT:order:123:FILLED'
    """
    return f"{exchange}:{venue}:{symbol}:order:{exchange_order_id}:{status}"


def make_position_dedup_key(
    exchange: str,
    venue: str,
    symbol: str,
    side: str,
    qty: str,
    avg_price: str,
) -> str:
    """PositionChanged용 dedup_key 생성 (스냅샷 기반)

    Args:
        exchange: 거래소
        venue: 거래 장소
        symbol: 심볼
        side: 포지션 방향 (LONG, SHORT, BOTH)
        qty: 포지션 수량 (문자열, Decimal 정밀도 유지)
        avg_price: 평균 진입가 (문자열, Decimal 정밀도 유지)

    Returns:
        dedup_key: {exchange}:{venue}:{symbol}:position:{side}:{qty}:{avg_price}

    Example:
        >>> make_position_dedup_key("BINANCE", "FUTURES", "XRPUSDT", "LONG", "100", "0.5123")
        'BINANCE:FUTURES:XRPUSDT:position:LONG:100:0.5123'
    """
    return f"{exchange}:{venue}:{symbol}:position:{side}:{qty}:{avg_price}"


def make_balance_dedup_key(
    exchange: str,
    venue: str,
    account_id: str,
    asset: str,
    free: str,
    locked: str,
) -> str:
    """BalanceChanged용 dedup_key 생성 (스냅샷 기반)

    Args:
        exchange: 거래소
        venue: 거래 장소
        account_id: 계좌 ID
        asset: 자산 (예: USDT)
        free: 사용 가능 잔고 (문자열)
        locked: 잠긴 잔고 (문자열)

    Returns:
        dedup_key: {exchange}:{venue}:{account_id}:{asset}:{free}:{locked}

    Example:
        >>> make_balance_dedup_key("BINANCE", "FUTURES", "main", "USDT", "1000.5", "50.0")
        'BINANCE:FUTURES:main:USDT:1000.5:50.0'
    """
    return f"{exchange}:{venue}:{account_id}:{asset}:{free}:{locked}"


def make_ws_event_dedup_key(
    exchange: str,
    event_type: str,
    ts_ms: int,
) -> str:
    """WebSocket 연결 이벤트용 dedup_key 생성

    Args:
        exchange: 거래소
        event_type: 이벤트 타입 (connected, disconnected, reconnected)
        ts_ms: 타임스탬프 (밀리초)

    Returns:
        dedup_key: {exchange}:ws:{event_type}:{ts_ms}

    Example:
        >>> make_ws_event_dedup_key("BINANCE", "connected", 1708408800000)
        'BINANCE:ws:connected:1708408800000'
    """
    return f"{exchange}:ws:{event_type}:{ts_ms}"


def make_config_dedup_key(key: str, version: int) -> str:
    """ConfigChanged용 dedup_key 생성

    Args:
        key: 설정 키
        version: 설정 버전

    Returns:
        dedup_key: config:{key}:{version}

    Example:
        >>> make_config_dedup_key("strategy_params", 5)
        'config:strategy_params:5'
    """
    return f"config:{key}:{version}"


def make_drift_dedup_key(
    exchange: str,
    venue: str,
    symbol: str,
    drift_kind: str,
    time_bucket: str,
) -> str:
    """DriftDetected용 dedup_key 생성 (스팸 방지용 time_bucket 포함)

    Args:
        exchange: 거래소
        venue: 거래 장소
        symbol: 심볼
        drift_kind: drift 종류 (position, balance, order 등)
        time_bucket: 시간 버킷 (예: 2026-02-20T12:00)

    Returns:
        dedup_key: {exchange}:{venue}:{symbol}:drift:{drift_kind}:{time_bucket}

    Example:
        >>> make_drift_dedup_key("BINANCE", "FUTURES", "XRPUSDT", "position", "2026-02-20T12:00")
        'BINANCE:FUTURES:XRPUSDT:drift:position:2026-02-20T12:00'
    """
    return f"{exchange}:{venue}:{symbol}:drift:{drift_kind}:{time_bucket}"


def make_reconciliation_dedup_key(
    exchange: str,
    venue: str,
    symbol: str,
    drift_event_seq: int,
) -> str:
    """ReconciliationPerformed용 dedup_key 생성

    Args:
        exchange: 거래소
        venue: 거래 장소
        symbol: 심볼
        drift_event_seq: 관련 drift 이벤트 시퀀스

    Returns:
        dedup_key: {exchange}:{venue}:{symbol}:recon:{drift_event_seq}

    Example:
        >>> make_reconciliation_dedup_key("BINANCE", "FUTURES", "XRPUSDT", 12345)
        'BINANCE:FUTURES:XRPUSDT:recon:12345'
    """
    return f"{exchange}:{venue}:{symbol}:recon:{drift_event_seq}"


def make_transfer_dedup_key(
    exchange: str,
    transfer_id: str,
) -> str:
    """InternalTransferCompleted용 dedup_key 생성

    Args:
        exchange: 거래소
        transfer_id: 내부이체 ID

    Returns:
        dedup_key: {exchange}:transfer:{transfer_id}

    Example:
        >>> make_transfer_dedup_key("BINANCE", "txn_123456")
        'BINANCE:transfer:txn_123456'
    """
    return f"{exchange}:transfer:{transfer_id}"


def make_deposit_dedup_key(
    exchange: str,
    deposit_id: str,
) -> str:
    """DepositDetected용 dedup_key 생성

    Args:
        exchange: 거래소
        deposit_id: 입금 ID 또는 tx_id

    Returns:
        dedup_key: {exchange}:deposit:{deposit_id}

    Example:
        >>> make_deposit_dedup_key("BINANCE", "0xabc123")
        'BINANCE:deposit:0xabc123'
    """
    return f"{exchange}:deposit:{deposit_id}"


def make_withdraw_dedup_key(
    exchange: str,
    withdraw_id: str,
) -> str:
    """WithdrawCompleted용 dedup_key 생성

    Args:
        exchange: 거래소
        withdraw_id: 출금 ID 또는 tx_id

    Returns:
        dedup_key: {exchange}:withdraw:{withdraw_id}

    Example:
        >>> make_withdraw_dedup_key("BINANCE", "wd_987654")
        'BINANCE:withdraw:wd_987654'
    """
    return f"{exchange}:withdraw:{withdraw_id}"


def make_funding_dedup_key(
    exchange: str,
    symbol: str,
    funding_ts: int,
) -> str:
    """FundingApplied용 dedup_key 생성

    Args:
        exchange: 거래소
        symbol: 심볼
        funding_ts: 펀딩 타임스탬프 (밀리초)

    Returns:
        dedup_key: {exchange}:{symbol}:funding:{funding_ts}

    Example:
        >>> make_funding_dedup_key("BINANCE", "XRPUSDT", 1708408800000)
        'BINANCE:XRPUSDT:funding:1708408800000'
    """
    return f"{exchange}:{symbol}:funding:{funding_ts}"


def make_fee_dedup_key(
    exchange: str,
    venue: str,
    symbol: str,
    trade_id: str,
) -> str:
    """FeeCharged용 dedup_key 생성

    Args:
        exchange: 거래소
        venue: 거래 장소
        symbol: 심볼
        trade_id: 관련 체결 ID

    Returns:
        dedup_key: {exchange}:{venue}:{symbol}:fee:{trade_id}

    Example:
        >>> make_fee_dedup_key("BINANCE", "FUTURES", "XRPUSDT", "123456789")
        'BINANCE:FUTURES:XRPUSDT:fee:123456789'
    """
    return f"{exchange}:{venue}:{symbol}:fee:{trade_id}"


def make_engine_event_dedup_key(
    event_type: str,
    ts_ms: int,
) -> str:
    """Engine 이벤트용 dedup_key 생성 (EngineStarted, EngineStopped 등)

    Args:
        event_type: 이벤트 타입
        ts_ms: 타임스탬프 (밀리초)

    Returns:
        dedup_key: engine:{event_type}:{ts_ms}

    Example:
        >>> make_engine_event_dedup_key("started", 1708408800000)
        'engine:started:1708408800000'
    """
    return f"engine:{event_type}:{ts_ms}"


def generate_balance_dedup_key(
    exchange: str,
    venue: str,
    asset: str,
    update_time: int,
) -> str:
    """BalanceChanged용 dedup_key 생성 (시간 기반)

    Args:
        exchange: 거래소
        venue: 거래 장소
        asset: 자산 (예: USDT)
        update_time: 업데이트 시간 (밀리초)

    Returns:
        dedup_key: {exchange}:{venue}:{asset}:balance:{update_time}

    Example:
        >>> generate_balance_dedup_key("BINANCE", "FUTURES", "USDT", 1708408800000)
        'BINANCE:FUTURES:USDT:balance:1708408800000'
    """
    return f"{exchange}:{venue}:{asset}:balance:{update_time}"


# -------------------------------------------------------------------------
# 과거 데이터 복구용 dedup_key 생성 함수
# -------------------------------------------------------------------------


def make_initial_capital_dedup_key(
    mode: str,
    snapshot_date: str,
) -> str:
    """InitialCapitalEstablished용 dedup_key 생성

    Args:
        mode: 운영 모드 (production, testnet)
        snapshot_date: 스냅샷 날짜 (YYYY-MM-DD)

    Returns:
        dedup_key: initial_capital:{mode}:{snapshot_date}

    Example:
        >>> make_initial_capital_dedup_key("production", "2024-01-15")
        'initial_capital:production:2024-01-15'
    """
    return f"initial_capital:{mode}:{snapshot_date}"


def make_income_dedup_key(
    exchange: str,
    income_type: str,
    tran_id: int | str,
) -> str:
    """Income History 이벤트용 dedup_key 생성 (FundingApplied, CommissionRebateReceived 등)

    Args:
        exchange: 거래소 (예: BINANCE)
        income_type: Income 유형 (FUNDING_FEE, COMMISSION_REBATE 등)
        tran_id: 거래소의 트랜잭션 ID

    Returns:
        dedup_key: {exchange}:income:{income_type}:{tran_id}

    Example:
        >>> make_income_dedup_key("BINANCE", "FUNDING_FEE", 9689322393)
        'BINANCE:income:FUNDING_FEE:9689322393'
    """
    return f"{exchange}:income:{income_type}:{tran_id}"


def make_convert_dedup_key(
    exchange: str,
    order_id: int | str,
) -> str:
    """ConvertExecuted용 dedup_key 생성

    Args:
        exchange: 거래소 (예: BINANCE)
        order_id: Convert 주문 ID

    Returns:
        dedup_key: {exchange}:convert:{order_id}

    Example:
        >>> make_convert_dedup_key("BINANCE", 940708407462087195)
        'BINANCE:convert:940708407462087195'
    """
    return f"{exchange}:convert:{order_id}"


def make_dust_dedup_key(
    exchange: str,
    trans_id: int | str,
) -> str:
    """DustConverted용 dedup_key 생성

    Args:
        exchange: 거래소 (예: BINANCE)
        trans_id: Dust 전환 트랜잭션 ID

    Returns:
        dedup_key: {exchange}:dust:{trans_id}

    Example:
        >>> make_dust_dedup_key("BINANCE", 45178372831)
        'BINANCE:dust:45178372831'
    """
    return f"{exchange}:dust:{trans_id}"


def make_commission_rebate_dedup_key(
    exchange: str,
    tran_id: int | str,
) -> str:
    """CommissionRebateReceived용 dedup_key 생성

    Args:
        exchange: 거래소 (예: BINANCE)
        tran_id: 트랜잭션 ID

    Returns:
        dedup_key: {exchange}:rebate:{tran_id}

    Example:
        >>> make_commission_rebate_dedup_key("BINANCE", 9689322394)
        'BINANCE:rebate:9689322394'
    """
    return f"{exchange}:rebate:{tran_id}"


def make_opening_adjustment_dedup_key(
    mode: str,
    venue: str,
    asset: str,
    timestamp_ms: int | None = None,
) -> str:
    """OpeningBalanceAdjusted용 dedup_key 생성

    Args:
        mode: 운영 모드 (production, testnet)
        venue: Venue (FUTURES, SPOT)
        asset: 자산 (예: USDT)
        timestamp_ms: 밀리초 타임스탬프, None이면 현재 시간 사용

    Returns:
        dedup_key: opening_adjustment:{mode}:{venue}:{asset}:{timestamp_ms}

    Example:
        >>> make_opening_adjustment_dedup_key("production", "FUTURES", "USDT", 1708550400000)
        'opening_adjustment:production:FUTURES:USDT:1708550400000'
    """
    from datetime import datetime, timezone
    
    if timestamp_ms is None:
        timestamp_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    
    return f"opening_adjustment:{mode}:{venue}:{asset}:{timestamp_ms}"
