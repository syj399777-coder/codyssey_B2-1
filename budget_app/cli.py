from __future__ import annotations

import argparse
import sys
from typing import Sequence

from .decorators import handle_errors, measure_time
from .models import Transaction
from .services import BudgetService
from .storage import BudgetStorage


def _print_tx_row(tx: Transaction) -> None:
    tags_str = f" [#{',#'.join(tx.tags)}]" if tx.tags else ""
    memo_str = f" | {tx.memo}" if tx.memo else ""
    print(f"{tx.id} | {tx.date} | {tx.type} | {tx.category} | {tx.amount}{memo_str}{tags_str}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="budget_app",
        description="콘솔 기반 나만의 용돈 기입장 프로그램",
    )
    parser.add_argument(
        "--data-dir",
        default="./data",
        help="데이터 저장 폴더 경로 (기본값: ./data)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # 1. add
    sub.add_parser("add", help="거래 추가 (대화형)")

    # 2. list
    p_list = sub.add_parser("list", help="거래 목록 조회 (최신순)")
    p_list.add_argument("--limit", type=int, default=20, help="최대 출력 건수 (기본값: 20)")

    # 3. search
    p_search = sub.add_parser("search", help="조건별 거래 검색 (최신순)")
    p_search.add_argument("--from", dest="date_from", help="시작일 (YYYY-MM-DD)")
    p_search.add_argument("--to", dest="date_to", help="종료일 (YYYY-MM-DD)")
    p_search.add_argument("--category", help="카테고리명")
    p_search.add_argument("--type", dest="tx_type", help="income 또는 expense")
    p_search.add_argument("--q", dest="query", help="메모 키워드")
    p_search.add_argument("--tag", help="태그명")

    # 4. summary
    p_sum = sub.add_parser("summary", help="월별 요약 및 예산 사용률 출력")
    p_sum.add_argument("--month", required=True, help="대상 월 (YYYY-MM)")
    p_sum.add_argument("--top", type=int, default=3, help="지출 TOP N (기본값: 3)")

    # 5. budget
    p_budget = sub.add_parser("budget", help="월 예산 설정")
    b_sub = p_budget.add_subparsers(dest="budget_cmd", required=True)
    p_b_set = b_sub.add_parser("set", help="월 예산 저장")
    p_b_set.add_argument("--month", required=True, help="대상 월 (YYYY-MM)")
    p_b_set.add_argument("--amount", required=True, type=int, help="예산 금액")

    # 6. category
    p_cat = sub.add_parser("category", help="카테고리 관리")
    c_sub = p_cat.add_subparsers(dest="cat_cmd", required=True)
    p_c_add = c_sub.add_parser("add", help="카테고리 추가 (대화형 또는 --name)")
    p_c_add.add_argument("--name", help="카테고리명")
    c_sub.add_parser("list", help="카테고리 목록 조회")
    p_c_rm = c_sub.add_parser("remove", help="카테고리 삭제")
    p_c_rm.add_argument("--name", required=True, help="삭제할 카테고리명")

    # 7. update (옵션 기반으로 고정)
    p_upd = sub.add_parser("update", help="거래 수정 (--id 기반 옵션 방식)")
    p_upd.add_argument("--id", required=True, help="수정할 거래 ID")
    p_upd.add_argument("--date", dest="date_str", help="날짜 (YYYY-MM-DD)")
    p_upd.add_argument("--type", dest="tx_type", help="income 또는 expense")
    p_upd.add_argument("--category", help="카테고리명")
    p_upd.add_argument("--amount", help="금액 (양수 정수)")
    p_upd.add_argument("--memo", help="메모")
    p_upd.add_argument("--tags", help="쉼표 구분 태그")

    # 8. delete
    p_del = sub.add_parser("delete", help="거래 삭제")
    p_del.add_argument("--id", required=True, help="삭제할 거래 ID")

    # 9. import / export
    p_imp = sub.add_parser("import", help="CSV 파일에서 거래 가져오기")
    p_imp.add_argument("--from", dest="src_csv", required=True, help="가져올 CSV 경로")

    p_exp = sub.add_parser("export", help="조건에 맞는 거래를 CSV로 내보내기")
    p_exp.add_argument("--out", dest="out_csv", required=True, help="저장할 CSV 경로")
    p_exp.add_argument("--month", help="대상 월 (YYYY-MM)")
    p_exp.add_argument("--from", dest="date_from", help="시작일 (YYYY-MM-DD)")
    p_exp.add_argument("--to", dest="date_to", help="종료일 (YYYY-MM-DD)")

    return parser


@handle_errors
@measure_time
def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    storage = BudgetStorage(data_dir=args.data_dir)
    service = BudgetService(storage)

    if args.command == "add":
        date_str = input("날짜(YYYY-MM-DD): ")
        tx_type = input("타입(income/expense): ")
        category = input("카테고리: ")
        amount_raw = input("금액(양수): ")
        memo = input("메모(선택): ")
        tags_raw = input("태그(쉼표로 구분, 없으면 엔터): ")
        tx = service.add_transaction(date_str, tx_type, category, amount_raw, memo, tags_raw)
        print(f"[저장 완료] id={tx.id}")
        return 0

    if args.command == "list":
        for tx in service.list_transactions(limit=args.limit):
            _print_tx_row(tx)
        return 0

    if args.command == "search":
        rows = service.search_transactions(
            date_from=args.date_from,
            date_to=args.date_to,
            category=args.category,
            tx_type=args.tx_type,
            query=args.query,
            tag=args.tag,
        )
        for tx in rows:
            _print_tx_row(tx)
        return 0

    if args.command == "summary":
        summary = service.summarize_month(month=args.month, top_n=args.top)
        if not summary["has_data"] and summary["budget"] is None:
            print("데이터 없음")
            return 0
        print(f"총 수입: {summary['total_income']}원")
        print(f"총 지출: {summary['total_expense']}원")
        print(f"잔액: {summary['balance']}원")
        if summary["budget"] is not None:
            budget = summary["budget"]
            rate = (summary["total_expense"] / budget * 100) if budget > 0 else 0.0
            print(f"예산: {budget}원 (사용률 {rate:.1f}%)")
            if summary["total_expense"] > budget:
                print(f"[경고] {summary['month']} 예산을 {summary['total_expense'] - budget}원 초과했습니다!")
        print(f"지출 TOP {args.top}")
        if summary["top_expenses"]:
            for idx, (cat, amt) in enumerate(summary["top_expenses"], start=1):
                print(f"{idx}) {cat} {amt}원")
        else:
            print("지출 내역 없음")
        return 0

    if args.command == "budget" and args.budget_cmd == "set":
        m, amt = service.set_budget(args.month, args.amount)
        print(f"[저장 완료] {m} 예산 {amt}원")
        return 0

    if args.command == "category":
        if args.cat_cmd == "add":
            name = args.name if args.name else input("카테고리명: ")
            saved = service.add_category(name)
            print(f"[저장 완료] category={saved}")
            return 0
        if args.cat_cmd == "list":
            for c in service.list_categories():
                print(f"- {c}")
            return 0
        if args.cat_cmd == "remove":
            removed = service.remove_category(args.name)
            print(f"[삭제 완료] category={removed}")
            return 0

    if args.command == "update":
        updated = service.update_transaction(
            tx_id=args.id,
            date_str=args.date_str,
            tx_type=args.tx_type,
            category=args.category,
            amount_raw=args.amount,
            memo=args.memo,
            tags_raw=args.tags,
        )
        print(f"[수정 완료] id={updated.id}")
        return 0

    if args.command == "delete":
        service.delete_transaction(args.id)
        print(f"[삭제 완료] id={args.id}")
        return 0

    if args.command == "import":
        imported, skipped = service.import_csv(args.src_csv)
        print(f"[완료] imported={imported}, skipped={skipped}")
        return 0

    if args.command == "export":
        count = service.export_csv(
            out_path=args.out_csv,
            month=args.month,
            date_from=args.date_from,
            date_to=args.date_to,
        )
        print(f"[완료] {args.out_csv} ({count} records)")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())