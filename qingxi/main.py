"""文件清理 Agent — CLI 入口。

完整流程：
  扫描 → AI 分类 → 生成报告 → 人工确认 → 执行清理 → 记录日志

使用方式：
  # 清理模式
  python main.py --scan-dir /path/to/scan
  python main.py --scan-dir /path/to/scan --dry-run
  python main.py --scan-dir /path/to/scan --yes  # 跳过确认

  # 恢复模式
  python main.py --restore                          # 列出隔离区文件
  python main.py --restore --execute                # 恢复全部
  python main.py --restore --pattern "*.pdf"        # 按模式恢复

  # 重复文件检测
  python main.py --dedup --scan-dir /path/to/scan
"""

import argparse
import logging
import os
import sys

from dotenv import load_dotenv

from agent.classifier import FileClassifier
from agent.dedup import DedupFinder, format_dedup_report
from agent.executor import execute_cleanup
from agent.logger import setup_logger
from agent.reporter import generate_report
from agent.restorer import Restorer
from agent.safelist import SafeList
from agent.scanner import FileScanner

load_dotenv()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="文件清理 Agent — 智能扫描、AI 分类、安全清理"
    )
    p.add_argument(
        "--scan-dir",
        default=os.getenv("SCAN_DIR", "."),
        help="要扫描的目录（默认: 当前目录）",
    )
    p.add_argument(
        "--config",
        default="config/rules.yaml",
        help="清理规则配置文件路径",
    )
    p.add_argument(
        "--quarantine-dir",
        default=os.getenv("QUARANTINE_DIR", "./quarantine"),
        help="隔离区目录（文件移到这里而非永久删除）",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="预览模式：只生成报告，不实际移动文件",
    )
    p.add_argument(
        "--yes",
        action="store_true",
        help="跳过人工确认，直接执行（谨慎使用）",
    )
    p.add_argument(
        "--no-ai",
        action="store_true",
        help="禁用 AI 分类，仅用规则匹配",
    )
    p.add_argument(
        "--safelist-config",
        default="config/safelist.yaml",
        help="白名单配置文件路径",
    )
    # ── 恢复模式 ──
    p.add_argument(
        "--restore",
        action="store_true",
        help="恢复模式：列出或恢复隔离区中的文件",
    )
    p.add_argument(
        "--execute",
        action="store_true",
        help="配合 --restore 使用，实际执行恢复（默认只列出）",
    )
    p.add_argument(
        "--pattern",
        default=None,
        help="配合 --restore 使用，按文件名模式恢复（如 *.pdf）",
    )
    p.add_argument(
        "--restore-target",
        default=None,
        help="恢复到指定目录（默认恢复到原始位置）",
    )
    # ── 重复文件检测 ──
    p.add_argument(
        "--dedup",
        action="store_true",
        help="重复文件检测模式",
    )
    p.add_argument(
        "--min-size",
        type=int,
        default=1,
        help="重复检测时跳过小于此大小的文件（字节，默认 1）",
    )
    return p


