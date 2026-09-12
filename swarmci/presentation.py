"""Read-only graph presentation. Grouping never changes exploration identity."""

import json
import re
from collections import defaultdict
from urllib.parse import urlsplit, urlunsplit

from swarmci.state import digest

PART_LABELS = {
    "history": "Action history",
    "historyLength": "Browser history length",
    "app": "Application data",
    "storage_key": "Stored browser data",
    "controls": "Controls and input values",
    "text": "Visible page text",
    "dialogs": "Open dialogs",
    "scroll": "Scroll position",
    "url": "Page address",
    "title": "Page title",
}


def page_identity(node):
    url = urlsplit(node.get("url", ""))
    # Hash-router paths identify pages; query strings and ordinary anchors do not.
    route_hash = url.fragment.split("?")[0] if url.fragment.startswith("/") else ""
    route = urlunsplit((url.scheme, url.netloc, url.path, "", route_hash))
    return digest(route), route


def facts_for(node, fixture=False):
    if fixture:
        # Historical fixture observations already contain this visible diagnostic.
        match = re.search(r"STATE\s*(\{[^{}]+\})", node.get("text", ""))
        try:
            state = json.loads(match[1]) if match else {}
        except ValueError:
            state = {}
        names = {
            "group": "Intermediate group",
            "copy": "Card copy",
            "swapped": "Component swapped",
            "broken": "Error screen",
        }
        facts = {
            label: ("Present" if state[key] else "Absent")
            for key, label in names.items()
            if isinstance(state.get(key), bool)
        }
        if facts:
            return facts
    controls = node.get("controls", [])
    facts = {
        "Visible controls": str(len(controls)),
        "Disabled controls": str(sum(bool(c.get("disabled")) for c in controls)),
    }
    selected = [c.get("label", "")[:70] for c in controls if c.get("selected") == "true"]
    if selected:
        facts["Selected tabs"] = ", ".join(selected[:3])
    return facts


def enrich_snapshot(snap):
    nodes = {n["id"]: {**n} for n in snap["nodes"]}
    order = []
    for edge in snap["edges"]:
        for key in (edge["source"], edge["target"]):
            if key not in order:
                order.append(key)
    order.extend(key for key in nodes if key not in order)
    pages, screens, arrivals = defaultdict(list), defaultdict(list), defaultdict(list)
    for edge in snap["edges"]:
        arrivals[edge["target"]].append(edge)
    fixture = snap["config"]["target"].get("isolation") == "fixture"
    for key in order:
        node = nodes[key]
        node["page_key"], node["page_url"] = page_identity(node)
        node["state_facts"] = facts_for(node, fixture)
        pages[node["page_key"]].append(node)
        screens[node["screen_key"]].append(node)
    groups = []
    for page_key, variants in pages.items():
        for index, node in enumerate(variants):
            node["variant"] = index + 1
            node["page_variants"] = len(variants)
            node["same_screen_variants"] = len(screens[node["screen_key"]])
            incoming = arrivals[node["id"]]
            node["arrival_count"] = len(incoming)
            node["arrival_paths"] = len({digest(e["payload"].get("path", [])) for e in incoming})
            node["arrival_workers"] = len(
                {e["payload"].get("worker") for e in incoming if e["payload"].get("worker")}
            )
            if fixture and "Intermediate group" in node["state_facts"]:
                f = node["state_facts"]
                node["variant_note"] = (
                    f"Group {f['Intermediate group'].lower()} · copy {f['Card copy'].lower()}"
                )
            elif node["same_screen_variants"] > 1:
                others = [n for n in screens[node["screen_key"]] if n["id"] != node["id"]]
                changed = [
                    k
                    for k, v in node.get("fingerprint_parts", {}).items()
                    if any(n.get("fingerprint_parts", {}).get(k) != v for n in others)
                ]
                node["variant_note"] = (
                    "Same screen · "
                    + ", ".join(PART_LABELS.get(k, k).lower() for k in changed[:2])
                    + " differs"
                )
            else:
                node["variant_note"] = f"{len(node.get('controls', []))} controls · distinct screen layout"
        first = variants[0]
        groups.append(
            {
                "id": page_key,
                "label": first.get("title") or "Application page",
                "url": first["page_url"],
                "states": [n["id"] for n in variants],
                "arrivals": sum(len(arrivals[n["id"]]) for n in variants),
                "screen_families": len({n["screen_key"] for n in variants}),
            }
        )
    return {**snap, "nodes": [nodes[key] for key in order], "page_groups": groups}
