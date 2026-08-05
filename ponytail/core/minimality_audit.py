"""Reproducible audit facts for minimal-change runs."""

from __future__ import annotations

import json
import subprocess
import tomllib
from pathlib import Path


DEPENDENCY_FILES = {
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "uv.lock",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
}


def build_run_minimality_audit(agent, task_state, duration_ms):
    from .evidence_summaries import build_minimality_metrics

    metrics = build_minimality_metrics(
        task_state,
        agent.last_prompt_metadata.get("minimal_policy"),
        agent.last_completion_metadata,
        duration_ms,
    )
    audit = audit_minimality(
        agent.root,
        task_state.changed_paths,
        write_scope=(agent.session.get("task_contract", {}) or {}).get("allowed_change_paths", agent.write_scope),
        verification=task_state.evidence_summaries.get("verification_signal", {}),
        baseline_git_clean=getattr(agent, "_run_git_clean", False),
    )
    return metrics, audit


def audit_minimality(
    root,
    changed_paths,
    *,
    write_scope=(),
    verification=None,
    baseline_git_clean=False,
):
    root = Path(root).resolve()
    changed = sorted(dict.fromkeys(str(path).replace("\\", "/") for path in changed_paths or []))
    diff = _git_diff(root) if baseline_git_clean else None
    findings = []
    blocking = []
    scope_status, out_of_scope = _scope_audit(root, changed, write_scope)
    if out_of_scope:
        findings.append("scope_violation")
        blocking.append("scope_violation")
    verification = dict(verification or {})
    verification_status = str(verification.get("state", "unknown") or "unknown")
    if changed and verification_status != "passed":
        findings.append("changed_paths_without_verification")
    if verification_status == "failed":
        findings.append("verifier_failed")
        blocking.append("verifier_failed")
    line_stats = _line_stats(diff, changed)
    dependencies = _added_dependencies(root, diff, changed)
    return {
        "schema_version": "ponytail.minimality_audit.v1",
        "audit_status": "failed" if blocking else "findings" if findings else "passed",
        "changed_files": len(changed),
        "changed_paths": changed,
        "added_lines": line_stats[0],
        "deleted_lines": line_stats[1],
        "dependencies_added": dependencies,
        "scope_status": scope_status,
        "out_of_scope_paths": out_of_scope,
        "verification_status": verification_status,
        "verification_evidence": {
            "state": verification_status,
            "source_span_id": verification.get("source_span_id"),
            "changed_paths": list(verification.get("changed_paths", []) or []),
        },
        "findings": findings,
        "blocking_findings": blocking,
    }


def _git_diff(root):
    try:
        result = subprocess.run(
            ["git", "diff", "--numstat", "--"],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    rows = {}
    for line in result.stdout.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            parts = line.split(None, 2)
        if len(parts) == 3:
            rows[parts[2].replace("\\", "/")] = (parts[0], parts[1])
    return rows


def _line_stats(diff, changed):
    if diff is None:
        return None, None
    if changed and not set(changed).issubset(diff):
        return None, None
    rows = [diff[path] for path in changed]
    if any(not added.isdigit() or not deleted.isdigit() for added, deleted in rows):
        return None, None
    return sum(int(added) for added, _ in rows), sum(int(deleted) for _, deleted in rows)


def _scope_audit(root, changed, write_scope):
    scopes = [str(path).strip() for path in write_scope or () if str(path).strip()]
    if not scopes:
        return "not_configured", []
    out = []
    for raw_path in changed:
        candidate = (root / raw_path).resolve()
        if not any(_under(candidate, (root / scope).resolve()) for scope in scopes):
            out.append(raw_path)
    return "failed" if out else "passed", out


def _under(path, parent):
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _added_dependencies(root, diff, changed):
    manifests = [path for path in changed if Path(path).name in DEPENDENCY_FILES]
    if not manifests:
        return [] if diff is not None else None
    if diff is None:
        return None
    added = set()
    for path in manifests:
        old = _git_head_text(root, path)
        new_path = root / path
        if old is None or not new_path.exists():
            return None
        old_dependencies = _manifest_dependencies(path, old)
        new_dependencies = _manifest_dependencies(path, new_path.read_text(encoding="utf-8"))
        if old_dependencies is None or new_dependencies is None:
            return None
        added.update(new_dependencies - old_dependencies)
    return sorted(added)


def _git_head_text(root, path):
    try:
        result = subprocess.run(
            ["git", "show", f"HEAD:{path}"],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout


def _manifest_dependencies(path, text):
    try:
        if path.endswith(".toml"):
            data = tomllib.loads(text)
            project = data.get("project", {})
            values = set(project.get("dependencies", []) or [])
            poetry = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
            values.update(str(key) for key in poetry if key.lower() != "python")
            return values
        if path.endswith(".json"):
            data = json.loads(text)
            values = set()
            for section in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
                values.update(str(key) for key in (data.get(section) or {}))
            return values
        values = set()
        for line in text.splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                values.add(line.split("[", 1)[0].strip())
        return values
    except (OSError, TypeError, ValueError, tomllib.TOMLDecodeError, json.JSONDecodeError):
        return None
