from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from astra_support.sim import data_sources
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

    def test_csv_sim_derives_pressure_from_altitude_when_pressure_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "demo.csv"
            csv_path.write_text("time,altitude\n0,123.4\n", encoding="utf-8")

            sim = data_sources.CSVSim(str(csv_path))
            packet = sim.get_next_packet()

        self.assertAlmostEqual(data_sources.pressure_to_msl_altitude(packet.pressure), 123.4, places=2)

    def test_noisy_sim_keeps_altitude_independent_from_pressure(self):
        class SinglePacketSource(data_sources.DataSource):
            def __init__(self):
                self._emitted = False

            def get_next_packet(self):
                self._emitted = True
                return data_sources.PacketData(
                    timestamp=0.0,
                    accel=np.zeros(3),
                    gyro=np.zeros(3),
                    mag=np.zeros(3),
                    pressure=data_sources.pressure_from_msl_altitude(100.0),
                    temp=25.0,
                    lat=45.0,
                    lon=-122.0,
                    alt=500.0,
                    fix=3,
                    sats=10,
                    heading=0.0,
                )

            def is_finished(self) -> bool:
                return self._emitted

        sim = data_sources.NoisySim(
            SinglePacketSource(),
            accel_noise=0.0,
            gyro_noise=0.0,
            mag_noise=0.0,
            baro_noise=0.0,
        )

        packet = sim.get_next_packet()

        self.assertAlmostEqual(packet.alt, 500.0, places=6)
        self.assertAlmostEqual(data_sources.pressure_to_msl_altitude(packet.pressure), 100.0, places=6)
