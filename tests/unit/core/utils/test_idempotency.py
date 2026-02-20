"""
core/utils/idempotency.py 테스트

client_order_id 생성, 파싱, 검증 기능 테스트
"""

import pytest

from core.utils.idempotency import (
    CLIENT_ORDER_PREFIX,
    make_client_order_id,
    parse_client_order_id,
    is_alphaengine_order,
    validate_client_order_id,
)


class TestClientOrderPrefix:
    """CLIENT_ORDER_PREFIX 상수 테스트"""

    def test_prefix_value(self) -> None:
        """접두사 값 확인"""
        assert CLIENT_ORDER_PREFIX == "ae"

    def test_prefix_is_string(self) -> None:
        """접두사가 문자열인지 확인"""
        assert isinstance(CLIENT_ORDER_PREFIX, str)


class TestMakeClientOrderId:
    """make_client_order_id 함수 테스트"""

    def test_basic_generation(self) -> None:
        """기본 생성"""
        command_id = "550e8400-e29b-41d4-a716-446655440000"
        result = make_client_order_id(command_id)
        assert result == "ae-550e8400-e29b-41d4-a716-446655440000"

    def test_deterministic(self) -> None:
        """동일 입력 → 동일 출력 (결정적)"""
        command_id = "test-command-id"
        result1 = make_client_order_id(command_id)
        result2 = make_client_order_id(command_id)
        assert result1 == result2

    def test_different_inputs(self) -> None:
        """다른 입력 → 다른 출력"""
        result1 = make_client_order_id("command-1")
        result2 = make_client_order_id("command-2")
        assert result1 != result2

    def test_format(self) -> None:
        """출력 형식 확인"""
        command_id = "my-command"
        result = make_client_order_id(command_id)
        assert result.startswith("ae-")
        assert result == f"ae-{command_id}"

    def test_empty_command_id_raises(self) -> None:
        """빈 command_id는 예외 발생"""
        with pytest.raises(ValueError, match="비어 있을 수 없습니다"):
            make_client_order_id("")

    def test_uuid_format(self) -> None:
        """UUID 형식 command_id"""
        uuid_str = "123e4567-e89b-12d3-a456-426614174000"
        result = make_client_order_id(uuid_str)
        assert result == f"ae-{uuid_str}"


class TestParseClientOrderId:
    """parse_client_order_id 함수 테스트"""

    def test_valid_alphaengine_format(self) -> None:
        """유효한 AlphaEngine 형식 파싱"""
        client_order_id = "ae-550e8400-e29b-41d4-a716-446655440000"
        result = parse_client_order_id(client_order_id)
        assert result == "550e8400-e29b-41d4-a716-446655440000"

    def test_non_alphaengine_format(self) -> None:
        """AlphaEngine 형식이 아닌 경우"""
        assert parse_client_order_id("other-12345") is None
        assert parse_client_order_id("manual-order") is None
        assert parse_client_order_id("12345") is None

    def test_empty_string(self) -> None:
        """빈 문자열"""
        assert parse_client_order_id("") is None

    def test_only_prefix(self) -> None:
        """접두사만 있는 경우"""
        assert parse_client_order_id("ae-") is None

    def test_prefix_without_dash(self) -> None:
        """대시 없는 접두사"""
        assert parse_client_order_id("ae12345") is None

    def test_roundtrip(self) -> None:
        """생성 → 파싱 왕복"""
        command_id = "my-test-command"
        client_order_id = make_client_order_id(command_id)
        parsed = parse_client_order_id(client_order_id)
        assert parsed == command_id


class TestIsAlphaengineOrder:
    """is_alphaengine_order 함수 테스트"""

    def test_alphaengine_order(self) -> None:
        """AlphaEngine 주문 인식"""
        assert is_alphaengine_order("ae-550e8400-e29b-41d4-a716-446655440000") is True
        assert is_alphaengine_order("ae-command-123") is True

    def test_external_order(self) -> None:
        """외부 주문 인식"""
        assert is_alphaengine_order("manual-order-123") is False
        assert is_alphaengine_order("binance-12345") is False
        assert is_alphaengine_order("12345") is False

    def test_empty_string(self) -> None:
        """빈 문자열"""
        assert is_alphaengine_order("") is False

    def test_only_prefix(self) -> None:
        """접두사만 있는 경우"""
        assert is_alphaengine_order("ae-") is True  # 접두사 시작이면 True

    def test_similar_prefix(self) -> None:
        """유사한 접두사"""
        assert is_alphaengine_order("ae123") is False  # 대시 없음
        assert is_alphaengine_order("aex-123") is False  # 다른 접두사


class TestValidateClientOrderId:
    """validate_client_order_id 함수 테스트"""

    def test_valid_format(self) -> None:
        """유효한 형식"""
        assert validate_client_order_id("ae-550e8400-e29b-41d4-a716-446655440000") is True
        assert validate_client_order_id("ae-command-123") is True

    def test_invalid_format(self) -> None:
        """유효하지 않은 형식"""
        assert validate_client_order_id("other-12345") is False
        assert validate_client_order_id("manual") is False

    def test_empty_string(self) -> None:
        """빈 문자열"""
        assert validate_client_order_id("") is False

    def test_only_prefix(self) -> None:
        """접두사만 있는 경우 (command_id 없음)"""
        assert validate_client_order_id("ae-") is False

    def test_generated_id_is_valid(self) -> None:
        """생성된 ID는 유효해야 함"""
        command_id = "test-command"
        client_order_id = make_client_order_id(command_id)
        assert validate_client_order_id(client_order_id) is True


class TestEdgeCases:
    """엣지 케이스 테스트"""

    def test_special_characters_in_command_id(self) -> None:
        """command_id에 특수문자"""
        command_id = "cmd_with-special.chars:123"
        client_order_id = make_client_order_id(command_id)
        parsed = parse_client_order_id(client_order_id)
        assert parsed == command_id

    def test_unicode_in_command_id(self) -> None:
        """command_id에 유니코드 (권장하지 않지만 처리 가능)"""
        command_id = "명령-123"
        client_order_id = make_client_order_id(command_id)
        parsed = parse_client_order_id(client_order_id)
        assert parsed == command_id

    def test_long_command_id(self) -> None:
        """긴 command_id"""
        command_id = "a" * 100
        client_order_id = make_client_order_id(command_id)
        parsed = parse_client_order_id(client_order_id)
        assert parsed == command_id

    def test_multiple_dashes_in_command_id(self) -> None:
        """command_id에 여러 대시"""
        command_id = "cmd-with-multiple-dashes"
        client_order_id = make_client_order_id(command_id)
        parsed = parse_client_order_id(client_order_id)
        assert parsed == command_id
