"""
Idempotency 유틸리티

client_order_id 생성 및 파싱 기능 제공
규칙: ae-{command_id}
"""

# AlphaEngine client_order_id 접두사
CLIENT_ORDER_PREFIX: str = "ae"


def make_client_order_id(command_id: str) -> str:
    """결정적 client_order_id 생성

    Args:
        command_id: Command의 고유 ID (UUID)

    Returns:
        client_order_id: ae-{command_id} 형식

    Example:
        >>> make_client_order_id("550e8400-e29b-41d4-a716-446655440000")
        'ae-550e8400-e29b-41d4-a716-446655440000'
    """
    if not command_id:
        raise ValueError("command_id는 비어 있을 수 없습니다")

    return f"{CLIENT_ORDER_PREFIX}-{command_id}"


def parse_client_order_id(client_order_id: str) -> str | None:
    """client_order_id에서 command_id 추출

    Args:
        client_order_id: ae-{command_id} 형식의 문자열

    Returns:
        command_id 또는 None (형식 불일치 시)

    Example:
        >>> parse_client_order_id("ae-550e8400-e29b-41d4-a716-446655440000")
        '550e8400-e29b-41d4-a716-446655440000'
        >>> parse_client_order_id("other-12345")
        None
    """
    if not client_order_id:
        return None

    prefix = f"{CLIENT_ORDER_PREFIX}-"

    if client_order_id.startswith(prefix):
        command_id = client_order_id[len(prefix) :]
        # 추출된 command_id가 비어있으면 None 반환
        return command_id if command_id else None

    return None


def is_alphaengine_order(client_order_id: str) -> bool:
    """AlphaEngine이 생성한 주문인지 확인

    Args:
        client_order_id: 검증할 client_order_id

    Returns:
        True: AlphaEngine이 생성한 주문
        False: 외부에서 생성한 주문

    Example:
        >>> is_alphaengine_order("ae-550e8400-e29b-41d4-a716-446655440000")
        True
        >>> is_alphaengine_order("manual-order-123")
        False
    """
    if not client_order_id:
        return False

    return client_order_id.startswith(f"{CLIENT_ORDER_PREFIX}-")


def validate_client_order_id(client_order_id: str) -> bool:
    """client_order_id 형식 유효성 검사

    AlphaEngine 형식(ae-{command_id})이고 command_id가 비어있지 않은지 확인

    Args:
        client_order_id: 검증할 client_order_id

    Returns:
        True: 유효한 형식
        False: 유효하지 않은 형식
    """
    if not client_order_id:
        return False

    parsed = parse_client_order_id(client_order_id)
    return parsed is not None and len(parsed) > 0
