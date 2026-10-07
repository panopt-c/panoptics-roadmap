"""Persistent manual study/workout logging and JSON-ready dashboard snapshots.

Dates are calendar dates in the user's local OS timezone unless explicitly
provided. Audit timestamps are UTC. Retry a write with the same request_id to
avoid duplicate logs/rewards; a changed payload with that ID is an error.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
import json
import sqlite3
from uuid import uuid4

from .db import Database, clean_text, finite_number, json_text, player_state, positive_int, utc_now

COURSES = ("Algebra 2", "Trigonometry", "Precalculus", "Calculus 1", "Calculus 2", "Calculus 3", "Linear Algebra")
STUDY_XP_PER_MINUTE = 1
WORKOUT_XP_PER_MINUTE = 2
DAILY_STUDY_BONUS_XP = 100
WEIGHT_GOAL_XP = 250


def calendar_day(value: str | date | None = None) -> str:
    if value is None:
        return date.today().isoformat()
    if isinstance(value, datetime):
        raise ValueError("Use a calendar date, not a datetime")
    if isinstance(value, date):
        result = value
    elif isinstance(value, str):
        try:
            result = date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("Date must use YYYY-MM-DD") from exc
        if result.isoformat() != value:
            raise ValueError("Date must use YYYY-MM-DD")
    else:
        raise ValueError("Date must be a date or YYYY-MM-DD string")
    if result > date.today():
        raise ValueError("Completed activities cannot be logged in the future")
    return result.isoformat()


def _activity(row: sqlite3.Row) -> dict:
    result = dict(row)
    result["details"] = json.loads(result.pop("details_json"))
    return result


class Tracker:
    def __init__(self, db: Database, player_id: int):
        db.get_player(player_id)
        self.db, self.player_id = db, player_id

    def _request(self, conn: sqlite3.Connection, request_id: str | None, kind: str,
                 day: str, details: dict) -> tuple[str, dict | None]:
        key = str(uuid4()) if request_id is None else clean_text(request_id, "request_id", 200)
        existing = conn.execute("SELECT * FROM activity_logs WHERE player_id=? AND request_id=?", (self.player_id, key)).fetchone()
        if existing is not None:
            if existing["kind"] != kind or existing["log_date"] != day or existing["details_json"] != json_text(details):
                raise ValueError("request_id was already used with a different activity payload")
            return key, _activity(existing)
        return key, None

    def _insert(self, conn: sqlite3.Connection, key: str, kind: str, day: str, details: dict) -> str:
        log_id = str(uuid4())
        conn.execute("INSERT INTO activity_logs(id,player_id,request_id,kind,log_date,details_json,created_at) VALUES (?,?,?,?,?,?,?)",
                     (log_id, self.player_id, key, kind, day, json_text(details), utc_now()))
        return log_id

    def _milestone(self, conn: sqlite3.Connection, key: str, title: str, category: str, details: dict, xp: int) -> int:
        inserted = conn.execute("""INSERT INTO milestones(player_id,milestone_key,title,category,details_json,achieved_at)
            VALUES (?,?,?,?,?,?) ON CONFLICT(player_id,milestone_key) DO NOTHING""",
            (self.player_id, key, title, category, json_text(details), utc_now())).rowcount
        if inserted:
            self.db.award_xp_in(conn, self.player_id, xp, f"milestone:{key}")
            return xp
        return 0

    def _finish(self, conn: sqlite3.Connection, log_id: str, xp: int) -> dict:
        conn.execute("UPDATE activity_logs SET xp_awarded=? WHERE id=?", (xp, log_id))
        return _activity(conn.execute("SELECT * FROM activity_logs WHERE id=?", (log_id,)).fetchone())

    def _habit(self, conn: sqlite3.Connection, key: str, day: str, value: float, note: str = "") -> None:
        conn.execute("""INSERT INTO habit_logs(player_id,habit_key,log_date,value,note,updated_at) VALUES (?,?,?,?,?,?)
            ON CONFLICT(player_id,habit_key,log_date) DO UPDATE SET
            value=excluded.value,note=excluded.note,updated_at=excluded.updated_at""",
            (self.player_id, key, day, value, note, utc_now()))

    def log_study(self, course: str, minutes: int, *, topic: str = "", on_date: str | date | None = None,
                  request_id: str | None = None) -> dict:
        if course not in COURSES:
            raise ValueError(f"course must be one of: {', '.join(COURSES)}")
        positive_int(minutes, "minutes", 1440)
        topic = clean_text(topic, "topic", 2000, empty=True)
        day = calendar_day(on_date)
        details = dict(course=course, minutes=minutes, topic=topic)
        with self.db.transaction() as conn:
            player = self.db.require_player(conn, self.player_id)
            key, prior = self._request(conn, request_id, "study", day, details)
            if prior is not None:
                return prior
            total = conn.execute("""SELECT COALESCE(SUM(s.minutes),0) FROM study_sessions s
                JOIN activity_logs a ON a.id=s.log_id WHERE a.player_id=? AND a.log_date=?""", (self.player_id, day)).fetchone()[0] + minutes
            if total > 1440:
                raise ValueError("Study minutes cannot exceed 24 hours in one calendar day")
            log_id = self._insert(conn, key, "study", day, details)
            conn.execute("INSERT INTO study_sessions(log_id,course,minutes,topic) VALUES (?,?,?,?)", (log_id, course, minutes, topic))
            xp = minutes * STUDY_XP_PER_MINUTE
            self.db.award_xp_in(conn, self.player_id, xp, f"activity:{log_id}")
            self._habit(conn, "study_minutes", day, total)
            if total >= player["study_goal_minutes"]:
                xp += self._milestone(conn, f"study-goal:{day}", "Daily math objective complete", "study",
                                      dict(date=day, goal_minutes=player["study_goal_minutes"]), DAILY_STUDY_BONUS_XP)
            return self._finish(conn, log_id, xp)

    def log_workout(self, activity: str, minutes: int, *, sets: int | None = None,
                    reps: int | None = None, load_lbs: float | None = None,
                    distance_miles: float | None = None, note: str = "",
                    on_date: str | date | None = None, request_id: str | None = None) -> dict:
        activity = clean_text(activity, "activity")
        positive_int(minutes, "minutes", 1440)
        note = clean_text(note, "note", 2000, empty=True)
        for name, value in (("sets", sets), ("reps", reps)):
            if value is not None:
                positive_int(value, name)
        load = None if load_lbs is None else finite_number(load_lbs, "load_lbs")
        distance = None if distance_miles is None else finite_number(distance_miles, "distance_miles")
        day = calendar_day(on_date)
        details = dict(activity=activity, minutes=minutes, sets=sets, reps=reps, load_lbs=load, distance_miles=distance, note=note)
        with self.db.transaction() as conn:
            self.db.require_player(conn, self.player_id)
            key, prior = self._request(conn, request_id, "workout", day, details)
            if prior is not None:
                return prior
            total = conn.execute("""SELECT COALESCE(SUM(f.minutes),0) FROM fitness_logs f
                JOIN activity_logs a ON a.id=f.log_id WHERE a.player_id=? AND a.log_date=? AND f.kind='workout'""",
                (self.player_id, day)).fetchone()[0] + minutes
            if total > 1440:
                raise ValueError("Workout minutes cannot exceed 24 hours in one calendar day")
            log_id = self._insert(conn, key, "workout", day, details)
            conn.execute("INSERT INTO fitness_logs(log_id,kind,minutes) VALUES (?,'workout',?)", (log_id, minutes))
            xp = minutes * WORKOUT_XP_PER_MINUTE
            self.db.award_xp_in(conn, self.player_id, xp, f"activity:{log_id}")
            self._habit(conn, "workout_minutes", day, total)
            xp += self._milestone(conn, "first-workout", "Training protocol activated", "fitness", {}, 50)
            return self._finish(conn, log_id, xp)

    def log_weight(self, weight_lbs: float, *, on_date: str | date | None = None,
                   request_id: str | None = None) -> dict:
        weight = finite_number(weight_lbs, "weight_lbs", positive=True)
        day = calendar_day(on_date)
        details = dict(weight_lbs=weight)
        with self.db.transaction() as conn:
            player = self.db.require_player(conn, self.player_id)
            key, prior = self._request(conn, request_id, "weight", day, details)
            if prior is not None:
                return prior
            log_id = self._insert(conn, key, "weight", day, details)
            conn.execute("INSERT INTO fitness_logs(log_id,kind,weight_lbs) VALUES (?,'weight',?)", (log_id, weight))
            self._habit(conn, "weight_lbs", day, weight)
            # Sort by effective day, then insertion order, including backdated logs.
            weights = self._weights(conn)
            baseline, target = weights[0]["weight_lbs"], player["target_weight_lbs"]
            # A backfilled crossing still counts even after a later rebound.
            reached = any(row["weight_lbs"] == target
                          or (baseline > target and row["weight_lbs"] < target)
                          or (baseline < target and row["weight_lbs"] > target)
                          for row in weights)
            xp = 0
            if reached:
                xp = self._milestone(conn, f"weight-goal:{target:g}", "Weight objective reached", "fitness",
                                     dict(target_weight_lbs=target), WEIGHT_GOAL_XP)
            return self._finish(conn, log_id, xp)

    def set_habit(self, habit_key: str, value: float, *, note: str = "", on_date: str | date | None = None) -> None:
        key = clean_text(habit_key, "habit_key")
        if key in {"study_minutes", "workout_minutes", "weight_lbs"}:
            raise ValueError("This habit is maintained by activity logs")
        number = finite_number(value, "value")
        day = calendar_day(on_date)
        note = clean_text(note, "note", 2000, empty=True)
        with self.db.transaction() as conn:
            self.db.require_player(conn, self.player_id)
            self._habit(conn, key, day, number, note)

    def _weights(self, conn: sqlite3.Connection, through: str | None = None) -> list[dict]:
        return [dict(row) for row in conn.execute("""SELECT a.log_date,f.weight_lbs FROM fitness_logs f
            JOIN activity_logs a ON a.id=f.log_id WHERE a.player_id=? AND f.kind='weight' AND a.log_date<=?
            ORDER BY a.log_date,a.rowid""", (self.player_id, through or date.today().isoformat()))]

    def dashboard(self, on_date: str | date | None = None) -> dict:
        """One consistent snapshot for UI workers; all returned values are JSON-safe.

        XP/inventory/milestones are current; activity aggregates are through the
        selected day. A current streak includes yesterday until today's goal is met.
        """
        day = calendar_day(on_date)
        with self.db.transaction() as conn:
            player = player_state(self.db.require_player(conn, self.player_id))
            totals = {row[0]: row[1] for row in conn.execute("""SELECT a.log_date,SUM(s.minutes)
                FROM study_sessions s JOIN activity_logs a ON a.id=s.log_id
                WHERE a.player_id=? AND a.log_date<=? GROUP BY a.log_date""", (self.player_id, day))}
            courses = {course: 0 for course in COURSES}
            courses.update({row[0]: row[1] for row in conn.execute("""SELECT s.course,SUM(s.minutes)
                FROM study_sessions s JOIN activity_logs a ON a.id=s.log_id
                WHERE a.player_id=? AND a.log_date<=? GROUP BY s.course""", (self.player_id, day))})
            completed = {date.fromisoformat(d) for d, total in totals.items() if total >= player["study_goal_minutes"]}
            cursor = date.fromisoformat(day)
            if cursor not in completed:
                cursor = cursor - timedelta(days=1) if cursor > date.min else None
            streak = 0
            while cursor in completed:
                streak += 1
                if cursor == date.min:
                    break
                cursor -= timedelta(days=1)
            best, run, previous = 0, 0, None
            for d in sorted(completed):
                run = run + 1 if previous is not None and d - previous == timedelta(days=1) else 1
                best, previous = max(best, run), d
            weights = self._weights(conn, day)
            baseline = weights[0]["weight_lbs"] if weights else None
            latest = weights[-1]["weight_lbs"] if weights else None
            target = player["target_weight_lbs"]
            progress = None
            if baseline is not None:
                progress = (1.0 if latest == target else 0.0) if baseline == target else max(0.0, min(1.0, (latest-baseline)/(target-baseline)))
            today_minutes = totals.get(day, 0)
            fitness_minutes = conn.execute("""SELECT COALESCE(SUM(f.minutes),0) FROM fitness_logs f
                JOIN activity_logs a ON a.id=f.log_id WHERE a.player_id=? AND a.log_date=? AND f.kind='workout'""", (self.player_id, day)).fetchone()[0]
            milestones = [dict(id=r[0], key=r[1], title=r[2], category=r[3], achieved_at=r[4]) for r in conn.execute(
                "SELECT id,milestone_key,title,category,achieved_at FROM milestones WHERE player_id=? ORDER BY id", (self.player_id,))]
            inventory = [dict(item_key=r[0], quantity=r[1], metadata=json.loads(r[2])) for r in conn.execute(
                "SELECT item_key,quantity,metadata_json FROM inventory WHERE player_id=? ORDER BY item_key", (self.player_id,))]
            habits = [dict(habit_key=r[0], value=r[1], note=r[2]) for r in conn.execute(
                "SELECT habit_key,value,note FROM habit_logs WHERE player_id=? AND log_date=? ORDER BY habit_key", (self.player_id, day))]
            recent = [_activity(r) for r in conn.execute("SELECT * FROM activity_logs WHERE player_id=? AND log_date<=? ORDER BY log_date DESC,rowid DESC LIMIT 20", (self.player_id, day))]
            return dict(player=player, date=day,
                        study=dict(today_minutes=today_minutes, goal_minutes=player["study_goal_minutes"],
                                   remaining_minutes=max(0, player["study_goal_minutes"]-today_minutes),
                                   progress=min(1.0, today_minutes/player["study_goal_minutes"]),
                                   total_minutes=sum(totals.values()), course_minutes=courses,
                                   current_streak_days=streak, best_streak_days=best),
                        fitness=dict(today_workout_minutes=fitness_minutes, target_weight_lbs=target,
                                     baseline_weight_lbs=baseline, latest_weight_lbs=latest,
                                     weight_progress=progress, weight_history=weights),
                        inventory=inventory, habits=habits, milestones=milestones, recent_activity=recent)
