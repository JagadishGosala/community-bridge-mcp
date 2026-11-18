import sqlite3

# SPEC §11. No requests (A-11).
NONPROFITS = [
    ("np_bridge", "Community Bridge"),
    ("np_harbor", "Harbor Neighbors"),
]

STAFF = [
    ("stf_bridge_cw", "np_bridge", "Casey Morgan", "CASE_WORKER"),
    ("stf_bridge_pm", "np_bridge", "Priya Shah", "PROGRAM_MANAGER"),
    ("stf_bridge_fin", "np_bridge", "Felix Ortega", "FINANCE"),
    ("stf_harbor_cw", "np_harbor", "Hana Lee", "CASE_WORKER"),
    ("stf_harbor_pm", "np_harbor", "Marcus Bell", "PROGRAM_MANAGER"),
    ("stf_harbor_fin", "np_harbor", "Nadia Cole", "FINANCE"),
]

PARTICIPANTS = [
    ("par_bridge_001", "np_bridge", "Jordan Avery"),
    ("par_bridge_002", "np_bridge", "Sam Patel"),
    ("par_bridge_003", "np_bridge", "Riley Chen"),
    ("par_harbor_001", "np_harbor", "Taylor Brooks"),
    ("par_harbor_002", "np_harbor", "Morgan Diaz"),
]

FUNDS = [
    ("fund_bridge_rent", "np_bridge", "Emergency Rent Relief", 1_000_000),
    ("fund_bridge_utility", "np_bridge", "Utility Assistance", 250_000),
    ("fund_harbor_general", "np_harbor", "General Emergency Assistance", 500_000),
]


def insert_seed(conn: sqlite3.Connection) -> None:
    conn.executemany("INSERT INTO nonprofits (id, name) VALUES (?, ?)", NONPROFITS)
    conn.executemany(
        "INSERT INTO staff (id, nonprofit_id, name, role) VALUES (?, ?, ?, ?)", STAFF
    )
    conn.executemany(
        "INSERT INTO participants (id, nonprofit_id, display_name) VALUES (?, ?, ?)",
        PARTICIPANTS,
    )
    conn.executemany(
        "INSERT INTO funds (id, nonprofit_id, name, allocation_cents) VALUES (?, ?, ?, ?)",
        FUNDS,
    )
