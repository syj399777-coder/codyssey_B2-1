from __future__ import annotations

import csv
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from .decorators import AppError
from .models import Transaction
from .storage import BudgetStorage

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def validate_date(value: str) -> str:
    """YYYY-MM-DD 날짜 형식 검증."""
    if not DATE_RE.match(value):
        raise AppError("날짜 형식이 올바르지 않습니다 (YYYY-MM-DD).", "예: 2026-11-21")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise AppError("존재하지 않는 달력 날짜입니다.", "예: 2026-11-21") from exc
    return value


def validate_month(value: str) -> str:
    """YYYY-MM 월 형식 검증."""
    if not MONTH_RE.match(value):
        raise AppError("월 형식이 올바르지 않습니다 (YYYY-MM).", "예: 2026-11")
    try:
        datetime.strptime(value + "-01", "%Y-%m-%d")
    except ValueError as exc:
        raise AppError("존재하지 않는 월입니다.", "예: 2026-11") from exc
    return value


def validate_type(tx_type: str) -> str:
    """거래 타입(income/expense) 검증."""
    cleaned = tx_type.strip().lower()
    if cleaned not in {"income", "expense"}:
        raise AppError("타입은 'income' 또는 'expense'만 가능합니다.", "예: expense")
    return cleaned


def validate_amount(raw_amount: str | int) -> int:
    """양수 정수 금액 검증."""
    try:
        amount = int(str(raw_amount).replace(",", "").strip())
    except ValueError as exc:
        raise AppError("금액은 정수로 입력해야 합니다.", "예: 15000") from exc
    if amount <= 0:
        raise AppError("금액은 0보다 큰 양수여야 합니다.", "예: 15000")
    return amount


