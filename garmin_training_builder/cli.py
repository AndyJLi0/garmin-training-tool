"""Command-line interface for Garmin Training Builder."""

import argparse
import json
import os
import sys

from .client import GarminClient
from .plan_parser import parse_plan


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


def cmd_import(args):
    """Import workouts and schedule from a YAML plan."""
    session = load_session(args.session)
    client = GarminClient(
        session_cookie=session["session_cookie"],
        csrf_token=session["csrf_token"],
        extra_cookies=session.get("extra_cookies"),
    )

    print(f"Parsing plan: {args.plan}")
    workouts, schedule = parse_plan(args.plan)
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
        workouts, schedule = parse_plan(args.plan)
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

    session_cookie = input("Paste your session cookie value (starts with Fe26.2*): ").strip()
    if not session_cookie:
        print("Error: Session cookie is required.")
        sys.exit(1)

    csrf_token = input("Paste your connect-csrf-token value: ").strip()
    if not csrf_token:
        print("Error: CSRF token is required.")
        sys.exit(1)

    session_data = {
        "session_cookie": session_cookie,
        "csrf_token": csrf_token,
        "extra_cookies": {},
    }

    # Optional: additional cookies
    print()
    print("Optional: paste additional cookies (one per line, format: name=value)")
    print("Common ones: GARMIN-SSO-CUST-GUID, SESSIONID")
    print("Press Enter on empty line to finish:")
    while True:
        line = input("  ").strip()
        if not line:
            break
        if "=" in line:
            key, value = line.split("=", 1)
            session_data["extra_cookies"][key.strip()] = value.strip()

    output_path = args.output or "session.json"
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
    p_import.add_argument("plan", help="Path to YAML training plan file")
    p_import.add_argument("--no-schedule", action="store_true", help="Create workouts but don't schedule them")
    p_import.set_defaults(func=cmd_import)

    # validate command
    p_validate = subparsers.add_parser("validate", help="Validate a YAML plan without uploading")
    p_validate.add_argument("plan", help="Path to YAML training plan file")
    p_validate.set_defaults(func=cmd_validate)

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
