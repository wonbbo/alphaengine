# AlphaEngine v2 개발 단계별 가이드

이 문서는 각 Dev-Phase를 시작할 때 Plan 모드에서 사용할 수 있는 요청 명령을 제공합니다.

각 단계를 시작할 때:
1. 해당 Phase의 **Plan 모드 요청**을 복사
2. Plan 모드에서 실행
3. 생성된 계획 검토 및 승인
4. Agent 모드로 전환하여 구현
5. 테스트 통과 확인
6. 완료 체크리스트 확인 후 다음 Phase로

---

# Dev-Phase 0: 핵심 유틸리티

## 목표
- 순수 Python, 외부 호출 없음
- 100% 단위 테스트 가능
- 타입 힌트 완전

## 구현 대상
| 순서 | 모듈 | 설명 |
|------|------|------|
| 0.1 | `core/constants.py` | 하드코딩 상수 (URL, 기본값, 경로) |
| 0.2 | `core/types.py` | Enum, TypedDict, Dataclass 정의 |
| 0.3 | `core/config/loader.py` | secrets.yaml 로더 |
| 0.4 | `core/config/config_store.py` | DB 설정 로더/저장 (인터페이스) |
| 0.5 | `core/domain/events.py` | Event Envelope, Event Types |
| 0.6 | `core/domain/commands.py` | Command Envelope, Command Types |
| 0.7 | `core/utils/dedup.py` | dedup_key 생성 유틸리티 |
| 0.8 | `core/utils/idempotency.py` | client_order_id 생성 |

## Plan 모드 요청

```
Dev-Phase 0 (핵심 유틸리티)를 시작한다.

다음 문서들을 참고해서 상세 구현 계획을 세워줘:
- @docs/plan/0.AlphaEngine_v2_Immediate_Action_Roadmap.md
- @docs/plan/11.AlphaEngine_v2_Implementation_Guide_KR.md
- @docs/plan/3.AlphaEngine_v2_TRD_EventModel_KR.md
- @docs/plan/4.AlphaEngine_v2_TRD_CommandModel_KR.md
- @.cursor/rules/alphaengine.mdc
- @.cursor/rules/python-general.mdc

조건:
- 외부 네트워크 호출 없음
- pytest 100% 통과 가능
- 타입 힌트 완전
- pathlib 사용 (크로스 플랫폼)
- Decimal 사용 (금융 계산)

다음을 포함해서 계획해줘:
1. 구현할 파일 목록 (의존성 순서대로)
2. 각 파일의 핵심 클래스/함수/상수
3. 대응하는 테스트 파일
4. 각 파일별 완료 기준
```

## 완료 체크리스트
- [ ] 모든 core 모듈 pytest 100% 통과
- [ ] 외부 네트워크 호출 없음
- [ ] 타입 힌트 완전
- [ ] pathlib으로 경로 처리
- [ ] Decimal으로 금융 값 처리

---

# Dev-Phase 1: 외부 서비스 어댑터

## 목표
- Protocol/ABC 정의
- 실제 구현 + Mock 구현
- Mock으로 교체 가능 확인

## 구현 대상
| 순서 | 모듈 | 설명 |
|------|------|------|
| 1.1 | `adapters/interfaces.py` | Protocol 정의 |
| 1.2 | `adapters/binance/rest_client.py` | Binance REST 구현 |
| 1.3 | `adapters/binance/ws_client.py` | Binance WebSocket 구현 |
| 1.4 | `adapters/binance/models.py` | Binance DTO 변환 |
| 1.5 | `adapters/mock/exchange_client.py` | Mock 거래소 클라이언트 |
| 1.6 | `adapters/db/sqlite_adapter.py` | SQLite 연결/WAL 설정 |

## Plan 모드 요청

```
Dev-Phase 1 (외부 서비스 어댑터)를 시작한다.

다음 문서들을 참고해서 상세 구현 계획을 세워줘:
- @docs/plan/0.AlphaEngine_v2_Immediate_Action_Roadmap.md
- @docs/plan/11.AlphaEngine_v2_Implementation_Guide_KR.md
- @docs/plan/8.AlphaEngine_v2_TRD_WebSocket_KR.md
- @docs/plan/7.AlphaEngine_v2_TRD_DB_Schema_KR.md
- @.cursor/rules/alphaengine.mdc
- @.cursor/rules/python-general.mdc

조건:
- Protocol(인터페이스) 먼저 정의
- 실제 구현과 Mock 구현 모두 작성
- Mock으로 교체 가능해야 함
- 단위 테스트는 Mock 사용

다음을 포함해서 계획해줘:
1. Protocol 인터페이스 목록과 메서드
2. 실제 구현 파일과 의존성
3. Mock 구현 파일
4. 테스트 파일과 테스트 케이스
5. 각 어댑터별 완료 기준
```

