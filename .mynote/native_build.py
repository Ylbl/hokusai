#!/usr/bin/env python3
"""Cross-build actual workspace Windows harnesses and package their runtime paths."""
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "target/mynote-ci"
OUT.mkdir(parents=True, exist_ok=True)
TARGET = ROOT / "target/mynote-xwin"
command = ["cargo", "xwin", "test", "--workspace", "--all-features", "--no-run",
           "--target", "x86_64-pc-windows-msvc", "--target-dir", str(TARGET), "--message-format=json"]
with (OUT / "build.jsonl").open("w") as stdout:
    subprocess.run(command, cwd=ROOT, stdout=stdout, check=True)
files = {}
tests = []
for line in (OUT / "build.jsonl").read_text().splitlines():
    try:
        message = json.loads(line)
    except json.JSONDecodeError:
        continue
    if message.get("reason") != "compiler-artifact":
        continue
    candidates = message.get("filenames", [])
    executable = message.get("executable")
    if executable:
        candidates = [*candidates, executable]
    for name in candidates:
        path = Path(name)
        if path.suffix.lower() not in (".exe", ".dll"):
            continue
        if name not in files:
            artifact = f"bin/{len(files):04}-{path.name}"
            destination = OUT / artifact
            destination.parent.mkdir(exist_ok=True)
            shutil.copy2(path, destination)
            files[name] = {"source_linux": name, "artifact": artifact}
    if executable and message.get("profile", {}).get("test"):
        tests.append({"source_linux": executable, "name": message["target"]["name"]})
if not tests:
    raise SystemExit("no real Windows test harnesses were produced")
subprocess.run(["git", "archive", "--format=tar", "--output", str(OUT / "source.tar"), "HEAD"], cwd=ROOT, check=True)
(OUT / "manifest.json").write_text(json.dumps({"source_root_linux": str(ROOT), "files": list(files.values()), "tests": tests}, indent=2))
print(f"Packaged {len(tests)} real MSVC Windows harnesses; no software-GPU or Wine fallback.")
