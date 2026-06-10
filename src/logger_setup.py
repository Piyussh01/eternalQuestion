"""
Structured logging setup for Deep Thought 2.0.

Outputs to:
- Console (rich formatting with colors)
- File (JSON structured logs)
- Leaderboard file (periodic snapshots)
"""

import json
import logging
import sys
import time
from pathlib import Path


class JSONFormatter(logging.Formatter):
    """Emit structured JSON log lines for machine parsing."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


class ConsoleFormatter(logging.Formatter):
    """Rich console formatting with phase/component prefixes."""

    COLORS = {
        "DEBUG": "\033[37m",      # Gray
        "INFO": "\033[32m",       # Green
        "WARNING": "\033[33m",    # Yellow
        "ERROR": "\033[31m",      # Red
        "CRITICAL": "\033[1;31m", # Bold red
    }
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Component-specific colors
    COMPONENT_COLORS = {
        "[COMPARE]": "\033[35m",  # Magenta
        "[JUDGE]": "\033[33m",    # Yellow
        "[EXPAND]": "\033[34m",   # Blue
        "[LEADER]": "\033[32m",   # Green
        "[SYSTEM]": "\033[37m",   # White
        "[PHASE]": "\033[1;36m",  # Bold cyan
        "[ITER": "\033[96m",      # Bright cyan
        "[LLM": "\033[90m",       # Dark gray
        "[HERMES]": "\033[95m",   # Bright magenta
        "[TOURNAMENT]": "\033[1;33m",  # Bold yellow
    }

    def format(self, record: logging.LogRecord) -> str:
        timestamp = time.strftime("%H:%M:%S", time.localtime(record.created))
        level_color = self.COLORS.get(record.levelname, "")
        msg = record.getMessage()

        # Apply component-specific colors
        for prefix, color in self.COMPONENT_COLORS.items():
            if prefix in msg:
                msg = msg.replace(prefix, f"{color}{prefix}{self.RESET}")
                break

        line = f"{self.DIM}{timestamp}{self.RESET} {level_color}{record.levelname:>7}{self.RESET} {msg}"

        if record.exc_info and record.exc_info[0]:
            line += f"\n{self.formatException(record.exc_info)}"

        return line


def setup_logging(log_dir: str = "logs", level: int = logging.INFO):
    """Configure logging for the entire application."""
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger("deep-thought")
    root.setLevel(level)

    # Avoid duplicate handlers on re-init
    root.handlers.clear()

    # Console handler (human-readable)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(ConsoleFormatter())
    root.addHandler(console)

    # File handler (structured JSON)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    file_handler = logging.FileHandler(log_path / f"deep_thought_{timestamp}.jsonl")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(JSONFormatter())
    root.addHandler(file_handler)

    # Suppress noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    root.info("[SYSTEM] Logging initialized: console + %s", file_handler.baseFilename)
