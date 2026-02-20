# AlphaEngine v2 설계 문서

본 폴더는 AlphaEngine v2의 설계 문서를 포함합니다.

------------------------------------------------------------------------

## 문서 목록

| 번호 | 문서 | 설명 |
|------|------|------|
| 0 | [Immediate Action Roadmap](0.AlphaEngine_v2_Immediate_Action_Roadmap.md) | 즉각적인 실행 단계 (Phase 0~3) |
| 1 | [Constitution](1.AlphaEngine_v2_Constitution_KR.md) | 핵심 정의 및 절대 변경 불가 원칙 |
| 2 | [PRD](2.AlphaEngine_v2_PRD_KR.md) | 제품 요구사항 정의서 |
| 3 | [TRD - Event Model](3.AlphaEngine_v2_TRD_EventModel_KR.md) | 이벤트 모델 기술 사양 |
| 4 | [TRD - Command Model](4.AlphaEngine_v2_TRD_CommandModel_KR.md) | 명령 모델 기술 사양 |
| 5 | [TRD - State Machines](5.AlphaEngine_v2_TRD_StateMachines_KR.md) | 상태머신 정의 |
| 6 | [ADR](6.AlphaEngine_v2_ADR_KR.md) | 아키텍처 결정 기록 |
| 7 | [TRD - DB Schema](7.AlphaEngine_v2_TRD_DB_Schema_KR.md) | PostgreSQL 스키마 |
| 8 | [TRD - WebSocket](8.AlphaEngine_v2_TRD_WebSocket_KR.md) | WebSocket 연동 사양 |
| 9 | [TRD - Bot/Web Architecture](9.AlphaEngine_v2_TRD_BotWeb_Architecture_KR.md) | Bot/Web 분리 아키텍처 |
| 10 | [TRD - Strategy Interface](10.AlphaEngine_v2_TRD_Strategy_Interface_KR.md) | 전략 인터페이스 |
| 11 | [Implementation Guide](11.AlphaEngine_v2_Implementation_Guide_KR.md) | 구현 가이드 |

------------------------------------------------------------------------

## v1 대비 주요 변경사항

| 항목 | v1 | v2 |
|------|-----|-----|
| 데이터 수신 | REST Polling only | **Hybrid (WebSocket + REST)** |
| 실시간성 | 1~30초 지연 | **50~100ms 지연** |
| 운영 환경 | Windows 개발용 | **Windows 개발 + Linux 운영** |
| 거래 모드 | 실거래만 | **실거래 + Testnet** |
| 아키텍처 | Bot only | **Bot + Web 모니터링** |
| DB | SQLite | **PostgreSQL** |
| DB 접근 | Bot만 Write | **Bot + Web 모두 Write** |
| Rate Limit | 고려 부족 | **헤더 추적 + 백오프** |

------------------------------------------------------------------------

## 핵심 설계 원칙

1. **모든 상태 변경은 Event로 기록**
2. **전략은 거래소 API를 직접 호출하지 않음**
3. **UI/Web은 Command를 통해서만 상태 변경**
4. **모든 Command는 idempotent**
5. **Exchange가 최종 진실, Reconciler 필수**
6. **Projection은 파생물 (Event Store가 진실)**
7. **WebSocket은 힌트, REST가 최종 정합 보장**
8. **Bot/Web은 PostgreSQL 트랜잭션으로 동시 접근 안전**

------------------------------------------------------------------------

## 아키텍처 개요

```
┌─────────────────────────────────────────────────────────────────┐
│                    Hybrid Architecture                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Binance Exchange                                                │
│  ┌──────────────┐    ┌──────────────┐                          │
│  │  WebSocket   │    │    REST      │                          │
│  │   Stream     │    │    API       │                          │
│  └──────┬───────┘    └──────┬───────┘                          │
│         │ 실시간            │ 정합                              │
│         │ 50~100ms          │ 30초                              │
│         ↓                   ↓                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    Bot Process                            │  │
│  │                                                           │  │
│  │  WebSocket ──→ Event Merger ←── Reconciler (REST)       │  │
│  │                     │                                     │  │
│  │                     ↓                                     │  │
│  │               Event Store                                 │  │
│  │                     │                                     │  │
│  │                     ↓                                     │  │
│  │    Projector ──→ Strategy ──→ Executor                   │  │
│  │                                                           │  │
│  └──────────────────────────┬────────────────────────────────┘  │
│                              │                                   │
│                              │ PostgreSQL                        │
│                              ↓                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    Web Process                            │  │
│  │                                                           │  │
│  │  Dashboard (Read) │ Config (Write) │ Commands (Write)    │  │
│  │                                                           │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

------------------------------------------------------------------------

## 읽기 순서 권장

1. **빠른 이해**: 0 (Roadmap) → 1 (Constitution) → 2 (PRD)
2. **상세 설계**: 3 (Event) → 4 (Command) → 5 (State Machines)
3. **기술 결정**: 6 (ADR) → 7 (DB Schema)
4. **구현 상세**: 8 (WebSocket) → 9 (Bot/Web) → 10 (Strategy)
5. **실제 구현**: 11 (Implementation Guide)

------------------------------------------------------------------------

## 구현 시작

AI에게 이 문서들을 전달하고 구현을 요청할 때:

```
docs/plan2 폴더의 설계 문서를 참고하여 AlphaEngine v2를 구현해주세요.

주요 요구사항:
1. Hybrid 방식 (WebSocket + REST Polling)
2. Bot/Web 분리 아키텍처
3. PostgreSQL 사용
4. 실거래/Testnet 듀얼 모드
5. Windows 개발, Linux 운영

11.AlphaEngine_v2_Implementation_Guide_KR.md의 구현 순서를 따라주세요.
```

------------------------------------------------------------------------

문서 종료
