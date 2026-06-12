"""Parse YAML training plan files into workout definitions and schedules."""

import yaml
import datetime

from .workout_builder import (
    hr_zone_target,
    pace_target,
    no_target,
    time_condition,
    distance_condition,
    lap_button_condition,
    pace_to_ms,
    build_workout,
)


# Mapping from pace category to approximate HR zone (for HR-only mode)
_PACE_TO_HR_ZONE = {
    "recovery": 1,
    "easy": 2,
    "general_aerobic": 3,
    "lt": 4,
    "tempo": 4,
    "threshold": 4,
    "vo2max": 5,
    "speed": 5,
    "strides": 5,
    "race": 4,
}


# Default zone percentages of LTHR (lactate threshold heart rate)
_DEFAULT_ZONE_PCT = {
    1: (0.60, 0.72),
    2: (0.72, 0.82),
    3: (0.82, 0.89),
    4: (0.89, 0.96),
    5: (0.96, 1.06),
}


def compute_hr_zones(lthr):
    """Compute HR zone BPM ranges from lactate threshold heart rate."""
    zones = {}
    for zone, (low_pct, high_pct) in _DEFAULT_ZONE_PCT.items():
        zones[zone] = (round(lthr * low_pct), round(lthr * high_pct))
    return zones


def _resolve_target(target_def, paces, target_mode=None, hr_zones=None):
    """Resolve a target definition from YAML into a target dict."""
    if target_def is None or target_def == "none":
        return no_target()

    if isinstance(target_def, str):
        # Heart rate zone: "z1", "z2", etc.
        if target_def.startswith("z"):
            zone = int(target_def[1:])
            if hr_zones and zone in hr_zones:
                low_bpm, high_bpm = hr_zones[zone]
                return hr_zone_target(low_bpm, high_bpm)
            raise ValueError(
                f"HR zone {zone} referenced but no heart rate zones configured. "
                f"Run 'garmin-training-tool setup' and enter your LTHR, or add "
                f"\"lthr\" to session.json."
            )

        # Pace reference: "$easy", "$lt", etc.
        if target_def.startswith("$"):
            pace_name = target_def[1:]

            # HR-only mode: map pace names to HR zones
            if target_mode == "hr":
                zone = _PACE_TO_HR_ZONE.get(pace_name, 3)
                if hr_zones and zone in hr_zones:
                    low_bpm, high_bpm = hr_zones[zone]
                    return hr_zone_target(low_bpm, high_bpm)
                raise ValueError(
                    f"HR zone mode requires heart rate zones configured. "
                    f"Run 'garmin-training-tool setup' and enter your LTHR, or add "
                    f"\"lthr\" to session.json."
                )

            if pace_name not in paces:
                raise ValueError(
                    f"Unknown pace '{pace_name}'. Define it in session.json under "
                    f"\"paces\" or in the plan's paces section.\n"
                    f"  Currently defined: {list(paces.keys()) if paces else '(none)'}"
                )
            slow, fast = paces[pace_name]
            return pace_target(slow, fast)

        # Inline pace: "5:00-5:30"
        if "-" in target_def and ":" in target_def:
            if target_mode == "hr":
                if hr_zones and 3 in hr_zones:
                    low_bpm, high_bpm = hr_zones[3]
                    return hr_zone_target(low_bpm, high_bpm)
                raise ValueError(
                    f"HR zone mode requires heart rate zones configured. "
                    f"Run 'garmin-training-tool setup' and enter your LTHR, or add "
                    f"\"lthr\" to session.json."
                )
            slow, fast = target_def.split("-")
            return pace_target(slow.strip(), fast.strip())

    raise ValueError(f"Unknown target format: {target_def}")


def _resolve_condition(condition_def):
    """Resolve a condition definition from YAML into a condition dict."""
    if isinstance(condition_def, str):
        if condition_def == "lap":
            return lap_button_condition()

        # Time: "30s", "5min", "1:30"
        if condition_def.endswith("s"):
            return time_condition(int(condition_def[:-1]))
        if condition_def.endswith("min"):
            return time_condition(int(condition_def[:-3]) * 60)
        if ":" in condition_def and "m" not in condition_def:
            parts = condition_def.split(":")
            secs = int(parts[0]) * 60 + int(parts[1])
            return time_condition(secs)

        # Distance: "1000m", "5km", "5k"
        if condition_def.endswith("km"):
            return distance_condition(int(float(condition_def[:-2]) * 1000))
        if condition_def.endswith("k"):
            return distance_condition(int(float(condition_def[:-1]) * 1000))
        if condition_def.endswith("m"):
            return distance_condition(int(condition_def[:-1]))

    if isinstance(condition_def, (int, float)):
        return distance_condition(int(condition_def))

    raise ValueError(f"Unknown condition format: {condition_def}")


