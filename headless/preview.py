"""Redacted preview artifacts.

Masking happens in `PreviewRecord.__post_init__`, before the record exists in
any other form, so no later code path can serialize a raw registry or secret
value (D6, FR-010, SC-002). Callers pass the raw value in at construction time;
what comes back out (`to_json()`, `write_artifacts`) never contains it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from headless.fields import redact


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


@dataclass
class PreviewRecord:
    errand: str
    mode: str
    url: str
    title: str
    handoff: str
    fields: list[dict] = field(default_factory=list)
    checks: list[dict] = field(default_factory=list)
    steps: list[dict] = field(default_factory=list)
    timestamp_utc: str = field(default_factory=_utc_timestamp)

    def __post_init__(self) -> None:
        masked_fields = []
        for entry in self.fields:
            source_kind = entry["source_kind"]
            raw_value = str(entry.get("value", ""))
            value_masked = raw_value if source_kind == "literal" else redact(raw_value)
            masked_fields.append(
                {
                    "name": entry["name"],
                    "selector": entry["selector"],
                    "source_kind": source_kind,
                    "value_masked": value_masked,
                }
            )
        self.fields = masked_fields
        self.checks = [{"selector": c["selector"], "found": bool(c["found"])} for c in self.checks]
        # Walk framework (v0.0.5): steps holds only {"kind", "name"} entries
        # for non-FieldPlan steps (ClickStep/HumanStep/CaptureStep) - never
        # a selector, an instruction string, or an extractor mapping. A
        # HumanStep's own instruction text is deliberately withheld here
        # even though a FieldPlan's selector is already recorded in clear
        # text elsewhere: an instruction could describe what a page shows in
        # enough detail to leak page content into a persisted file, so
        # name-only is the safer default (data-model.md).
        self.steps = [{"kind": s["kind"], "name": s["name"]} for s in self.steps]

    def to_json(self) -> str:
        payload = {
            "errand": self.errand,
            "mode": self.mode,
            "url": self.url,
            "title": self.title,
            "timestamp_utc": self.timestamp_utc,
            "handoff": self.handoff,
            "fields": self.fields,
            "checks": self.checks,
            "steps": self.steps,
        }
        return json.dumps(payload, indent=2)


def write_artifacts(
    record: PreviewRecord, screenshot_png: bytes | None, preview_dir: Path
) -> tuple[Path | None, Path]:
    """Write `<errand>-<timestamp_utc>.json` (always) and `.png` under
    `preview_dir`, creating it. `screenshot_png=None` (config.screenshots=False,
    `--no-screenshot`) writes only the JSON; the PNG path is then None."""
    preview_dir = Path(preview_dir)
    preview_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{record.errand}-{record.timestamp_utc}"
    json_path = preview_dir / f"{stem}.json"
    json_path.write_text(record.to_json(), encoding="utf-8")

    png_path = None
    if screenshot_png is not None:
        png_path = preview_dir / f"{stem}.png"
        png_path.write_bytes(screenshot_png)
    return png_path, json_path
