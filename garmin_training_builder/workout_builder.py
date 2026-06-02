"""Build Garmin Connect running workout payloads from simple definitions."""


RUNNING_SPORT_TYPE = {"sportTypeId": 1, "sportTypeKey": "running"}

STEP_TYPES = {
    "warmup": {"stepTypeId": 1, "stepTypeKey": "warmup"},
    "cooldown": {"stepTypeId": 2, "stepTypeKey": "cooldown"},
    "interval": {"stepTypeId": 3, "stepTypeKey": "interval"},
    "recovery": {"stepTypeId": 4, "stepTypeKey": "recovery"},
    "repeat": {"stepTypeId": 6, "stepTypeKey": "repeat"},
}


def pace_to_ms(pace_str):
    """Convert 'M:SS' pace per km to meters/second."""
    parts = pace_str.split(":")
    total_seconds = int(parts[0]) * 60 + int(parts[1])
    return 1000.0 / total_seconds


# === Target builders ===

def hr_zone_target(zone):
    return {
        "targetType": {"workoutTargetTypeId": 4, "workoutTargetTypeKey": "heart.rate.zone"},
        "targetValueOne": zone,
        "targetValueTwo": zone,
    }


def pace_target(slow_pace, fast_pace):
    """Create pace target. Paces in 'M:SS' per km format (slow is the easier pace)."""
    return {
        "targetType": {"workoutTargetTypeId": 6, "workoutTargetTypeKey": "pace.zone"},
        "targetValueOne": pace_to_ms(slow_pace),
        "targetValueTwo": pace_to_ms(fast_pace),
    }


def no_target():
    return {
        "targetType": {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target"},
        "targetValueOne": None,
        "targetValueTwo": None,
    }


# === End condition builders ===

def time_condition(seconds):
    return {
        "endCondition": {"conditionTypeId": 2, "conditionTypeKey": "time"},
        "endConditionValue": seconds,
    }


def distance_condition(meters):
    return {
        "endCondition": {"conditionTypeId": 3, "conditionTypeKey": "distance"},
        "endConditionValue": meters,
        "preferredEndConditionUnit": {"unitKey": "kilometer"},
    }


def lap_button_condition():
    return {
        "endCondition": {"conditionTypeId": 1, "conditionTypeKey": "lap.button"},
        "endConditionValue": None,
    }


# === Step builders ===

def _build_step(step_type, condition, target, order):
    s = {
        "type": "ExecutableStepDTO",
        "stepId": order,
        "stepOrder": order,
        "stepType": STEP_TYPES[step_type],
    }
    s.update(condition)
    s.update(target)
    return s


def _build_repeat(iterations, steps, order, child_step_id):
    return {
        "type": "RepeatGroupDTO",
        "stepId": order,
        "stepOrder": order,
        "stepType": STEP_TYPES["repeat"],
        "childStepId": child_step_id,
        "numberOfIterations": iterations,
        "workoutSteps": steps,
        "smartRepeat": False,
    }


def build_workout(name, steps_def):
    """Build a Garmin workout payload from a step definition list.

    Each step is a tuple: ("step_type", condition_dict, target_dict)
    Repeats are: ("repeat", iterations, [sub_steps])
    """
    order = [0]

    def next_order():
        order[0] += 1
        return order[0]

    def build_steps(steps_list):
        result = []
        for s in steps_list:
            if s[0] == "repeat":
                _, iterations, sub_steps = s
                rep_order = next_order()
                child_id = order[0] + 1
                built_sub = build_steps(sub_steps)
                result.append(_build_repeat(iterations, built_sub, rep_order, child_id))
            else:
                step_type, condition, target = s
                result.append(_build_step(step_type, condition, target, next_order()))
        return result

    workout_steps = build_steps(steps_def)

    return {
        "workoutName": name,
        "sportType": RUNNING_SPORT_TYPE,
        "workoutSegments": [{
            "segmentOrder": 1,
            "sportType": RUNNING_SPORT_TYPE,
            "workoutSteps": workout_steps,
        }],
    }
