"""
jobs_config.py — Data-driven run plan for the content platform.

`jobs.yaml` lists every job (one channel of one show: module + channel + language
+ publishing/scheduling metadata). Adding a channel is a YAML edit, not a code
change. The engine iterates jobs; the gold module's CHANNEL_CONFIG is derived
from the gold jobs here for backward compatibility.

Tracker: PLAT-005 (jobs/shows config layer).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

JOBS_FILE = Path(os.environ.get("JOBS_CONFIG_FILE", Path(__file__).parent / "jobs.yaml"))

VALID_FORMATS = {"long", "short"}
_PLACEHOLDER_CHANNEL_ID = "UCxxxxxxxxxxxxxxxxx"


@dataclass
class Job:
    id: str
    module: str
    channel: str
    language: str
    region_name: str = ""
    youtube_token_file: str = ""
    channel_id: str = ""
    formats: list[str] = field(default_factory=lambda: ["long"])
    schedule: str | None = None
    enabled: bool = True
    video_style: str = "card"        # "card" (Ken Burns) or "avatar" (talking head)
    avatar_image: str | None = None  # portrait image path for video_style: avatar


def _load_raw(path=None) -> list[dict]:
    path = Path(path) if path else JOBS_FILE
    if not path.exists():
        raise FileNotFoundError(f"Jobs config not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    jobs = data.get("jobs")
    if not isinstance(jobs, list):
        raise ValueError(f"{path}: top-level 'jobs' must be a list")
    return jobs


def _parse_job(entry: dict, index: int) -> Job:
    if not isinstance(entry, dict):
        raise ValueError(f"Job #{index}: each job must be a mapping")
    required = ("id", "module", "channel", "language")
    missing = [k for k in required if not entry.get(k)]
    if missing:
        raise ValueError(f"Job #{index}: missing required field(s): {', '.join(missing)}")

    formats = entry.get("formats") or ["long"]
    bad = set(formats) - VALID_FORMATS
    if bad:
        raise ValueError(
            f"Job '{entry['id']}': invalid format(s) {sorted(bad)}; allowed: {sorted(VALID_FORMATS)}"
        )

    channel_id = entry.get("channel_id", "") or ""
    env = entry.get("channel_id_env")
    if env:
        channel_id = os.environ.get(env, "") or channel_id or _PLACEHOLDER_CHANNEL_ID

    return Job(
        id=str(entry["id"]),
        module=str(entry["module"]),
        channel=str(entry["channel"]),
        language=str(entry["language"]),
        region_name=str(entry.get("region_name", "")),
        youtube_token_file=str(entry.get("youtube_token_file", "")),
        channel_id=channel_id,
        formats=list(formats),
        schedule=entry.get("schedule"),
        enabled=bool(entry.get("enabled", True)),
        video_style=str(entry.get("video_style", "card")),
        avatar_image=entry.get("avatar_image"),
    )


def load_jobs(path=None) -> list[Job]:
    """Load and validate all jobs. Raises ValueError on malformed config."""
    jobs: list[Job] = []
    seen: set[str] = set()
    for i, entry in enumerate(_load_raw(path)):
        job = _parse_job(entry, i)
        if job.id in seen:
            raise ValueError(f"Duplicate job id '{job.id}' in jobs config")
        seen.add(job.id)
        jobs.append(job)
    return jobs


def jobs_for_module(module_key: str, *, enabled_only: bool = True, path=None) -> list[Job]:
    return [
        j for j in load_jobs(path)
        if j.module == module_key and (j.enabled or not enabled_only)
    ]


def get_job(job_id: str, path=None) -> Job:
    for j in load_jobs(path):
        if j.id == job_id:
            return j
    raise KeyError(f"Unknown job id '{job_id}'")


def channel_config_for_module(module_key: str, path=None) -> dict:
    """Build a legacy CHANNEL_CONFIG-shaped dict (channel -> meta) for a module.

    Keeps existing gold importers (config.CHANNEL_CONFIG) working unchanged while
    the underlying source of truth is jobs.yaml.
    """
    out: dict[str, dict] = {}
    for j in load_jobs(path):
        if j.module != module_key:
            continue
        out[j.channel] = {
            "language": j.language,
            "region_name": j.region_name,
            "channel_id": j.channel_id,
            "youtube_token_file": j.youtube_token_file,
            "enabled": j.enabled,
            "formats": j.formats,
        }
    return out
