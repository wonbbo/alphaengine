# 입금 플로우 이슈 분석 및 개선 제안 (2026-02)

다음 세션에서 입금 관련 버그 수정·개선 시 참고할 수 있도록 정리한 문서입니다.

---

## 1. 증상 요약

| 항목 | 내용 |
|------|------|
| **사건** | 99,000원 입금 요청 |
| **표시된 결과** | 7.4 USDT만 기록됨 (약 26 TRX 매도분에 해당) |
| **실제 기대** | 약 215 TRX 전송 → 60 USDT대 수령 |
| **타이밍** | 실제 전송이 완료되기 전에 입출금이 완료된 것으로 처리됨 |
| **로그** | Step 2 "Upbit 출금 요청" 직후 로그가 나오지 않음 (시스템 문제 가능, 재시도 예정) |

- Step 1: TRX 240.87 매수 정상
- Step 2: Upbit 출금 요청 215.888321 TRX 직후 로그 없음 → Step 3~6 동작은 로그로 확인 불가

---

## 2. 원인 분석

### 2.1 결론

- **Step 4**에서 Binance Spot TRX를 매도할 때 **215 TRX가 아니라 약 26 TRX만** 있어서 7.4 USDT만 기록된 상황으로 추정.
- 원인: **Step 2를 조기 완료/타임아웃 복구 등으로 끝낸 경우 `deposit:step2_trx`를 저장하지 않음** → Step 3에서 **예상 금액 범위 없이** 입금 대기 → **과거 소액 입금(예: 26 TRX)**이 “이번 입금”으로 잘못 매칭 → 215 TRX 도착 전에 Step 4로 진행 → 26 TRX만 매도되어 7.4 USDT로 완료 처리.

### 2.2 Step 2에서 `deposit:step2_trx` 저장 위치

- **저장하는 경로**: Upbit 출금 완료 후 정상 반환 시에만 `deposit:step2_trx:{transfer_id}`에 `withdraw_amount` 저장.
- **저장하지 않는 경로** (문제):
  - **조기 완료**: Binance TRX 도착 확인 후 Upbit done 전에 return (366~376라인) → 저장 없음.
  - **타임아웃 복구**: 출금 타임아웃이지만 Binance에 TRX 도착했다고 판단해 Step 4로 복구 (384~396라인) → 저장 없음.
  - **복구**: Binance에 TRX 이미 있어 전송 스킵 (228~238라인) → 저장 로직 없음.

### 2.3 Step 3 동작

- `deposit_handler.py` Step 3에서 `config_store.get("deposit:step2_trx:{transfer_id}")`로 예상 TRX 금액을 읽음.
- **값이 없거나 예외**면 `expected_min`/`expected_max`가 `None` → Binance `wait_deposit_confirmed`에 범위 미전달.
- `wait_deposit_confirmed`는 `expected_amount_min/max`가 없으면 **min_amount(1.0) 이상인 첫 입금**을 그대로 “이번 입금”으로 반환.
- 따라서 **과거 26 TRX 입금**이 먼저 반환되면, 215 TRX 도착 전에 Step 3 완료 → Step 4에서 그 시점 Spot TRX(26 TRX)만 매도 → 7.4 USDT 기록.

### 2.4 복구 경로 보조 확인

- “Binance에 TRX 이미 있음” 복구 조건: `binance_trx_free >= amount_to_send` (215.88) 필요.
- 26 TRX만 있을 때는 복구되면 안 되므로, 타입/단위 혼동이 없다면 7.4 USDT 원인 1순위는 “step2_trx 미저장 → Step 3 잘못 매칭”으로 보는 것이 타당.

---

## 3. 수정·개선 제안

### 3.1 Step 2 모든 완료 경로에서 `deposit:step2_trx` 저장 (필수)

- **조기 완료** (Binance TRX 도착 확인 후 return): return 직전에 이번 전송분 예상량(`withdraw_amount`)을 `deposit:step2_trx:{transfer_id}`에 저장.
- **타임아웃 복구** (출금 타임아웃 but Binance TRX 도착으로 Step 4 복구): Step 4로 넘기기 직전에 동일하게 이번 전송 예상량 저장.
- **복구** (전송 스킵): 선택적으로 `amount_to_send`를 저장해 두면, 이후 Step 3 로직 변경 시나 로그/감사에 유리.

이렇게 하면 Step 3가 항상 `expected_amount_min/max`를 사용해 **다른 금액이 이번 건으로 매칭되는 일을 방지**할 수 있음.

### 3.2 Step 2 로그 보강

- 조기 완료 / 타임아웃 복구 / 복구 시 다음 값을 로그에 남기면 재발 시 원인 추적이 쉬움:
  - `baseline_trx`, `withdraw_amount`, `current_trx`, `min_expected_trx`
  - 복구 시: `binance_trx_free`, `amount_to_send`

### 3.3 Step 4 안전장치 (선택)

- 요청 KRW(`requested_amount`)가 있을 때, “현재 Spot TRX로 환산한 예상 USDT”가 “요청 KRW를 적당한 환율로 환산한 USDT”의 50% 미만이면:
  - 경고 로그 후 추가 대기 또는 실패 처리 등으로 **소액만 매도되어 완료되는 상황**을 방지할 수 있음.

### 3.4 복구 조건 재확인

- `should_skip_send` 판단 시 사용하는 `binance_trx_free`와 `amount_to_send`가 “이번에 보낼 TRX량”과 “현재 Binance TRX 잔고”와 정확히 대응하는지, 단위/필드 혼동이 없는지 한 번 더 점검 권장.

---

## 4. 관련 코드 위치

| 구분 | 파일 | 참고 위치 |
|------|------|-----------|
| Step 2 복구 조건 | `bot/transfer/deposit_handler.py` | 204~238라인 (복구), 334~338라인 (baseline/min_expected) |
| Step 2 조기 완료 | `bot/transfer/deposit_handler.py` | 366~376라인 |
| Step 2 타임아웃 복구 | `bot/transfer/deposit_handler.py` | 384~396라인 |
| Step 2 step2_trx 저장 | `bot/transfer/deposit_handler.py` | 412~425라인 (정상 경로만) |
| Step 3 예상 금액 조회 | `bot/transfer/deposit_handler.py` | 454~469라인, 471~479라인 |
| 입금 범위 매칭 | `adapters/binance/rest_client.py` | `wait_deposit_confirmed` (1130~1194라인) |
| Step 4 TRX 매도·actual 기록 | `bot/transfer/deposit_handler.py` | 498~530라인, `_parse_usdt_from_sell_order` 566~577라인 |

---

## 5. 참고

- 로그가 “끊긴” 것이 아니라 **해당 시점에 로그가 나오지 않은 것**으로 보며, 시스템 이슈 가능성이 있어 재시도 예정.
- 위 수정 적용 후 동일 증상 재발 시, Step 2 보강 로그로 **조기 완료/타임아웃 복구/복구** 중 어느 경로로 완료됐는지 확인하면 원인 특정에 도움이 됨.