## 완료 체크리스트
- [ ] 모든 어댑터 Protocol 준수
- [ ] Mock 어댑터로 교체 가능
- [ ] 단위 테스트 통과
- [ ] Binance API 응답 파싱 정상

---

# Dev-Phase 2: Testnet E2E 시나리오 검증

## 목표
- 실제 Binance Testnet에서 핵심 시나리오 동작 확인
- 각 시나리오별 로그/결과 문서화

## 검증 시나리오
| 분류 | 시나리오 |
|------|----------|
| 연결 | REST 연결, WebSocket 연결, WebSocket 재연결 |
| 자금 | 잔고 조회, 입금 감지 |
| 매매 | 시장가 매수/매도, 지정가 주문, 주문 취소, 부분 체결 |
| 리스크 | 손절, 익절, 레버리지 변경 |
| 장애 | API 타임아웃, Rate Limit, WebSocket 끊김 |

## Plan 모드 요청

```
Dev-Phase 2 (Testnet E2E 시나리오 검증)를 시작한다.

다음 문서들을 참고해서 E2E 테스트 계획을 세워줘:
- @docs/plan/0.AlphaEngine_v2_Immediate_Action_Roadmap.md
- @docs/plan/11.AlphaEngine_v2_Implementation_Guide_KR.md
- @docs/plan/8.AlphaEngine_v2_TRD_WebSocket_KR.md
- @.cursor/rules/testing.mdc

조건:
- Binance Testnet 사용 (secrets.yaml의 testnet 설정)
- 각 시나리오별 독립 실행 가능
- 결과 로그 저장

다음을 포함해서 계획해줘:
1. 시나리오별 테스트 파일 구조
2. 각 시나리오의 실행 순서와 검증 항목
3. 예상 이벤트 흐름
4. 장애 시나리오 복구 방법
5. 결과 기록 방법
```

```bash
# pytest-asyncio 설치 필요
pip install pytest-asyncio

# 전체 E2E 테스트 실행
pytest tests/e2e -v -m e2e

# 특정 시나리오만 실행
pytest tests/e2e/scenarios/test_01_connection.py -v

# 느린 테스트 제외
pytest tests/e2e -v -m "e2e and not slow"

# 결과 로그 저장
pytest tests/e2e -v --e2e-log-dir=tests/e2e/results
```

## 완료 체크리스트
- [ ] Testnet에서 모든 시나리오 성공
- [ ] 시나리오별 로그/결과 문서화
- [ ] 장애 시나리오 복구 확인
- [ ] WebSocket 끊김 시 REST로 복구 확인

---

# Dev-Phase 3: Thin Slice (최소 동작 흐름)

## 목표
- 전체 흐름을 관통하는 최소 기능 동작 확인
- DB 스키마 생성 및 기본 CRUD

## 동작 흐름
```
secrets.yaml 로드
    ↓
Binance REST 연결
    ↓
잔고 조회
    ↓
SQLite DB 저장 (event_store)
    ↓
콘솔/로그 출력
```

## 구현 대상
| 순서 | 작업 | 설명 |
|------|------|------|
| 3.1 | DB 스키마 생성 | event_store, command_store, config_store |
| 3.2 | EventStore 구현 | append, get_by_id, get_after |
| 3.3 | Thin Slice 스크립트 | 위 흐름 동작 확인 |

## Plan 모드 요청

```
Dev-Phase 3 (Thin Slice)를 시작한다.

다음 문서들을 참고해서 Thin Slice 구현 계획을 세워줘:
- @docs/plan/0.AlphaEngine_v2_Immediate_Action_Roadmap.md
- @docs/plan/11.AlphaEngine_v2_Implementation_Guide_KR.md
- @docs/plan/7.AlphaEngine_v2_TRD_DB_Schema_KR.md
- @.cursor/rules/alphaengine.mdc

목표:
- 설정 로드 → REST 연결 → 잔고 조회 → DB 저장 → 조회
- 단일 스크립트로 전체 흐름 확인

다음을 포함해서 계획해줘:
1. DB 스키마 DDL (SQLite)
2. EventStore 클래스 구현
3. Thin Slice 스크립트 구조
4. 실행 및 검증 방법
```

