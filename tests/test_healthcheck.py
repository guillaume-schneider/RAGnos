from __future__ import annotations

import io
import unittest
from unittest.mock import AsyncMock, patch

from tests import test_support  # noqa: F401

import ragnos.healthcheck as healthcheck_mod
from ragnos.health import HealthCheck, HealthReport


class HealthcheckTests(unittest.TestCase):
    def test_healthcheck_main_prints_report(self) -> None:
        report = HealthReport(
            ok=True,
            checks=[HealthCheck(name="redis", ok=True, details="redis://localhost")],
        )

        with patch("ragnos.healthcheck.load_config", return_value=object()), patch(
            "ragnos.healthcheck.build_health_report",
            new=AsyncMock(return_value=report),
        ), patch("ragnos.healthcheck.log_event") as log_mock, patch("sys.stdout", new_callable=io.StringIO) as stdout:
            exit_code = healthcheck_mod.main([])

        self.assertEqual(exit_code, 0)
        self.assertIn("Status systeme", stdout.getvalue())
        log_mock.assert_called_once()
