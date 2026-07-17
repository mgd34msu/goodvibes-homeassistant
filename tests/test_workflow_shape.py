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
  the *branch*-ref actions, not the tag-ref ones;
* the zero-touch release automation is wired correctly: ci.yml's
  ``auto-release`` job depends on every other job in ci.yml, only runs on a
  push to main, and can write repository contents (to create the release
  tag); its tag-creation step checks whether the tag already exists before
  ever creating one; and it dispatches release.yml with ``mode=release``.
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


def test_auto_release_needs_covers_every_other_ci_job():
    ci = _load_workflow("ci.yml")
    jobs = dict(_iter_jobs(ci))
    assert "auto-release" in jobs, "ci.yml is missing the auto-release job"

    other_job_ids = set(jobs) - {"auto-release"}
    needs = jobs["auto-release"].get("needs")
    assert needs, "ci.yml: auto-release job has no 'needs'"
    needs_set = {needs} if isinstance(needs, str) else set(needs)

    missing = other_job_ids - needs_set
    assert not missing, (
        f"ci.yml: auto-release does not wait on every other job — missing "
        f"{sorted(missing)}"
    )


def test_auto_release_only_runs_on_a_main_push():
    ci = _load_workflow("ci.yml")
    jobs = dict(_iter_jobs(ci))
    condition = jobs["auto-release"].get("if", "")
    assert "github.ref == 'refs/heads/main'" in condition
    assert "github.event_name == 'push'" in condition


def test_auto_release_can_write_repository_contents():
    ci = _load_workflow("ci.yml")
    jobs = dict(_iter_jobs(ci))
    permissions = jobs["auto-release"].get("permissions", {})
    assert permissions.get("contents") == "write", (
        "ci.yml: auto-release needs contents: write to create the release tag"
    )
    assert permissions.get("actions") == "write", (
        "ci.yml: auto-release needs actions: write to dispatch release.yml"
    )


def test_auto_release_checks_tag_existence_before_creating_one():
    ci = _load_workflow("ci.yml")
    jobs = dict(_iter_jobs(ci))
    run_steps = "\n".join(
        step.get("run", "") for step in _iter_steps(jobs["auto-release"])
    )

    exists_check_pos = run_steps.find("git ls-remote --tags origin")
    tag_create_pos = run_steps.find("git tag -a")
    assert exists_check_pos != -1, (
        "ci.yml: auto-release does not check whether the tag already exists"
    )
    assert tag_create_pos != -1, "ci.yml: auto-release never creates the tag"
    assert exists_check_pos < tag_create_pos, (
        "ci.yml: auto-release must check tag existence before creating the tag"
    )


def test_auto_release_dispatches_release_workflow_in_release_mode():
    ci = _load_workflow("ci.yml")
    jobs = dict(_iter_jobs(ci))
    run_steps = "\n".join(
        step.get("run", "") for step in _iter_steps(jobs["auto-release"])
    )
    assert "gh workflow run release.yml" in run_steps
    assert "mode=release" in run_steps


def test_release_dispatch_accepts_a_dry_run_or_release_mode():
    release = _load_workflow("release.yml")
    # PyYAML's safe_load parses the bare YAML key "on:" as the boolean True
    # (YAML 1.1 treats on/off as booleans), not the string "on".
    triggers = release[True]
    dispatch_inputs = triggers["workflow_dispatch"]["inputs"]
    assert "mode" in dispatch_inputs, (
        "release.yml: workflow_dispatch is missing the 'mode' input"
    )
    mode_input = dispatch_inputs["mode"]
    assert set(mode_input.get("options", [])) == {"dry-run", "release"}
    assert mode_input.get("default") == "dry-run"


def test_release_job_still_runs_on_a_plain_tag_push():
    release = _load_workflow("release.yml")
    _, release_job = next(_iter_jobs(release))
    condition = release_job.get("if", "")
    assert "github.event_name == 'push'" in condition, (
        "release.yml: the release job must still run on a plain tag push"
    )
    assert "workflow_dispatch" in condition and "mode == 'release'" in condition, (
        "release.yml: a manual dispatch must require mode=release to publish"
    )
