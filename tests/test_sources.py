from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from astra_support.sim.sources import list_available_sources, resolve_csv_source


class SourceTests(unittest.TestCase):
    def test_resolve_csv_source_from_project_dataset(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            dataset_dir = root / "datasets" / "example"
            dataset_dir.mkdir(parents=True)
            csv_path = dataset_dir / "demo.csv"
            csv_path.write_text("time,altitude\n0,0\n", encoding="utf-8")

            self.assertIn("demo", list_available_sources(root))
            resolved = resolve_csv_source("demo", root)
            self.assertEqual(resolved, csv_path.resolve())
