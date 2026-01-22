#!/usr/bin/env python3
"""
Recalculate scheduled_time for approved images.

Usage example:
  WF_DATABASE_URL=... python Scripts/recalculate_schedule.py \
    --images-per-day 8 \
    --window-start 09:00 \
    --window-end 21:00 \
    --timezone America/Los_Angeles

Optional environment defaults:
  WF_IMAGES_PER_DAY / IMAGES_PER_DAY / POSTS_PER_DAY
  WF_POSTING_WINDOW_START / POSTING_WINDOW_START
  WF_POSTING_WINDOW_END / POSTING_WINDOW_END
  WF_TIMEZONE / TZ
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_DIR = os.path.join(ROOT_DIR, "services", "api")
sys.path.insert(0, API_DIR)

from app.database import SessionLocal  # noqa: E402
from app.models import RunImage, RunImageStatus  # noqa: E402

ENV_IMAGES_PER_DAY = ("WF_IMAGES_PER_DAY", "IMAGES_PER_DAY", "POSTS_PER_DAY")
ENV_WINDOW_START = ("WF_POSTING_WINDOW_START", "POSTING_WINDOW_START")
ENV_WINDOW_END = ("WF_POSTING_WINDOW_END", "POSTING_WINDOW_END")
ENV_TIMEZONE = ("WF_TIMEZONE", "TZ")


def _get_first_env(keys: tuple[str, ...]) -> tuple[str | None, str | None]:
    for key in keys:
        value = os.getenv(key)
        if value:
            return value, key
    return None, None


def _parse_time(value: str) -> time:
    try:
        parsed = time.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid time '{value}'. Expected HH:MM or HH:MM:SS."
        ) from exc
    if parsed.tzinfo is not None:
        raise argparse.ArgumentTypeError("Time values must not include timezone offsets.")
    return parsed


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid date '{value}'. Expected YYYY-MM-DD."
        ) from exc


def _normalize_dt(value: datetime, tz: ZoneInfo | None) -> datetime:
    if tz is None:
        return value.replace(tzinfo=None) if value.tzinfo else value
    if value.tzinfo is None:
        return value.replace(tzinfo=tz)
    return value.astimezone(tz)


def _infer_window(images: list[RunImage], tz: ZoneInfo | None) -> tuple[time, time]:
    times: list[time] = []
    for image in images:
        if image.scheduled_time is None:
            continue
        local_dt = _normalize_dt(image.scheduled_time, tz)
        times.append(time(local_dt.hour, local_dt.minute, local_dt.second))
    if not times:
        raise ValueError("No scheduled times available to infer a window.")
    min_time = min(times)
    max_time = max(times)
    if min_time == max_time:
        raise ValueError(
            "Unable to infer window from schedule. Provide --window-start/--window-end."
        )
    return min_time, max_time


def _window_duration_seconds(window_start: time, window_end: time) -> float:
    base_day = date(2000, 1, 1)
    start_dt = datetime.combine(base_day, window_start)
    end_dt = datetime.combine(base_day, window_end)
    if end_dt <= start_dt:
        raise ValueError("Window end must be later than window start.")
    return (end_dt - start_dt).total_seconds()


def _build_schedule(
    images: list[RunImage],
    *,
    images_per_day: int,
    start_date: date,
    window_start: time,
    window_end: time,
    tz: ZoneInfo | None,
) -> list[datetime]:
    window_seconds = _window_duration_seconds(window_start, window_end)
    interval_seconds = window_seconds / images_per_day
    new_times: list[datetime] = []
    for index, _image in enumerate(images):
        day_offset = index // images_per_day
        slot_index = index % images_per_day
        current_day = start_date + timedelta(days=day_offset)
        if tz is None:
            window_start_dt = datetime.combine(current_day, window_start)
        else:
            window_start_dt = datetime.combine(current_day, window_start, tzinfo=tz)
        scheduled_dt = window_start_dt + timedelta(
            seconds=interval_seconds * slot_index
        )
        new_times.append(scheduled_dt.replace(microsecond=0))
    return new_times


def _format_time(t: time) -> str:
    return t.strftime("%H:%M:%S")


def _format_dt(dt: datetime) -> str:
    if dt.tzinfo is None:
        return dt.isoformat(sep=" ")
    return dt.isoformat()


def main() -> None:
    env_images_value, env_images_key = _get_first_env(ENV_IMAGES_PER_DAY)
    env_window_start, env_window_start_key = _get_first_env(ENV_WINDOW_START)
    env_window_end, env_window_end_key = _get_first_env(ENV_WINDOW_END)
    env_timezone, env_timezone_key = _get_first_env(ENV_TIMEZONE)

    parser = argparse.ArgumentParser(
        description="Recalculate scheduled_time for approved images."
    )
    parser.add_argument(
        "--images-per-day",
        type=int,
        default=None,
        help="Images to post per day.",
    )
    parser.add_argument(
        "--window-start",
        type=_parse_time,
        default=None,
        help="Posting window start (HH:MM or HH:MM:SS).",
    )
    parser.add_argument(
        "--window-end",
        type=_parse_time,
        default=None,
        help="Posting window end (HH:MM or HH:MM:SS).",
    )
    parser.add_argument(
        "--timezone",
        type=str,
        default=None,
        help="Timezone (IANA name). Defaults to existing schedule timezone.",
    )
    parser.add_argument(
        "--start-date",
        type=_parse_date,
        default=None,
        help="Start scheduling from this date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the recalculated schedule without updating the database.",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=5,
        help="Number of sample rows to print.",
    )

    args = parser.parse_args()

    images_per_day = args.images_per_day
    images_source = "args"
    if images_per_day is None:
        if env_images_value is not None:
            images_per_day = int(env_images_value)
            images_source = f"env({env_images_key})"
        else:
            images_per_day = None
    if images_per_day is None or images_per_day <= 0:
        raise SystemExit(
            "images-per-day is required and must be > 0 "
            f"(env checked: {', '.join(ENV_IMAGES_PER_DAY)})."
        )

    session = SessionLocal()
    try:
        stmt = (
            select(RunImage)
            .where(
                RunImage.status == RunImageStatus.APPROVED,
                RunImage.scheduled_time.is_not(None),
            )
            .order_by(RunImage.scheduled_time.asc(), RunImage.id.asc())
        )
        images = session.execute(stmt).scalars().all()
        if not images:
            print("No approved scheduled images found.")
            return

        tz: ZoneInfo | None = None
        timezone_source = "naive"
        if args.timezone:
            tz = ZoneInfo(args.timezone)
            timezone_source = "args"
        elif env_timezone:
            tz = ZoneInfo(env_timezone)
            timezone_source = f"env({env_timezone_key})"
        elif images[0].scheduled_time and images[0].scheduled_time.tzinfo:
            tz = images[0].scheduled_time.tzinfo
            timezone_source = "existing schedule"

        window_start = args.window_start
        window_end = args.window_end
        if window_start or window_end:
            if not (window_start and window_end):
                raise SystemExit(
                    "Both --window-start and --window-end are required when "
                    "overriding the window."
                )
            window_source = "args"
        elif env_window_start or env_window_end:
            if not (env_window_start and env_window_end):
                raise SystemExit(
                    "Both window start/end env values are required. "
                    f"Checked: {', '.join(ENV_WINDOW_START + ENV_WINDOW_END)}."
                )
            window_source = f"env({env_window_start_key},{env_window_end_key})"
            window_start = _parse_time(env_window_start)
            window_end = _parse_time(env_window_end)
        else:
            window_source = "inferred"
            window_start, window_end = _infer_window(images, tz)

        if window_start is None or window_end is None:
            raise SystemExit(
                "Posting window start/end are required. "
                "Use --window-start/--window-end or set env defaults."
            )

        if args.start_date:
            start_date = args.start_date
            start_source = "args"
        else:
            first_dt = _normalize_dt(images[0].scheduled_time, tz)
            start_date = first_dt.date()
            start_source = "first scheduled date"

        new_times = _build_schedule(
            images,
            images_per_day=images_per_day,
            start_date=start_date,
            window_start=window_start,
            window_end=window_end,
            tz=tz,
        )

        interval_seconds = (
            _window_duration_seconds(window_start, window_end) / images_per_day
        )
        interval_minutes = interval_seconds / 60.0

        print(f"Found {len(images)} approved scheduled images.")
        print(
            "Scheduling {count}/day between {start}-{end} "
            "({interval:.2f} min spacing).".format(
                count=images_per_day,
                start=_format_time(window_start),
                end=_format_time(window_end),
                interval=interval_minutes,
            )
        )
        if tz:
            print(f"Timezone: {tz} ({timezone_source})")
        else:
            print(f"Timezone: naive ({timezone_source})")
        print(f"Images per day source: {images_source}")
        print(f"Window source: {window_source}")
        print(f"Start date source: {start_source} ({start_date.isoformat()})")

        sample_count = min(args.sample, len(images))
        if sample_count > 0:
            print("Sample schedule:")
            for image, new_time in zip(images[:sample_count], new_times[:sample_count]):
                old_time = image.scheduled_time
                old_str = _format_dt(_normalize_dt(old_time, tz)) if old_time else "None"
                new_str = _format_dt(new_time)
                print(f"  {image.id}: {old_str} -> {new_str}")

        if args.dry_run:
            print("Dry run enabled; no database updates applied.")
            return

        for image, new_time in zip(images, new_times):
            image.scheduled_time = new_time

        session.commit()
        print(f"Updated scheduled_time for {len(images)} images.")
    except Exception as exc:
        session.rollback()
        print(f"Error: {exc}")
        raise SystemExit(1) from exc
    finally:
        session.close()


if __name__ == "__main__":
    main()
