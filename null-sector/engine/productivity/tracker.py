"""Persistent manual study/workout logging and JSON-ready dashboard snapshots.

Dates are calendar dates in the user's local OS timezone unless explicitly
provided. Audit timestamps are UTC. Retry a write with the same request_id to
avoid duplicate logs/rewards; a changed payload with that ID is an error. A retry
that omits on_date reuses the day the original was filed under, so a retry that
lands after midnight still matches.

Weight goal: the first measurement ever logged (insertion order) fixes the goal
direction (lose or gain toward the target). Backfilling older measurements never
flips it. The baseline shown is the earliest-dated measurement on the starting side
of the target, and only measurements dated on or after that baseline can reach the
goal, so old history logged later can never award the goal by itself.

Armory: every milestone may drop one item (see ITEM_DROPS). Drops are recorded in
`item_grants`, so each milestone drops exactly once, also for milestones that
existed before items did.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
import json
import sqlite3
from uuid import uuid4

from .db import Database, bounded_number, clean_text, finite_number, json_text, player_state, utc_now

COURSES = ("Algebra 2", "Trigonometry", "Precalculus", "Calculus 1", "Calculus 2", "Calculus 3", "Linear Algebra")
STUDY_XP_PER_MINUTE = 1
WORKOUT_XP_PER_MINUTE = 2
DAILY_STUDY_BONUS_XP = 100
WEIGHT_GOAL_XP = 250
STREAK_MILESTONES = (3, 7, 30)        # consecutive completed study days; no XP, an Armory item each
RECENT_MILESTONES = 20                # snapshots carry the newest N milestones plus per-category counts

# One limit table, shared with the browser form (client/js/ui/screens/productivity.js LIMITS).
# Optional fields are omitted (or null) when not measured; 0 sets/reps is not a measurement.
LIMITS = {
    "minutes": (1, 1440),
    "sets": (1, 1000),
    "reps": (1, 10000),
    "load_lbs": (0, 2000),
    "distance_miles": (0, 500),
    "weight_lbs": (50, 800),
}

# milestone key prefix -> (item_key, metadata). Stackable drops share an item_key.
ITEM_DROPS = {
    "study-goal:": ("focus_chip", {"name": "Focus Chip", "rarity": "uncommon", "icon": "◈",
                                   "description": "Compiled from a completed daily math objective."}),
    "study-streak:3": ("overclock_module", {"name": "Overclock Module", "rarity": "rare", "icon": "⚡",
                                            "description": "Three straight days of completed math objectives."}),
    "study-streak:7": ("neural_lattice", {"name": "Neural Lattice", "rarity": "epic", "icon": "✦",
                                          "description": "A full week of completed math objectives."}),
    "study-streak:30": ("core_key", {"name": "Core Key", "rarity": "legendary", "icon": "⬢",
                                     "description": "Thirty straight days of completed math objectives."}),
    "first-workout": ("training_wraps", {"name": "Training Wraps", "rarity": "common", "icon": "▣",
                                         "description": "Issued when your training protocol activated."}),
    "weight-goal:": ("target_lock", {"name": "Target Lock", "rarity": "legendary", "icon": "◎",
                                     "description": "Your weight objective, reached."}),
    "coding:": ("breach_shard", {"name": "Breach Shard", "rarity": "uncommon", "icon": "◆",
                                 "description": "Recovered from a cleared coding mission."}),
}


def item_for(milestone_key: str) -> tuple[str, dict] | None:
    """The Armory item a milestone drops, or None."""
    exact = ITEM_DROPS.get(milestone_key)
    if exact is not None:
        return exact
    for prefix, drop in ITEM_DROPS.items():
        if prefix.endswith(":") and milestone_key.startswith(prefix):
            return drop
    return None


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


def _limited_int(value, name: str) -> int:
    low, high = LIMITS[name]
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        hint = " (leave it empty if you did not count it)" if name in ("sets", "reps") else ""
        raise ValueError(f"{name} must be an integer between {low} and {high}{hint}")
    return value


def _limited_number(value, name: str, unit: str = "") -> float:
    low, high = LIMITS[name]
    return bounded_number(value, name, low, high, unit)


def _activity(row: sqlite3.Row) -> dict:
    result = dict(row)
    result["details"] = json.loads(result.pop("details_json"))
    return result


def _goal_side(weight: float, target: float, direction: int) -> bool:
    """True when `weight` has reached the target in the goal's direction."""
    if direction < 0:
        return weight <= target
    if direction > 0:
        return weight >= target
    return weight == target


def _start_side(weight: float, target: float, direction: int) -> bool:
    """True when `weight` is on the side of the target the goal starts from."""
    if direction < 0:
        return weight > target
    if direction > 0:
        return weight < target
    return True


