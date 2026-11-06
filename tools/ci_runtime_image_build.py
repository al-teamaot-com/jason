#!/usr/bin/env python3
"""Build the existing runtime in CI with bounded official-base availability.

Only the repository's existing ECR mirror and original Docker Official Image are
allowed. Resolve and pin the content digest before the one real image build.
A source/build failure is never retried or converted into a successful check.
"""
from __future__ import annotations

import re
import subprocess
from typing import Callable

BASE_IMAGES = (
    'public.ecr.aws/docker/library/python:3.12-slim',
    'docker.io/library/python:3.12-slim',
)


def build_runtime_image(*, runner: Callable = subprocess.run) -> int:
    for index, image in enumerate(BASE_IMAGES):
        print(f'CI_BASE_IMAGE_RESOLVE={image}', flush=True)
        try:
            pull = runner(['docker', 'pull', image], capture_output=True,
                          text=True, check=False, timeout=300)
        except (OSError, subprocess.TimeoutExpired):
            print('CI_BASE_IMAGE_RESOLUTION_FAILED=process_or_timeout', flush=True)
            return 1
        output = (pull.stdout or '') + '\n' + (pull.stderr or '')
        if pull.returncode:
            limited = bool(re.search(r'(?i)\b429\b|toomanyrequests|too many requests', output))
            # No registry rotation for denied credentials, certificate errors,
            # unknown images, or a failing application/package build.
            if index == 0 and limited:
                print('CI_BASE_MIRROR_THROTTLED=using_existing_official_origin_once', flush=True)
                continue
            print(f'CI_BASE_IMAGE_RESOLUTION_FAILED=exit_{pull.returncode}', flush=True)
            print(output[-4000:], flush=True)
            return 1
        digests = set(re.findall(r'(?m)^Digest:\s*(sha256:[0-9a-f]{64})\s*$', output))
        if len(digests) != 1:
            print('CI_BASE_IMAGE_RESOLUTION_FAILED=missing_or_ambiguous_digest', flush=True)
            return 1
        base = image.rsplit(':', 1)[0] + '@' + next(iter(digests))
        print(f'CI_BASE_IMAGE_PINNED={base}', flush=True)
        command = ['docker', 'build', '--build-arg', f'PYTHON_BASE_IMAGE={base}',
                   '--file', 'infrastructure/jason-runtime/Dockerfile',
                   '--tag', 'jason-runtime:provider-read-ci', '.']
        try:
            built = runner(command, check=False, timeout=900)
        except (OSError, subprocess.TimeoutExpired):
            print('JASON_RUNTIME_CLEAN_BUILD=FAIL', flush=True)
            return 1
        passed = built.returncode == 0
        print('JASON_RUNTIME_CLEAN_BUILD=' + ('PASS' if passed else 'FAIL'), flush=True)
        return 0 if passed else 1
    return 1


if __name__ == '__main__':
    raise SystemExit(build_runtime_image())
