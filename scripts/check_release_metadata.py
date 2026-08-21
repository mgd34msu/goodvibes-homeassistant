#!/usr/bin/env python3
"""Check that the integration's release metadata agrees with itself.

Run from the repository root:

    python scripts/check_release_metadata.py

Verifies that manifest.json, const.py and hacs.json tell the same story about
the version, the repository and the HACS release asset. Lives in a script
rather than inline in a workflow because two workflows need it: ci.yml gates
every push and pull request on it, and release.yml's gate job re-runs it
against the tagged commit before anything is published.

Exits non-zero with a single-line reason on the first disagreement.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPONENT_ROOT = REPO_ROOT / "custom_components" / "goodvibes"


def main() -> int:
    manifest = json.loads((COMPONENT_ROOT / "manifest.json").read_text())
    const_py = (COMPONENT_ROOT / "const.py").read_text()
    hacs = json.loads((REPO_ROOT / "hacs.json").read_text())

    version_match = re.search(
        r'^INTEGRATION_VERSION = "([^"]+)"$', const_py, re.MULTILINE
    )
    repo_match = re.search(r'^UPDATE_REPOSITORY = "([^"]+)"$', const_py, re.MULTILINE)

    if version_match is None:
        print("Missing INTEGRATION_VERSION in const.py", file=sys.stderr)
        return 1
    if repo_match is None:
        print("Missing UPDATE_REPOSITORY in const.py", file=sys.stderr)
        return 1

    version = version_match.group(1)
    repository = repo_match.group(1)
    repository_url = f"https://github.com/{repository}"

    problems: list[str] = []
    if manifest["version"] != version:
        problems.append(
            f"manifest version {manifest['version']} != const version {version}"
        )
    if manifest["documentation"] != repository_url:
        problems.append("manifest documentation does not match UPDATE_REPOSITORY")
    if manifest["issue_tracker"] != f"{repository_url}/issues":
        problems.append("manifest issue_tracker does not match UPDATE_REPOSITORY")
    if repository.startswith("OWNER/") or "OWNER/" in const_py:
        problems.append("Repository metadata still contains placeholder OWNER")
    if not hacs.get("zip_release") or hacs.get("filename") != "goodvibes.zip":
        problems.append("hacs.json must point to goodvibes.zip release assets")

    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        return 1

    print(f"Release metadata is consistent: version {version}, repo {repository}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
