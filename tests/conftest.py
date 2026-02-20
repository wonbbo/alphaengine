"""
pytest 공통 fixture 정의

Dev-Phase 0: 핵심 유틸리티 테스트용 fixture
"""

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_dir() -> Path:
    """OS 독립적인 임시 디렉토리 생성"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_secrets_file(temp_dir: Path) -> Path:
    """테스트용 secrets.yaml 파일 생성"""
    secrets_content = """# 테스트용 secrets.yaml
mode: testnet

production:
  api_key: "prod_api_key_12345"
  api_secret: "prod_api_secret_67890"

testnet:
  api_key: "test_api_key_abcde"
  api_secret: "test_api_secret_fghij"

web:
  secret_key: "test_jwt_secret_key_xyz"
"""
    secrets_path = temp_dir / "secrets.yaml"
    secrets_path.write_text(secrets_content, encoding="utf-8")
    return secrets_path


@pytest.fixture
def temp_secrets_file_production(temp_dir: Path) -> Path:
    """테스트용 secrets.yaml 파일 생성 (production 모드)"""
    secrets_content = """mode: production

production:
  api_key: "prod_api_key_12345"
  api_secret: "prod_api_secret_67890"

testnet:
  api_key: "test_api_key_abcde"
  api_secret: "test_api_secret_fghij"

web:
  secret_key: "prod_jwt_secret_key_xyz"
"""
    secrets_path = temp_dir / "secrets_prod.yaml"
    secrets_path.write_text(secrets_content, encoding="utf-8")
    return secrets_path


@pytest.fixture
def temp_secrets_file_invalid_mode(temp_dir: Path) -> Path:
    """잘못된 모드의 secrets.yaml 파일 생성"""
    secrets_content = """mode: invalid_mode

production:
  api_key: "prod_api_key"
  api_secret: "prod_api_secret"

testnet:
  api_key: "test_api_key"
  api_secret: "test_api_secret"

web:
  secret_key: "jwt_secret"
"""
    secrets_path = temp_dir / "secrets_invalid.yaml"
    secrets_path.write_text(secrets_content, encoding="utf-8")
    return secrets_path
