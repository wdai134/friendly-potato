"""面试官Pro — CLI 入口。

三模式：
  1. 题库管理：添加、搜索、导入、导出题目
  2. 模拟面试：CLI 模式下面试（无 UI）
  3. 统计分析：命令行输出统计报告

使用方式：
  # 添加题目
  python main.py --add --title "Python GIL" --answer "全局解释器锁..." --category Python基础

  # 搜索题目
  python main.py --search "装饰器"

  # 导入/导出
  python main.py --import questions.json
  python main.py --export --category Python基础

  # 统计
  python main.py --stats

  # 启动 Web 面板
  streamlit run dashboard/app.py
"""

import argparse
import json
import os
import sys

from dotenv import load_dotenv

from agent.database import init_db
from agent.question_bank import (
    add_question, list_questions, count_questions, import_questions, export_questions,
    delete_question, get_question,
)
from agent.search import search_questions
from agent.categorizer import get_categories, get_category_stats, DIFFICULTY_LEVELS
from agent.reporter import overall_stats, progress_trend
from agent.logger import setup_logger

load_dotenv()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="面试官Pro — AI 辅助面试模拟与题库管理"
    )

    # 题库操作
    p.add_argument("--add", action="store_true", help="添加题目模式")
    p.add_argument("--title", help="题目标题")
    p.add_argument("--role", default="数据标注", help="岗位（默认: 数据标注）")
    p.add_argument("--content", default="", help="题目描述")
    p.add_argument("--answer", default="", help="参考答案")
    p.add_argument("--category", default="未分类", help="分类")
    p.add_argument("--difficulty", default="中等", help="难度")
    p.add_argument("--tags", default="", help="标签（逗号分隔）")
    p.add_argument("--source", default="", help="来源")

    # 搜索
    p.add_argument("--search", default=None, help="FTS5 全文搜索")

    # 列表
    p.add_argument("--list", action="store_true", help="列出题目")
    p.add_argument("--role-filter", default=None, dest="role_filter", help="按岗位筛选")
    p.add_argument("--cat", default=None, help="按分类筛选")
    p.add_argument("--diff", default=None, help="按难度筛选")

    # 导入/导出
    p.add_argument("--import", dest="import_file", default=None, help="从 JSON 文件导入题目")
    p.add_argument("--export", action="store_true", help="导出题目为 JSON")

    # 统计
    p.add_argument("--stats", action="store_true", help="显示全局统计")

    return p


def main() -> None:
    args = build_parser().parse_args()
    logger = setup_logger(level=os.getenv("LOG_LEVEL", "INFO"))

    # 初始化数据库
    init_db()

    # ── 添加题目 ──
    if args.add:
        if not args.title:
            logger.error("添加题目需要 --title")
            sys.exit(1)
        tags = [t.strip() for t in args.tags.split(",") if t.strip()]
        qid = add_question(
            title=args.title, role=args.role, content=args.content, answer=args.answer,
            category=args.category, difficulty=args.difficulty,
            tags=tags, source=args.source,
        )
        logger.info("已添加题目 #%d: %s", qid, args.title)
        return

    # ── 搜索 ──
    if args.search:
        results = search_questions(
            args.search, category=args.cat, difficulty=args.diff,
        )
        print(f"\n🔍 搜索「{args.search}」— {len(results)} 道匹配题目:\n")
        for q in results:
            print(f"  #{q['id']} {q['title']}")
            print(f"     分类: {q['category']} | 难度: {q['difficulty']}")
            if q.get("content"):
                print(f"     描述: {q['content'][:100]}")
            if q.get("answer"):
                print(f"     答案: {q['answer'][:100]}")
            print()
        return

    # ── 列表 ──
    if args.list:
        questions = list_questions(role=args.role_filter, category=args.cat, difficulty=args.diff)
        print(f"\n📚 题库 — 共 {count_questions()} 道，当前显示 {len(questions)} 道:\n")
        for q in questions:
            tags_str = " · ".join(q.get("tags", [])) if q.get("tags") else ""
            role_str = f" [{q.get('role', '')}]" if q.get("role") else ""
            print(f"  #{q['id']} {q['title']}{role_str} [{q['category']} · {q['difficulty']}] {tags_str}")
        return

    # ── 导入 ──
    if args.import_file:
        with open(args.import_file, encoding="utf-8") as f:
            data = json.load(f)
        count, errors = import_questions(data)
        logger.info("导入完成: %d/%d 道题目", count, len(data))
        for err in errors:
            logger.warning("  #%d %s — %s", err["index"] + 1, err["title"], err["error"])
        return

    # ── 导出 ──
    if args.export:
        questions = export_questions(role=args.role_filter, category=args.cat, difficulty=args.diff)
        output = json.dumps(questions, ensure_ascii=False, indent=2)
        filename = f"questions_export_{len(questions)}.json"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(output)
        logger.info("已导出 %d 道题目 → %s", len(questions), filename)
        return

    # ── 统计 ──
    if args.stats:
        stats = overall_stats()
        print("\n📊 面试官Pro — 全局统计\n")
        print(f"  题库总量: {stats['total_questions']}")
        print(f"  面试次数: {stats['total_sessions']}")
        print(f"  已评分数: {stats['total_answers']}")
        print(f"  历史均分: {stats['overall_avg_score']}/100" if stats["overall_avg_score"] else "  历史均分: --")

        print("\n  分类分布:")
        for c in stats["top_categories"]:
            bar = "█" * (c["cnt"] or 0)
            print(f"    {c['category']:12s} {bar} ({c['cnt']})")

        trend = progress_trend(limit=5)
        if trend:
            print("\n  最近面试:")
            for t in trend:
                avg = f"{t['avg_score']:.0f}/100" if t['avg_score'] else "未评分"
                print(f"    #{t['id']} {t['started_at'][:10]} {t['mode']:8s} {avg}")
        return

    # ── 默认：显示帮助 ──
    build_parser().print_help()
    print("\n💡 启动 Web 面板: streamlit run dashboard/app.py")


if __name__ == "__main__":
    main()
