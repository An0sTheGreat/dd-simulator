"""Rebuild the offline project dashboard from Git and project notes. Standard library only.

Reads dashboard.config.json (next to this file), data/curation.json and data/sessions.json,
then writes data/project.json and the equivalent data/project-data.js bootstrap.
Every input except Git itself is optional: missing files, headings or lists become empty data.
"""

import argparse
import collections
import datetime as dt
import fnmatch
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG_NAME = "dashboard.config.json"
ROAD_STATUSES = {"done", "next", "planned", "gated"}
PLAN_STATUSES = {"implemented", "partial", "planned", "design"}
HEALTH_STATUSES = {"healthy", "warning", "danger", "unknown"}
SYSTEM_STATUSES = {"stable", "active", "planned", "blocked"}
THEMES = {"default", "forest-green", "light-blue", "track-gold", "orange", "purple", "aqua"}
DEFAULT_HANDOFF = {"currentState": "Current State", "inProgress": "In Progress", "nextSteps": "Next Steps"}
DEFAULT_LANGUAGES = {".py": "Python", ".js": "JavaScript", ".ts": "TypeScript", ".css": "CSS", ".html": "HTML"}
DEFAULT_SIZE_GROUPS = [
    {"label": "Git history", "match": [".git"]},
    {"label": "Dependencies & caches", "match": ["node_modules", "__pycache__", ".venv", "venv", ".cache",
                                                 "build", "dist", "bin", "obj", "target"]},
]
IMAGES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t#]*$", re.MULTILINE)
DOCX = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def git(root, *args):
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                            encoding="utf-8", errors="replace", check=True)
    return result.stdout


def read_json(path, default):
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else default


def read_text(root, relative):
    """Text of an optional project file; '' when the path is unset or missing."""
    path = root / relative if relative else None
    return path.read_text(encoding="utf-8-sig") if path and path.is_file() else ""


def repo_root(here, config):
    if config.get("repoRoot"):
        return (here / config["repoRoot"]).resolve()
    if not in_git(here):
        raise ValueError("This folder is not inside a Git repository. Set repoRoot in dashboard.config.json "
                         "(for example \"..\") to point at the project folder.")
    return Path(git(here, "rev-parse", "--show-toplevel").strip()).resolve()


# ---------- Markdown ----------

def sections(text, level):
    """Sections at exactly `level`; each body runs to the next heading of that level or higher."""
    found = [m for m in HEADING.finditer(text) if len(m[1]) <= level]
    return [{"title": m[2].strip(), "body": text[m.end():found[i + 1].start() if i + 1 < len(found) else len(text)].strip()}
            for i, m in enumerate(found) if len(m[1]) == level]


def section(text, title):
    """Body under the first heading named `title` (any level, case-insensitive)."""
    if not title:
        return ""
    for match in HEADING.finditer(text):
        if match[2].strip().casefold() == title.casefold():
            level = len(match[1])
            end = next((n.start() for n in HEADING.finditer(text, match.end()) if len(n[1]) <= level), len(text))
            return text[match.end():end].strip()
    return ""


def bullets(text):
    return [re.sub(r"^\s*(?:\d+\.|[-*])\s+", "", line).strip()
            for line in text.splitlines() if re.match(r"^\s*(?:\d+\.|[-*])\s+", line)]


# ---------- Plan document (.md or .docx) ----------

def docx_paragraphs(path):
    """(style id, text) for every body paragraph, table cells included; split text runs are joined."""
    with zipfile.ZipFile(path) as archive:
        xml = ET.fromstring(archive.read("word/document.xml"))
    result = []
    for p in xml.findall(".//w:body//w:p", DOCX):
        style = p.find("w:pPr/w:pStyle", DOCX)
        style_id = style.get(f"{{{DOCX['w']}}}val", "") if style is not None else ""
        result.append((style_id, "".join(t.text or "" for t in p.findall(".//w:t", DOCX))))
    return result


