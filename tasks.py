"""Invoke tasks for CI. Jenkins runs `invoke jenkins.pre-commit` on pull requests."""
import dl_pre_commit_hooks.tasks.jenkins
from invoke import Collection

namespace = Collection(dl_pre_commit_hooks.tasks.jenkins)
