# AlphaEngine 배포 가이드

이 디렉토리는 AlphaEngine의 배포 및 운영에 필요한 문서를 포함합니다.

## 운영 환경

| 환경 | OS | 용도 |
|------|-----|------|
| 개발 | Windows | 코드 작성, 로컬 테스트 |
| 운영 | Linux (Ubuntu 22.04+) | 24/7 Bot + Web 실행 |

## 문서 목록

| 문서 | 상태 | 설명 |
|------|------|------|
| [setup.md](setup.md) | 미작성 | 서버 초기 설정 (의존성, 사용자, 디렉토리) |
| [systemd.md](systemd.md) | 미작성 | systemd 서비스 설정 (Bot, Web) |
| [nginx.md](nginx.md) | 미작성 | nginx 리버스 프록시 설정 |
| [backup.md](backup.md) | 미작성 | DB 백업/복구 절차 |
| [monitoring.md](monitoring.md) | 미작성 | 로그, 모니터링, 알림 설정 |
| [troubleshooting.md](troubleshooting.md) | 미작성 | 운영 중 문제 해결 가이드 |

## 퀵 스타트 (요약)

```bash
# 1. 서버 접속
ssh user@your-server

# 2. 프로젝트 클론
git clone <repo-url> /opt/alphaengine
cd /opt/alphaengine

# 3. 가상환경 생성 및 의존성 설치
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 4. 설정 파일 작성
cp config/secrets.yaml.example config/secrets.yaml
# secrets.yaml 편집 (API Key 등)

# 5. systemd 서비스 등록
sudo cp deploy/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable alphaengine-bot alphaengine-web

# 6. 서비스 시작
sudo systemctl start alphaengine-bot alphaengine-web
```

자세한 내용은 각 문서를 참고하세요.

## 문서 작성 원칙

1. **즉시 문서화**: 배포/운영 관련 결정 시 바로 문서에 반영
2. **복사-붙여넣기**: 모든 명령어는 그대로 복사해서 실행 가능하게 작성
3. **전체 설정**: 설정 파일은 부분이 아닌 전체 내용 포함
4. **문제 기록**: 운영 중 발생한 문제와 해결책은 즉시 `troubleshooting.md`에 추가

## 관련 문서

- [ADR-006: 운영 환경](../plan/6.AlphaEngine_v2_ADR_KR.md#adr-006-운영-환경-windows-개발--linux-운영) - 크로스 플랫폼 결정 사항
- [Bot/Web Architecture TRD](../plan/9.AlphaEngine_v2_TRD_BotWeb_Architecture_KR.md) - 아키텍처 상세
