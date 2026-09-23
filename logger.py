"""JSONL logger for DeFi yield scoring results."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


class JSONLLogger:
    """Append-only JSONL logger for scoring runs."""

    def __init__(self, path: str = "data/scores.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, record: Dict[str, Any]) -> None:
        """Append a single JSON record to the log."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **record,
        }
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")

    def log_batch(self, records: List[Dict[str, Any]]) -> int:
        """Append multiple records. Returns count written."""
        ts = datetime.now(timezone.utc).isoformat()
        with open(self.path, "a", encoding="utf-8") as f:
            for rec in records:
                entry = {"timestamp": ts, **rec}
                f.write(json.dumps(entry, default=str) + "\n")
        return len(records)

    def read_all(self) -> List[Dict[str, Any]]:
        """Read all logged records."""
        if not self.path.exists():
            return []
        records = []
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records

    def read_last(self, n: int = 10) -> List[Dict[str, Any]]:
        """Read the last N records efficiently."""
        if not self.path.exists():
            return []
        with open(self.path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        records = []
        for line in lines[-n:]:
            line = line.strip()
            if line:
                records.append(json.loads(line))
        return records

    def clear(self) -> None:
        """Truncate the log file."""
        self.path.write_text("")
