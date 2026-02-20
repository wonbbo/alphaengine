# AlphaEngine 백업 및 복구

SQLite 데이터베이스와 설정 파일 백업/복구 절차입니다.

## 백업 대상

| 대상 | 경로 | 중요도 | 주기 |
|------|------|--------|------|
| SQLite DB | `/opt/alphaengine/data/*.db` | 높음 | 매시간 |
| secrets.yaml | `/opt/alphaengine/config/secrets.yaml` | 높음 | 변경 시 |
| 로그 | `/opt/alphaengine/logs/` | 낮음 | 매일 |

## 자동 백업 스크립트

### /opt/alphaengine/scripts/backup.sh

```bash
#!/bin/bash
# AlphaEngine 백업 스크립트

set -e

# 설정
BACKUP_DIR="/opt/alphaengine/backups"
DATA_DIR="/opt/alphaengine/data"
CONFIG_DIR="/opt/alphaengine/config"
RETENTION_DAYS=30

# 타임스탬프
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_PATH="${BACKUP_DIR}/${TIMESTAMP}"

# 로그 함수
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# 백업 디렉토리 생성
mkdir -p "${BACKUP_PATH}"

# SQLite 백업 (온라인 백업)
log "SQLite 백업 시작..."

for db_file in ${DATA_DIR}/*.db; do
    if [ -f "$db_file" ]; then
        db_name=$(basename "$db_file")
        backup_file="${BACKUP_PATH}/${db_name}"
        
        # sqlite3 .backup 명령 사용 (WAL 안전)
        sqlite3 "$db_file" ".backup '${backup_file}'"
        
        log "  백업 완료: ${db_name}"
    fi
done

# 설정 파일 백업
log "설정 파일 백업..."
cp "${CONFIG_DIR}/secrets.yaml" "${BACKUP_PATH}/secrets.yaml"

# 압축
log "압축 중..."
cd "${BACKUP_DIR}"
tar -czf "${TIMESTAMP}.tar.gz" "${TIMESTAMP}/"
rm -rf "${TIMESTAMP}/"

log "백업 완료: ${TIMESTAMP}.tar.gz"

# 오래된 백업 삭제
log "오래된 백업 정리 (${RETENTION_DAYS}일 이상)..."
find "${BACKUP_DIR}" -name "*.tar.gz" -mtime +${RETENTION_DAYS} -delete

# 백업 목록 출력
log "현재 백업 목록:"
ls -lh "${BACKUP_DIR}"/*.tar.gz | tail -10

log "백업 스크립트 완료"
```

### 스크립트 설정

```bash
# 스크립트 디렉토리 생성
sudo -u alphaengine mkdir -p /opt/alphaengine/scripts
sudo -u alphaengine mkdir -p /opt/alphaengine/backups

# 스크립트 생성
sudo -u alphaengine vi /opt/alphaengine/scripts/backup.sh

# 실행 권한 부여
sudo chmod +x /opt/alphaengine/scripts/backup.sh

# 테스트 실행
sudo -u alphaengine /opt/alphaengine/scripts/backup.sh
```

## Cron 설정

```bash
# alphaengine 사용자의 crontab 편집
sudo -u alphaengine crontab -e
```

### crontab 내용

```cron
# AlphaEngine 백업 (매시간 정각)
0 * * * * /opt/alphaengine/scripts/backup.sh >> /opt/alphaengine/logs/backup.log 2>&1

# 일별 전체 백업 (매일 03:00)
0 3 * * * /opt/alphaengine/scripts/backup.sh >> /opt/alphaengine/logs/backup.log 2>&1
```

## 원격 백업 (선택)

### S3 업로드 스크립트

```bash
#!/bin/bash
# S3 백업 업로드

BACKUP_DIR="/opt/alphaengine/backups"
S3_BUCKET="s3://your-bucket/alphaengine-backups"

# 최신 백업 파일
LATEST=$(ls -t ${BACKUP_DIR}/*.tar.gz | head -1)

if [ -n "$LATEST" ]; then
    aws s3 cp "$LATEST" "$S3_BUCKET/"
    echo "S3 업로드 완료: $(basename $LATEST)"
fi
```