def _parse_steps(steps_yaml, paces, target_mode=None, hr_zones=None):
    """Parse a list of step definitions from YAML."""
    steps = []
    for step_def in steps_yaml:
        if isinstance(step_def, dict):
            step_type = list(step_def.keys())[0]

            # Repeat step
            if step_type.startswith("repeat"):
                count = int(step_type.replace("repeat", "").strip("() "))
                sub_steps = _parse_steps(step_def[step_type], paces, target_mode, hr_zones)
                steps.append(("repeat", count, sub_steps))
            else:
                # Regular step: warmup, cooldown, run, recovery
                details = step_def[step_type]
                if isinstance(details, dict):
                    condition = _resolve_condition(details.get("duration") or details.get("distance") or "lap")
                    target = _resolve_target(details.get("target"), paces, target_mode, hr_zones)
                elif isinstance(details, str):
                    parts = details.split()
                    condition = _resolve_condition(parts[0])
                    target = _resolve_target(parts[1] if len(parts) > 1 else None, paces, target_mode, hr_zones)
                else:
                    raise ValueError(f"Invalid step details: {details}")

                garmin_type = step_type
                if garmin_type == "run":
                    garmin_type = "interval"

                steps.append((garmin_type, condition, target))
        else:
            raise ValueError(f"Invalid step format: {step_def}")

    return steps


def parse_plan(yaml_path, race_date=None, user_paces=None, target_mode=None, lthr=None, hr_zones=None):
    """Parse a YAML training plan file.

    Args:
        yaml_path: Path to the YAML plan file.
        race_date: Optional race date (datetime.date). If provided and the plan
                   uses schedule_template, dates are computed backwards from race day.
        user_paces: Optional dict of user-defined paces from session.json.
                    Used as fallback when plan doesn't define its own paces.
        target_mode: Optional "hr" to convert all pace targets to HR zones instead.
        lthr: Optional lactate threshold heart rate (int). Used to compute zone BPM ranges.
        hr_zones: Optional pre-computed dict of {zone: (low_bpm, high_bpm)}.

    Returns:
        tuple: (workouts_dict, schedule_list)
            - workouts_dict: {name: garmin_payload}
            - schedule_list: [(date, workout_name), ...]
    """
    with open(yaml_path) as f:
        plan = yaml.safe_load(f)

    # Compute HR zones from LTHR or use provided zones
    if hr_zones is None and lthr:
        hr_zones = compute_hr_zones(lthr)

    # Parse pace definitions: plan paces override user paces
    paces = {}
    if user_paces:
        for name, value in user_paces.items():
            if isinstance(value, str) and "-" in value:
                slow, fast = value.split("-")
                paces[name] = (slow.strip(), fast.strip())
    if "paces" in plan:
        for name, value in plan["paces"].items():
            if isinstance(value, str) and "-" in value:
                slow, fast = value.split("-")
                paces[name] = (slow.strip(), fast.strip())
            else:
                raise ValueError(f"Pace '{name}' must be in format 'M:SS-M:SS' (slow-fast)")

    # Parse workout definitions
    workouts = {}
    if "workouts" in plan:
        for workout_name, steps_yaml in plan["workouts"].items():
            steps = _parse_steps(steps_yaml, paces, target_mode, hr_zones)
            workouts[workout_name] = build_workout(workout_name, steps)

    # Parse schedule
    schedule = []

    if "schedule_template" in plan:
        # Template-based schedule: weeks counted backwards from race day
        schedule = _parse_schedule_template(plan["schedule_template"], workouts, race_date)
    elif "schedule" in plan:
        # Fixed-date schedule
        start_date = plan["schedule"]["start"]
        if isinstance(start_date, str):
            start_date = datetime.date.fromisoformat(start_date)

        for day_offset, entry in enumerate(plan["schedule"]["days"]):
            date = start_date + datetime.timedelta(days=day_offset)
            if entry and entry.lower() != "rest":
                for workout_name in entry.split(","):
                    workout_name = workout_name.strip()
                    if workout_name not in workouts:
                        raise ValueError(
                            f"Scheduled workout '{workout_name}' not found in workouts section"
                        )
                    schedule.append((date, workout_name))

    return workouts, schedule


def _parse_schedule_template(template, workouts, race_date):
    """Parse a schedule_template (weeks before race) into dated schedule.

    The template has keys like week_12, week_11, ..., week_1.
    Week 1 is race week. Race day is the last day (Sunday) of week 1.
    Each week starts on Monday.
    """
    if race_date is None:
        return []

    if isinstance(race_date, str):
        race_date = datetime.date.fromisoformat(race_date)

    # Find the highest week number to determine plan length
    week_numbers = []
    for key in template:
        num = int(key.replace("week_", ""))
        week_numbers.append(num)
    week_numbers.sort(reverse=True)
    total_weeks = week_numbers[0]

    # Race day is the last day of week_1 (Sunday)
    # Week 1 Monday = race_date - 6 days (if race is Sunday)
    # More generally: find the Monday of race week
    # race_date.weekday(): 0=Mon, 6=Sun
    race_week_monday = race_date - datetime.timedelta(days=race_date.weekday())

    # Week 1 starts at race_week_monday
    # Week N starts at race_week_monday - (N-1)*7 days
    schedule = []

    for week_num in sorted(week_numbers, reverse=True):
        key = f"week_{week_num}"
        days = template[key]
        weeks_before_race_week = week_num - 1
        week_monday = race_week_monday - datetime.timedelta(weeks=weeks_before_race_week)

        for day_offset, entry in enumerate(days):
            if entry and entry.lower() != "rest":
                date = week_monday + datetime.timedelta(days=day_offset)
                for workout_name in entry.split(","):
                    workout_name = workout_name.strip()
                    if workout_name not in workouts:
                        raise ValueError(
                            f"Scheduled workout '{workout_name}' (week {week_num}, "
                            f"day {day_offset+1}) not found in workouts section"
                        )
                    schedule.append((date, workout_name))

    schedule.sort(key=lambda x: x[0])
    return schedule
