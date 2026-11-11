"""Read the raw CSV defensively (SPEC R-ING-02 … R-ING-06)."""
from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass, field
from pathlib import Path

REQUIRED_COLUMNS = ("transaction_id", "date", "amount", "store_id", "category")
_ENCODINGS = ("utf-8-sig", "cp1252", "latin-1")


class IngestError(Exception):
    """Input cannot be processed at all -> exit code 2."""


@dataclass
class RawRow:
    line_no: int                      # physical line number in the file (header = 1)
    fields: dict[str, str]            # required column -> raw string ("" if absent)
    malformed: bool = False           # field count != header count


@dataclass
class IngestResult:
    rows: list[RawRow]
    encoding: str
    sha256: str
    blank_lines: int = 0
    extra_columns: list[str] = field(default_factory=list)


def _decode(data: bytes) -> tuple[str, str]:
    for enc in _ENCODINGS:
        try:
            return data.decode(enc), enc
        except UnicodeDecodeError:
            continue
    raise IngestError("could not decode input")  # unreachable: latin-1 decodes any byte


def read_csv(path: Path) -> IngestResult:
    path = Path(path)
    if not path.exists():
        raise IngestError(f"input file not found: {path}")
    if not path.is_file():
        raise IngestError(f"input path is not a file: {path}")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise IngestError(f"cannot read input {path}: {exc.strerror or exc}") from exc
    return parse_bytes(data)


def parse_bytes(data: bytes) -> IngestResult:
    if not data.strip():
        raise IngestError("input file is empty (no data rows)")
    text, encoding = _decode(data)
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header_raw = next(reader)
    except StopIteration:
        raise IngestError("input file is empty (no data rows)") from None
    except csv.Error as exc:
        raise IngestError(f"CSV error in header: {exc}") from exc

    header = [h.strip().lower() for h in header_raw]
    seen: set[str] = set()
    dupes = sorted({h for h in header if h in seen or seen.add(h)})
    if dupes:
        raise IngestError(f"duplicate column(s) in header: {', '.join(dupes)}")
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        raise IngestError(f"missing required column(s): {', '.join(missing)}")
    extra = [h for h in header if h not in REQUIRED_COLUMNS]
    index = {name: header.index(name) for name in REQUIRED_COLUMNS}

    rows: list[RawRow] = []
    blank = 0
    line_start = reader.line_num + 1
    try:
        for record in reader:
            line_no = line_start
            line_start = reader.line_num + 1
            if not record or all(cell.strip() == "" for cell in record):
                blank += 1
                continue
            fields = {name: (record[i] if i < len(record) else "") for name, i in index.items()}
            rows.append(RawRow(line_no=line_no, fields=fields, malformed=len(record) != len(header)))
    except csv.Error as exc:
        raise IngestError(f"CSV error near line {reader.line_num}: {exc}") from exc

    if not rows:
        raise IngestError("input has a header but no data rows")
    return IngestResult(
        rows=rows,
        encoding=encoding,
        sha256=hashlib.sha256(data).hexdigest(),
        blank_lines=blank,
        extra_columns=extra,
    )