def read_plan(path, level=1, pattern=""):
    """Plan sections by heading. .docx headings are paragraphs styled 'Heading<level>', or, when
    `pattern` is set, paragraphs whose text matches it (a named group 'title' becomes the title)."""
    if path.suffix.lower() == ".docx":
        heading = re.compile(pattern) if pattern else None
        result = []
        for style, text in docx_paragraphs(path):
            match = heading.search(text) if heading else None
            is_heading = bool(match) if heading else style.replace(" ", "").lower() == f"heading{level}"
            if is_heading and text.strip():
                title = match["title"] if match and "title" in match.re.groupindex else text
                result.append({"title": title.strip(), "paragraphs": []})
            elif result and text.strip():
                result[-1]["paragraphs"].append(text.strip())
    else:
        text = path.read_text(encoding="utf-8-sig")
        result = [{"title": s["title"], "paragraphs": [p.strip() for p in re.split(r"\n\s*\n", s["body"]) if p.strip()]}
                  for s in sections(text, level)]
    for number, item in enumerate(result, 1):
        item["number"] = number
    return result


# ---------- Git ----------

def commit_history(root):
    if subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "-q", "HEAD"],
                      capture_output=True).returncode:
        return []  # repository without commits yet
    # NUL framing preserves tabs/newlines in paths.
    raw = git(root, "log", "--format=%x00COMMIT%x00%H%x00%aI%x00%s%x00", "--numstat", "-z", "--no-renames", "HEAD")
    commits = []
    for record in raw.split("\0COMMIT\0")[1:]:
        sha, date, subject, stats = record.split("\0", 3)
        files = []
        for row in stats.split("\0"):
            row = row.lstrip("\r\n")
            if not row:
                continue
            added, deleted, name = row.split("\t", 2)
            files.append({"path": name, "added": int(added) if added.isdigit() else None,
                          "deleted": int(deleted) if deleted.isdigit() else None})
        commits.append({"sha": sha, "short": sha[:7], "date": date, "subject": subject, "files": files,
                        "added": sum(f["added"] or 0 for f in files),
                        "deleted": sum(f["deleted"] or 0 for f in files)})
    return commits


def in_git(root):
    """True when root is inside a Git work tree and Git is installed."""
    try:
        return subprocess.run(["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
                              capture_output=True).returncode == 0
    except OSError:
        return False


def walk_files(root, skip_prefix):
    """Repo-relative files for a folder without Git: hidden folders, dependency/build caches and the
    dashboard folder itself are left out, standing in for what `git ls-files` would ignore."""
    skip = {name for group in DEFAULT_SIZE_GROUPS for name in group["match"]}
    result = []
    for folder, dirs, files in os.walk(root):
        relative = Path(folder).relative_to(root).as_posix()
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in skip
                   and not (skip_prefix and f"{relative}/{d}/".lstrip("./").startswith(skip_prefix))]
        result += [f if relative == "." else f"{relative}/{f}" for f in files]
    return sorted(result)


def latest_tag(root):
    """Nearest tag reachable from HEAD, or '' when there is none."""
    result = subprocess.run(["git", "-C", str(root), "describe", "--tags", "--abbrev=0", "HEAD"],
                            capture_output=True, encoding="utf-8", errors="replace")
    return result.stdout.strip() if result.returncode == 0 else ""


def working_tree(root, exclude_prefix):
    status = git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    result, records = [], iter(status.split("\0"))
    for row in records:
        if not row:
            continue
        if row[0] in "RC" or row[1] in "RC":
            next(records, None)  # skip the rename source
        # The dashboard's own generated files should not make every refresh look dirty.
        if not (exclude_prefix and row[3:].startswith(exclude_prefix)):
            result.append({"status": row[:2], "path": row[3:]})
    return result


def matches(path, patterns):
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


# ---------- Sessions and size ----------

def validate_sessions(entries):
    if not isinstance(entries, list):
        raise ValueError("data/sessions.json must contain a list.")
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Every session entry must be an object.")
        for key in ("date", "agent", "title", "summary"):
            if not isinstance(entry.get(key), str) or not entry[key].strip():
                raise ValueError(f"Every session needs a nonempty {key} string.")
        dt.date.fromisoformat(entry["date"])
        for key in ("tokens", "toolCalls", "costUsd", "minutes"):
            value = entry.get(key)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                      or not math.isfinite(value) or value < 0):
                raise ValueError(f"Session {key} must be a nonnegative number or null.")
        # Optional AI fields: who/what ran the session and which commits it produced.
        for key in ("model", "provider", "role"):
            if entry.get(key) is not None and not isinstance(entry[key], str):
                raise ValueError(f"Session {key} must be a string or null.")
        if entry.get("local") is not None and not isinstance(entry["local"], bool):
            raise ValueError("Session local must be true, false or null.")
        if not isinstance(entry.get("commits", []), list) or not all(isinstance(c, str) for c in entry.get("commits", [])):
            raise ValueError("Session commits must be a list of commit hashes.")
    return entries


