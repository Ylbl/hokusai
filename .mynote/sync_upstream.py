#!/usr/bin/env python3
"""Prepare an upstream merge; publish only its successful CI completion event."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import yaml

PREFIX = "mynote/upstream/"
PATTERN = re.compile(r"^mynote/upstream/([0-9a-f]{40})/([0-9a-f]{40})$")
ROOT = Path(__file__).resolve().parents[1]


def run(*args, capture=False):
    result = subprocess.run(args, cwd=ROOT, text=True, check=True,
                            stdout=subprocess.PIPE if capture else None)
    return result.stdout.strip() if capture else None


def git(*args, capture=False):
    return run("git", *args, capture=capture)


def repo():
    return os.environ["GITHUB_REPOSITORY"]


def remote_main():
    git("fetch", "--no-tags", "origin", "main")
    return git("rev-parse", "refs/remotes/origin/main", capture=True)


def provenance(upstream_sha):
    path = ROOT / "MYNOTE-SOURCE.toml"
    text = path.read_text()
    version = run("git", "show", "upstream/main:Cargo.toml", capture=True)
    import tomllib
    version = tomllib.loads(version)["workspace"]["package"]["version"]
    for name, value in [("upstream_commit", upstream_sha), ("upstream_version", version)]:
        text, count = re.subn(rf'(?m)^{name} = ".*"$', f'{name} = "{value}"', text)
        if count != 1:
            raise RuntimeError(f"expected one mutable provenance field: {name}")
    path.write_text(text)
    git("add", "--", "MYNOTE-SOURCE.toml")
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode:
        git("commit", "-m", f"mynote: record upstream {upstream_sha}")


def prepare(force):
    base = remote_main()
    git("checkout", "--detach", base)
    remotes = git("remote", capture=True).splitlines()
    if "upstream" not in remotes:
        git("remote", "add", "upstream", "https://github.com/reearth/hokusai.git")
    git("fetch", "--no-tags", "upstream", "main")
    upstream = git("rev-parse", "upstream/main", capture=True)
    unchanged = subprocess.run(["git", "merge-base", "--is-ancestor", upstream, base], cwd=ROOT).returncode == 0
    if unchanged and not force:
        print(f"Already contains upstream {upstream}; nothing to merge.")
        return
    branch = f"{PREFIX}{upstream}/{base}"
    existing = git("ls-remote", "--heads", "origin", f"refs/heads/{branch}", capture=True)
    if existing:
        if force:
            run("gh", "workflow", "run", "ci.yml", "--repo", repo(), "--ref", branch)
            print(f"Explicitly rechecking existing candidate {branch}; main unchanged.")
        else:
            print(f"Candidate already submitted: {branch}; main unchanged, no repeated automatic retries.")
        return
    if not unchanged:
        # Never resolve a conflict by preferring our tree or upstream's tree.
        git("merge", "--no-edit", upstream)
    provenance(upstream)
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    if workflow.get("name") != "CI":
        raise RuntimeError("upstream CI identity changed; update the workflow_run integration before publishing")
    if "mynote-native" not in workflow.get("jobs", {}):
        raise RuntimeError("candidate lost the native cross-build gate")
    git("push", "origin", f"HEAD:refs/heads/{branch}")
    # Explicit dispatch is required: a GITHUB_TOKEN push does not trigger push CI.
    run("gh", "workflow", "run", "ci.yml", "--repo", repo(), "--ref", branch)
    print(f"Submitted {branch}; only the complete CI success event may publish main.")


def publish():
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    ci = event["workflow_run"]
    match = PATTERN.fullmatch(ci.get("head_branch") or "")
    if not match or ci.get("conclusion") != "success":
        raise RuntimeError("not a successful owned update candidate")
    if ci["head_repository"]["full_name"] != repo() or ci.get("event") != "workflow_dispatch":
        raise RuntimeError("CI is not the explicitly submitted fork candidate")
    upstream, base = match.groups()
    branch = ci["head_branch"]
    if remote_main() != base:
        raise RuntimeError("fork main moved during CI; refusing a stale candidate")
    git("fetch", "--no-tags", "origin", f"refs/heads/{branch}")
    head = git("rev-parse", "FETCH_HEAD", capture=True)
    if head != ci["head_sha"]:
        raise RuntimeError("candidate ref no longer matches the tested commit")
    git("checkout", "--detach", head)
    git("merge-base", "--is-ancestor", base, head)
    git("merge-base", "--is-ancestor", upstream, head)
    import tomllib
    metadata = tomllib.loads((ROOT / "MYNOTE-SOURCE.toml").read_text())
    if metadata["upstream_commit"] != upstream:
        raise RuntimeError("tested source provenance does not identify the merged upstream")
    # No force push: an intervening main update must be rejected by the server.
    git("push", "origin", "HEAD:refs/heads/main")
    git("push", "origin", f":refs/heads/{branch}")
    print(f"Published tested commit {head} containing upstream {upstream}.")


if __name__ == "__main__":
    if sys.argv[1:] == ["publish"]:
        publish()
    elif sys.argv[1:] in (["prepare"], ["prepare", "--force-checks"]):
        prepare("--force-checks" in sys.argv)
    else:
        raise SystemExit("usage: sync_upstream.py prepare [--force-checks] | publish")
