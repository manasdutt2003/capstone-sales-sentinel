"""Configuration loading and validation (SPEC R-ING-01, R-OPS-02)."""
from __future__ import annotations

import datetime as dt
import hashlib
import os
import tomllib
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

ENV_INPUT = "SALES_SENTINEL_INPUT"
ENV_OUTPUT = "SALES_SENTINEL_OUTPUT_DIR"

DEFAULT_CATEGORIES = ("Electronics", "Clothing", "Grocery")
DEFAULT_WEIGHTS = {"completeness": 0.30, "validity": 0.30, "consistency": 0.15, "uniqueness": 0.25}


class ConfigError(Exception):
    """Invalid configuration -> exit code 2."""


@dataclass
class Config:
    input_path: Path | None = None
    output_dir: Path | None = None
    date_order: str = "MDY"
    business_date: dt.date | None = None
    max_age_days: int = 7
    future_tolerance_days: int = 0
    max_amount: Decimal = Decimal("100000.00")
    missing_strategy: str = "group_median"
    min_group_size: int = 3
    outlier_z: float = 3.5
    dedupe_policy: str = "content"
    burst_threshold: int = 5
    categories: tuple[str, ...] = DEFAULT_CATEGORIES
    category_aliases: dict[str, str] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    max_quarantine_rate: float = 0.10
    min_score: float = 60.0
    source_path: Path | None = None
    source_sha256: str = ""

    def validate(self) -> "Config":
        if self.date_order not in ("MDY", "DMY"):
            raise ConfigError(f"dates.order must be MDY or DMY, got {self.date_order!r}")
        if self.missing_strategy not in ("group_median", "quarantine"):
            raise ConfigError(
                f"amounts.missing_strategy must be group_median or quarantine, got {self.missing_strategy!r}"
            )
        if self.dedupe_policy not in ("content", "id"):
            raise ConfigError(f"dedupe.policy must be content or id, got {self.dedupe_policy!r}")
        if self.max_age_days < 0 or self.future_tolerance_days < 0:
            raise ConfigError("dates.max_age_days and future_tolerance_days must be >= 0")
        if self.max_amount <= 0:
            raise ConfigError("amounts.max_amount must be > 0")
        if self.min_group_size < 1:
            raise ConfigError("amounts.min_group_size must be >= 1")
        if self.burst_threshold < 2:
            raise ConfigError("dedupe.burst_threshold must be >= 2")
        if not self.categories:
            raise ConfigError("domain.categories must not be empty")
        canon = {c.casefold() for c in self.categories}
        for alias, target in self.category_aliases.items():
            if target.casefold() not in canon:
                raise ConfigError(f"category alias {alias!r} points to unknown category {target!r}")
        if set(self.weights) != set(DEFAULT_WEIGHTS):
            raise ConfigError(f"scoring.weights must have exactly {sorted(DEFAULT_WEIGHTS)}")
        if any(w < 0 for w in self.weights.values()) or abs(sum(self.weights.values()) - 1.0) > 1e-6:
            raise ConfigError("scoring.weights must be non-negative and sum to 1.0")
        return self

    def effective(self) -> dict[str, Any]:
        """JSON-serialisable view for the run manifest."""
        return {
            "date_order": self.date_order,
            "business_date": self.business_date.isoformat() if self.business_date else None,
            "max_age_days": self.max_age_days,
            "future_tolerance_days": self.future_tolerance_days,
            "max_amount": str(self.max_amount),
            "missing_strategy": self.missing_strategy,
            "min_group_size": self.min_group_size,
            "outlier_z": self.outlier_z,
            "dedupe_policy": self.dedupe_policy,
            "burst_threshold": self.burst_threshold,
            "categories": list(self.categories),
            "category_aliases": dict(self.category_aliases),
            "weights": dict(self.weights),
            "max_quarantine_rate": self.max_quarantine_rate,
            "min_score": self.min_score,
        }


def parse_business_date(value: str | None) -> dt.date | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return dt.date.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise ConfigError(f"business date must be YYYY-MM-DD, got {value!r}") from exc


def _get(data: dict, section: str, key: str, default: Any) -> Any:
    sec = data.get(section, {})
    if not isinstance(sec, dict):
        raise ConfigError(f"[{section}] must be a table")
    return sec.get(key, default)


def load_config(path: Path | None) -> Config:
    """Load a TOML config. ``None`` -> built-in defaults (no paths)."""
    cfg = Config()
    if path is None:
        return cfg.validate()
    path = Path(path)
    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        raise ConfigError(f"cannot read config {path}: {exc.strerror or exc}") from exc
    try:
        data = tomllib.loads(raw_bytes.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise ConfigError(f"invalid TOML in {path}: {exc}") from exc

    base = path.resolve().parent
    inp = _get(data, "paths", "input", None)
    out = _get(data, "paths", "output_dir", None)
    cfg.input_path = (base / inp).resolve() if inp else None
    cfg.output_dir = (base / out).resolve() if out else None

    try:
        cfg.date_order = str(_get(data, "dates", "order", cfg.date_order)).upper()
        cfg.business_date = parse_business_date(_get(data, "dates", "business_date", ""))
        cfg.max_age_days = int(_get(data, "dates", "max_age_days", cfg.max_age_days))
        cfg.future_tolerance_days = int(_get(data, "dates", "future_tolerance_days", cfg.future_tolerance_days))
        cfg.max_amount = Decimal(str(_get(data, "amounts", "max_amount", cfg.max_amount)))
        cfg.missing_strategy = str(_get(data, "amounts", "missing_strategy", cfg.missing_strategy))
        cfg.min_group_size = int(_get(data, "amounts", "min_group_size", cfg.min_group_size))
        cfg.outlier_z = float(_get(data, "amounts", "outlier_z", cfg.outlier_z))
        cfg.dedupe_policy = str(_get(data, "dedupe", "policy", cfg.dedupe_policy))
        cfg.burst_threshold = int(_get(data, "dedupe", "burst_threshold", cfg.burst_threshold))
        domain = data.get("domain", {})
        cfg.categories = tuple(domain.get("categories", cfg.categories))
        cfg.category_aliases = {str(k): str(v) for k, v in domain.get("category_aliases", {}).items()}
        weights = data.get("scoring", {}).get("weights")
        if weights is not None:
            cfg.weights = {str(k): float(v) for k, v in weights.items()}
        cfg.max_quarantine_rate = float(_get(data, "quality_gate", "max_quarantine_rate", cfg.max_quarantine_rate))
        cfg.min_score = float(_get(data, "quality_gate", "min_score", cfg.min_score))
    except (TypeError, ValueError, InvalidOperation) as exc:
        raise ConfigError(f"invalid value in {path}: {exc}") from exc

    cfg.source_path = path.resolve()
    cfg.source_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    return cfg.validate()


def resolve_path(cli_value: str | None, env_name: str, config_value: Path | None) -> Path | None:
    """CLI > environment > config (R-ING-01). CLI/env relative paths resolve against CWD."""
    if cli_value:
        return Path(cli_value).expanduser().resolve()
    env_value = os.environ.get(env_name, "").strip()
    if env_value:
        return Path(env_value).expanduser().resolve()
    return config_value
