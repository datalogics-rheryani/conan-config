#!/usr/bin/env python3
"""Render every profile with the Conan client's installed config.

Run after `conan config install .`. A profile that cannot render on its own is
accepted as a mix-in only if a profile that does render includes it.
"""
import os
import re
import subprocess
import sys

PROFILES = "profiles"
INCLUDE = re.compile(r"^include\((.+)\)\s*$", re.MULTILINE)


def render(name):
    """Return None if the profile renders, else Conan's error text."""
    result = subprocess.run(
        ("conan", "profile", "show", "-pr:a", name),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    if result.returncode == 0:
        return None
    lines = [line for line in result.stderr.splitlines() if line.startswith("ERROR")]
    return " ".join(lines) or result.stderr.strip()


def main():
    names = sorted(os.listdir(PROFILES))
    includes = {}
    for name in names:
        with open(os.path.join(PROFILES, name), encoding="utf-8") as handle:
            includes[name] = INCLUDE.findall(handle.read())

    failures = {}
    for name in names:
        message = render(name)
        if message:
            failures[name] = message

    # Everything reachable through include() from a profile that rendered.
    covered = set()
    pending = [name for name in names if name not in failures]
    while pending:
        for included in includes.get(pending.pop(), []):
            if included not in covered:
                covered.add(included)
                pending.append(included)

    broken = {name: message for name, message in failures.items() if name not in covered}
    for name, message in sorted(broken.items()):
        print("error: %s/%s: %s" % (PROFILES, name, message), file=sys.stderr)
    print(
        "%d profiles: %d rendered, %d mix-ins, %d failed"
        % (len(names), len(names) - len(failures), len(failures) - len(broken), len(broken))
    )
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
