import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class Caller:
    staff_id: str
    staff_name: str
    role: str
    nonprofit_id: str
    nonprofit_name: str


def resolve(conn: sqlite3.Connection, staff_id: str) -> Caller | None:
    """Resolve a staff id to its role and nonprofit (REQ-01); None if unknown."""
    row = conn.execute(
        "SELECT s.id, s.name, s.role, n.id, n.name"
        " FROM staff s JOIN nonprofits n ON n.id = s.nonprofit_id"
        " WHERE s.id = ?",
        (staff_id,),
    ).fetchone()
    return Caller(*row) if row else None
