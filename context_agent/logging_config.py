from __future__ import annotations

import logging


def configure_logging(level: int = logging.INFO) -> None:
    """配置应用日志。"""

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    for logger_name in ("mcp_agent", "mcp"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = False
        logger.setLevel(logging.CRITICAL)