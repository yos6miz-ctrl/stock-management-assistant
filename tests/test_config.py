from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from investment_agent.config import ConfigurationError, load_config


class ConfigTests(unittest.TestCase):
    def test_loads_provider_neutral_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            config_path = root / "settings.json"
            config_path.write_text(
                json.dumps(
                    {
                        "storage_path": "state.json",
                        "log_level": "debug",
                        "base_currency": "usd",
                        "market_data_provider": "placeholder",
                        "portfolio_analysis_provider": "placeholder",
                        "opportunity_research_provider": "placeholder",
                    }
                ),
                encoding="utf-8",
            )

            config = load_config(config_path)

            self.assertEqual((root / "state.json").resolve(), config.storage_path)
            self.assertEqual("DEBUG", config.log_level)
            self.assertEqual("USD", config.base_currency)
            self.assertEqual("placeholder", config.market_data_provider)
            self.assertEqual("gpt-5.6-sol", config.openai_model)
            self.assertEqual("medium", config.openai_reasoning_effort)

    def test_accepts_openai_provider_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "settings.json"
            config_path.write_text(
                json.dumps(
                    {
                        "storage_path": "state.json",
                        "market_data_provider": "openai",
                        "portfolio_analysis_provider": "openai",
                        "opportunity_research_provider": "openai",
                        "openai_model": "gpt-5.6-sol",
                        "openai_reasoning_effort": "high",
                    }
                ),
                encoding="utf-8",
            )

            config = load_config(config_path)

            self.assertEqual("openai", config.market_data_provider)
            self.assertEqual("high", config.openai_reasoning_effort)

    def test_rejects_unimplemented_provider(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "settings.json"
            config_path.write_text(
                json.dumps(
                    {
                        "storage_path": "state.json",
                        "market_data_provider": "unconfigured-live-provider",
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ConfigurationError):
                load_config(config_path)
