"""报告生成器 — 将扫描结果和 AI 分类决策渲染为可读的清理报告。"""

from datetime import datetime

from agent.scanner import FileEntry, ScanResult


def _format_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def _format_entry(entry: FileEntry, decision: dict[str, str] | None = None) -> str:
    action = decision["action"] if decision else entry.action
    reason = decision.get("reason", "") if decision else ""
    icon = {"cleanup": "[删]", "keep": "[留]", "review": "[?]"}.get(action, "[?]")

    return (
        f"  {icon} {entry.name}\n"
        f"      路径: {entry.path}\n"
        f"      大小: {_format_size(entry.size_bytes)}  |  "
        f"距今: {entry.age_days} 天  |  "
        f"规则: {entry.matched_rule}"
        + (f"  |  原因: {reason}" if reason else "")
    )


def generate_report(
    scan_result: ScanResult,
    ai_decisions: list[dict[str, str]] | None = None,
) -> str:
    decision_map: dict[str, dict[str, str]] = {}
    if ai_decisions:
        decision_map = {d["name"]: d for d in ai_decisions}

    lines = [
        "=" * 60,
        "         文件清理报告",
        "=" * 60,
        f"扫描目录: {scan_result.scan_dir}",
        f"扫描时间: {scan_result.scan_time}",
        f"文件总数: {scan_result.total_files}",
        "",
    ]

    cleanup_count = 0
    keep_count = 0
    cleanup_size = 0

    for entry in scan_result.entries:
        decision = decision_map.get(entry.name)
        action = decision["action"] if decision else entry.action
        if action == "cleanup":
            cleanup_count += 1
            cleanup_size += entry.size_bytes
        elif action == "keep":
            keep_count += 1

    lines.append(f"建议清理: {cleanup_count} 个文件")
    lines.append(f"可释放空间: {_format_size(cleanup_size)}")
    lines.append(f"建议保留: {keep_count} 个文件")
    lines.append("")

    lines.append("-" * 60)
    lines.append("  建议清理的文件")
    lines.append("-" * 60)
    for entry in scan_result.entries:
        decision = decision_map.get(entry.name)
        action = decision["action"] if decision else entry.action
        if action == "cleanup":
            lines.append(_format_entry(entry, decision))

    lines.append("")
    lines.append("-" * 60)
    lines.append("  AI 判断结果（来自 DeepSeek 分类）")
    lines.append("-" * 60)
    if ai_decisions:
        for d in ai_decisions:
            lines.append(f"  {d['name']} → {d['action']}（{d.get('reason', '')})")
    else:
        lines.append("  （无 AI 分类数据）")

    lines.append("")
    lines.append("-" * 60)
    lines.append("  保留的文件")
    lines.append("-" * 60)
    for entry in scan_result.entries:
        decision = decision_map.get(entry.name)
        action = decision["action"] if decision else entry.action
        if action == "keep":
            lines.append(_format_entry(entry, decision))

    lines.append("")
    lines.append("=" * 60)
    lines.append(f"报告生成时间: {datetime.now().isoformat()}")
    lines.append("=" * 60)

    return "\n".join(lines)
