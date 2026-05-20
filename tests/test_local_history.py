from __future__ import annotations

import asyncio
import unittest
from pathlib import Path

from chainlit.context import init_http_context
from chainlit.step import StepDict
from chainlit.types import Pagination, ThreadFilter
from chainlit.user import User

from ragnos.local_history import LocalSQLiteDataLayer
from tests.test_support import workspace_tempdir


class LocalHistoryTests(unittest.TestCase):
    def test_data_layer_persists_and_lists_threads(self) -> None:
        async def scenario() -> tuple[object, object]:
            with workspace_tempdir() as root:
                db_path = root / "history.sqlite3"
                layer = LocalSQLiteDataLayer(db_path)
                user = await layer.create_user(User(identifier="admin", metadata={"role": "operator"}))
                init_http_context(thread_id="thread-1", user=user)

                step = StepDict(
                    id="step-1",
                    name="User",
                    type="user_message",
                    threadId="thread-1",
                    output="Bonjour historique",
                    input="",
                    metadata={},
                )
                await layer.create_step(step)

                listed = await layer.list_threads(Pagination(first=10), ThreadFilter(userId=user.id))
                thread = await layer.get_thread("thread-1")
                return listed, thread

        listed, thread = asyncio.run(scenario())

        self.assertEqual(len(listed.data), 1)
        self.assertEqual(listed.data[0]["id"], "thread-1")
        self.assertEqual(listed.data[0]["name"], "Bonjour historique")
        self.assertIsNotNone(thread)
        self.assertEqual(thread["steps"][0]["output"], "Bonjour historique")

    def test_update_thread_merges_metadata(self) -> None:
        async def scenario():
            with workspace_tempdir() as root:
                db_path = root / "history.sqlite3"
                layer = LocalSQLiteDataLayer(db_path)
                user = await layer.create_user(User(identifier="admin", metadata={}))
                init_http_context(thread_id="thread-2", user=user)

                await layer.update_thread("thread-2", metadata={"chat_profile": "default"})
                await layer.update_thread("thread-2", metadata={"mode": "resume"})
                return await layer.get_thread("thread-2")

        thread = asyncio.run(scenario())

        self.assertEqual(thread["metadata"]["chat_profile"], "default")
        self.assertEqual(thread["metadata"]["mode"], "resume")
