import importlib.util
from pathlib import Path
import tempfile
import io
import urllib.error
import os
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

spec = importlib.util.spec_from_file_location('metrics', Path(__file__).parents[1] / 'scripts/update_metrics.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class MetricsTests(unittest.TestCase):
    def repo(self):
        return {'name': 'sample&project', 'stars': 3, 'forks': 0, 'open_issues_and_prs': 2, 'created_at': '2026-10-01T00:00:00Z', 'star_dates': ['2026-10-02T01:00:00Z', '2026-10-02T03:00:00Z', '2026-10-04T00:00:00Z'], 'fork_dates': []}

    def test_retained_dates_accumulate_without_inventing_events(self):
        self.assertEqual(m.retained_series(self.repo()['star_dates'], '2026-10-01', '2026-10-06'), [('2026-10-01', 0), ('2026-10-02', 2), ('2026-10-04', 3), ('2026-10-06', 3)])

    def test_cross_repo_denial_falls_back_to_public_request(self):
        response = unittest.mock.MagicMock()
        response.__enter__.return_value = io.BytesIO(b'[]')
        denied = urllib.error.HTTPError('https://api.github.com/test', 403, 'Forbidden', {}, io.BytesIO(b'{}'))
        with patch.dict(os.environ, {'GH_TOKEN': 'test-only'}), patch.object(m.urllib.request, 'urlopen', side_effect=[denied, response]) as call:
            self.assertEqual(m.get('/test'), [])
            self.assertIn('Authorization', call.call_args_list[0].args[0].headers)
            self.assertNotIn('Authorization', call.call_args_list[1].args[0].headers)

    def test_event_auth_denial_preserves_original_timestamp(self):
        denied = urllib.error.HTTPError('https://api.github.com/test', 401, 'Unauthorized', {}, None)
        with patch('builtins.print'):
            dates, when = m.event_history(unittest.mock.Mock(side_effect=denied), ['2026-09-01T00:00:00Z'], '2026-10-01T00:00:00Z', '2026-10-06T00:00:00Z')
        self.assertEqual(when, '2026-10-01T00:00:00Z')
        self.assertEqual(len(dates), 1)

    def test_no_cache_is_unavailable_not_fake_zero_history(self):
        r = self.repo()
        r['star_history_observed_at'] = None
        r['star_dates'] = []
        svg = m.chart(r, [], '2026-10-06T00:00:00Z')
        self.assertIn('Event history unavailable', svg)

    def test_event_transient_failure_still_fails(self):
        denied = urllib.error.HTTPError('https://api.github.com/test', 503, 'Unavailable', {}, None)
        with self.assertRaises(urllib.error.HTTPError):
            m.event_history(unittest.mock.Mock(side_effect=denied), [], None, '2026-10-06T00:00:00Z')

    def test_rate_limit_is_not_bypassed(self):
        denied = urllib.error.HTTPError('https://api.github.com/test', 403, 'Forbidden', {'X-RateLimit-Remaining': '0'}, io.BytesIO(b'{}'))
        with patch.dict(os.environ, {'GH_TOKEN': 'test-only'}), patch.object(m.urllib.request, 'urlopen', side_effect=denied) as call:
            with self.assertRaises(urllib.error.HTTPError):
                m.get('/test')
            self.assertEqual(call.call_count, 1)

    def test_zero_events(self):
        self.assertEqual(m.retained_series([], '2026-10-01', '2026-10-06'), [('2026-10-01', 0), ('2026-10-06', 0)])

    def test_same_day_is_idempotent(self):
        r = self.repo()
        first = m.upsert_daily([], [r], '2026-10-06T01:00:00Z')
        r['stars'] = 2
        second = m.upsert_daily(first, [r], '2026-10-06T02:00:00Z')
        self.assertEqual(len(second), 1)
        self.assertEqual(second[0]['repos'][r['name']]['stars'], 2)

    def test_daily_preserves_real_declines_and_missing_days(self):
        r = self.repo()
        h = m.upsert_daily([], [r], '2026-10-01T01:00:00Z')
        r['stars'] = 1
        h = m.upsert_daily(h, [r], '2026-10-04T01:00:00Z')
        self.assertEqual(len(h), 2)
        svg = m.chart(r, h, '2026-10-04T01:00:00Z', False)
        ET.fromstring(svg)
        self.assertNotIn('2026-10-02', svg)

    def test_single_observation_is_not_fake_trend(self):
        r = self.repo()
        h = m.upsert_daily([], [r], '2026-10-06T00:00:00Z')
        svg = m.chart(r, h, '2026-10-06T00:00:00Z', False)
        self.assertIn('A trend needs another day.', svg)
        ET.fromstring(svg)

    def test_svg_is_escaped_and_states_coverage(self):
        svg = m.chart(self.repo(), [], '2026-10-06T00:00:00Z')
        ET.fromstring(svg)
        self.assertIn('sample&amp;project', svg)
        self.assertIn('Not historical net totals', svg)
        self.assertIn('3/3 stars', svg)

    def test_pagination(self):
        with patch.object(m, 'get', side_effect=[list(range(100)), [100]]) as get:
            self.assertEqual(len(m.pages('/test?sort=name')), 101)
            self.assertEqual(get.call_count, 2)

    def test_api_error_never_writes_partial_files(self):
        with patch.object(m, 'get', side_effect=RuntimeError('failed')), patch.object(m, 'write') as write:
            with self.assertRaises(RuntimeError):
                m.pages('/test')
            write.assert_not_called()

    def test_directory_keeps_all_types(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(m, 'ROOT', Path(folder)):
            p = Path(folder) / 'README.md'
            p.write_text('intro\n<!-- PUBLIC-REPOS:START -->old<!-- PUBLIC-REPOS:END -->\nfooter')
            repos = [{'name': 'forked', 'is_fork': True, 'archived': False, 'stars': 0, 'forks': 0, 'description': 'a|b'}, {'name': 'archived', 'is_fork': False, 'archived': True, 'stars': 1, 'forks': 0, 'description': None}]
            m.update_directory('README.md', repos, {})
            result = p.read_text()
            self.assertIn('forked', result)
            self.assertIn('Archived', result)
            self.assertIn('a\\|b', result)
            self.assertTrue(result.endswith('footer'))
            m.update_directory('README.md', repos, {})
            self.assertEqual(p.read_text(), result)

    def test_refuse_missing_directory_marker(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(m, 'ROOT', Path(folder)):
            (Path(folder) / 'README.md').write_text('keep me')
            with self.assertRaises(ValueError):
                m.update_directory('README.md', [], {})


if __name__ == '__main__':
    unittest.main()
