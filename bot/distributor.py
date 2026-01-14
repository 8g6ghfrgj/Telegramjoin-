# bot/distributor.py
from bot import db

MAX_LINKS_PER_SESSION = 1000

def distribute_links_to_sessions() -> dict:
    """
    Assign up to 1000 unassigned links for each active session.
    Returns report dict.
    """
    sessions = db.list_sessions()
    if not sessions:
        return {"ok": False, "error": "No sessions found"}

    total_unassigned_before = db.count_links_unassigned()

    report = {
        "ok": True,
        "sessions": len(sessions),
        "unassigned_before": total_unassigned_before,
        "assigned_total": 0,
        "per_session": []
    }

    for (sid, _, _, _) in sessions:
        assigned = db.assign_unassigned_links(sid, MAX_LINKS_PER_SESSION)
        report["assigned_total"] += assigned
        report["per_session"].append({"session_id": sid, "assigned": assigned})

    report["unassigned_after"] = db.count_links_unassigned()
    return report

def estimate_needed_sessions() -> dict:
    unassigned = db.count_links_unassigned()
    # how many sessions needed to cover all unassigned links
    needed = (unassigned + MAX_LINKS_PER_SESSION - 1) // MAX_LINKS_PER_SESSION
    return {"unassigned": unassigned, "needed_sessions": needed}
