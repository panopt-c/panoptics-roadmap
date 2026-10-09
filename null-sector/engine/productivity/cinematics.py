"""Durable cinematic reward payloads, independent of any vendor API.

These are Neon Command v1 envelopes, NOT a claimed Higgsfield request schema.
No network requests occur. A provider adapter can translate an exported payload
after its endpoint, credentials, model and accepted schema are configured.
"""
from __future__ import annotations

import json
from uuid import uuid4

from .db import Database, json_text, utc_now

SCENES = {
    "study": "A neon-lit mathematician unlocks a holographic lattice above a rain-soaked cyberpunk city.",
    "fitness": "An augmented runner reaches a rooftop beacon as the futuristic city lights turn gold.",
    "coding": "A cyberpunk engineer repairs the city's central AI core; circuits pulse cyan across the skyline.",
}


class CinematicRouter:
    def __init__(self, db: Database, player_id: int):
        db.get_player(player_id)
        self.db, self.player_id = db, player_id

    def queue_rewards(self) -> list[dict]:
        """Atomically materialize missing rewards, once per milestone.

        Returns only newly created jobs. Read jobs() to recover previously queued
        payloads after a crash. Private fitness measurements and notes are omitted.
        """
        jobs = []
        with self.db.transaction() as conn:
            self.db.require_player(conn, self.player_id)
            milestones = conn.execute("""SELECT m.* FROM milestones m
                LEFT JOIN cinematic_jobs j ON j.milestone_id=m.id
                WHERE m.player_id=? AND j.id IS NULL ORDER BY m.id""", (self.player_id,)).fetchall()
            for milestone in milestones:
                job_id = str(uuid4())
                payload = {
                    "schema_version": "neon.cinematic.v1",
                    "request_id": job_id,
                    "reward": {"milestone_id": milestone["id"], "category": milestone["category"]},
                    "generation": {"media_type": "video", "duration_seconds": 5, "aspect_ratio": "16:9",
                                   "prompt": SCENES[milestone["category"]],
                                   "style": "cinematic cyberpunk, volumetric light, neon reflections"},
                }
                conn.execute("INSERT INTO cinematic_jobs(id,milestone_id,payload_json,created_at) VALUES (?,?,?,?)",
                             (job_id, milestone["id"], json_text(payload), utc_now()))
                jobs.append(payload)
        return jobs

    def jobs(self) -> list[dict]:
        with self.db.transaction() as conn:
            self.db.require_player(conn, self.player_id)
            return [json.loads(row[0]) for row in conn.execute("""SELECT j.payload_json FROM cinematic_jobs j
                JOIN milestones m ON m.id=j.milestone_id WHERE m.player_id=? ORDER BY m.id""", (self.player_id,))]

    def recent_jobs(self, limit: int) -> list[dict]:
        """The newest `limit` payloads, newest first (snapshots stay small; jobs() has the full history)."""
        with self.db.transaction() as conn:
            self.db.require_player(conn, self.player_id)
            return [json.loads(row[0]) for row in conn.execute("""SELECT j.payload_json FROM cinematic_jobs j
                JOIN milestones m ON m.id=j.milestone_id WHERE m.player_id=? ORDER BY m.id DESC LIMIT ?""",
                (self.player_id, limit))]

    def job_count(self) -> int:
        with self.db.transaction() as conn:
            self.db.require_player(conn, self.player_id)
            return conn.execute("""SELECT COUNT(*) FROM cinematic_jobs j JOIN milestones m ON m.id=j.milestone_id
                WHERE m.player_id=?""", (self.player_id,)).fetchone()[0]
