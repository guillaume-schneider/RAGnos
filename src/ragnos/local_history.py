from __future__ import annotations

import asyncio
import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from chainlit.context import context
from chainlit.data.base import BaseDataLayer
from chainlit.element import Element, ElementDict
from chainlit.step import StepDict
from chainlit.types import Feedback, PageInfo, PaginatedResponse, Pagination, ThreadDict, ThreadFilter
from chainlit.user import PersistedUser, User
from chainlit.utils import utc_now


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


def _json_loads_dict(value: str | None) -> dict:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _json_loads_list(value: str | None) -> list:
    if not value:
        return []
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return []
    return loaded if isinstance(loaded, list) else []


def _coerce_bool(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _truncate_thread_name(text: str) -> str:
    cleaned = " ".join(text.strip().split())
    if len(cleaned) <= 80:
        return cleaned
    return cleaned[:77].rstrip() + "..."


class LocalSQLiteDataLayer(BaseDataLayer):
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    identifier TEXT NOT NULL UNIQUE,
                    createdAt TEXT NOT NULL,
                    metadata TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS threads (
                    id TEXT PRIMARY KEY,
                    createdAt TEXT NOT NULL,
                    name TEXT,
                    userId TEXT,
                    userIdentifier TEXT,
                    tags TEXT,
                    metadata TEXT
                );

                CREATE TABLE IF NOT EXISTS steps (
                    id TEXT PRIMARY KEY,
                    threadId TEXT NOT NULL,
                    parentId TEXT,
                    name TEXT,
                    type TEXT NOT NULL,
                    streaming INTEGER DEFAULT 0,
                    waitForAnswer INTEGER,
                    isError INTEGER,
                    metadata TEXT,
                    tags TEXT,
                    input TEXT,
                    output TEXT,
                    createdAt TEXT,
                    start TEXT,
                    "end" TEXT,
                    generation TEXT,
                    showInput TEXT,
                    defaultOpen INTEGER,
                    language TEXT,
                    FOREIGN KEY(threadId) REFERENCES threads(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS elements (
                    id TEXT PRIMARY KEY,
                    threadId TEXT,
                    forId TEXT,
                    type TEXT,
                    chainlitKey TEXT,
                    url TEXT,
                    objectKey TEXT,
                    name TEXT,
                    display TEXT,
                    size INTEGER,
                    page INTEGER,
                    language TEXT,
                    autoPlay INTEGER,
                    playerConfig TEXT,
                    mime TEXT,
                    FOREIGN KEY(threadId) REFERENCES threads(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS feedbacks (
                    id TEXT PRIMARY KEY,
                    forId TEXT NOT NULL,
                    value REAL NOT NULL,
                    comment TEXT
                );
                """
            )

    async def _run(self, func, *args):
        return await asyncio.to_thread(func, *args)

    def _get_current_user_fields(self) -> tuple[str | None, str | None]:
        user = getattr(context.session, "user", None)
        if user is None:
            return None, None
        user_id = getattr(user, "id", None)
        identifier = getattr(user, "identifier", None)
        return (str(user_id) if user_id else None, str(identifier) if identifier else None)

    def _ensure_thread(self, conn: sqlite3.Connection, thread_id: str, name_hint: str | None = None) -> None:
        row = conn.execute('SELECT id, name FROM threads WHERE id = ?', (thread_id,)).fetchone()
        if row:
            if name_hint and not row["name"]:
                conn.execute('UPDATE threads SET name = ? WHERE id = ?', (name_hint, thread_id))
            return

        user_id, user_identifier = self._get_current_user_fields()
        conn.execute(
            """
            INSERT INTO threads (id, createdAt, name, userId, userIdentifier, tags, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                thread_id,
                utc_now(),
                name_hint,
                user_id,
                user_identifier,
                _json_dumps([]),
                _json_dumps({}),
            ),
        )

    def _upsert_step_sync(self, step_dict: StepDict) -> None:
        thread_id = step_dict.get("threadId")
        if not thread_id:
            return

        name_hint = None
        if step_dict.get("type") == "user_message":
            content = (step_dict.get("output") or step_dict.get("input") or "").strip()
            if content:
                name_hint = _truncate_thread_name(content)

        with self._connect() as conn:
            self._ensure_thread(conn, thread_id, name_hint=name_hint)
            conn.execute(
                """
                INSERT INTO steps (
                    id, threadId, parentId, name, type, streaming, waitForAnswer, isError,
                    metadata, tags, input, output, createdAt, start, "end", generation,
                    showInput, defaultOpen, language
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    threadId=excluded.threadId,
                    parentId=excluded.parentId,
                    name=excluded.name,
                    type=excluded.type,
                    streaming=excluded.streaming,
                    waitForAnswer=excluded.waitForAnswer,
                    isError=excluded.isError,
                    metadata=excluded.metadata,
                    tags=excluded.tags,
                    input=excluded.input,
                    output=excluded.output,
                    createdAt=COALESCE(steps.createdAt, excluded.createdAt),
                    start=excluded.start,
                    "end"=excluded."end",
                    generation=excluded.generation,
                    showInput=excluded.showInput,
                    defaultOpen=excluded.defaultOpen,
                    language=excluded.language
                """,
                (
                    step_dict["id"],
                    thread_id,
                    step_dict.get("parentId"),
                    step_dict.get("name"),
                    step_dict.get("type", "run"),
                    int(bool(step_dict.get("streaming", False))),
                    None if step_dict.get("waitForAnswer") is None else int(bool(step_dict.get("waitForAnswer"))),
                    None if step_dict.get("isError") is None else int(bool(step_dict.get("isError"))),
                    _json_dumps(step_dict.get("metadata", {})),
                    _json_dumps(step_dict.get("tags", [])),
                    step_dict.get("input", ""),
                    step_dict.get("output", ""),
                    step_dict.get("createdAt") or utc_now(),
                    step_dict.get("start"),
                    step_dict.get("end"),
                    _json_dumps(step_dict.get("generation", {})),
                    json.dumps(step_dict.get("showInput")) if step_dict.get("showInput") is not None else None,
                    None if step_dict.get("defaultOpen") is None else int(bool(step_dict.get("defaultOpen"))),
                    step_dict.get("language"),
                ),
            )

    def _get_user_sync(self, identifier: str) -> PersistedUser | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, identifier, createdAt, metadata FROM users WHERE identifier = ?",
                (identifier,),
            ).fetchone()
        if not row:
            return None
        return PersistedUser(
            id=row["id"],
            identifier=row["identifier"],
            createdAt=row["createdAt"],
            metadata=_json_loads_dict(row["metadata"]),
        )

    async def get_user(self, identifier: str) -> PersistedUser | None:
        return await self._run(self._get_user_sync, identifier)

    def _create_user_sync(self, user: User) -> PersistedUser:
        existing = self._get_user_sync(user.identifier)
        if existing:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE users SET metadata = ? WHERE identifier = ?",
                    (_json_dumps(user.metadata), user.identifier),
                )
            return PersistedUser(
                id=existing.id,
                identifier=existing.identifier,
                createdAt=existing.createdAt,
                metadata=user.metadata,
            )

        persisted_user = PersistedUser(
            id=str(uuid.uuid4()),
            identifier=user.identifier,
            createdAt=utc_now(),
            metadata=user.metadata,
        )
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO users (id, identifier, createdAt, metadata) VALUES (?, ?, ?, ?)",
                (persisted_user.id, persisted_user.identifier, persisted_user.createdAt, _json_dumps(user.metadata)),
            )
        return persisted_user

    async def create_user(self, user: User) -> PersistedUser | None:
        return await self._run(self._create_user_sync, user)

    def _delete_feedback_sync(self, feedback_id: str) -> bool:
        with self._connect() as conn:
            conn.execute("DELETE FROM feedbacks WHERE id = ?", (feedback_id,))
        return True

    async def delete_feedback(self, feedback_id: str) -> bool:
        return await self._run(self._delete_feedback_sync, feedback_id)

    def _upsert_feedback_sync(self, feedback: Feedback) -> str:
        feedback_id = feedback.id or str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO feedbacks (id, forId, value, comment)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET value = excluded.value, comment = excluded.comment
                """,
                (feedback_id, feedback.forId, float(feedback.value), feedback.comment),
            )
        return feedback_id

    async def upsert_feedback(self, feedback: Feedback) -> str:
        return await self._run(self._upsert_feedback_sync, feedback)

    async def create_element(self, element: Element):
        def _create() -> None:
            with self._connect() as conn:
                if element.thread_id:
                    self._ensure_thread(conn, element.thread_id)
                conn.execute(
                    """
                    INSERT INTO elements (
                        id, threadId, forId, type, chainlitKey, url, objectKey, name,
                        display, size, page, language, autoPlay, playerConfig, mime
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        threadId=excluded.threadId,
                        forId=excluded.forId,
                        type=excluded.type,
                        chainlitKey=excluded.chainlitKey,
                        url=excluded.url,
                        objectKey=excluded.objectKey,
                        name=excluded.name,
                        display=excluded.display,
                        size=excluded.size,
                        page=excluded.page,
                        language=excluded.language,
                        autoPlay=excluded.autoPlay,
                        playerConfig=excluded.playerConfig,
                        mime=excluded.mime
                    """,
                    (
                        element.id,
                        element.thread_id,
                        element.for_id,
                        element.type,
                        element.chainlit_key,
                        element.url,
                        getattr(element, "object_key", None),
                        element.name,
                        element.display,
                        element.size,
                        getattr(element, "page", None),
                        getattr(element, "language", None),
                        None if getattr(element, "auto_play", None) is None else int(bool(element.auto_play)),
                        _json_dumps(getattr(element, "player_config", {})),
                        element.mime,
                    ),
                )

        await self._run(_create)

    def _get_element_sync(self, thread_id: str, element_id: str) -> ElementDict | None:
        with self._connect() as conn:
            row = conn.execute(
                'SELECT * FROM elements WHERE id = ? AND threadId = ?',
                (element_id, thread_id),
            ).fetchone()
        if not row:
            return None
        return ElementDict(
            id=row["id"],
            threadId=row["threadId"],
            type=row["type"],
            chainlitKey=row["chainlitKey"],
            url=row["url"],
            objectKey=row["objectKey"],
            name=row["name"],
            display=row["display"],
            size=row["size"],
            page=row["page"],
            language=row["language"],
            autoPlay=bool(row["autoPlay"]) if row["autoPlay"] is not None else None,
            playerConfig=_json_loads_dict(row["playerConfig"]),
            forId=row["forId"],
            mime=row["mime"],
        )

    async def get_element(self, thread_id: str, element_id: str) -> ElementDict | None:
        return await self._run(self._get_element_sync, thread_id, element_id)

    def _delete_element_sync(self, element_id: str, thread_id: str | None = None) -> None:
        with self._connect() as conn:
            if thread_id:
                conn.execute('DELETE FROM elements WHERE id = ? AND threadId = ?', (element_id, thread_id))
            else:
                conn.execute('DELETE FROM elements WHERE id = ?', (element_id,))

    async def delete_element(self, element_id: str, thread_id: str | None = None):
        await self._run(self._delete_element_sync, element_id, thread_id)

    async def create_step(self, step_dict: StepDict):
        await self._run(self._upsert_step_sync, step_dict)

    async def update_step(self, step_dict: StepDict):
        await self._run(self._upsert_step_sync, step_dict)

    def _delete_step_sync(self, step_id: str) -> None:
        with self._connect() as conn:
            conn.execute('DELETE FROM feedbacks WHERE forId = ?', (step_id,))
            conn.execute('DELETE FROM elements WHERE forId = ?', (step_id,))
            conn.execute('DELETE FROM steps WHERE id = ?', (step_id,))

    async def delete_step(self, step_id: str):
        await self._run(self._delete_step_sync, step_id)

    def _get_thread_author_sync(self, thread_id: str) -> str:
        with self._connect() as conn:
            row = conn.execute('SELECT userIdentifier FROM threads WHERE id = ?', (thread_id,)).fetchone()
        if not row or not row["userIdentifier"]:
            raise ValueError(f"Author not found for thread_id {thread_id}")
        return str(row["userIdentifier"])

    async def get_thread_author(self, thread_id: str) -> str:
        return await self._run(self._get_thread_author_sync, thread_id)

    def _delete_thread_sync(self, thread_id: str) -> None:
        with self._connect() as conn:
            conn.execute('DELETE FROM feedbacks WHERE forId IN (SELECT id FROM steps WHERE threadId = ?)', (thread_id,))
            conn.execute('DELETE FROM elements WHERE threadId = ?', (thread_id,))
            conn.execute('DELETE FROM steps WHERE threadId = ?', (thread_id,))
            conn.execute('DELETE FROM threads WHERE id = ?', (thread_id,))

    async def delete_thread(self, thread_id: str):
        await self._run(self._delete_thread_sync, thread_id)

    def _list_threads_sync(self, pagination: Pagination, filters: ThreadFilter) -> PaginatedResponse[ThreadDict]:
        if not filters.userId:
            return PaginatedResponse(pageInfo=PageInfo(hasNextPage=False, startCursor=None, endCursor=None), data=[])

        limit = pagination.first
        offset = int(pagination.cursor or 0)
        clauses = ['userId = ?']
        params: list[Any] = [filters.userId]

        if filters.search:
            clauses.append('LOWER(COALESCE(name, "")) LIKE ?')
            params.append(f"%{filters.search.lower()}%")

        where_sql = " AND ".join(clauses)
        with self._connect() as conn:
            total_row = conn.execute(f'SELECT COUNT(*) AS count FROM threads WHERE {where_sql}', params).fetchone()
            rows = conn.execute(
                f'''
                SELECT id, createdAt, name, userId, userIdentifier, tags, metadata
                FROM threads
                WHERE {where_sql}
                ORDER BY datetime(createdAt) DESC
                LIMIT ? OFFSET ?
                ''',
                (*params, limit, offset),
            ).fetchall()

        data: list[ThreadDict] = []
        for row in rows:
            data.append(
                ThreadDict(
                    id=row["id"],
                    createdAt=row["createdAt"],
                    name=row["name"],
                    userId=row["userId"],
                    userIdentifier=row["userIdentifier"],
                    tags=_json_loads_list(row["tags"]),
                    metadata=_json_loads_dict(row["metadata"]),
                    steps=[],
                    elements=[],
                )
            )

        total = int(total_row["count"]) if total_row else 0
        end_cursor = str(offset + len(data)) if (offset + len(data)) < total else None
        start_cursor = str(offset) if data else None
        return PaginatedResponse(
            pageInfo=PageInfo(
                hasNextPage=(offset + len(data)) < total,
                startCursor=start_cursor,
                endCursor=end_cursor,
            ),
            data=data,
        )

    async def list_threads(self, pagination: Pagination, filters: ThreadFilter) -> PaginatedResponse[ThreadDict]:
        return await self._run(self._list_threads_sync, pagination, filters)

    def _get_thread_sync(self, thread_id: str) -> ThreadDict | None:
        with self._connect() as conn:
            thread_row = conn.execute(
                'SELECT id, createdAt, name, userId, userIdentifier, tags, metadata FROM threads WHERE id = ?',
                (thread_id,),
            ).fetchone()
            if not thread_row:
                return None

            step_rows = conn.execute(
                '''
                SELECT id, name, type, threadId, parentId, streaming, waitForAnswer, isError,
                       metadata, tags, input, output, createdAt, start, "end", generation,
                       showInput, defaultOpen, language
                FROM steps
                WHERE threadId = ?
                ORDER BY datetime(COALESCE(createdAt, start, "end")) ASC, rowid ASC
                ''',
                (thread_id,),
            ).fetchall()
            element_rows = conn.execute(
                'SELECT * FROM elements WHERE threadId = ? ORDER BY rowid ASC',
                (thread_id,),
            ).fetchall()

        steps: list[StepDict] = []
        for row in step_rows:
            show_input = None
            if row["showInput"] is not None:
                try:
                    show_input = json.loads(row["showInput"])
                except json.JSONDecodeError:
                    show_input = row["showInput"]

            steps.append(
                StepDict(
                    id=row["id"],
                    name=row["name"],
                    type=row["type"],
                    threadId=row["threadId"],
                    parentId=row["parentId"],
                    streaming=bool(row["streaming"]),
                    waitForAnswer=_coerce_bool(row["waitForAnswer"]),
                    isError=_coerce_bool(row["isError"]),
                    metadata=_json_loads_dict(row["metadata"]),
                    tags=_json_loads_list(row["tags"]),
                    input=row["input"] or "",
                    output=row["output"] or "",
                    createdAt=row["createdAt"],
                    start=row["start"],
                    end=row["end"],
                    generation=_json_loads_dict(row["generation"]),
                    showInput=show_input,
                    defaultOpen=_coerce_bool(row["defaultOpen"]),
                    language=row["language"],
                )
            )

        elements: list[ElementDict] = []
        for row in element_rows:
            elements.append(
                ElementDict(
                    id=row["id"],
                    threadId=row["threadId"],
                    type=row["type"],
                    chainlitKey=row["chainlitKey"],
                    url=row["url"],
                    objectKey=row["objectKey"],
                    name=row["name"],
                    display=row["display"],
                    size=row["size"],
                    page=row["page"],
                    language=row["language"],
                    autoPlay=_coerce_bool(row["autoPlay"]),
                    playerConfig=_json_loads_dict(row["playerConfig"]),
                    forId=row["forId"],
                    mime=row["mime"],
                )
            )

        return ThreadDict(
            id=thread_row["id"],
            createdAt=thread_row["createdAt"],
            name=thread_row["name"],
            userId=thread_row["userId"],
            userIdentifier=thread_row["userIdentifier"],
            tags=_json_loads_list(thread_row["tags"]),
            metadata=_json_loads_dict(thread_row["metadata"]),
            steps=steps,
            elements=elements,
        )

    async def get_thread(self, thread_id: str) -> ThreadDict | None:
        return await self._run(self._get_thread_sync, thread_id)

    def _update_thread_sync(
        self,
        thread_id: str,
        name: str | None = None,
        user_id: str | None = None,
        metadata: dict | None = None,
        tags: list[str] | None = None,
    ) -> None:
        with self._connect() as conn:
            existing = conn.execute(
                'SELECT createdAt, name, userId, userIdentifier, tags, metadata FROM threads WHERE id = ?',
                (thread_id,),
            ).fetchone()

            existing_metadata = _json_loads_dict(existing["metadata"]) if existing else {}
            if metadata:
                existing_metadata.update(metadata)

            user_identifier = None
            if user_id:
                user_row = conn.execute('SELECT identifier FROM users WHERE id = ?', (user_id,)).fetchone()
                if user_row:
                    user_identifier = user_row["identifier"]
            elif existing:
                user_id = existing["userId"]
                user_identifier = existing["userIdentifier"]
            else:
                current_user_id, current_identifier = self._get_current_user_fields()
                user_id = user_id or current_user_id
                user_identifier = current_identifier

            conn.execute(
                """
                INSERT INTO threads (id, createdAt, name, userId, userIdentifier, tags, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    userId=excluded.userId,
                    userIdentifier=excluded.userIdentifier,
                    tags=excluded.tags,
                    metadata=excluded.metadata
                """,
                (
                    thread_id,
                    existing["createdAt"] if existing else utc_now(),
                    name if name is not None else (existing["name"] if existing else None),
                    user_id,
                    user_identifier,
                    _json_dumps(tags if tags is not None else (_json_loads_list(existing["tags"]) if existing else [])),
                    _json_dumps(existing_metadata),
                ),
            )

    async def update_thread(
        self,
        thread_id: str,
        name: str | None = None,
        user_id: str | None = None,
        metadata: dict | None = None,
        tags: list[str] | None = None,
    ):
        await self._run(self._update_thread_sync, thread_id, name, user_id, metadata, tags)

    async def build_debug_url(self) -> str:
        return ""

    async def close(self) -> None:
        return None

    def _get_favorite_steps_sync(self, user_id: str) -> list[StepDict]:
        with self._connect() as conn:
            rows = conn.execute(
                '''
                SELECT s.*
                FROM steps s
                JOIN threads t ON t.id = s.threadId
                WHERE t.userId = ?
                ORDER BY datetime(COALESCE(s.createdAt, s.start, s."end")) DESC, s.rowid DESC
                ''',
                (user_id,),
            ).fetchall()

        favorites: list[StepDict] = []
        for row in rows:
            metadata = _json_loads_dict(row["metadata"])
            if not metadata.get("favorite"):
                continue
            favorites.append(
                StepDict(
                    id=row["id"],
                    name=row["name"],
                    type=row["type"],
                    threadId=row["threadId"],
                    parentId=row["parentId"],
                    streaming=bool(row["streaming"]),
                    waitForAnswer=_coerce_bool(row["waitForAnswer"]),
                    isError=_coerce_bool(row["isError"]),
                    metadata=metadata,
                    tags=_json_loads_list(row["tags"]),
                    input=row["input"] or "",
                    output=row["output"] or "",
                    createdAt=row["createdAt"],
                    start=row["start"],
                    end=row["end"],
                    language=row["language"],
                )
            )
        return favorites

    async def get_favorite_steps(self, user_id: str) -> list[StepDict]:
        return await self._run(self._get_favorite_steps_sync, user_id)
