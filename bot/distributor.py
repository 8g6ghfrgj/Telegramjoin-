# bot/distributor.py
from bot import db
from bot.config import RESERVE_LINKS

MAX_LINKS_PER_SESSION = 1000


def distribute_links_to_sessions() -> dict:
    """
    Assign up to 1000 ACTIVE unassigned links for each active session,
    while always keeping a reserve pool of RESERVE_LINKS links.

    Reserve definition:
    - ACTIVE links
    - Unassigned (not in assignments)
    - Keep at least RESERVE_LINKS in DB

    Returns report dict.
    """
    sessions = db.list_sessions()
    if not sessions:
        return {"ok": False, "error": "No sessions found"}

    # Unassigned active links only (reserve pool)
    unassigned_active_before = db.count_links_unassigned_active()

    # Leave RESERVE_LINKS untouched
    distributable = unassigned_active_before - RESERVE_LINKS
    if distributable < 0:
        distributable = 0

    report = {
        "ok": True,
        "sessions": len(sessions),
        "reserve_target": RESERVE_LINKS,
        "unassigned_active_before": unassigned_active_before,
        "distributable_before": distributable,
        "assigned_total": 0,
        "per_session": [],
    }

    remaining = distributable

    # Distribute in order: session 1, session 2, ...
    for (sid, _, _, _) in sessions:
        if remaining <= 0:
            assigned = 0
        else:
            to_assign = min(MAX_LINKS_PER_SESSION, remaining)
            assigned = db.assign_unassigned_links(sid, to_assign)
            remaining -= assigned

        report["assigned_total"] += assigned
        report["per_session"].append({"session_id": sid, "assigned": assigned})

    # After distribution
    unassigned_active_after = db.count_links_unassigned_active()
    report["unassigned_active_after"] = unassigned_active_after

    # reserve after distribution should be >= RESERVE_LINKS (unless DB doesn't have enough)
    report["reserve_after"] = unassigned_active_after
    report["distributable_after"] = max(unassigned_active_after - RESERVE_LINKS, 0)

    return report


def estimate_needed_sessions() -> dict:
    """
    Estimate number of additional sessions needed to process all active unassigned links
    ABOVE the reserve pool.

    Example:
    - unassigned_active=3200
    - reserve=500
    - distributable=2700
    => needed_sessions=3
    """
    unassigned_active = db.count_links_unassigned_active()

    distributable = unassigned_active - RESERVE_LINKS
    if distributable < 0:
        distributable = 0

    needed_sessions = (distributable + MAX_LINKS_PER_SESSION - 1) // MAX_LINKS_PER_SESSION

    return {
        "unassigned_active": unassigned_active,
        "reserve_target": RESERVE_LINKS,
        "distributable": distributable,
        "needed_sessions": needed_sessions,
    }
