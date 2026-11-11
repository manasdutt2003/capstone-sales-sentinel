"""Command-line entry point and exit-code policy (SPEC R-OPS-01 … 04)."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import ENV_INPUT, ENV_OUTPUT, ConfigError, load_config, parse_business_date, resolve_path
from .ingest import IngestError, read_csv
from .pipeline import InvariantError, run_pipeline
from .report import write_outputs
from .scoring import money, score

EXIT_OK, EXIT_INVARIANT, EXIT_INPUT, EXIT_GATE = 0, 1, 2, 3

# Project root = two levels above this package (src/sentinel -> src -> root); never an absolute literal.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "pipeline.toml"

log = logging.getLogger("sentinel")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sales-sentinel", description="Ledger-first cleaning of daily sales CSVs.")
    p.add_argument("--input", "-i", help=f"input CSV (default: ${ENV_INPUT} or config paths.input)")
    p.add_argument("--output-dir", "-o", help=f"output directory (default: ${ENV_OUTPUT} or config paths.output_dir)")
    p.add_argument("--config", "-c", help="TOML config (default: config/pipeline.toml)")
    p.add_argument("--business-date", help="override business date YYYY-MM-DD")
    p.add_argument("--dedupe-policy", choices=("content", "id"), help="override dedupe.policy")
    p.add_argument("--missing-strategy", choices=("group_median", "quarantine"), help="override amounts.missing_strategy")
    p.add_argument("--strict", action="store_true", help="exit 3 if the quality gate fails")
    p.add_argument("--quiet", "-q", action="store_true", help="only print errors")
    return p


def _fail(code: int, message: str) -> int:
    print(f"ERROR: {message}", file=sys.stderr)
    return code


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.WARNING if args.quiet else logging.INFO,
                        format="%(levelname)s %(message)s", stream=sys.stderr)
    try:
        config_path = Path(args.config).resolve() if args.config else (DEFAULT_CONFIG if DEFAULT_CONFIG.exists() else None)
        cfg = load_config(config_path)
        if args.business_date:
            cfg.business_date = parse_business_date(args.business_date)
        if args.dedupe_policy:
            cfg.dedupe_policy = args.dedupe_policy
        if args.missing_strategy:
            cfg.missing_strategy = args.missing_strategy
        cfg.validate()
        input_path = resolve_path(args.input, ENV_INPUT, cfg.input_path)
        output_dir = resolve_path(args.output_dir, ENV_OUTPUT, cfg.output_dir)
        if input_path is None:
            raise ConfigError("no input given (use --input, $SALES_SENTINEL_INPUT or paths.input)")
        if output_dir is None:
            raise ConfigError("no output dir given (use --output-dir, $SALES_SENTINEL_OUTPUT_DIR or paths.output_dir)")
        ingest = read_csv(input_path)
    except (ConfigError, IngestError) as exc:
        return _fail(EXIT_INPUT, str(exc))

    log.info("read %d rows from %s (%s)", len(ingest.rows), input_path.name, ingest.encoding)
    try:
        result = run_pipeline(ingest.rows, cfg)
        sc, mo = score(result), money(result)
        if not mo.balanced:
            raise InvariantError("money does not reconcile")
    except InvariantError as exc:
        return _fail(EXIT_INVARIANT, f"invariant violated: {exc}")

    try:
        write_outputs(output_dir, result, ingest, sc, mo, input_path)
    except OSError as exc:
        return _fail(EXIT_INPUT, f"cannot write outputs to {output_dir}: {exc.strerror or exc}")

    n = len(result.records)
    q_rate = len(result.quarantined) / n
    if not args.quiet:
        print(f"OK processed={n} kept={len(result.kept)} duplicates={len(result.duplicates)} "
              f"quarantined={len(result.quarantined)} nulls_filled={len(result.imputed)} "
              f"score={sc.overall:.1f}({sc.grade}) -> {output_dir}")
    if args.strict and (q_rate > cfg.max_quarantine_rate or sc.overall < cfg.min_score):
        return _fail(EXIT_GATE, f"quality gate failed: quarantine_rate={q_rate:.1%} "
                                f"(max {cfg.max_quarantine_rate:.0%}), score={sc.overall:.1f} (min {cfg.min_score:.0f})")
    return EXIT_OK
