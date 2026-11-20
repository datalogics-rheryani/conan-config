#!/usr/bin/env python3
"""Lint the Conan config as staged in the git index.

usage: lint.py [--all] [FILE...]

Checks the named files, or the staged files when none are named. --all checks
every tracked file, including the names of existing profiles.
"""
import json
import os
import re
import subprocess
import sys

# Sections whose entries are key=value assignments.
KEYED_SECTIONS = {"settings", "options", "conf", "buildenv", "runenv"}
# Mixed-case or underscored tokens that Conan settings force into profile names.
NAME_TOKENS = re.compile(r"iOSSim|iOS|x86_64")

errors = []


def error(message):
    errors.append(message)


def git(*args):
    return subprocess.run(("git",) + args, stdout=subprocess.PIPE, check=True).stdout


def paths(*args):
    return [p for p in git(*args).decode("utf-8").split("\0") if p]


def staged_blob(path):
    return git("cat-file", "blob", ":" + path)


def regular_files():
    """Paths in the index that are plain files, not symlinks or submodules."""
    result = set()
    for entry in paths("ls-files", "-s", "-z"):
        meta, path = entry.split("\t", 1)
        if meta.split()[0] in ("100644", "100755"):
            result.add(path)
    return result


def check_text(path, data):
    if not data.endswith(b"\n"):
        error("%s: no trailing newline" % path)
    for number, line in enumerate(data.split(b"\n"), 1):
        if b"\t" in line:
            error("%s:%d: tab character" % (path, number))
            break


def check_profile_name(path):
    name = os.path.basename(path)
    if not re.fullmatch(r"[a-z0-9.-]+", NAME_TOKENS.sub("", name)):
        error("%s: profile names are lowercase with dashes" % path)


def check_profile(path, text):
    templated = re.search(r"{%-?\s*(if|for)\b", text) is not None
    section = None
    seen = set()
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith(("#", "{%", "{#")):
            continue
        if section is None and line.startswith("include("):
            continue
        header = re.fullmatch(r"\[(\w+)\]", line)
        if header:
            section = header.group(1)
            continue
        if section is None:
            error("%s:%d: entry before any [section] header" % (path, number))
            section = ""
            continue
        # Branches of a template may legitimately assign the same key.
        if templated or section not in KEYED_SECTIONS:
            continue
        key, separator, value = line.partition("=")
        key = key.strip()
        # Append, prepend, update and unset operators accumulate by design.
        if not separator or key.endswith(("+", "*")) or value.lstrip().startswith(("+", "!")):
            continue
        if (section, key) in seen:
            error("%s:%d: duplicate key '%s' in [%s]" % (path, number, key, section))
        seen.add((section, key))


def remote_names(text):
    return [remote.get("name") for remote in json.loads(text).get("remotes", [])]


def check_remotes(path, text):
    try:
        remotes = json.loads(text)["remotes"]
    except (ValueError, KeyError, TypeError) as exc:
        error("%s: not a valid remotes file: %s" % (path, exc))
        return
    for remote in remotes:
        name = remote.get("name")
        url = remote.get("url", "")
        if not url.startswith("https://"):
            error("%s: remote '%s' must use https" % (path, name))
        if "@" in url:
            error("%s: remote '%s' embeds credentials in its URL" % (path, name))
        if remote.get("verify_ssl") is not True:
            error("%s: remote '%s' must set verify_ssl to true" % (path, name))

    # Remote order is resolution priority; changing it needs an explicit opt-in.
    if os.environ.get("ALLOW_REMOTE_REORDER") == "1":
        return
    head = subprocess.run(
        ("git", "cat-file", "blob", "HEAD:" + path),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if head.returncode != 0:
        return
    try:
        old = remote_names(head.stdout.decode("utf-8"))
    except (ValueError, AttributeError):
        return
    new = [remote.get("name") for remote in remotes]
    if [n for n in old if n in new] != [n for n in new if n in old]:
        error(
            "%s: remote order changed; set ALLOW_REMOTE_REORDER=1 if intended" % path
        )


def check_settings_yml(path, text):
    for number, line in enumerate(text.splitlines(), 1):
        indent = len(line) - len(line.lstrip(" "))
        # Wrapped flow sequences align to their opening bracket; only keys are checked.
        if indent % 2 and re.match(r'["\w.-]+:(\s|$)', line.lstrip(" ")):
            error("%s:%d: indentation is not a multiple of two spaces" % (path, number))
    try:
        import yaml
    except ImportError:
        print("lint: PyYAML not available; skipping %s parse" % path, file=sys.stderr)
        return
    try:
        yaml.safe_load(text)
    except yaml.YAMLError as exc:
        error("%s: invalid YAML: %s" % (path, " ".join(str(exc).split())))


def main():
    named = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    added = paths("diff", "--cached", "--name-only", "--diff-filter=AR", "-z")
    if "--all" in sys.argv[1:]:
        changed = added = paths("ls-files", "-z")
    elif named:
        changed = named
        added = [path for path in added if path in named]
    else:
        changed = paths("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")

    regular = regular_files()
    for path in changed:
        if path not in regular:
            continue
        data = staged_blob(path)
        if not data or b"\0" in data:
            continue
        check_text(path, data)
        text = data.decode("utf-8", errors="replace")
        if path.startswith("profiles/"):
            check_profile(path, text)
        elif path == "remotes.json":
            check_remotes(path, text)
        elif path == "settings.yml":
            check_settings_yml(path, text)

    for path in added:
        if path.startswith("profiles/"):
            check_profile_name(path)

    # Keeps repo-only files out of consumers' Conan homes.
    if ".conanignore" not in regular:
        error(".conanignore: missing")

    for message in errors:
        print("error: " + message, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
