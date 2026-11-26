"""SQLite snapshots for manual recovery by the owning account."""

import json

RETENTION_SECONDS = 7 * 24 * 60 * 60


class RunRecoveryStore:
    def __init__(self, auth):
        self.auth = auth
        # The standard launcher runs one HTTP worker per database. Candidate
        # deployments start with their own temporary database.
        with auth.connection() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS research_jobs (
                    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, created_at REAL NOT NULL,
                    request TEXT NOT NULL, interrupted INTEGER NOT NULL DEFAULT 0)
            """)
            db.execute(
                "CREATE INDEX IF NOT EXISTS research_jobs_owner ON research_jobs(owner_id, created_at)"
            )
            self._purge(db)
            db.execute("UPDATE research_jobs SET interrupted = 1 WHERE interrupted = 0")

    def _cutoff(self):
        return self.auth.clock() - RETENTION_SECONDS

    def _purge(self, db):
        db.execute("DELETE FROM research_jobs WHERE created_at <= ?", (self._cutoff(),))

    def add(self, job):
        with self.auth.connection() as db:
            self._purge(db)
            db.execute(
                "INSERT INTO research_jobs (id, owner_id, created_at, request) VALUES (?, ?, ?, ?)",
                (job.id, job.owner, self.auth.clock(), json.dumps(job.request, ensure_ascii=False)),
            )

    def interrupted(self, owner, job_id=None):
        query = (
            "SELECT id, request FROM research_jobs WHERE owner_id = ? AND interrupted = 1 AND created_at > ?"
        )
        args = (owner, self._cutoff())
        if job_id is not None:
            query += " AND id = ?"
            args += (job_id,)
        with self.auth.connection() as db:
            rows = db.execute(query + " ORDER BY created_at DESC, id", args).fetchall()
        jobs = []
        for row in rows:
            request = json.loads(row["request"])
            jobs.append(
                {
                    "id": row["id"],
                    "status": "interrupted",
                    "done": 0,
                    "total": request["n"] * len(request["scenario"]["variants"]),
                    "record": None,
                    "error": "Сервис перезапустился до сохранения результата. Настройки исследования сохранены.",
                    "saved": False,
                    "request": request,
                }
            )
        return jobs

    def remove(self, owner, job_id, *, interrupted_only=False):
        query = "DELETE FROM research_jobs WHERE owner_id = ? AND id = ?"
        args = (owner, job_id)
        if interrupted_only:
            query += " AND interrupted = 1 AND created_at > ?"
            args += (self._cutoff(),)
        with self.auth.connection() as db:
            return db.execute(query, args).rowcount == 1