def project_size(root, groups=None):
    """Logical bytes of every file under root, ignored files included; links/junctions are skipped.
    A file belongs to the first group whose `match` names (fnmatch) equal any of its path parts."""
    groups = DEFAULT_SIZE_GROUPS if groups is None else groups
    totals, skipped, count, pending = collections.Counter(), [], 0, [root]
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    try:
                        info = entry.stat(follow_symlinks=False)
                        if entry.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
                            skipped.append(Path(entry.path).relative_to(root).as_posix())
                        elif entry.is_dir(follow_symlinks=False):
                            pending.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            parts = Path(entry.path).relative_to(root).parts
                            label = next((g["label"] for g in groups
                                          if any(fnmatch.fnmatch(part, m) for part in parts for m in g["match"])),
                                         "Project files")
                            totals[label] += info.st_size
                            count += 1
                    except OSError:
                        skipped.append(Path(entry.path).relative_to(root).as_posix())
        except OSError:
            skipped.append(Path(directory).relative_to(root).as_posix())
    return {"totalBytes": sum(totals.values()), "fileCount": count, "groups": dict(totals), "skipped": skipped}


# ---------- Build ----------

def build(here=HERE, copy_media=True):
    config = read_json(here / CONFIG_NAME, {})
    curation = read_json(here / "data" / "curation.json", {})
    root = repo_root(here, config)
    paths = config.get("paths", {})
    levels = {"completed": 2, "plan": 1, **config.get("headingLevels", {})}
    headings = {**DEFAULT_HANDOFF, **config.get("handoff", {})}

    handoff = read_text(root, paths.get("handoff"))
    milestones = sections(read_text(root, paths.get("completed")), levels["completed"])
    try:
        inside = here.relative_to(root).as_posix() + "/"
    except ValueError:
        inside = None  # dashboard lives outside the repository
    versioned = in_git(root)  # without Git, history is empty and files come from the folder itself
    commits = commit_history(root) if versioned else []
    hints = curation.get("milestoneMatches", {})
    for milestone in milestones:
        hashes = re.findall(r"\b[0-9a-f]{7,40}\b", milestone["title"] + milestone["body"])
        linked = [c for c in commits if any(c["sha"].startswith(h) for h in hashes)]
        if not linked:
            terms = hints.get(milestone["title"], [])
            linked = [c for c in commits if any(t.casefold() in c["subject"].casefold() for t in terms)]
        milestone.update({"commits": [c["short"] for c in linked],
                          "date": min((c["date"] for c in linked), default=None)})

    plan_file = root / paths["plan"] if paths.get("plan") else None
    plan = read_plan(plan_file, levels["plan"], config.get("planHeadingPattern", "")) \
        if plan_file and plan_file.is_file() else []
    plan_status = curation.get("planStatus", {})
    for item in plan:
        item.update({"status": "design", "note": "", **plan_status.get(str(item["number"]), {})})

    tracked = [p for p in (git(root, "ls-files", "-z").split("\0") if versioned else walk_files(root, inside))
               if p and (root / p).is_file()]
    source = config.get("source", {})
    languages = source.get("languages", DEFAULT_LANGUAGES)
    first_party = [p for p in tracked if matches(p, source.get("include", ["*"]))
                   and not matches(p, source.get("exclude", []))]
    lines = collections.Counter()
    for name in first_party:
        label = languages.get(Path(name).suffix.lower())
        if label:
            lines[label] += len((root / name).read_text(encoding="utf-8-sig", errors="replace").splitlines())
    content = {c["label"]: sum(fnmatch.fnmatch(p, c["glob"]) for p in tracked) for c in config.get("content", [])}

    areas = collections.Counter()
    for commit in commits:
        for file in commit["files"]:
            parts = file["path"].split("/")
            areas["/".join(parts[:2]) if len(parts) > 1 else "(root files)"] += 1

    media, banner = collect_media(root, here, config, curation, copy_media)
    size = config.get("size", {})
    data = {
        "schemaVersion": 1, "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(), "demo": False,
        "project": {"name": "Project", "subtitle": "", "description": "", "repository": "", "timezone": "",
                    "accent": "", "stage": "", "flow": [], "facts": [], **config.get("project", {})},
        "dashboard": {"refreshCommand": f'python "{inside}refresh.py"' if inside else "python refresh.py"},
        "git": {"branch": (git(root, "branch", "--show-current").strip() or "Detached HEAD") if versioned else "",
                "head": commits[0]["sha"] if commits else "", "tag": latest_tag(root) if commits else "",
                "commits": commits,
                "workingTree": working_tree(root, inside) if versioned else [],
                "firstCommit": commits[-1]["date"] if commits else None,
                "latestCommit": commits[0]["date"] if commits else None},
        "brief": {"currentState": section(handoff, headings["currentState"]),
                  "inProgress": section(handoff, headings["inProgress"]),
                  "nextSteps": bullets(section(handoff, headings["nextSteps"])),
                  "handoff": handoff, "rules": read_text(root, paths.get("rules")),
                  "pillars": curation.get("pillars", []), "phases": curation.get("phases", []),
                  "roadmap": curation.get("roadmap", []), "decisions": curation.get("decisions", []),
                  "health": curation.get("health", []), "systems": curation.get("systems", [])},
        "milestones": milestones, "plan": plan,
        "sessions": validate_sessions(read_json(here / "data" / "sessions.json", [])),
        "media": media, "banner": banner,
        "numbers": {"trackedFiles": len(tracked), "sourceFiles": len(first_party),
                    "changedPaths": len({f["path"] for c in commits for f in c["files"]}),
                    "content": content, "sourceLines": dict(lines.most_common()),
                    "areas": dict(areas.most_common(12)),
                    "added": sum(c["added"] for c in commits), "deleted": sum(c["deleted"] for c in commits),
                    "projectSize": project_size(root, size.get("groups")) if size.get("enabled", True) else None},
        "sources": [{"key": key, "label": Path(rel).name,
                     "path": Path(os.path.relpath(root / rel, here)).as_posix(),
                     "modifiedAt": dt.datetime.fromtimestamp((root / rel).stat().st_mtime, dt.timezone.utc).isoformat()}
                    for key, rel in paths.items() if rel and (root / rel).is_file()],
    }
    validate_report(data)
    return data


