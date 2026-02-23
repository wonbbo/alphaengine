# 전략 on_tick 실행 흐름 및 컨텍스트

이 문서는 AlphaEngine v2에서 전략의 `on_tick` 함수까지 도달하는 과정과 `ctx`(StrategyTickContext) 변수에 담긴 내용을 정리합니다.

## 목차

1. [on_tick 도달 과정](#1-on_tick-도달-과정)
2. [ctx 변수 내용](#2-ctx-변수-내용)
3. [문서 vs 구현 검토](#3-문서-vs-구현-검토)

---

## 1. on_tick 도달 과정

### 1.1 진입점

```
python -m bot  →  bot/__main__.py  →  main()  →  BotEngine
```

### 1.2 초기화 및 전략 로드

| 단계 | 컴포넌트 | 동작 |
|------|----------|------|
| 1 | `BotEngine.initialize()` | EventStore, CommandStore, ConfigStore, Projector, RiskGuard, StrategyRunner, MarketDataProvider 등 생성 |
| 2 | `BotEngine.start()` | WebSocket 연결, Reconciler 초기 동기화, Projection 적용 후 `_load_and_start_strategy()` 호출 |
| 3 | `_load_and_start_strategy()` | config_store에서 전략 설정 로드 → `load_strategy()` → `start()` (auto_start 시) |
| 4 | `StrategyRunner.load_strategy()` | importlib로 전략 모듈 로드, 인스턴스 생성, `on_init(params)` 호출 |
| 5 | `StrategyRunner.start()` | DB에서 전략 상태 복원, `_build_context()`로 ctx 생성, `on_start(ctx)` 호출 |

### 1.3 메인 루프에서 on_tick 호출

메인 루프(`run_main_loop`)에서 **5초마다** 다음이 실행됩니다:

```
1. Projector: 새 이벤트 처리 → Projection 업데이트
2. Command Processor: 대기 중인 Command 처리
3. Reconciler: 거래소 상태 동기화
4. Strategy Runner: strategy_runner.tick()  ← on_tick 호출
5. BnbFeeManager: BNB 비율 체크
6. Poller: REST API 폴링
```

**`strategy_tick_interval = 5.0`** (초) → 5초마다 `on_tick` 호출

### 1.4 tick() 내부 흐름

```
StrategyRunner.tick()
  ├─ ctx = await _build_context()
  └─ await strategy.on_tick(ctx, emit)
```

### 1.5 전체 흐름 다이어그램

```
BotEngine.run_main_loop()
  └─ (5초마다) strategy_runner.tick()
       ├─ ctx = await _build_context()
       │    └─ ContextBuilder.build(projector, market_data_provider, ...)
       └─ strategy.on_tick(ctx, emit)
```

---

## 2. ctx 변수 내용

`StrategyTickContext`는 `ContextBuilder.build()`에서 구성됩니다.

### 2.1 직접 속성

| 속성 | 출처 | 설명 |
|------|------|------|
| `scope` | StrategyRunner.scope | 거래 범위 (exchange, venue, account_id, symbol, mode) |
| `now` | `datetime.now(timezone.utc)` | 현재 시각 (UTC) |
| `position` | `projector.get_position()` | 현재 포지션 (없으면 None) |
| `balances` | `projector.get_balance()` | USDT 잔고 딕셔너리 |
| `open_orders` | `projector.get_open_orders()` | 미체결 주문 목록 |
| `ohlcv` | `market_data_provider.get_ohlcv(symbol, "5m", 100)` | 5분봉 OHLCV DataFrame |
| `bars` | `market_data_provider.get_bars(symbol, "5m", 100)` | 5분봉 Bar 리스트 (레거시) |
| `current_price` | `ohlcv["close"].iloc[-1]` 또는 `bars[-1].close` | 최신 종가 |
| `strategy_state` | `StrategyRunner._strategy_state` | 틱 간 유지되는 전략 상태 |
| `engine_mode` | `state_machine.state` | RUNNING, PAUSED, SAFE |
| `market_data` | MarketDataProvider | Multi-Timeframe 조회용 |
| `risk_config` | `config_store.get_risk_config()` | 리스크 설정 딕셔너리 |

### 2.2 OHLCV DataFrame 구조

- **Index**: `DatetimeIndex` (UTC, timezone-aware), name=`"time"`
- **Columns**: `open`, `high`, `low`, `close`, `volume` (float64)
- **출처**: `MarketDataProvider.get_ohlcv()` → Binance REST API `get_klines` → 변환
- **캐시**: 60초 TTL

### 2.3 파생 속성 (property)

| 속성 | 설명 |
|------|------|
| `ctx.symbol` | scope.symbol |
| `ctx.usdt_balance` | balances.get("USDT") |
| `ctx.has_position` | 포지션 보유 여부 |
| `ctx.has_open_orders` | 오픈 주문 존재 여부 |
| `ctx.can_trade` | engine_mode == "RUNNING" |
| `ctx.close_only` | engine_mode == "SAFE" |
| `ctx.risk_per_trade` | risk_config["risk_per_trade"] (기본 "0.02") |
| `ctx.reward_ratio` | risk_config["reward_ratio"] (기본 "1.5") |
| `ctx.partial_tp_ratio` | risk_config["partial_tp_ratio"] (기본 "0.5") |
| `ctx.equity_reset_trades` | risk_config["equity_reset_trades"] (기본 50) |

### 2.4 Multi-Timeframe 조회

```python
# ctx.get_ohlcv() - DataFrame 반환 (권장)
ohlcv_15m = await ctx.get_ohlcv("15m", limit=50)
ohlcv_1h = await ctx.get_ohlcv("1h", limit=24)

# ctx.get_bars() - Bar 리스트 (레거시)
bars_15m = await ctx.get_bars("15m", limit=50)
```

---

## 3. 문서 vs 구현 검토

`docs/strategy/README.md`와 실제 구현을 비교한 결과입니다.

### 3.1 일치하는 부분

- 전략 구조, Strategy 상속, on_tick 시그니처
- OHLCV DataFrame 구조 (Index name='time', columns)
- Indicator 사용법, ctx.ohlcv, ctx.can_trade 등
- StrategyTickContext 주요 속성
- ctx.get_ohlcv(), ctx.get_bars() Multi-Timeframe 조회
- emit.place_order(), emit.close_position() 등 Command 발행
- TradeEvent, OrderEvent 구조
- on_trade, on_order_update 콜백 설명

### 3.2 차이점 (문서 보완 권장)

| 항목 | README.md | 실제 구현 |
|------|-----------|-----------|
| **전략 설정 저장** | secrets.yaml의 strategy 섹션 | config_store (DB)의 "strategy" 키 |
| **on_tick 호출 주기** | "5분 간격" | 5초마다 (strategy_tick_interval=5.0) |
| **place_order 파라미터** | stop_price, reduce_only 등 | position_side 파라미터 추가 존재 |

### 3.3 전략 설정 상세

실제 전략 설정은 **config_store** (DB `config_store` 테이블)에서 관리됩니다.

```json
{
  "name": "SMA Cross",
  "module": "strategies.examples.sma_cross",
  "class": "SmaCrossStrategy",
  "params": {"fast_period": 5, "slow_period": 20},
  "auto_start": true
}
```

- `config_store.get("strategy")`로 로드
- Web UI 또는 API를 통해 수정 가능
- secrets.yaml이 아닌 런타임 설정 저장소 사용

### 3.4 on_tick 호출 주기 상세

- **실제**: 5초마다 `strategy_runner.tick()` 호출
- **OHLCV 갱신**: MarketDataProvider 캐시 TTL 60초
- **의미**: 5분봉 기준 전략이지만, 틱은 5초마다 실행되어 새 캔들/데이터 반영 시점을 더 자주 확인

---

## 참고 파일

| 파일 | 역할 |
|------|------|
| `bot/__main__.py` | Bot 진입점 |
| `bot/bootstrap.py` | BotEngine, 메인 루프, 전략 로드 |
| `bot/strategy/runner.py` | StrategyRunner, tick(), _build_context() |
| `bot/strategy/context.py` | ContextBuilder |
| `bot/market_data/provider.py` | OHLCV DataFrame 제공 |
| `strategies/base.py` | StrategyTickContext, Strategy 추상 클래스 |
| `core/storage/config_store.py` | 전략/리스크 설정 저장 |
