import json
import tempfile
import unittest
from pathlib import Path

from scripts.benchmark_retrieval import BenchmarkSample, compute_percentile, load_benchmark_cases, summarize_samples


class RetrievalBenchmarkTestCase(unittest.TestCase):
    def test_compute_percentile_returns_interpolated_value(self):
        self.assertEqual(compute_percentile([], 0.95), 0.0)
        self.assertEqual(compute_percentile([10, 20, 30, 40], 0.5), 25.0)
        self.assertEqual(compute_percentile([10, 20, 30, 40], 0.95), 38.5)

    def test_summarize_samples_aggregates_latency_and_success(self):
        summary = summarize_samples(
            [
                BenchmarkSample(case_id='case-a', iteration=1, duration_ms=120, success=True, source_count=3, rule_count=2),
                BenchmarkSample(case_id='case-a', iteration=2, duration_ms=240, success=True, source_count=2, rule_count=1),
                BenchmarkSample(case_id='case-a', iteration=3, duration_ms=360, success=False, source_count=0, rule_count=0, error='boom'),
            ]
        )
        self.assertEqual(summary['total_requests'], 3)
        self.assertEqual(summary['success_count'], 2)
        self.assertEqual(summary['error_count'], 1)
        self.assertEqual(summary['success_rate'], 0.6667)
        self.assertEqual(summary['latency_ms']['min'], 120)
        self.assertEqual(summary['latency_ms']['max'], 240)
        self.assertEqual(summary['latency_ms']['p50'], 180.0)

    def test_load_benchmark_cases_supports_array_and_items_object(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            array_path = Path(temp_dir) / 'array.json'
            array_path.write_text(json.dumps([{'case_id': 'case-a', 'session_id': 'sess-1', 'query': 'a'}]), encoding='utf-8')
            self.assertEqual(load_benchmark_cases(str(array_path))[0]['case_id'], 'case-a')

            items_path = Path(temp_dir) / 'items.json'
            items_path.write_text(
                json.dumps({'items': [{'case_id': 'case-b', 'session_id': 'sess-2', 'query': 'b'}]}),
                encoding='utf-8',
            )
            self.assertEqual(load_benchmark_cases(str(items_path))[0]['case_id'], 'case-b')


if __name__ == '__main__':
    unittest.main()