def collect_media(root, here, config, curation, copy_media):
    """Copy captures and the banner into media/ so the folder is shareable on its own."""
    def take(item):
        source = root / item["source"]
        if not source.is_file():
            return None  # missing captures are skipped, never fatal
        if copy_media:
            (here / "media").mkdir(exist_ok=True)
            shutil.copyfile(source, here / "media" / source.name)
        return {"title": source.stem.replace("_", " ").replace("-", " ").capitalize(), "caption": "",
                **item, "path": "media/" + source.name}

    listed = list(curation.get("captures", []))
    if config.get("capturesFolder"):
        folder, known = root / config["capturesFolder"], {Path(c["source"]).name for c in listed}
        if folder.is_dir():
            listed += [{"source": p.relative_to(root).as_posix()} for p in sorted(folder.iterdir())
                       if p.suffix.lower() in IMAGES and p.name not in known]
    media = [m for m in map(take, listed) if m]
    banner = curation.get("banner") or ({"source": config["banner"]} if config.get("banner") else None)
    return media, take(banner) if banner else None


def validate_report(data):
    """Structural sanity only; content counts are the project's business."""
    def check(condition, message):
        if not condition:
            raise ValueError(message)
    project, brief = data["project"], data["brief"]
    check(isinstance(project["name"], str) and project["name"].strip(), "project.name must be a nonempty string.")
    check(not project["accent"] or re.fullmatch(r"#[0-9a-fA-F]{6}", project["accent"]),
          "project.accent must be a #rrggbb colour.")
    check(isinstance(project.get("version", ""), str), "project.version must be a string.")
    check(project.get("theme", "default") in THEMES | {""}, f"project.theme must be one of {sorted(THEMES)}.")
    check(all(isinstance(f, dict) and {"label", "value"} <= f.keys() for f in project["facts"]),
          "project.facts entries need label and value.")
    check(all(f.get("status") in HEALTH_STATUSES | {None} for f in project["facts"]),
          f"project.facts status must be one of {sorted(HEALTH_STATUSES)}.")
    check(all(isinstance(h, dict) and h.get("label") and h.get("status", "unknown") in HEALTH_STATUSES
              for h in brief["health"]),
          f"Every health signal needs a label and a status in {sorted(HEALTH_STATUSES)}.")
    check(all(isinstance(s, dict) and s.get("name") and s.get("status", "stable") in SYSTEM_STATUSES
              and isinstance(s.get("paths", []), list) for s in brief["systems"]),
          f"Every system needs a name, a status in {sorted(SYSTEM_STATUSES)} and a list of paths.")
    commits = data["git"]["commits"]
    check(len({c["sha"] for c in commits}) == len(commits), "Duplicate commits collected.")
    check(all(re.fullmatch(r"[0-9a-f]{40}", c["sha"]) for c in commits), "Unexpected commit id format.")
    check(all(isinstance(r, dict) and r.get("id") and r.get("title") and r.get("status") in ROAD_STATUSES
              and isinstance(r.get("tests", []), list) for r in brief["roadmap"]),
          f"Every roadmap item needs id, title and a status in {sorted(ROAD_STATUSES)}.")
    check(all(isinstance(d, dict) and d.get("title") for d in brief["decisions"]), "Every decision needs a title.")
    check(all(isinstance(p, dict) and p.get("name") for p in brief["pillars"]), "Every pillar needs a name.")
    check(all(isinstance(p, dict) and p.get("title") for p in brief["phases"]), "Every phase needs a title.")
    check(all(s["status"] in PLAN_STATUSES for s in data["plan"]),
          f"Plan status must be one of {sorted(PLAN_STATUSES)}.")


