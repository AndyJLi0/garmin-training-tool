"""Garmin Connect API client using browser session authentication."""

import requests


class GarminClient:
    """Client for Garmin Connect workout API using browser session cookies.

    Garmin uses Cloudflare TLS fingerprinting which blocks non-browser HTTP
    clients. This client works by reusing session cookies and CSRF token
    from an authenticated browser session.
    """

    API_BASE = "https://connect.garmin.com/gc-api/workout-service"

    def __init__(self, session_cookie, csrf_token, extra_cookies=None):
        self.cookies = {
            "session": session_cookie,
            "connect-csrf-token": csrf_token,
        }
        if extra_cookies:
            self.cookies.update(extra_cookies)

        self.headers = {
            "connect-csrf-token": csrf_token,
            "Content-Type": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/148.0.0.0 Safari/537.36"
            ),
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
        }

    def create_workout(self, workout_payload):
        """Create a workout on Garmin Connect. Returns the workout ID."""
        response = requests.post(
            f"{self.API_BASE}/workout",
            cookies=self.cookies,
            headers=self.headers,
            json=workout_payload,
        )
        response.raise_for_status()
        data = response.json()
        if not data or "workoutId" not in data:
            raise RuntimeError(
                f"Failed to create workout. Response: {response.text[:200]}. "
                "Your session may have expired - get fresh cookies from your browser."
            )
        return data["workoutId"]

    def schedule_workout(self, workout_id, date_str):
        """Schedule a workout on a specific date (YYYY-MM-DD format)."""
        response = requests.post(
            f"{self.API_BASE}/schedule/{workout_id}",
            cookies=self.cookies,
            headers=self.headers,
            json={"date": date_str},
        )
        response.raise_for_status()
        data = response.json()
        if not data:
            raise RuntimeError(
                f"Failed to schedule workout {workout_id} on {date_str}. "
                "Your session may have expired."
            )
        return data

    def list_workouts(self):
        """List all workouts on the account."""
        response = requests.get(
            f"{self.API_BASE}/workouts",
            cookies=self.cookies,
            headers=self.headers,
            params={"start": 1, "limit": 999, "myWorkoutsOnly": True},
        )
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list):
            return data
        return []

    def delete_workout(self, workout_id):
        """Delete a workout by ID."""
        response = requests.delete(
            f"{self.API_BASE}/workout/{workout_id}",
            cookies=self.cookies,
            headers=self.headers,
        )
        response.raise_for_status()
