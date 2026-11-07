"""Offline regression checks for the asynchronous authentication path."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from scripts.aiograpi_login_check import verify_client

class AsyncLoginTests(unittest.IsolatedAsyncioTestCase):
    async def test_awaits_login_and_account_info(self):
        client = SimpleNamespace(
            login=AsyncMock(return_value=True),
            user_id="123",
            account_info=AsyncMock(return_value=SimpleNamespace(username="TESTUSER")),
        )
        stage = {}
        await verify_client(client, "testuser", "not-a-real-password", "", stage)
        client.login.assert_awaited_once()
        client.account_info.assert_awaited_once()
        self.assertEqual(stage["value"], "authenticated account_info")

    async def test_login_failure_does_not_read_account(self):
        client = SimpleNamespace(
            login=AsyncMock(return_value=False),
            user_id=None,
            account_info=AsyncMock(),
        )
        with self.assertRaisesRegex(RuntimeError, "did not confirm"):
            await verify_client(client, "testuser", "no-password", "", {})
        client.account_info.assert_not_awaited()

    async def test_missing_session_does_not_read_account(self):
        client = SimpleNamespace(
            login=AsyncMock(return_value=True),
            user_id=None,
            account_info=AsyncMock(),
        )
        with self.assertRaisesRegex(RuntimeError, "Missing authenticated"):
            await verify_client(client, "testuser", "no-password", "", {})
        client.account_info.assert_not_awaited()

    async def test_account_mismatch_fails(self):
        client = SimpleNamespace(
            login=AsyncMock(return_value=True),
            user_id="123",
            account_info=AsyncMock(return_value=SimpleNamespace(username="other")),
        )
        with self.assertRaisesRegex(RuntimeError, "mismatch"):
            await verify_client(client, "testuser", "no-password", "", {})
        client.account_info.assert_awaited_once()
