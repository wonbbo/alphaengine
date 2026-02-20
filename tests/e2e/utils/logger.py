"""
E2E 테스트 로깅 유틸리티

테스트 결과를 콘솔과 파일에 기록.
"""

import json
import logging
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

# KST 타임존 (로그 출력용)
KST = timezone(timedelta(hours=9))


class E2EFormatter(logging.Formatter):
    """E2E 테스트용 로그 포맷터
    
    로그 출력은 KST로 표시 (내부 UTC, 표시 KST 원칙)
    """
    
    def format(self, record: logging.LogRecord) -> str:
        # KST로 변환하여 출력
        timestamp = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
        level = record.levelname.ljust(5)
        return f"[{timestamp}] {level} {record.getMessage()}"


def setup_e2e_logger(
    test_name: str,
    log_dir: Path | None = None,
    level: int = logging.INFO,
) -> logging.Logger:
    """E2E 테스트용 로거 설정
    
    Args:
        test_name: 테스트 이름 (로거 이름 및 파일명에 사용)
        log_dir: 로그 파일 저장 디렉토리 (None이면 파일 출력 안 함)
        level: 로그 레벨
        
    Returns:
        설정된 Logger 인스턴스
    """
    logger = logging.getLogger(f"e2e.{test_name}")
    logger.setLevel(level)
    
    # 기존 핸들러 제거 (중복 방지)
    logger.handlers.clear()
    
    # 콘솔 핸들러
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(E2EFormatter())
    logger.addHandler(console_handler)
    
    # 파일 핸들러 (log_dir 지정 시)
    if log_dir is not None:
        log_file = log_dir / f"{test_name}.log"
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(E2EFormatter())
        logger.addHandler(file_handler)
    
    return logger


class E2EResultRecorder:
    """E2E 테스트 결과 기록기
    
    테스트 실행 결과를 수집하고 JSON으로 저장.
    """
    
    def __init__(self, run_id: str | None = None) -> None:
        # KST로 표시 (사용자 친화적)
        self.run_id = run_id or datetime.now(KST).strftime("%Y-%m-%d_%H-%M-%S")
        self.start_time = datetime.now(timezone.utc)  # 내부 계산은 UTC
        self.results: dict[str, list[dict[str, Any]]] = {}
        self.failures: list[dict[str, Any]] = []
    
    def add_result(
        self,
        scenario: str,
        test_name: str,
        passed: bool,
        duration: float,
        error: str | None = None,
        traceback: str | None = None,
    ) -> None:
        """테스트 결과 추가
        
        Args:
            scenario: 시나리오 이름 (connection, balance, trading 등)
            test_name: 테스트 함수 이름
            passed: 통과 여부
            duration: 실행 시간 (초)
            error: 에러 메시지 (실패 시)
            traceback: 트레이스백 (실패 시)
        """
        if scenario not in self.results:
            self.results[scenario] = []
        
        result = {
            "test": test_name,
            "passed": passed,
            "duration": duration,
        }
        
        self.results[scenario].append(result)
        
        if not passed and error:
            self.failures.append({
                "test": test_name,
                "scenario": scenario,
                "error": error,
                "traceback": traceback,
            })
    
    def get_summary(self) -> dict[str, Any]:
        """전체 결과 요약 반환"""
        total = 0
        passed = 0
        failed = 0
        
        scenarios_summary: dict[str, dict[str, int]] = {}
        
        for scenario, tests in self.results.items():
            scenario_passed = sum(1 for t in tests if t["passed"])
            scenario_failed = len(tests) - scenario_passed
            
            scenarios_summary[scenario] = {
                "passed": scenario_passed,
                "failed": scenario_failed,
            }
            
            total += len(tests)
            passed += scenario_passed
            failed += scenario_failed
        
        duration = (datetime.now(timezone.utc) - self.start_time).total_seconds()
        
        return {
            "run_id": self.run_id,
            "mode": "testnet",
            "total_tests": total,
            "passed": passed,
            "failed": failed,
            "skipped": 0,
            "duration_seconds": round(duration, 2),
            "scenarios": scenarios_summary,
            "failures": self.failures,
        }
    
    def save(self, output_dir: Path) -> Path:
        """결과를 JSON 파일로 저장
        
        Args:
            output_dir: 출력 디렉토리
            
        Returns:
            저장된 파일 경로
        """
        # run_id 디렉토리 생성
        run_dir = output_dir / self.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        
        # summary.json 저장
        summary_file = run_dir / "summary.json"
        summary = self.get_summary()
        
        summary_file.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        
        return summary_file


def create_run_directory(base_dir: Path) -> Path:
    """타임스탬프 기반 실행 디렉토리 생성
    
    Args:
        base_dir: 베이스 디렉토리 (tests/e2e/results)
        
    Returns:
        생성된 디렉토리 경로
    """
    # KST로 표시 (사용자 친화적 디렉토리명)
    run_id = datetime.now(KST).strftime("%Y-%m-%d_%H-%M-%S")
    run_dir = base_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    
    # latest 심볼릭 링크 업데이트 (Windows에서는 무시)
    latest_link = base_dir / "latest"
    try:
        if latest_link.exists() or latest_link.is_symlink():
            latest_link.unlink()
        latest_link.symlink_to(run_dir.name)
    except OSError:
        # Windows에서 심볼릭 링크 실패 시 무시
        pass
    
    return run_dir
