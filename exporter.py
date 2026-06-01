"""Export runtime logs as JSON or raw text."""
import re
import json
from pathlib import Path
from typing import Optional, List, Dict, Union

from logger import LOG_DIR

LOG_FILE = LOG_DIR / "music-dl.log"


def get_log_stats() -> dict:
    """Return log statistics: total_lines, errors, warnings, file_size."""
    stats = {"total_lines": 0, "errors": 0, "warnings": 0, "file_size_bytes": 0}
    if not LOG_FILE.exists():
        return stats
    stats["file_size_bytes"] = LOG_FILE.stat().st_size
    content = LOG_FILE.read_text(encoding="utf-8", errors="replace")
    lines = content.strip().split("\n") if content.strip() else []
    stats["total_lines"] = len(lines)
    for line in lines:
        if "[ERROR]" in line:
            stats["errors"] += 1
        elif "[WARNING]" in line:
            stats["warnings"] += 1
    return stats


def export_logs(format: str = "json", date: Optional[str] = None) -> Union[List[dict], str]:
    """Export logs in JSON (list of parsed entries) or TXT (raw text).

    Args:
        format: "json" or "txt"
        date: ISO date string like "2026-06-01". If None, exports all logs.
    """
    if not LOG_FILE.exists():
        return [] if format == "json" else ""

    content = LOG_FILE.read_text(encoding="utf-8", errors="replace")
    lines = content.strip().split("\n") if content.strip() else []

    # Filter by date if specified
    if date:
        lines = [l for l in lines if l.startswith(date)]

    if format == "txt":
        return "\n".join(lines)

    # JSON format: parse each line into structured dict
    entries = []
    log_pattern = re.compile(
        r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \[(\w+)\s*\] (\S+): (.*)$"
    )
    for line in lines:
        m = log_pattern.match(line)
        if m:
            entries.append({
                "timestamp": m.group(1),
                "level": m.group(2),
                "module": m.group(3),
                "message": m.group(4),
            })
        else:
            entries.append({"raw": line})
    return entries