## 완료 체크리스트
- [ ] Thin Slice 동작 확인
- [ ] DB CRUD 정상
- [ ] 이벤트 저장/조회 성공

---

# Dev-Phase 4: Bot/Web 스켈레톤

## 목표
- Bot/Web 기본 구조 구축
- 메인 루프, 라우트 정의
- 시작/종료 정상 동작

## 구현 대상
| 순서 | 모듈 | 설명 |
|------|------|------|
| 4.1 | `bot/__main__.py` | Bot 진입점 |
| 4.2 | `bot/bootstrap.py` | 설정 로드, 의존성 주입, 메인 루프 |
| 4.3 | `web/__main__.py` | Web 진입점 |
| 4.4 | `web/app.py` | FastAPI 앱, 라우트 등록 |
| 4.5 | `web/routes/` | API 라우트 스켈레톤 |

## Plan 모드 요청

```
Dev-Phase 4 (Bot/Web 스켈레톤)를 시작한다.

다음 문서들을 참고해서 스켈레톤 구현 계획을 세워줘:
- @docs/plan/0.AlphaEngine_v2_Immediate_Action_Roadmap.md
- @docs/plan/11.AlphaEngine_v2_Implementation_Guide_KR.md
- @docs/plan/9.AlphaEngine_v2_TRD_BotWeb_Architecture_KR.md
- @.cursor/rules/alphaengine.mdc
- @.cursor/rules/fastapi.mdc

목표:
- Bot: python -m bot 으로 시작 → 정상 종료
- Web: python -m web 으로 시작 → /health 응답 → 정상 종료

다음을 포함해서 계획해줘:
1. Bot 모듈 구조와 진입점
2. Bot 메인 루프 구조 (asyncio)
3. Web 모듈 구조와 라우트
4. 의존성 주입 방식
5. 시작/종료 테스트 방법
```

## 완료 체크리스트
- [ ] Bot 시작/종료 정상
- [ ] Web 시작/종료 정상
- [ ] 설정 로드 정상
- [ ] /health 엔드포인트 응답

---

# Dev-Phase 5: 코어 로직 순차 개발

## 목표
- 전체 이벤트 흐름 동작
- 전략 교체 가능
- 리스크 가드 동작

## 구현 대상
| 순서 | 모듈 | 설명 | 의존성 |
|------|------|------|--------|
| 5.1 | `bot/websocket/listener.py` | WebSocket 이벤트 수신 | Phase 1 어댑터 |
| 5.2 | `bot/reconciler/reconciler.py` | REST 정합 검사 | Phase 1 어댑터 |
| 5.3 | `bot/executor/executor.py` | Command 실행 | Phase 1 어댑터 |
| 5.4 | `bot/projector/projector.py` | Projection 업데이트 | EventStore |
| 5.5 | `core/domain/state_machines.py` | 상태 머신 | Phase 0 타입 |
| 5.6 | `bot/risk/guard.py` | 리스크 가드 | Projection |
| 5.7 | `strategies/base.py` | 전략 인터페이스 | - |
| 5.8 | `strategies/examples/sma_cross.py` | 예제 전략 | 전략 인터페이스 |

## Plan 모드 요청

```
Dev-Phase 5 (코어 로직)를 시작한다.

다음 문서들을 참고해서 코어 로직 구현 계획을 세워줘:
- @docs/plan/0.AlphaEngine_v2_Immediate_Action_Roadmap.md
- @docs/plan/11.AlphaEngine_v2_Implementation_Guide_KR.md
- @docs/plan/5.AlphaEngine_v2_TRD_StateMachines_KR.md
- @docs/plan/10.AlphaEngine_v2_TRD_Strategy_Interface_KR.md
- @docs/plan/8.AlphaEngine_v2_TRD_WebSocket_KR.md
- @.cursor/rules/alphaengine.mdc

목표:
- WebSocket 이벤트 → Event 저장 → Projection 업데이트
- Command 발행 → 실행 → 결과 이벤트
- 전략 인터페이스 정의 및 예제 전략

다음을 포함해서 계획해줘:
1. 각 모듈의 역할과 의존성
2. 이벤트 흐름 (WebSocket → EventStore → Projection)
3. Command 흐름 (Strategy → Executor → Exchange)
4. 상태 머신 정의 (Order, Position, Engine)
5. 전략 인터페이스와 예제 구현
6. 리스크 가드 체크 포인트
```

