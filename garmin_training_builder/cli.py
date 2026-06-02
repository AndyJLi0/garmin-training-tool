"""Command-line interface for Garmin Training Builder."""

import argparse
import datetime
import json
import os
import sys

from .client import GarminClient
from .plan_parser import parse_plan
from .presets import list_presets, get_preset_path


def load_session(session_path=None):
    """Load session credentials from file."""
    if session_path is None:
        session_path = os.path.join(os.getcwd(), "session.json")

    if not os.path.exists(session_path):
        print(f"Error: Session file not found at '{session_path}'")
        print()
        print("To get started, run:")
        print("  garmin-training-builder setup")
        print()
        print("Or create session.json manually (see README).")
        sys.exit(1)

    with open(session_path) as f:
        session = json.load(f)

    required = ["session_cookie", "csrf_token"]
    for key in required:
        if key not in session:
            print(f"Error: Missing '{key}' in session.json")
            sys.exit(1)

    return session


def _resolve_plan_path(plan_arg):
    """Resolve a plan argument to a file path (could be a preset name or file path)."""
    if os.path.exists(plan_arg):
        return plan_arg
    try:
        return get_preset_path(plan_arg)
    except ValueError:
        pass
    print(f"Error: '{plan_arg}' is not a file path or a known preset.")
    print(f"\nAvailable presets:")
    for name in list_presets():
        print(f"  - {name}")
    sys.exit(1)


def cmd_import(args):
    """Import workouts and schedule from a YAML plan."""
    session = load_session(args.session)
    client = GarminClient(
        session_cookie=session["session_cookie"],
        csrf_token=session["csrf_token"],
        extra_cookies=session.get("extra_cookies"),
    )

    plan_path = _resolve_plan_path(args.plan)
    race_date = None
    if args.race_date:
        race_date = datetime.date.fromisoformat(args.race_date)

    print(f"Parsing plan: {plan_path}")
    if race_date:
        print(f"Race date: {race_date}")
    workouts, schedule = parse_plan(plan_path, race_date=race_date)
    print(f"Found {len(workouts)} workouts, {len(schedule)} scheduled days")

    # Create workouts
    print("\n=== CREATING WORKOUTS ===")
    workout_ids = {}
    for name, payload in workouts.items():
        print(f"  Creating: {name}...", end=" ", flush=True)
        try:
            workout_id = client.create_workout(payload)
            workout_ids[name] = workout_id
            print(f"OK (id={workout_id})")
        except Exception as e:
            print(f"FAILED ({e})")

    print(f"\nCreated {len(workout_ids)}/{len(workouts)} workouts")

    if not schedule:
        print("\nNo schedule defined. Done!")
        return

    # Schedule workouts
    if args.no_schedule:
        print("\nSkipping scheduling (--no-schedule flag).")
        return

    print("\n=== SCHEDULING WORKOUTS ===")
    scheduled = 0
    for date, workout_name in schedule:
        if workout_name not in workout_ids:
            print(f"  SKIP {date}: '{workout_name}' was not created")
            continue

        date_str = date.isoformat()
        print(f"  {date_str}: {workout_name}...", end=" ", flush=True)
        try:
            client.schedule_workout(workout_ids[workout_name], date_str)
            scheduled += 1
            print("OK")
        except Exception as e:
            print(f"FAILED ({e})")

    print(f"\nScheduled {scheduled}/{len(schedule)} workouts")
    print("\nDone! Check your Garmin Connect calendar.")


def cmd_list(args):
    """List existing workouts on Garmin Connect."""
    session = load_session(args.session)
    client = GarminClient(
        session_cookie=session["session_cookie"],
        csrf_token=session["csrf_token"],
        extra_cookies=session.get("extra_cookies"),
    )

    workouts = client.list_workouts()
    if not workouts:
        print("No workouts found.")
        return

    print(f"Found {len(workouts)} workouts:\n")
    for w in workouts:
        print(f"  {w['workoutId']:>12}  {w['workoutName']}")


def cmd_validate(args):
    """Validate a YAML plan without uploading."""
    try:
        plan_path = _resolve_plan_path(args.plan)
        race_date = None
        if args.race_date:
            race_date = datetime.date.fromisoformat(args.race_date)

        workouts, schedule = parse_plan(plan_path, race_date=race_date)
        print(f"Plan is valid!")
        print(f"  Workouts: {len(workouts)}")
        print(f"  Scheduled days: {len(schedule)}")
        if schedule:
            print(f"  Date range: {schedule[0][0]} to {schedule[-1][0]}")
        print("\nWorkouts defined:")
        for name in workouts:
            steps = workouts[name]["workoutSegments"][0]["workoutSteps"]
            print(f"  - {name} ({len(steps)} steps)")
    except Exception as e:
        print(f"Validation failed: {e}")
        sys.exit(1)