def main() -> None:
    args = build_parser().parse_args()
    logger = setup_logger(level=os.getenv("LOG_LEVEL", "INFO"))

    # ── 恢复模式 ──────────────────────────────────────────
    if args.restore:
        _handle_restore(args, logger)
        return

    # ── 重复文件检测 ──────────────────────────────────────
    if args.dedup:
        _handle_dedup(args, logger)
        return

    # ── 扫描 ──
    logger.info("开始扫描目录: %s", args.scan_dir)
    try:
        scanner = FileScanner.from_config(args.config)
        scan_result = scanner.scan(args.scan_dir)
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)

    logger.info(
        "扫描完成: %d 个文件, 其中 %d 个建议清理, %d 个需 AI 判断",
        scan_result.total_files,
        len(scan_result.cleanup_candidates),
        len(scan_result.review_candidates),
    )

    # ── AI 分类 ──
    ai_decisions = None
    if not args.no_ai and scan_result.review_candidates:
        logger.info(
            "调用 AI 分类 %d 个待审核文件...",
            len(scan_result.review_candidates),
        )
        try:
            classifier = FileClassifier()
            ai_decisions = classifier.classify(scan_result.review_candidates)
            logger.info("AI 分类完成: %d 条决策", len(ai_decisions))
        except Exception as e:
            logger.warning("AI 分类失败，将保留所有 review 文件: %s", e)
            ai_decisions = [
                {
                    "name": f.name,
                    "action": "keep",
                    "reason": "AI故障保守处理",
                }
                for f in scan_result.review_candidates
            ]
    elif args.no_ai:
        logger.info("已禁用 AI 分类，review 文件将全部保留")

    # ── 生成报告 ──
    report = generate_report(scan_result, ai_decisions)
    print("\n" + report + "\n")

    # ── 收集待清理文件 ──
    decision_map: dict[str, str] = {}
    if ai_decisions:
        decision_map = {d["name"]: d["action"] for d in ai_decisions}

    to_clean = list(scan_result.cleanup_candidates)
    for entry in scan_result.review_candidates:
        if decision_map.get(entry.name) == "cleanup":
            to_clean.append(entry)

    if not to_clean:
        logger.info("没有需要清理的文件，退出")
        return

    # ── 人工确认 ──
    if not args.yes:
        print(f"\n共 {len(to_clean)} 个文件待清理")
        print("文件将被移至隔离区（非永久删除），可随时恢复")
        print(f"隔离区路径: {args.quarantine_dir}")
        print()
        try:
            response = input("确认执行清理？[y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n已取消")
            return
        if response not in ("y", "yes"):
            logger.info("用户取消清理操作")
            return

    # ── 加载白名单 ──
    safelist = None
    try:
        safelist = SafeList.from_config(args.safelist_config)
    except FileNotFoundError:
        logger.info("未找到白名单配置文件，跳过白名单检查")

    # ── 执行清理 ──
    logger.info("开始执行清理...")
    result = execute_cleanup(
        to_clean, args.quarantine_dir, dry_run=args.dry_run, safelist=safelist,
    )

    if args.dry_run:
        logger.info(
            "[预览模式] 将清理 %d 个文件，跳过 %d 个，封锁 %d 个",
            result.success_count,
            len(result.skipped),
            len(result.blocked),
        )
    else:
        logger.info(
            "清理完毕: 成功 %d, 跳过 %d, 封锁 %d, 失败 %d",
            result.success_count,
            len(result.skipped),
            len(result.blocked),
            len(result.errors),
        )
        if result.blocked:
            logger.warning("以下文件被白名单封锁:")
            for path in result.blocked:
                logger.warning("  🔴 %s", path)
        if result.errors:
            logger.warning("以下文件清理失败:")
            for path, err in result.errors:
                logger.warning("  %s: %s", path, err)


def _handle_restore(args: argparse.Namespace, logger: logging.Logger) -> None:
    """处理 --restore 模式。"""
    try:
        restorer = Restorer(args.quarantine_dir)
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)

    entries = restorer.list_quarantined()
    if not entries:
        logger.info("隔离区为空，没有可恢复的文件")
        return

    total_size = sum(e.size_bytes for e in entries)
    logger.info(
        "隔离区共 %d 个文件，总计 %s",
        len(entries),
        _format_size(total_size),
    )
    print()
    for e in entries:
        tag = "[TS]" if e.has_timestamp else "    "
        print(f"  {tag} {e.original_name}")
        print(f"       隔离区: {e.quarantine_path}")
        print(f"       恢复至: {e.original_path}")
    print()

    if not args.execute:
        logger.info("预览模式，使用 --execute 执行恢复")
        return

    # 执行恢复
    if args.pattern:
        result = restorer.restore_by_pattern(
            args.pattern,
            target_dir=args.restore_target,
            dry_run=args.dry_run,
        )
    else:
        result = restorer.restore_all(
            target_dir=args.restore_target,
            dry_run=args.dry_run,
        )

    if args.dry_run:
        logger.info(
            "[预览模式] 将恢复 %d 个文件",
            result.success_count,
        )
    else:
        logger.info(
            "恢复完成: 成功 %d, 跳过 %d, 失败 %d",
            result.success_count,
            len(result.skipped),
            len(result.errors),
        )
        if result.errors:
            logger.warning("以下文件恢复失败:")
            for path, err in result.errors:
                logger.warning("  %s: %s", path, err)


def _handle_dedup(args: argparse.Namespace, logger: logging.Logger) -> None:
    """处理 --dedup 模式。"""
    scan_dir = args.scan_dir
    logger.info("开始重复文件检测: %s", scan_dir)

    try:
        finder = DedupFinder(min_size=args.min_size)
        result = finder.find_duplicates(scan_dir)
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)

    report = format_dedup_report(result)
    print("\n" + report + "\n")

    if result.groups:
        logger.info(
            "检测完成: %d 组重复, %d 个重复文件, 可释放 %s",
            result.group_count,
            result.duplicate_count,
            _format_size(result.wasted_bytes),
        )
    else:
        logger.info("检测完成: 未发现重复文件")


def _format_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


if __name__ == "__main__":
    main()
