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
* every action is pinned to a full commit SHA, first-party ones included,
  with the friendly ref kept as a trailing comment. A moving ref (``@master``,
  ``@main``) and a version tag (``@v6``) are both mutable: the tag-ref case
  was treated as acceptable here until it was pointed out that ``@v6`` can be
  repointed at any commit just as ``@main`` can;
* the zero-touch release automation is wired correctly: ci.yml's
  ``auto-release`` job depends on every other job in ci.yml, only runs on a
  push to main, and can write repository contents (to create the release
  tag); its tag-creation step checks whether the tag already exists before
  ever creating one; and it dispatches release.yml with ``mode=release``;
* release.yml gates publishing on a job that actually runs the tests, and the
  publishing job waits on it. Both of release.yml's entry paths reach that
  gate, which is the point: the ``push: tags: v*`` path has no CI run behind
  it and used to publish straight to HACS users untested.
"""

from __future__ import annotations

import json
import pathlib
import re

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
WORKFLOW_FILES = ["ci.yml", "release.yml", "sdk-drift.yml"]

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
# A `uses:` line in the raw YAML, capturing whatever follows it on the line so
# the trailing "# v6.1.0" comment can be checked. The parsed YAML cannot be used
# for this: PyYAML discards comments.
_USES_LINE_RE = re.compile(r"^\s*(?:-\s*)?uses:\s*(\S+)\s*(.*)$", re.MULTILINE)


def _load_workflow(name: str) -> dict:
    text = (WORKFLOWS_DIR / name).read_text(encoding="utf-8")
    return yaml.safe_load(text)


def _load_workflow_text(name: str) -> str:
    return (WORKFLOWS_DIR / name).read_text(encoding="utf-8")


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


def _find_unpinned_actions(workflow: dict, filename: str) -> list[str]:
    hits: list[str] = []
    for job_id, job in _iter_jobs(workflow):
        for step in _iter_steps(job):
            uses = step.get("uses")
            if not uses or "@" not in uses:
                continue
            action, ref = uses.rsplit("@", 1)
            if _SHA_RE.match(ref):
                continue
            hits.append(
                f"{filename}: job '{job_id}' step uses '{action}@{ref}': "
                "every action must be pinned to a full commit SHA, including "
                "first-party actions/* ones"
            )
    return hits


def _find_uses_without_version_comment(text: str, filename: str) -> list[str]:
    hits: list[str] = []
    for match in _USES_LINE_RE.finditer(text):
        uses, trailing = match.group(1), match.group(2).strip()
        if not trailing.startswith("#") or not trailing.lstrip("# ").strip():
            hits.append(
                f"{filename}: '{uses}' has no trailing version comment. A bare "
                "SHA says nothing about which version is pinned, so record it "
                "as e.g. '# v6.1.0'."
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


def test_every_action_is_sha_pinned():
    violations: list[str] = []
    for filename in WORKFLOW_FILES:
        violations.extend(_find_unpinned_actions(_load_workflow(filename), filename))
    assert not violations, "\n".join(violations)


def test_every_pinned_action_records_its_version_in_a_comment():
    violations: list[str] = []
    for filename in WORKFLOW_FILES:
        violations.extend(
            _find_uses_without_version_comment(_load_workflow_text(filename), filename)
        )
    assert not violations, "\n".join(violations)


def test_release_zip_filename_matches_hacs_json():
    hacs = json.loads((REPO_ROOT / "hacs.json").read_text(encoding="utf-8"))
    assert hacs.get("zip_release") is True
    expected_filename = hacs.get("filename")
    assert expected_filename, "hacs.json is missing a filename for zip_release"

    release = _load_workflow("release.yml")
    # By job id, not by position: release.yml's first job is the gate.
    release_job = dict(_iter_jobs(release))["release"]

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
        f"ci.yml: auto-release does not wait on every other job: missing "
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


def test_sdk_drift_checks_the_vendored_client_hash():
    """Version strings alone would not notice a hand-edit elsewhere in the file."""

    jobs = dict(_iter_jobs(_load_workflow("sdk-drift.yml")))
    runs = "\n".join(
        step.get("run", "") for job in jobs.values() for step in _iter_steps(job)
    )
    assert "tests/generated_client.sha256" in runs, (
        "sdk-drift.yml does not verify the vendored client against its "
        "recorded hash"
    )


def test_sdk_drift_reports_failures_somewhere_a_human_will_look():
    """A scheduled red run notifies nobody, so the workflow files an issue."""

    workflow = _load_workflow("sdk-drift.yml")
    permissions = workflow.get("permissions", {})
    assert permissions.get("issues") == "write", (
        "sdk-drift.yml needs issues: write to report a drift failure"
    )

    jobs = dict(_iter_jobs(workflow))
    reporting = [
        step
        for job in jobs.values()
        for step in _iter_steps(job)
        if "failure()" in str(step.get("if", ""))
    ]
    assert reporting, "sdk-drift.yml has no step that runs on failure"
    reporting_runs = "\n".join(step.get("run", "") for step in reporting)
    assert "gh issue create" in reporting_runs
    assert "gh issue comment" in reporting_runs, (
        "sdk-drift.yml should update an existing issue rather than opening a "
        "new one every scheduled run"
    )


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


def test_publishing_waits_on_a_gate_that_runs_the_tests():
    """Nothing reaches HACS users until a job that ran pytest has passed.

    The gap this closes: `push: tags: v*` starts release.yml directly, with no
    ci.yml run behind it, so a hand-pushed tag published dist/goodvibes.zip
    without a single test having run.
    """

    jobs = dict(_iter_jobs(_load_workflow("release.yml")))
    assert "gate" in jobs, "release.yml is missing the gate job"

    needs = jobs["release"].get("needs")
    assert needs, "release.yml: the release job has no 'needs'"
    needs_set = {needs} if isinstance(needs, str) else set(needs)
    assert "gate" in needs_set, (
        "release.yml: the release job must wait on the gate job, or publishing "
        "can run without it"
    )

    gate_runs = "\n".join(step.get("run", "") for step in _iter_steps(jobs["gate"]))
    assert "pytest" in gate_runs, "release.yml: the gate job does not run pytest"
    assert "ruff check" in gate_runs, "release.yml: the gate job does not run ruff"
    gate_uses = [step.get("uses", "") for step in _iter_steps(jobs["gate"])]
    assert any("hassfest" in uses for uses in gate_uses), (
        "release.yml: the gate job does not run hassfest"
    )


def test_the_release_gate_tests_the_tagged_commit():
    """The gate must check out the ref being released, not the default branch."""

    jobs = dict(_iter_jobs(_load_workflow("release.yml")))
    checkouts = [
        step
        for step in _iter_steps(jobs["gate"])
        if "actions/checkout" in step.get("uses", "")
    ]
    assert checkouts, "release.yml: the gate job never checks out the repository"
    ref = checkouts[0].get("with", {}).get("ref", "")
    assert "inputs.tag" in ref and "github.ref" in ref, (
        "release.yml: the gate job must check out the same ref the release job "
        f"does, but its checkout ref is {ref!r}"
    )


def test_the_release_gate_runs_on_both_entry_paths():
    """A tag push and a mode=release dispatch must both reach the gate."""

    jobs = dict(_iter_jobs(_load_workflow("release.yml")))
    gate_condition = jobs["gate"].get("if", "")
    assert "github.event_name == 'push'" in gate_condition
    assert "mode == 'release'" in gate_condition
    assert gate_condition == jobs["release"].get("if", ""), (
        "release.yml: the gate and release jobs must share one condition, or a "
        "path exists where one runs without the other"
    )


def test_release_job_still_runs_on_a_plain_tag_push():
    release = _load_workflow("release.yml")
    # By job id, not by position: release.yml's first job is the gate.
    release_job = dict(_iter_jobs(release))["release"]
    condition = release_job.get("if", "")
    assert "github.event_name == 'push'" in condition, (
        "release.yml: the release job must still run on a plain tag push"
    )
    assert "workflow_dispatch" in condition and "mode == 'release'" in condition, (
        "release.yml: a manual dispatch must require mode=release to publish"
    )
