from __future__ import annotations

import functools
import sys
import time
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


class AppError(Exception):
    """사용자 안내용 오류."""

    def __init__(self, message: str, hint: str = "", exit_code: int = 1) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.exit_code = exit_code


def handle_errors(func: F) -> F:
    """오류를 깔끔하게 출력하고 종료 코드를 반환하는 데코레이터."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except AppError as e:
            print(f"[오류] {e.message}", file=sys.stderr)
            if e.hint:
                print(f"[힌트] {e.hint}", file=sys.stderr)
            return e.exit_code
        except Exception as e:
            print(f"[오류] 예기치 못한 문제가 발생했습니다: {e}", file=sys.stderr)
            print("[힌트] 입력값이나 데이터 파일 상태를 확인해 주세요.", file=sys.stderr)
            return 1

    return wrapper  # type: ignore[return-value]


def measure_time(func: F) -> F:
    """실행 시간을 측정하는 데코레이터."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        if elapsed >= 0.05:
            print(f"[시간] 실행 소요: {elapsed:.3f}초")
        return result

    return wrapper  # type: ignore[return-value]