def write_report(data, here=HERE):
    payload = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)
    # The JS bootstrap lets index.html work when opened directly via file://.
    js = "window.PROJECT_DATA = " + payload.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029") + ";\n"
    for name, text in (("project.json", payload + "\n"), ("project-data.js", js)):
        target = here / "data" / name
        temp = target.with_suffix(target.suffix + ".tmp")
        temp.write_text(text, encoding="utf-8")
        temp.replace(target)


def refresh_once(check=False, here=HERE):
    try:
        report = build(here, copy_media=not check)
        if not check:
            write_report(report, here)
        print(f"{'Checked' if check else 'Updated'}: {len(report['git']['commits'])} commits, "
              f"{len(report['milestones'])} milestones, {len(report['plan'])} plan sections.", flush=True)
    except (OSError, ValueError, subprocess.CalledProcessError, zipfile.BadZipFile, ET.ParseError, re.error) as error:
        print(f"Dashboard refresh failed: {error}", file=sys.stderr)
        return 1
    return 0


def fingerprint(here=HERE):
    config = read_json(here / CONFIG_NAME, {})
    root = repo_root(here, config)
    inputs = [here / CONFIG_NAME, here / "data" / "curation.json", here / "data" / "sessions.json",
              *(root / p for p in config.get("paths", {}).values() if p)]
    stamp = tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in inputs if p.is_file())
    try:
        exclude = [f":(exclude){here.relative_to(root).as_posix()}"]
    except ValueError:
        exclude = []
    if not in_git(root):
        return stamp, "", ""
    head = subprocess.run(["git", "-C", str(root), "rev-parse", "-q", "--verify", "HEAD"],
                          capture_output=True, text=True).stdout  # empty before the first commit
    return stamp, head, git(root, "status", "--porcelain", "--", ".", *exclude)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Validate without writing the snapshot or media")
    mode.add_argument("--watch", action="store_true", help="Refresh when notes or Git state change; Ctrl+C to stop")
    args = parser.parse_args()
    result = refresh_once(args.check)
    if not args.watch:
        return result
    print("Watching project notes and Git state every 5 seconds. Reload the browser after an update.", flush=True)
    try:
        previous = fingerprint()
        while True:
            time.sleep(5)
            try:
                current = fingerprint()
                if current != previous:
                    refresh_once()
                    previous = current
            except (OSError, subprocess.CalledProcessError) as error:
                print(f"Watch check failed: {error}", file=sys.stderr, flush=True)
    except KeyboardInterrupt:
        print("Stopped watching.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
