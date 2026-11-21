from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Iterator

from .decorators import AppError
from .models import Transaction

DEFAULT_CATEGORIES = ["food", "transport", "rent", "salary", "etc"]


class BudgetStorage:
    """JSONL 기반 파일 저장소 (거래/카테고리/예산 3파일 분리)."""

    def __init__(self, data_dir: Path | str = Path("./data")) -> None:
        self.data_dir = Path(data_dir)
        self.tx_file = self.data_dir / "transactions.jsonl"
        self.cat_file = self.data_dir / "categories.jsonl"
        self.budget_file = self.data_dir / "budgets.jsonl"
        self._ensure_initialized()

    def _ensure_initialized(self) -> None:
        """저장 폴더 및 기본 파일 초기화."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if not self.tx_file.exists():
            self.tx_file.write_text("", encoding="utf-8")
        if not self.budget_file.exists():
            self.budget_file.write_text("", encoding="utf-8")
        if not self.cat_file.exists():
            lines = [json.dumps({"name": c}, ensure_ascii=False) for c in DEFAULT_CATEGORIES]
            self.cat_file.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    def _atomic_write_lines(self, target: Path, lines: list[str]) -> None:
        """임시 파일에 기록한 뒤 원자적으로 교체."""
        fd, tmp_name = tempfile.mkstemp(dir=self.data_dir, prefix=".tmp_")
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                if lines:
                    f.write("\n".join(lines) + "\n")
            os.replace(tmp_path, target)
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            raise

    def stream_transactions(self) -> Iterator[Transaction]:
        """거래 내역을 제너레이터로 한 줄씩 스트리밍 조회."""
        if not self.tx_file.exists():
            return
        with self.tx_file.open("r", encoding="utf-8") as f:
            for line in f:
                raw = line.strip()
                if not raw:
                    continue
                data = json.loads(raw)
                yield Transaction(
                    id=data["id"],
                    type=data["type"],
                    date=data["date"],
                    amount=int(data["amount"]),
                    category=data["category"],
                    memo=data.get("memo", ""),
                    tags=list(data.get("tags", [])),
                )

    def next_tx_id(self) -> str:
        """다음 거래 ID(TX-000001 형식) 생성."""
        max_num = 0
        for tx in self.stream_transactions():
            if tx.id.startswith("TX-"):
                try:
                    num = int(tx.id.split("-", 1)[1])
                    if num > max_num:
                        max_num = num
                except ValueError:
                    pass
        return f"TX-{max_num + 1:06d}"

    def append_transaction(self, tx: Transaction) -> None:
        """새 거래 추가."""
        payload = {
            "id": tx.id,
            "type": tx.type,
            "date": tx.date,
            "amount": tx.amount,
            "category": tx.category,
            "memo": tx.memo,
            "tags": tx.tags,
        }
        with self.tx_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def rewrite_transactions(self, items: list[Transaction]) -> None:
        """거래 목록 전체를 원자적으로 재작성."""
        lines = [
            json.dumps(
                {
                    "id": tx.id,
                    "type": tx.type,
                    "date": tx.date,
                    "amount": tx.amount,
                    "category": tx.category,
                    "memo": tx.memo,
                    "tags": tx.tags,
                },
                ensure_ascii=False,
            )
            for tx in items
        ]
        self._atomic_write_lines(self.tx_file, lines)

    def list_categories(self) -> list[str]:
        """카테고리 목록 반환."""
        if not self.cat_file.exists():
            return []
        cats: list[str] = []
        with self.cat_file.open("r", encoding="utf-8") as f:
            for line in f:
                raw = line.strip()
                if not raw:
                    continue
                cats.append(json.loads(raw)["name"])
        return cats

    def save_categories(self, categories: list[str]) -> None:
        """카테고리 목록 저장."""
        lines = [json.dumps({"name": c}, ensure_ascii=False) for c in categories]
        self._atomic_write_lines(self.cat_file, lines)

    def load_budgets(self) -> dict[str, int]:
        """월별 예산 딕셔너리({YYYY-MM: amount}) 반환."""
        budgets: dict[str, int] = {}
        if not self.budget_file.exists():
            return budgets
        with self.budget_file.open("r", encoding="utf-8") as f:
            for line in f:
                raw = line.strip()
                if not raw:
                    continue
                obj = json.loads(raw)
                budgets[obj["month"]] = int(obj["amount"])
        return budgets

    def set_budget(self, month: str, amount: int) -> None:
        """월별 예산 저장 또는 갱신."""
        if amount <= 0:
            raise AppError("예산 금액은 0보다 큰 정수여야 합니다.", "예: --amount 500000")
        budgets = self.load_budgets()
        budgets[month] = amount
        lines = [
            json.dumps({"month": m, "amount": amt}, ensure_ascii=False)
            for m, amt in sorted(budgets.items())
        ]
        self._atomic_write_lines(self.budget_file, lines)