### rsync 동기화

```bash
# 원격 서버로 백업 동기화
rsync -avz --delete \
    /opt/alphaengine/backups/ \
    backup-user@backup-server:/backup/alphaengine/
```

## 복구 절차

### 1. 백업 파일 확인

```bash
ls -la /opt/alphaengine/backups/
```

### 2. 서비스 중지

```bash
sudo systemctl stop alphaengine-web
sudo systemctl stop alphaengine-bot
```

### 3. 백업 압축 해제

```bash
cd /opt/alphaengine/backups
tar -xzf 20240101_120000.tar.gz
```

### 4. 데이터 복구

```bash
# 기존 DB 백업
mv /opt/alphaengine/data/alphaengine_test.db /opt/alphaengine/data/alphaengine_test.db.old

# 복구
cp 20240101_120000/alphaengine_test.db /opt/alphaengine/data/

# 권한 설정
chown alphaengine:alphaengine /opt/alphaengine/data/alphaengine_test.db
```

### 5. 무결성 확인

```bash
# SQLite 무결성 체크
sqlite3 /opt/alphaengine/data/alphaengine_test.db "PRAGMA integrity_check;"

# 이벤트 수 확인
sqlite3 /opt/alphaengine/data/alphaengine_test.db "SELECT COUNT(*) FROM event_store;"
```

### 6. 서비스 재시작

```bash
sudo systemctl start alphaengine-bot
sudo systemctl start alphaengine-web

# 상태 확인
sudo systemctl status alphaengine-bot
sudo systemctl status alphaengine-web
```

## WAL 파일 처리

SQLite WAL 모드 사용 시 추가 파일이 생성됩니다:

```
alphaengine_test.db
alphaengine_test.db-wal
alphaengine_test.db-shm
```

### WAL 체크포인트 (백업 전)

```bash
# WAL 데이터를 메인 DB에 병합
sqlite3 /opt/alphaengine/data/alphaengine_test.db "PRAGMA wal_checkpoint(TRUNCATE);"
```

### 안전한 백업 방법

```bash
# sqlite3 .backup 명령 (WAL 안전)
sqlite3 /opt/alphaengine/data/alphaengine_test.db ".backup '/path/to/backup.db'"
```

## 재해 복구 계획

### 시나리오 1: DB 손상

1. 서비스 중지
2. 최신 백업으로 복구
3. 서비스 재시작
4. 손실 데이터 확인 (마지막 백업 ~ 손상 시점)

### 시나리오 2: 서버 장애

1. 새 서버 프로비저닝
2. [setup.md](setup.md) 따라 환경 구성
3. 원격 백업에서 데이터 복원
4. secrets.yaml 재설정 (보안상 별도 보관)
5. 서비스 시작

### 시나리오 3: 잘못된 설정 변경

1. config_store 테이블 확인
2. 이전 버전 설정으로 롤백
3. 또는 전체 백업에서 config_store 복원

## 백업 검증

정기적으로 백업 파일의 유효성을 검증합니다:

```bash
#!/bin/bash
# 백업 검증 스크립트

LATEST=$(ls -t /opt/alphaengine/backups/*.tar.gz | head -1)

# 임시 디렉토리에 압축 해제
TMP_DIR=$(mktemp -d)
tar -xzf "$LATEST" -C "$TMP_DIR"

# DB 무결성 확인
for db_file in ${TMP_DIR}/*/*.db; do
    if [ -f "$db_file" ]; then
        result=$(sqlite3 "$db_file" "PRAGMA integrity_check;")
        if [ "$result" = "ok" ]; then
            echo "OK: $(basename $db_file)"
        else
            echo "FAILED: $(basename $db_file) - $result"
        fi
    fi
done

# 정리
rm -rf "$TMP_DIR"
```

## 관련 문서

- [초기 설정](setup.md)
- [systemd 설정](systemd.md)
- [문제 해결](troubleshooting.md)