def cmd_presets(args):
    """List available preset training plans."""
    import yaml
    presets = list_presets()
    if not presets:
        print("No presets available.")
        return

    print("Available preset training plans:\n")
    for name in presets:
        path = get_preset_path(name)
        with open(path) as f:
            plan = yaml.safe_load(f)
        meta = plan.get("meta", {})
        desc = meta.get("description", "")
        level = meta.get("level", "")
        weeks = meta.get("weeks", "?")
        distance = meta.get("distance", "")
        print(f"  {name}")
        print(f"    {desc}")
        print(f"    Distance: {distance} | Weeks: {weeks} | Level: {level}")
        print()

    print("Usage:")
    print("  garmin-training-builder import <preset-name> --race-date YYYY-MM-DD")
    print()
    print("Example:")
    print("  garmin-training-builder import pfitz-half-12-47 --race-date 2026-09-13")


def cmd_setup(args):
    """Interactive setup to create session.json."""
    print("=" * 60)
    print("  Garmin Training Builder - Session Setup")
    print("=" * 60)
    print()
    print("This tool needs your browser session cookies to authenticate")
    print("with Garmin Connect. Follow these steps:")
    print()
    print("1. Open https://connect.garmin.com in Chrome/Firefox")
    print("2. Log in to your account")
    print("3. Open Developer Tools (F12 or Cmd+Option+I)")
    print("4. Go to the Network tab")
    print("5. Navigate to the Workouts page")
    print("6. Find a request to a URL containing 'workout-service'")
    print("7. In the Request Headers, find these values:")
    print()
    print("   - 'cookie' header -> the 'session=Fe26.2*...' value")
    print("   - 'connect-csrf-token' header -> the CSRF token")
    print()
    print("=" * 60)
    print()
    print("Because cookie values contain special characters (* ! etc.),")
    print("pasting them directly can cause shell issues.")
    print()
    print("RECOMMENDED: Create session.json manually by pasting into a file:")
    print()

    output_path = args.output or "session.json"
    example_path = output_path + ".example"

    print(f'  1. Copy session.json.example to {output_path}')
    print(f'  2. Open {output_path} in a text editor')
    print(f'  3. Replace the placeholder values with your real values')
    print()
    print("Alternatively, paste your values here (press Enter twice to skip).")
    print()

    print("CSRF Token (short UUID like cc526168-e8b9-4b6f-...): ")
    csrf_token = ""
    try:
        csrf_token = input("> ").strip()
    except (EOFError, KeyboardInterrupt):
        print()

    if not csrf_token:
        print()
        print(f"No input received. Please create {output_path} manually.")
        print(f"See session.json.example for the format.")
        sys.exit(0)

    print()
    print("Session cookie (the long Fe26.2*... value):")
    print("TIP: Paste it into a temp file and provide the path, OR paste directly.")
    print("     If pasting directly, press Enter when done.")
    print()

    session_cookie = ""
    try:
        line = input("> ").strip()
        if os.path.isfile(line):
            with open(line) as f:
                session_cookie = f.read().strip()
            print(f"  Read cookie from file: {line}")
        else:
            session_cookie = line
    except (EOFError, KeyboardInterrupt):
        print()

    if not session_cookie:
        print("Error: Session cookie is required.")
        sys.exit(1)

    # Clean up - remove "session=" prefix if they copied the whole cookie header
    if session_cookie.startswith("session="):
        session_cookie = session_cookie[len("session="):]
    # Trim at semicolon if they pasted multiple cookies
    if ";" in session_cookie:
        session_cookie = session_cookie.split(";")[0].strip()

    session_data = {
        "session_cookie": session_cookie,
        "csrf_token": csrf_token,
        "extra_cookies": {},
    }

    with open(output_path, "w") as f:
        json.dump(session_data, f, indent=2)

    print(f"\nSession saved to: {output_path}")
    print("You can now run: garmin-training-builder import your_plan.yaml")


def main():
    parser = argparse.ArgumentParser(
        prog="garmin-training-builder",
        description="Create and schedule running workouts on Garmin Connect from YAML plans",
    )
    parser.add_argument(
        "--session", "-s",
        help="Path to session.json (default: ./session.json)",
    )
    subparsers = parser.add_subparsers(dest="command")

    # import command
    p_import = subparsers.add_parser("import", help="Import a training plan to Garmin Connect")
    p_import.add_argument("plan", help="Path to YAML plan file, or a preset name (see 'presets' command)")
    p_import.add_argument("--race-date", "-r", help="Race date (YYYY-MM-DD). Required for preset plans.")
    p_import.add_argument("--no-schedule", action="store_true", help="Create workouts but don't schedule them")
    p_import.set_defaults(func=cmd_import)

    # validate command
    p_validate = subparsers.add_parser("validate", help="Validate a YAML plan without uploading")
    p_validate.add_argument("plan", help="Path to YAML plan file, or a preset name")
    p_validate.add_argument("--race-date", "-r", help="Race date (YYYY-MM-DD). Required for preset plans.")
    p_validate.set_defaults(func=cmd_validate)

    # presets command
    p_presets = subparsers.add_parser("presets", help="List available preset training plans")
    p_presets.set_defaults(func=cmd_presets)

    # list command
    p_list = subparsers.add_parser("list", help="List workouts on your Garmin Connect account")
    p_list.set_defaults(func=cmd_list)

    # setup command
    p_setup = subparsers.add_parser("setup", help="Interactive setup to create session.json")
    p_setup.add_argument("--output", "-o", help="Output path for session.json")
    p_setup.set_defaults(func=cmd_setup)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
