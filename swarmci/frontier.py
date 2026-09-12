"""Control-oriented exploration priorities; browser actions remain Browser Use's job."""

import math
from urllib.parse import urlparse

from swarmci.state import digest


def control_key(control):
    return digest({k: control.get(k) for k in ("tag", "role", "label", "href", "type")})


def exploration_frontier(state, target, attempted, count=3):
    candidates = []
    seen = set()
    origin = urlparse(target.url).hostname
    for control in state["controls"]:
        name = (control.get("label") or "").strip()
        if control.get("disabled") or not name or len(name) > 180:
            continue
        if control.get("type") in ("password", "file"):
            continue
        if any(term in name.lower() for term in ("sign out", "log out", "delete workspace", "delete project")):
            continue
        href = control.get("href") or ""
        if href and urlparse(href).hostname not in (None, origin, *target.allowed_domains):
            continue
        key = control_key(control)
        if key in seen:
            continue
        seen.add(key)
        attempts = attempted.get(key, 0)
        if attempts >= 3:
            continue
        kind = (
            "input"
            if control["tag"] in ("input", "textarea") or control.get("editable")
            else "navigation"
            if href
            else "control"
        )
        priority = (
            40 / (1 + attempts) + (8 if kind == "navigation" else 0) + 8 * math.log2(2 + state["depth"])
        )
        instruction = (
            f"Investigate the visible {kind} named {name!r} first. "
            "Then follow that workflow through several meaningful steps. "
            "Verify what changed; do not repeatedly reopen the same menu. "
            "For editing, exercise save/cancel/reopen or undo/reload when available. "
            "For navigation, follow the destination and test returning. "
            "If a control is disabled, choose another available control. "
            "Report a concrete observed failure using report_ux_issue."
        )
        candidate = {"objective": instruction, "control_key": key, "priority": priority}
        if control.get("selector") and control["tag"] in ("a", "button"):
            candidate["first_control"] = key
        candidates.append(candidate)
    candidates.sort(key=lambda c: (-c["priority"], c["control_key"]))
    return candidates[:count]