## 완료 체크리스트
- [ ] 전체 이벤트 흐름 동작
- [ ] Command 실행 → 결과 이벤트 저장
- [ ] 전략 교체 가능
- [ ] 리스크 가드 동작
- [ ] Projection 업데이트 정상

---

# Dev-Phase 6: 통합 및 운영 준비

## 목표
- 전체 시스템 E2E 테스트
- 24시간 무중단 운영 확인
- Production 전환 준비

## 작업 목록
| 순서 | 작업 | 설명 |
|------|------|------|
| 6.1 | 통합 테스트 | 전체 흐름 E2E 테스트 |
| 6.2 | Web UI | 대시보드, 설정 화면 |
| 6.3 | 배포 설정 | systemd, nginx |
| 6.4 | 모니터링 | 로깅, 알림 |
| 6.5 | Production 전환 | Testnet → Production |

## Plan 모드 요청

```
Dev-Phase 6 (통합 및 운영 준비)를 시작한다.

다음 문서들을 참고해서 통합 및 운영 계획을 세워줘:
- @docs/plan/0.AlphaEngine_v2_Immediate_Action_Roadmap.md
- @docs/plan/11.AlphaEngine_v2_Implementation_Guide_KR.md
- @docs/plan/9.AlphaEngine_v2_TRD_BotWeb_Architecture_KR.md
- @docs/plan/6.AlphaEngine_v2_ADR_KR.md
- @docs/deploy/README.md
- @.cursor/rules/alphaengine.mdc

목표:
- Testnet에서 24시간 무중단 운영
- Production 전환 준비 완료
- 배포/운영 문서 완성

다음을 포함해서 계획해줘:
1. 통합 테스트 시나리오
2. Web UI 필수 화면 목록
3. systemd 서비스 설정
4. 모니터링/알림 설정
5. Production 전환 체크리스트
6. docs/deploy/ 문서 작성 목록
```

## 완료 체크리스트
- [ ] Testnet 24시간 무중단 운영
- [ ] 통합 테스트 전체 통과
- [ ] Web UI 기본 기능 동작
- [ ] systemd 서비스 설정 완료
- [ ] 모니터링/알림 설정 완료
- [ ] docs/deploy/ 문서 완성
- [ ] Production 전환 준비 완료

---

# 사용 방법

## 1. Phase 시작

해당 Phase의 **Plan 모드 요청** 블록을 복사하여 Plan 모드에서 실행합니다.

```
[Cursor에서]
1. Cmd+L (또는 Ctrl+L)로 채팅 열기
2. Plan 모드 선택 (또는 /plan 입력)
3. 위 요청 붙여넣기
4. 실행
```

## 2. 계획 검토

Plan 모드가 생성한 계획을 검토합니다:
- 파일 목록이 적절한가?
- 의존성 순서가 맞는가?
- 테스트 커버리지가 충분한가?

필요시 수정 요청합니다.

## 3. Agent 모드로 구현

계획 승인 후 Agent 모드로 전환하여 구현합니다:

```
"계획대로 첫 번째 작업인 [파일명]을 구현해줘.
테스트 파일도 함께 작성해."
```

## 4. 테스트 확인

```
"pytest tests/unit/[모듈]/ 실행해서 통과하는지 확인해줘."
```

## 5. 반복

모든 작업 완료 → 완료 체크리스트 확인 → 다음 Phase로

---

# 관련 문서

- [Immediate Action Roadmap](plan/0.AlphaEngine_v2_Immediate_Action_Roadmap.md) - 전체 로드맵
- [Implementation Guide](plan/11.AlphaEngine_v2_Implementation_Guide_KR.md) - 구현 상세 가이드
- [Constitution](plan/1.AlphaEngine_v2_Constitution_KR.md) - 핵심 원칙
- [PRD](plan/2.AlphaEngine_v2_PRD_KR.md) - 제품 요구사항
