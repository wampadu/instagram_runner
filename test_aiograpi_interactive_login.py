"""No-network tests for one-time interactive auth and session persistence."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from scripts.aiograpi_interactive_login import authenticate

class InteractiveAuthTests(unittest.IsolatedAsyncioTestCase):
    async def test_saves_settings_only_after_authenticated_read(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "session.json"
            client = SimpleNamespace(
                login=AsyncMock(return_value=True),
                account_info=AsyncMock(return_value=SimpleNamespace(username="TEST")),
                dump_settings=Mock(side_effect=lambda p: p.write_text("{}")),
                load_settings=Mock(),
                challenge_code_handler=None,
            )
            result = await authenticate(client, "test", "dummy-password", "", path)
            self.assertEqual(result, path)
            self.assertTrue(path.is_file())
            client.login.assert_awaited_once()
            client.account_info.assert_awaited_once()
            client.dump_settings.assert_called_once_with(path)
            client.load_settings.assert_not_called()

    async def test_reuses_saved_settings(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "session.json"
            path.write_text("{}")
            client = SimpleNamespace(
                login=AsyncMock(return_value=True),
                account_info=AsyncMock(return_value=SimpleNamespace(username="test")),
                dump_settings=Mock(),
                load_settings=Mock(),
                challenge_code_handler=None,
            )
            await authenticate(client, "test", "dummy-password", "", path)
            client.load_settings.assert_called_once_with(path)

    async def test_does_not_save_on_account_mismatch(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "session.json"
            client = SimpleNamespace(
                login=AsyncMock(return_value=True),
                account_info=AsyncMock(return_value=SimpleNamespace(username="another_account")),
                dump_settings=Mock(),
                challenge_code_handler=None,
            )
            with self.assertRaisesRegex(RuntimeError, "does not match"):
                await authenticate(client, "test", "dummy-password", "", path)
            client.dump_settings.assert_not_called()
            self.assertFalse(path.exists())