def weight_goal(rows: list[dict], target: float) -> dict:
    """Direction, baseline and goal state from weigh-ins (each: log_date, weight_lbs, created_at, rowid).

    `rows` must be in chronological order (log_date, then insertion). The direction
    comes from the first measurement ever logged, which never changes.
    """
    if not rows:
        return dict(direction=0, baseline=None, reached=False)
    first = min(rows, key=lambda r: (r["created_at"], r["rowid"]))
    direction = (target > first["weight_lbs"]) - (target < first["weight_lbs"])
    baseline = next((r for r in rows if _start_side(r["weight_lbs"], target, direction)), first)
    reached = any(r["log_date"] >= baseline["log_date"] and _goal_side(r["weight_lbs"], target, direction)
                  for r in rows)
    return dict(direction=direction, baseline=baseline, reached=reached)


class Tracker:
    def __init__(self, db: Database, player_id: int):
        db.get_player(player_id)
        self.db, self.player_id = db, player_id

    def _request(self, conn: sqlite3.Connection, request_id: str | None, kind: str,
                 day: str, details: dict, explicit_day: bool = True) -> tuple[str, dict | None]:
        key = str(uuid4()) if request_id is None else clean_text(request_id, "request_id", 200)
        existing = conn.execute("SELECT * FROM activity_logs WHERE player_id=? AND request_id=?", (self.player_id, key)).fetchone()
        if existing is not None:
            # Without an explicit on_date the day was only a default: the original filing wins,
            # so a retry that arrives after midnight still matches its first attempt.
            same_day = existing["log_date"] == day or not explicit_day
            if existing["kind"] != kind or not same_day or existing["details_json"] != json_text(details):
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
        if inserted and xp > 0:
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

    def _completed_days(self, conn: sqlite3.Connection, goal: int, through: str | None = None) -> set[date]:
        rows = conn.execute("""SELECT a.log_date,SUM(s.minutes) FROM study_sessions s
            JOIN activity_logs a ON a.id=s.log_id WHERE a.player_id=? AND a.log_date<=? GROUP BY a.log_date""",
            (self.player_id, through or "9999-12-31"))
        return {date.fromisoformat(d) for d, total in rows if total >= goal}

    def _streak_milestones(self, conn: sqlite3.Connection, day: str, goal: int) -> None:
        """Record streak milestones for the run of completed days that contains `day` (backfills can join runs)."""
        completed = self._completed_days(conn, goal)
        anchor = date.fromisoformat(day)
        if anchor not in completed:
            return
        start = end = anchor
        while start > date.min and start - timedelta(days=1) in completed:
            start -= timedelta(days=1)
        while end < date.max and end + timedelta(days=1) in completed:
            end += timedelta(days=1)
        length = (end - start).days + 1
        for days in STREAK_MILESTONES:
            if length >= days:
                self._milestone(conn, f"study-streak:{days}", f"{days}-day study streak", "study",
                                dict(days=days), 0)

    def log_study(self, course: str, minutes: int, *, topic: str = "", on_date: str | date | None = None,
                  request_id: str | None = None) -> dict:
        if course not in COURSES:
            raise ValueError(f"course must be one of: {', '.join(COURSES)}")
        _limited_int(minutes, "minutes")
        topic = clean_text(topic, "topic", 2000, empty=True)
        day = calendar_day(on_date)
        details = dict(course=course, minutes=minutes, topic=topic)
        with self.db.transaction() as conn:
            player = self.db.require_player(conn, self.player_id)
            key, prior = self._request(conn, request_id, "study", day, details, on_date is not None)
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
                self._streak_milestones(conn, day, player["study_goal_minutes"])
            return self._finish(conn, log_id, xp)

    def log_workout(self, activity: str, minutes: int, *, sets: int | None = None,
                    reps: int | None = None, load_lbs: float | None = None,
                    distance_miles: float | None = None, note: str = "",
                    on_date: str | date | None = None, request_id: str | None = None) -> dict:
        activity = clean_text(activity, "activity")
        _limited_int(minutes, "minutes")
        note = clean_text(note, "note", 2000, empty=True)
        for name, value in (("sets", sets), ("reps", reps)):
            if value is not None:
                _limited_int(value, name)
        load = None if load_lbs is None else _limited_number(load_lbs, "load_lbs", "lb")
        distance = None if distance_miles is None else _limited_number(distance_miles, "distance_miles", "miles")
        day = calendar_day(on_date)
        details = dict(activity=activity, minutes=minutes, sets=sets, reps=reps, load_lbs=load, distance_miles=distance, note=note)
        with self.db.transaction() as conn:
            self.db.require_player(conn, self.player_id)
            key, prior = self._request(conn, request_id, "workout", day, details, on_date is not None)
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
        weight = _limited_number(weight_lbs, "weight_lbs", "lb")
        day = calendar_day(on_date)
        details = dict(weight_lbs=weight)
        with self.db.transaction() as conn:
            player = self.db.require_player(conn, self.player_id)
            key, prior = self._request(conn, request_id, "weight", day, details, on_date is not None)
            if prior is not None:
                return prior
            log_id = self._insert(conn, key, "weight", day, details)
            conn.execute("INSERT INTO fitness_logs(log_id,kind,weight_lbs) VALUES (?,'weight',?)", (log_id, weight))
            self._habit(conn, "weight_lbs", day, weight)
            target = player["target_weight_lbs"]
            # A backfilled crossing after the baseline still counts even after a later rebound;
            # history from before the baseline (or a backfill that would flip the direction) never does.
            xp = 0
            if weight_goal(self._weight_rows(conn), target)["reached"]:
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

    def grant_items(self) -> list[dict]:
        """Drop the Armory item of every milestone that has not dropped one yet. Returns the new drops."""
        granted = []
        with self.db.transaction() as conn:
            self.db.require_player(conn, self.player_id)
            pending = conn.execute("""SELECT m.id,m.milestone_key FROM milestones m
                LEFT JOIN item_grants g ON g.milestone_id=m.id
                WHERE m.player_id=? AND g.milestone_id IS NULL ORDER BY m.id""", (self.player_id,)).fetchall()
            for milestone_id, milestone_key in pending:
                drop = item_for(milestone_key)
                item_key = drop[0] if drop else None
                conn.execute("INSERT INTO item_grants(milestone_id,item_key,granted_at) VALUES (?,?,?)",
                             (milestone_id, item_key, utc_now()))
                if drop is None:
                    continue
                metadata = drop[1]
                conn.execute("""INSERT INTO inventory(player_id,item_key,quantity,metadata_json) VALUES (?,?,1,?)
                    ON CONFLICT(player_id,item_key) DO UPDATE SET quantity=inventory.quantity+1""",
                             (self.player_id, item_key, json_text(metadata)))
                granted.append(dict(item_key=item_key, quantity=1, metadata=dict(metadata),
                                    milestone_key=milestone_key))
        return granted

    def _weight_rows(self, conn: sqlite3.Connection, through: str | None = None) -> list[dict]:
        """Weigh-ins in chronological order (effective day, then insertion order)."""
        return [dict(row) for row in conn.execute("""SELECT a.log_date,f.weight_lbs,a.created_at,a.rowid AS rowid
            FROM fitness_logs f JOIN activity_logs a ON a.id=f.log_id
            WHERE a.player_id=? AND f.kind='weight' AND a.log_date<=?
            ORDER BY a.log_date,a.created_at,a.rowid""", (self.player_id, through or "9999-12-31"))]

    def _weights(self, conn: sqlite3.Connection, through: str | None = None) -> list[dict]:
        return [dict(log_date=r["log_date"], weight_lbs=r["weight_lbs"])
                for r in self._weight_rows(conn, through or date.today().isoformat())]

    def dashboard(self, on_date: str | date | None = None) -> dict:
        """One consistent snapshot for UI workers; all returned values are JSON-safe.

        XP/inventory/milestones are current; activity aggregates are through the
        selected day. A current streak includes yesterday until today's goal is met.
        Milestones are the newest RECENT_MILESTONES (newest first) plus per-category counts.
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
            target = player["target_weight_lbs"]
            rows = self._weight_rows(conn, day)
            # The goal direction is fixed by the first measurement ever logged, even for a past-day view.
            direction = weight_goal(self._weight_rows(conn), target)["direction"]
            baseline_row = next((r for r in rows if _start_side(r["weight_lbs"], target, direction)),
                                min(rows, key=lambda r: (r["created_at"], r["rowid"])) if rows else None)
            baseline = baseline_row["weight_lbs"] if baseline_row else None
            latest = rows[-1]["weight_lbs"] if rows else None
            weights = [dict(log_date=r["log_date"], weight_lbs=r["weight_lbs"]) for r in rows]
            progress = None
            if baseline is not None:
                progress = (1.0 if latest == target else 0.0) if baseline == target else max(0.0, min(1.0, (latest-baseline)/(target-baseline)))
            today_minutes = totals.get(day, 0)
            fitness_minutes = conn.execute("""SELECT COALESCE(SUM(f.minutes),0) FROM fitness_logs f
                JOIN activity_logs a ON a.id=f.log_id WHERE a.player_id=? AND a.log_date=? AND f.kind='workout'""", (self.player_id, day)).fetchone()[0]
            milestones = [dict(id=r[0], key=r[1], title=r[2], category=r[3], achieved_at=r[4]) for r in conn.execute(
                "SELECT id,milestone_key,title,category,achieved_at FROM milestones WHERE player_id=? ORDER BY id DESC LIMIT ?",
                (self.player_id, RECENT_MILESTONES))]
            counts = {category: 0 for category in ("study", "fitness", "coding")}
            counts.update({r[0]: r[1] for r in conn.execute(
                "SELECT category,COUNT(*) FROM milestones WHERE player_id=? GROUP BY category", (self.player_id,))})
            counts["total"] = sum(counts.values())
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
                                     weight_progress=progress, weight_history=weights,
                                     goal_direction={-1: "lose", 1: "gain"}.get(direction, "hold") if rows else None),
                        inventory=inventory, habits=habits, milestones=milestones, milestone_counts=counts,
                        recent_activity=recent, limits={k: list(v) for k, v in LIMITS.items()})
