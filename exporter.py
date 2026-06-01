"""Export runtime logs as JSON or raw text.

Reads all rotated log files (music-dl.log + .1/.2/.3 backups).
"""
import re
import json
from pathlib import Path
from typing import Optional, List, Dict, Union

from logger import LOG_DIR

LOG_FILE = LOG_DIR / "music-dl.log"
LOG_GLOB = "music-dl.log*"


def _read_all_lines(date: Optional[str] = None) -> List[str]:
    """Read lines from all log files (current + rotated), optionally filtered by date."""
    lines: List[str] = []
    for log_path in sorted(LOG_DIR.glob(LOG_GLOB)):
        try:
            content = log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in content.split("\n"):
            line = line.strip()
            if not line:
                continue
            if date and not line.startswith(date):
                continue
            lines.append(line)
    return lines


def get_log_stats() -> dict:
    """Return log statistics across all rotated log files."""
    stats: Dict[str, int] = {"total_lines": 0, "errors": 0, "warnings": 0, "file_size_bytes": 0}
    for log_path in LOG_DIR.glob(LOG_GLOB):
        try:
            stats["file_size_bytes"] += log_path.stat().st_size
            for line in log_path.read_text(encoding="utf-8", errors="replace").split("\n"):
                if not line.strip():
                    continue
                stats["total_lines"] += 1
                level = _extract_level(line)
                if level == "ERROR":
                    stats["errors"] += 1
                elif level == "WARNING":
                    stats["warnings"] += 1
        except OSError:
            continue
    return stats


def export_logs(format: str = "json", date: Optional[str] = None) -> Union[List[dict], str]:
    """Export logs in JSON (list of parsed entries) or TXT (raw text).

    Args:
        format: "json" or "txt". Invalid formats default to json.
        date: ISO date string like "2026-06-01". If None, exports all logs.
    """
    lines = _read_all_lines(date=date)

    if not lines:
        return [] if format == "json" else ""

    if format == "txt":
        return "\n".join(lines)

    # JSON format: parse each line into structured dict
    entries: List[dict] = []
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


def _extract_level(line: str) -> Optional[str]:
    """Extract log level from a formatted log line using the same regex as export."""
    m = re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \[(\w+)\s*\]", line)
    return m.group(1) if m else None
