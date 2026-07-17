"""Shape checks for the GitHub Actions workflows in ``.github/workflows``.

These do not run the workflows; they parse the committed YAML and assert
structural properties the team has decided every job must have, so a
regression is caught by the pytest suite instead of only being noticed the
next time CI itself misbehaves:

* every job declares ``timeout-minutes`` (a run that hangs must not be able
  to spin forever on a shared runner);
* no job or step sets ``continue-on-error`` (a gating job's result must mean
  what it says; per-job green is the only green);
* the release job's zip filename matches the filename ``hacs.json`` declares
  under ``zip_release`` (HACS resolves the release asset by that name, so a
  mismatch would silently break updates);
* actions pinned to a moving branch reference (such as ``@master`` or
  ``@main``) are pinned to a full commit SHA instead, with the friendly ref
  kept as a trailing comment. Actions pinned to a version tag (``@v6``,
  ``@v2.6.2``) are left alone — this repo's SHA-pinning gap has always been
  the *branch*-ref actions, not the tag-ref ones.
"""

from __future__ import annotations

import json
import pathlib
import re

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
WORKFLOW_FILES = ["ci.yml", "release.yml"]

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
# A version-tag-shaped ref, e.g. "v6", "v5", "v2.6.2", "6.3.0".
_VERSION_TAG_RE = re.compile(r"^v?[0-9]+(\.[0-9]+)*$")


def _load_workflow(name: str) -> dict:
    text = (WORKFLOWS_DIR / name).read_text(encoding="utf-8")
    return yaml.safe_load(text)


def _iter_jobs(workflow: dict):
    """Yield (job_id, job_dict) for every job in a parsed workflow."""

    for job_id, job in workflow.get("jobs", {}).items():
        yield job_id, job


def _iter_steps(job: dict):
    """Yield each step dict in a job (jobs without a 'steps' key have none)."""

    return job.get("steps", []) or []


def _find_continue_on_error(workflow: dict, filename: str) -> list[str]:
    hits: list[str] = []
    for job_id, job in _iter_jobs(workflow):
        if "continue-on-error" in job:
            hits.append(f"{filename}: job '{job_id}' sets continue-on-error")
        for step in _iter_steps(job):
            if "continue-on-error" in step:
                step_name = step.get("name", "<unnamed step>")
                hits.append(
                    f"{filename}: job '{job_id}' step '{step_name}' sets "
                    "continue-on-error"
                )
    return hits


def _find_missing_timeouts(workflow: dict, filename: str) -> list[str]:
    return [
        f"{filename}: job '{job_id}' has no timeout-minutes"
        for job_id, job in _iter_jobs(workflow)
        if "timeout-minutes" not in job
    ]


def _find_unpinned_branch_refs(workflow: dict, filename: str) -> list[str]:
    hits: list[str] = []
    for job_id, job in _iter_jobs(workflow):
        for step in _iter_steps(job):
            uses = step.get("uses")
            if not uses or "@" not in uses:
                continue
            action, ref = uses.rsplit("@", 1)
            if _SHA_RE.match(ref) or _VERSION_TAG_RE.match(ref):
                continue
            hits.append(
                f"{filename}: job '{job_id}' step uses '{action}@{ref}' — "
                "a moving branch ref must be pinned to a full commit SHA"
            )
    return hits


def test_every_job_has_a_timeout():
    violations: list[str] = []
    for filename in WORKFLOW_FILES:
        violations.extend(_find_missing_timeouts(_load_workflow(filename), filename))
    assert not violations, "\n".join(violations)


def test_no_continue_on_error_anywhere():
    violations: list[str] = []
    for filename in WORKFLOW_FILES:
        violations.extend(
            _find_continue_on_error(_load_workflow(filename), filename)
        )
    assert not violations, "\n".join(violations)


def test_branch_ref_actions_are_sha_pinned():
    violations: list[str] = []
    for filename in WORKFLOW_FILES:
        violations.extend(
            _find_unpinned_branch_refs(_load_workflow(filename), filename)
        )
    assert not violations, "\n".join(violations)


def test_release_zip_filename_matches_hacs_json():
    hacs = json.loads((REPO_ROOT / "hacs.json").read_text(encoding="utf-8"))
    assert hacs.get("zip_release") is True
    expected_filename = hacs.get("filename")
    assert expected_filename, "hacs.json is missing a filename for zip_release"

    release = _load_workflow("release.yml")
    _, release_job = next(_iter_jobs(release))

    zip_filenames: set[str] = set()
    for step in _iter_steps(release_job):
        run = step.get("run")
        if not run:
            continue
        zip_filenames.update(
            pathlib.PurePosixPath(match).name
            for match in re.findall(r"[\w./-]+\.zip", run)
        )
        files = step.get("with", {}).get("files") if "with" in step else None
        if files:
            zip_filenames.update(
                pathlib.PurePosixPath(match).name
                for match in re.findall(r"[\w./-]+\.zip", str(files))
            )

    assert zip_filenames, "release.yml does not appear to build or publish a .zip"
    assert expected_filename in zip_filenames, (
        f"hacs.json expects '{expected_filename}' but release.yml references "
        f"{sorted(zip_filenames)}"
    )
