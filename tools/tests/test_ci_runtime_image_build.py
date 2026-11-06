import importlib.util
from pathlib import Path
import subprocess
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'ci_runtime_image_build.py'
spec = importlib.util.spec_from_file_location('ci_runtime_image_build', SOURCE)
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)
DIGEST = 'sha256:' + 'a' * 64


class BuildTests(unittest.TestCase):
    def run_case(self, responses):
        calls = []
        def runner(args, **kwargs):
            calls.append((args, kwargs))
            result = responses.pop(0)
            if isinstance(result, Exception):
                raise result
            code, output = result
            return subprocess.CompletedProcess(args, code, output, '')
        result = build.build_runtime_image(runner=runner)
        self.assertFalse(responses)
        return result, calls

    def test_primary_image_digest_is_pinned_and_build_is_real(self):
        result, calls = self.run_case([(0, 'Digest: ' + DIGEST), (0, '')])
        self.assertEqual(result, 0)
        self.assertEqual(len(calls), 2)
        self.assertIn('PYTHON_BASE_IMAGE=public.ecr.aws/docker/library/python@' + DIGEST, calls[-1][0])
        self.assertEqual(calls[-1][0][-1], '.')
        self.assertEqual(calls[-1][1]['timeout'], 900)

    def test_throttled_mirror_uses_only_original_official_registry_once(self):
        result, calls = self.run_case([(1, '429 Too Many Requests - Data limit exceeded'),
                                       (0, 'Digest: ' + DIGEST), (0, '')])
        self.assertEqual(result, 0)
        self.assertEqual(calls[1][0], ['docker', 'pull', build.BASE_IMAGES[1]])
        self.assertIn('PYTHON_BASE_IMAGE=docker.io/library/python@' + DIGEST, calls[-1][0])

    def test_both_registries_limited_fails_without_build(self):
        result, calls = self.run_case([(1, 'toomanyrequests'), (1, '429')])
        self.assertEqual(result, 1)
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(args[1] == 'pull' for args, _ in calls))

    def test_other_pull_failures_do_not_rotate_registries(self):
        for message in ('403 denied', '401 unauthorized', 'certificate invalid', 'manifest unknown'):
            with self.subTest(message=message):
                result, calls = self.run_case([(1, message)])
                self.assertEqual(result, 1)
                self.assertEqual(len(calls), 1)

    def test_build_failure_does_not_use_another_base_or_retry(self):
        result, calls = self.run_case([(0, 'Digest: ' + DIGEST), (1, 'pip 429')])
        self.assertEqual(result, 1)
        self.assertEqual(len(calls), 2)

    def test_missing_or_ambiguous_digest_is_rejected(self):
        for output in ('success without digest', 'Digest: '+DIGEST+'\nDigest: sha256:'+'b'*64):
            with self.subTest(output=output):
                result, calls = self.run_case([(0, output)])
                self.assertEqual(result, 1)
                self.assertEqual(len(calls), 1)

    def test_timeout_is_bounded_not_retried(self):
        result, calls = self.run_case([subprocess.TimeoutExpired(['docker','pull'], 300)])
        self.assertEqual(result, 1)
        self.assertEqual(len(calls), 1)

    def test_build_timeout_never_reports_success(self):
        result, calls = self.run_case([(0, 'Digest: '+DIGEST), subprocess.TimeoutExpired(['docker','build'],900)])
        self.assertEqual(result, 1)
        self.assertEqual(len(calls), 2)


if __name__ == '__main__':
    unittest.main()
