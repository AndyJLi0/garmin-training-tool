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


def _resolve_target(target_def, paces):
    """Resolve a target definition from YAML into a target dict."""
    if target_def is None or target_def == "none":
        return no_target()

    if isinstance(target_def, str):
        # Heart rate zone: "z1", "z2", etc.
        if target_def.startswith("z"):
            zone = int(target_def[1:])
            return hr_zone_target(zone)

        # Pace reference: "$easy", "$lt", etc.
        if target_def.startswith("$"):
            pace_name = target_def[1:]
            if pace_name not in paces:
                raise ValueError(f"Unknown pace '{pace_name}'. Defined paces: {list(paces.keys())}")
            slow, fast = paces[pace_name]
            return pace_target(slow, fast)

        # Inline pace: "5:00-5:30"
        if "-" in target_def and ":" in target_def:
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


def _parse_steps(steps_yaml, paces):
    """Parse a list of step definitions from YAML."""
    steps = []
    for step_def in steps_yaml:
        if isinstance(step_def, dict):
            step_type = list(step_def.keys())[0]

            # Repeat step
            if step_type.startswith("repeat"):
                count = int(step_type.replace("repeat", "").strip("() "))
                sub_steps = _parse_steps(step_def[step_type], paces)
                steps.append(("repeat", count, sub_steps))
            else:
                # Regular step: warmup, cooldown, run, recovery
                details = step_def[step_type]
                if isinstance(details, dict):
                    condition = _resolve_condition(details.get("duration") or details.get("distance") or "lap")
                    target = _resolve_target(details.get("target"), paces)
                elif isinstance(details, str):
                    parts = details.split()
                    condition = _resolve_condition(parts[0])
                    target = _resolve_target(parts[1] if len(parts) > 1 else None, paces)
                else:
                    raise ValueError(f"Invalid step details: {details}")

                garmin_type = step_type
                if garmin_type == "run":
                    garmin_type = "interval"

                steps.append((garmin_type, condition, target))
        else:
            raise ValueError(f"Invalid step format: {step_def}")

    return steps


def parse_plan(yaml_path):
    """Parse a YAML training plan file.

    Returns:
        tuple: (workouts_dict, schedule_list)
            - workouts_dict: {name: garmin_payload}
            - schedule_list: [(date, workout_name), ...]
    """
    with open(yaml_path) as f:
        plan = yaml.safe_load(f)

    # Parse pace definitions
    paces = {}
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
            steps = _parse_steps(steps_yaml, paces)
            workouts[workout_name] = build_workout(workout_name, steps)

    # Parse schedule
    schedule = []
    if "schedule" in plan:
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
