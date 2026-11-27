"""Parse and dispatch local vector-store maintenance subcommands."""

from __future__ import annotations

import argparse

from tools.vectors import purge_noise, snr


def main(argv: list[str] | None = None) -> int:
    """Dispatch a required subcommand and return its exit code."""
    parser = argparse.ArgumentParser(
        prog="vectors",
        description="Inspect and maintain a local vector store.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    snr.add_arguments(subparsers.add_parser(
        "snr", help="Inspect SNR and optionally delete below a chosen cut.",
    ))
    purge_noise.add_arguments(subparsers.add_parser(
        "purge-noise", help="Preview or purge noise-shaped vectors.",
    ))
    args = parser.parse_args(argv)
    if args.command == "snr":
        if args.execute and args.max_snr is None:
            parser.error("snr --execute requires --max-snr")
        return snr.run(args.path, args.label, args.max_snr, args.execute)
    return purge_noise.run(args.path, args.label, args.execute)
