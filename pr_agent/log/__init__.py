import os
os.environ["AUTO_CAST_FOR_DYNACONF"] = "false"
import json
import logging
import sys
from enum import Enum

from loguru import logger

from pr_agent.config_loader import get_settings

try:
    from pr_agent.log.dashboard_sink import setup_dashboard_sink, get_dashboard_sink
except ImportError:
    # Dashboard sink is optional
    setup_dashboard_sink = None
    get_dashboard_sink = None


class LoggingFormat(str, Enum):
    CONSOLE = "CONSOLE"
    JSON = "JSON"


def json_format(record: dict) -> str:
    return record["message"]


def analytics_filter(record: dict) -> bool:
    return record.get("extra", {}).get("analytics", False)


def inv_analytics_filter(record: dict) -> bool:
    return not record.get("extra", {}).get("analytics", False)


def setup_logger(level: str = "INFO", fmt: LoggingFormat = LoggingFormat.CONSOLE):
    level: int = logging.getLevelName(level.upper())
    if type(level) is not int:
        level = logging.INFO

    if fmt == LoggingFormat.JSON and os.getenv("LOG_SANE", "0").lower() == "0":  # better debugging github_app
        logger.remove(None)
        logger.add(
            sys.stdout,
            filter=inv_analytics_filter,
            level=level,
            format="{message}",
            colorize=False,
            serialize=True,
        )
    elif fmt == LoggingFormat.CONSOLE: # does not print the 'extra' fields
        logger.remove(None)
        logger.add(sys.stdout, level=level, colorize=True, filter=inv_analytics_filter)

    log_folder = get_settings().get("CONFIG.ANALYTICS_FOLDER", "")
    if log_folder:
        pid = os.getpid()
        log_file = os.path.join(log_folder, f"pr-agent.{pid}.log")
        logger.add(
            log_file,
            filter=analytics_filter,
            level=level,
            format="{message}",
            colorize=False,
            serialize=True,
        )

    # Setup dashboard sink if configured
    if (setup_dashboard_sink and 
        (get_settings().get("DASHBOARD.URL") or get_settings().get("DASHBOARD.ENABLED"))):
        try:
            setup_dashboard_sink()
        except Exception as e:
            print(f"Failed to setup dashboard sink: {e}")

    return logger


def get_logger(*args, **kwargs):
    # Try to get contextual logger with job/operation context
    try:
        from pr_agent.log.job_context import get_contextual_logger
        return get_contextual_logger()
    except ImportError:
        # Fall back to regular logger if job_context is not available
        return logger
    except Exception:
        # Fall back to regular logger if context binding fails
        return logger
