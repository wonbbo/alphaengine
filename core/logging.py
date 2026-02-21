"""
로깅 설정 유틸리티

Bot과 Web 모두에서 사용하는 공통 로깅 설정.
- 콘솔: INFO 레벨
- 파일: INFO 레벨 (TimedRotatingFileHandler, daily)

사용법:
    from core.logging import setup_logging
    setup_logging("bot")  # Bot용 로거 설정
    setup_logging("web")  # Web용 로거 설정
"""

import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from core.constants import Paths


# 로그 설정 상수
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_FILE_BACKUP_COUNT = 7  # 최대 7일치 파일 유지

# 불필요한 로그를 생성하는 로거 목록 (레벨 조정 대상)
NOISY_LOGGERS = [
    "aiosqlite",      # DB 쿼리마다 executing/completed 로그 (매우 많음)
    "httpcore",       # HTTP 연결 상세 로그
    "httpx",          # HTTP 요청 상세 로그
    "websockets",     # WebSocket 프레임 로그
    "asyncio",        # 비동기 이벤트 루프 로그
    "urllib3",        # HTTP 라이브러리 로그
]


def setup_logging(
    process_name: str,
    console_level: int = logging.INFO,
    file_level: int = logging.INFO,
) -> logging.Logger:
    """로깅 설정 초기화
    
    프로세스 타입에 따라 적절한 로그 디렉토리에 파일 로그 저장.
    Daily 롤링으로 매일 자정에 새 파일 생성.
    
    Args:
        process_name: 프로세스 이름 ("bot" 또는 "web")
        console_level: 콘솔 로그 레벨 (기본: INFO)
        file_level: 파일 로그 레벨 (기본: INFO)
        
    Returns:
        설정된 루트 Logger
        
    사용 예:
        # Bot 시작 시
        setup_logging("bot")
        logger = logging.getLogger("bot")
        
        # Web 시작 시
        setup_logging("web")
        logger = logging.getLogger("web")
    """
    # 프로세스별 로그 디렉토리 결정
    if process_name == "bot":
        log_dir = Paths.BOT_LOGS_DIR
    elif process_name == "web":
        log_dir = Paths.WEB_LOGS_DIR
    else:
        log_dir = Paths.LOGS_DIR
    
    # 로그 디렉토리 생성 (없으면)
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # 로그 파일 경로
    log_file = log_dir / f"{process_name}.log"
    
    # 루트 로거 설정
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # 루트는 DEBUG로 설정 (핸들러에서 필터링)
    
    # 기존 핸들러 제거 (중복 방지)
    root_logger.handlers.clear()
    
    # 포맷터
    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
    
    # 1. 콘솔 핸들러 (StreamHandler)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # 2. 파일 핸들러 (TimedRotatingFileHandler - daily)
    file_handler = TimedRotatingFileHandler(
        filename=log_file,
        when="midnight",          # 매일 자정에 롤링
        interval=1,               # 1일 간격
        backupCount=LOG_FILE_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.suffix = "%Y-%m-%d"  # 백업 파일 형식: bot.log.2026-02-21
    file_handler.setLevel(file_level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    # 3. 불필요한 로거 레벨 조정 (로그 볼륨 감소)
    for logger_name in NOISY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)
    
    # 설정 완료 로그
    root_logger.info(f"로깅 초기화 완료: {process_name}")
    root_logger.info(f"  - 콘솔: {logging.getLevelName(console_level)}")
    root_logger.info(f"  - 파일: {log_file} ({logging.getLevelName(file_level)}, daily rotation)")
    root_logger.info(f"  - 보관: {LOG_FILE_BACKUP_COUNT}일")
    
    return root_logger


def get_log_file_path(process_name: str) -> Path:
    """로그 파일 경로 반환
    
    Args:
        process_name: 프로세스 이름 ("bot" 또는 "web")
        
    Returns:
        로그 파일 Path
    """
    if process_name == "bot":
        return Paths.BOT_LOGS_DIR / f"{process_name}.log"
    elif process_name == "web":
        return Paths.WEB_LOGS_DIR / f"{process_name}.log"
    else:
        return Paths.LOGS_DIR / f"{process_name}.log"
