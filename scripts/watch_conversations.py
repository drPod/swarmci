#!/usr/bin/env python3
"""Append project conversation text to one Markdown file, without tool traffic.

Run with --once for a single sync; otherwise polls every three seconds.
Progress and a crash-recovery journal live outside the transcript in data/.
"""

import argparse
import fcntl
import json
import os
import re
import time
from pathlib import Path


def normalize(text):
    return re.sub(r"\s+", " ", text).strip()


def message_text(row):
    payload = row.get("payload", {})
    if row.get("type") != "response_item" or payload.get("type") != "message":
        return None
    role = payload.get("role")
    metadata = payload.get("internal_chat_message_metadata_passthrough", {})
    kinds = metadata.get("content_item_kinds", [])
    if role == "user":
        if "user.text" not in kinds:
            return None
    elif role == "assistant":
        if payload.get("phase", payload.get("channel")) not in (
            None, "commentary", "final_answer", "final"
        ):
            return None
    else:
        return None
    text = "\n".join(
        part.get("text", "") for part in payload.get("content", [])
        if part.get("type") in ("input_text", "output_text")
    )
    # Screenshots and fenced code are not plain-English conversation output.
    text = re.sub(r"<image\b[^>]*>.*?</image>", "", text, flags=re.S)
    text = re.sub(r"<image\b[^>]*?/?>", "", text)
    text = re.sub(
        r"(?ms)^\s*(```|~~~)[^\n]*\n.*?^\s*\1[^\n]*(?:\n|$)", "", text
    ).strip()
    if not text or text.startswith((
        "<environment_context>", "<turn_aborted>", "<subagent_notification>"
    )):
        return None
    return text


def save(path, state):
    temporary = path.with_suffix(".tmp")
    with temporary.open("w") as stream:
        json.dump(state, stream)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def recover(target, state_path, state):
    pending = state.get("pending")
    if not pending:
        return
    data = pending["text"].encode()
    with target.open("r+b") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.seek(pending["position"])
        found = stream.read(len(data))
        if found != data:
            # Recover an interrupted write only when its exact prefix is present.
            stream.seek(0, 2)
            end = stream.tell()
            if end != pending["position"] + len(found) or not data.startswith(found):
                raise RuntimeError("Transcript changed during recovery; refusing to overwrite it")
            stream.write(data[len(found):])
            stream.flush()
            os.fsync(stream.fileno())
    del state["pending"]
    save(state_path, state)


def sync(project, sessions, target, state_path, state):
    recover(target, state_path, state)
    initial = not state.get("initialized", False)
    seen = set(state.get("seen", []))
    candidates = []
    changed = False
    # Ignore earlier brainstorming before the conversation this file records.
    since = state.get("since", "")
    anchor = target.stem.removeprefix("conversation-")
    if not since:
        for path in sessions.rglob(f"*{anchor}.jsonl"):
            with path.open() as stream:
                since = json.loads(stream.readline())["payload"].get("timestamp", "")
            break
        state["since"] = since
    cursors = state.setdefault("files", {})
    for path in sorted(sessions.rglob("*.jsonl")):
        key = str(path)
        cursor = cursors.get(key, {})
        if cursor.get("ignore"):
            continue
        size = path.stat().st_size
        if cursor.get("offset") == size:
            continue
        with path.open("rb") as stream:
            if not cursor:
                first = stream.readline()
                if not first.endswith(b"\n"):
                    continue
                try:
                    meta = json.loads(first).get("payload", {})
                except (ValueError, UnicodeDecodeError):
                    continue
                if meta.get("cwd") != str(project):
                    cursors[key] = {"ignore": True}
                    changed = True
                    continue
                cursor = {"offset": stream.tell()}
            else:
                stream.seek(cursor["offset"] if size >= cursor["offset"] else 0)
            while True:
                position = stream.tell()
                line = stream.readline()
                if not line.endswith(b"\n"):
                    stream.seek(position)
                    break
                try:
                    row = json.loads(line)
                except (ValueError, UnicodeDecodeError):
                    continue
                text = message_text(row)
                if text is None or row.get("timestamp", "") < since:
                    continue
                payload = row["payload"]
                identity = payload.get("id") or f"{key}:{position}"
                if identity in seen:
                    continue
                seen.add(identity)
                candidates.append((row.get("timestamp", ""), identity, text))
            cursor["offset"] = stream.tell()
            cursors[key] = cursor
            changed = True
    candidates.sort(key=lambda item: (item[0], item[1]))
    with target.open("r+b") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        before = stream.read()
        known = normalize(before.decode()) if initial else ""
        additions = []
        for _, _, text in candidates:
            if initial:
                # The preexisting hand-maintained file lacks message IDs. Match
                # its paragraphs once, then preserve repeated messages by ID.
                parts = [part for part in re.split(r"\n\s*\n", text)
                         if part.strip() and normalize(part) not in known]
                text = "\n\n".join(parts)
                known += " " + normalize(text)
            if text:
                additions.append(text)
        state["seen"] = sorted(seen)
        state["initialized"] = True
        state["last_sync"] = time.time()
        if additions:
            suffix = "\n\n" + "\n\n".join(additions) + "\n"
            state["pending"] = {"position": len(before), "text": suffix}
            # Journal both offsets and the pending append before writing.
            save(state_path, state)
            stream.seek(0, 2)
            stream.write(suffix.encode())
            stream.flush()
            os.fsync(stream.fileno())
            del state["pending"]
            state["messages_appended"] = state.get("messages_appended", 0) + len(additions)
        if changed or initial or additions:
            save(state_path, state)
    if additions:
        print(f"Appended {len(additions)} messages", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--sessions", type=Path, default=Path.home() / ".codex/sessions")
    parser.add_argument("--target", type=Path)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=3)
    args = parser.parse_args()
    project = args.project.resolve()
    target = args.target or project / "conversation-01a0970d-c680-74f0-b02b-3dfbe4c7f87b.md"
    state_path = args.state or project / "data/conversation-watcher/state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with state_path.with_suffix(".lock").open("a") as lock:
        # Only one writer process may use this cursor journal.
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        while True:
            sync(project, args.sessions, target, state_path, state)
            if args.once:
                return
            time.sleep(max(1, args.interval))


if __name__ == "__main__":
    main()