class BudgetService:
    """가계부 비즈니스 로직."""

    def __init__(self, storage: BudgetStorage) -> None:
        self.storage = storage

    def add_transaction(
        self,
        date_str: str,
        tx_type: str,
        category: str,
        amount_raw: str | int,
        memo: str = "",
        tags_raw: str | list[str] = "",
    ) -> Transaction:
        v_date = validate_date(date_str.strip())
        v_type = validate_type(tx_type)
        v_cat = category.strip()
        categories = self.storage.list_categories()
        if not categories:
            raise AppError(
                "등록된 카테고리가 없습니다.",
                "먼저 'category add' 명령으로 카테고리를 추가하세요.",
            )
        if v_cat not in categories:
            raise AppError(
                f"존재하지 않는 카테고리입니다: {v_cat}",
                f"등록된 카테고리({', '.join(categories)}) 중 선택하거나 'category add'로 추가하세요.",
            )
        v_amount = validate_amount(amount_raw)

        if isinstance(tags_raw, list):
            tags = [t.strip() for t in tags_raw if t.strip()]
        else:
            tags = [t.strip() for t in str(tags_raw).split(",") if t.strip()]

        tx = Transaction(
            id=self.storage.next_tx_id(),
            type=v_type,
            date=v_date,
            amount=v_amount,
            category=v_cat,
            memo=memo.strip(),
            tags=tags,
        )
        self.storage.append_transaction(tx)
        return tx

    def list_transactions(self, limit: int = 20) -> list[Transaction]:
        """최신순 거래 조회 (스트리밍 기반)."""
        if limit <= 0:
            raise AppError("--limit 값은 1 이상이어야 합니다.", "예: --limit 10")
        items = list(self.storage.stream_transactions())
        items.sort(key=lambda t: (t.date, t.id), reverse=True)
        return items[:limit]

    def search_transactions(
        self,
        date_from: str | None = None,
        date_to: str | None = None,
        category: str | None = None,
        tx_type: str | None = None,
        query: str | None = None,
        tag: str | None = None,
    ) -> list[Transaction]:
        """조건 기반 검색 후 최신순 반환."""
        v_from = validate_date(date_from) if date_from else None
        v_to = validate_date(date_to) if date_to else None
        v_type = validate_type(tx_type) if tx_type else None
        q_lower = query.strip().lower() if query else None
        tag_clean = tag.strip() if tag else None
        cat_clean = category.strip() if category else None

        matched: list[Transaction] = []
        for tx in self.storage.stream_transactions():
            if v_from and tx.date < v_from:
                continue
            if v_to and tx.date > v_to:
                continue
            if cat_clean and tx.category != cat_clean:
                continue
            if v_type and tx.type != v_type:
                continue
            if q_lower and q_lower not in tx.memo.lower():
                continue
            if tag_clean and tag_clean not in tx.tags:
                continue
            matched.append(tx)

        matched.sort(key=lambda t: (t.date, t.id), reverse=True)
        return matched

    def update_transaction(
        self,
        tx_id: str,
        date_str: str | None = None,
        tx_type: str | None = None,
        category: str | None = None,
        amount_raw: str | int | None = None,
        memo: str | None = None,
        tags_raw: str | None = None,
    ) -> Transaction:
        """ID로 거래 수정."""
        items = list(self.storage.stream_transactions())
        target_idx = next((i for i, t in enumerate(items) if t.id == tx_id), None)
        if target_idx is None:
            raise AppError(f"거래 ID '{tx_id}'를 찾을 수 없습니다.", "'list' 명령으로 ID를 확인하세요.")

        current = items[target_idx]
        new_date = validate_date(date_str.strip()) if date_str else current.date
        new_type = validate_type(tx_type) if tx_type else current.type
        new_amount = validate_amount(amount_raw) if amount_raw is not None else current.amount

        if category is not None:
            new_cat = category.strip()
            cats = self.storage.list_categories()
            if new_cat not in cats:
                raise AppError(
                    f"존재하지 않는 카테고리입니다: {new_cat}",
                    f"사용 가능 카테고리: {', '.join(cats)}",
                )
        else:
            new_cat = current.category

        new_memo = memo.strip() if memo is not None else current.memo
        if tags_raw is not None:
            new_tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
        else:
            new_tags = current.tags

        updated = Transaction(
            id=current.id,
            type=new_type,
            date=new_date,
            amount=new_amount,
            category=new_cat,
            memo=new_memo,
            tags=new_tags,
        )
        items[target_idx] = updated
        self.storage.rewrite_transactions(items)
        return updated

    def delete_transaction(self, tx_id: str) -> None:
        """ID로 거래 삭제."""
        items = list(self.storage.stream_transactions())
        filtered = [t for t in items if t.id != tx_id]
        if len(filtered) == len(items):
            raise AppError(f"거래 ID '{tx_id}'를 찾을 수 없습니다.", "'list' 명령으로 ID를 확인하세요.")
        self.storage.rewrite_transactions(filtered)

    def summarize_month(self, month: str, top_n: int = 5) -> dict:
        """월별 수입/지출/잔액/예산/카테고리 TOP N 계산."""
        v_month = validate_month(month)
        if top_n <= 0:
            raise AppError("--top 값은 1 이상이어야 합니다.", "예: --top 3")

        month_txs = [tx for tx in self.storage.stream_transactions() if tx.date.startswith(v_month + "-")]
        total_income = sum(tx.amount for tx in month_txs if tx.type == "income")
        total_expense = sum(tx.amount for tx in month_txs if tx.type == "expense")
        balance = total_income - total_expense

        expense_by_cat: dict[str, int] = defaultdict(int)
        for tx in month_txs:
            if tx.type == "expense":
                expense_by_cat[tx.category] += tx.amount

        top_expenses = sorted(expense_by_cat.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
        budgets = self.storage.load_budgets()
        budget_amount = budgets.get(v_month)

        return {
            "month": v_month,
            "has_data": len(month_txs) > 0,
            "total_income": total_income,
            "total_expense": total_expense,
            "balance": balance,
            "top_expenses": top_expenses,
            "budget": budget_amount,
        }

    def set_budget(self, month: str, amount: int) -> tuple[str, int]:
        v_month = validate_month(month)
        v_amount = validate_amount(amount)
        self.storage.set_budget(v_month, v_amount)
        return v_month, v_amount

    def add_category(self, name: str) -> str:
        cleaned = name.strip()
        if not cleaned:
            raise AppError("카테고리명을 입력해 주세요.", "예: food")
        cats = self.storage.list_categories()
        if cleaned in cats:
            raise AppError(f"이미 존재하는 카테고리입니다: {cleaned}", "'category list'로 확인하세요.")
        cats.append(cleaned)
        self.storage.save_categories(cats)
        return cleaned

    def list_categories(self) -> list[str]:
        return self.storage.list_categories()

    def remove_category(self, name: str) -> str:
        cleaned = name.strip()
        cats = self.storage.list_categories()
        if cleaned not in cats:
            raise AppError(f"존재하지 않는 카테고리입니다: {cleaned}", "'category list'로 확인하세요.")
        in_use = any(tx.category == cleaned for tx in self.storage.stream_transactions())
        if in_use:
            raise AppError(
                f"카테고리 '{cleaned}'를 사용하는 거래 내역이 있어 삭제할 수 없습니다.",
                "해당 거래를 수정/삭제한 뒤 다시 시도하세요.",
            )
        cats.remove(cleaned)
        self.storage.save_categories(cats)
        return cleaned

    def import_csv(self, csv_path: Path | str) -> tuple[int, int]:
        """CSV 파일에서 거래 일괄 가져오기."""
        path = Path(csv_path)
        if not path.exists():
            raise AppError(f"가져올 CSV 파일이 없습니다: {path}", "파일 경로를 확인해 주세요.")

        imported = 0
        skipped = 0
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            expected = {"date", "type", "category", "amount"}
            if not reader.fieldnames or not expected.issubset(set(reader.fieldnames)):
                raise AppError(
                    "CSV 헤더가 올바르지 않습니다.",
                    "필수 열: date, type, category, amount (선택: memo, tags)",
                )
            for row in reader:
                try:
                    self.add_transaction(
                        date_str=(row.get("date") or "").strip(),
                        tx_type=(row.get("type") or "").strip(),
                        category=(row.get("category") or "").strip(),
                        amount_raw=(row.get("amount") or "").strip(),
                        memo=(row.get("memo") or "").strip(),
                        tags_raw=(row.get("tags") or "").strip(),
                    )
                    imported += 1
                except AppError:
                    skipped += 1
        return imported, skipped

    def export_csv(
        self,
        out_path: Path | str,
        month: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> int:
        """조건에 맞는 거래를 CSV로 내보내기."""
        if not month and not (date_from and date_to):
            raise AppError(
                "내보내기 조건이 필요합니다.",
                "--month YYYY-MM 또는 --from YYYY-MM-DD --to YYYY-MM-DD를 지정하세요.",
            )

        if month:
            v_month = validate_month(month)
            txs = [tx for tx in self.storage.stream_transactions() if tx.date.startswith(v_month + "-")]
        else:
            v_from = validate_date(date_from or "")
            v_to = validate_date(date_to or "")
            txs = [tx for tx in self.storage.stream_transactions() if v_from <= tx.date <= v_to]

        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["date", "type", "category", "amount", "memo", "tags"])
            writer.writeheader()
            for tx in txs:
                writer.writerow(
                    {
                        "date": tx.date,
                        "type": tx.type,
                        "category": tx.category,
                        "amount": tx.amount,
                        "memo": tx.memo,
                        "tags": ",".join(tx.tags),
                    }
                )
        return len(txs)