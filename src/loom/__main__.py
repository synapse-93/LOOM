"""CLI entrypoint for running LOOM as a module (`python -m loom`)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loom import __version__
from loom.config.loader import load_config
from loom.config.models import LoomConfig
from loom.utils.logging import get_logger, setup_logging

logger = get_logger("loom.cli")


def main(argv: list[str] | None = None) -> int:
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        prog="loom",
        description="VIDEO2PRINT: Smartphone Video to 3D Printable Object",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"loom {__version__}",
    )
    parser.add_argument(
        "--config",
        "-c",
        type=Path,
        default=None,
        help="Path to YAML configuration file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration and stage prerequisites without executing compute.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity level.",
    )

    args = parser.parse_args(argv)
    setup_logging(level=args.log_level)

    logger.info("Initializing LOOM (version %s)", __version__)

    if args.config is not None:
        try:
            config = load_config(args.config)
            logger.info("Loaded configuration: '%s' from %s", config.name, args.config)
        except Exception as exc:
            logger.error("Failed to load configuration: %s", exc)
            return 1
    else:
        config = LoomConfig()
        logger.info("Using default scaffold configuration ('%s')", config.name)

    if args.dry_run:
        logger.info("Dry-run mode selected. Architecture scaffold verified successfully.")
        return 0

    logger.info(
        "Scaffold operational. Pipeline stages will be implemented incrementally across roadmap phases."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
