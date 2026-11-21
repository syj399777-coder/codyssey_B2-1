from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Transaction:
    """거래 내역 모델."""

    id: str
    type: str  # "income" 또는 "expense"
    date: str  # "YYYY-MM-DD"
    amount: int  # 양수 정수
    category: str
    memo: str = ""
    tags: list[str] = field(default_factory=list)