"""Hermes-native Lossless Context Management context engine.

This is a small, dependency-free V0 port of the useful parts of
martian-engineering/lossless-claw into Hermes Agent's ContextEngine seam.

Design goals for V0:
- keep the built-in compressor as the default unless ``context.engine`` is set;
- persist raw messages before compaction so recall is lossless;
- replace compacted prompt spans with a deterministic handoff marker that tells
  the model how to recover details;
- expose model-callable ``lcm_*`` tools for grep, describe, expand, and status.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, List, Sequence

from agent.context_engine import ContextEngine

try:  # pragma: no cover - exercised in real Hermes runtime, not unit tests
    from hermes_constants import get_hermes_home
except Exception:  # pragma: no cover
    get_hermes_home = None  # type: ignore[assignment]


_CHARS_PER_TOKEN = 4
_DEFAULT_CONTEXT_LENGTH = 200_000
_MAX_CONTENT_CHARS = 40_000


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return json.dumps(str(value), ensure_ascii=False)


def _content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif item.get("type"):
                    parts.append(f"[{item.get('type')}]")
                else:
                    parts.append(_safe_json(item))
            else:
                parts.append(str(item))
        return "\n".join(p for p in parts if p)
    if isinstance(content, dict):
        if isinstance(content.get("text"), str):
            return content["text"]
        return _safe_json(content)
    return str(content)


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _truncate(text: str, max_chars: int = 220) -> str:
    one_line = re.sub(r"\s+", " ", text).strip()
    if len(one_line) <= max_chars:
        return one_line
    return one_line[: max_chars - 3] + "..."


def _json_response(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _normalise_terms(query: str) -> list[str]:
    quoted = re.findall(r'"([^"]+)"', query)
    if quoted:
        return [term.strip().casefold() for term in quoted if term.strip()]
    return [term.casefold() for term in re.findall(r"[\w-]+", query) if term]


def _matches_full_text(text: str, query: str) -> bool:
    terms = _normalise_terms(query)
    if not terms:
        return False
    folded = text.casefold()
    return all(term in folded for term in terms)


def _hash_message(message: Dict[str, Any], ordinal: int) -> str:
    payload = {
        "ordinal": ordinal,
        "role": message.get("role"),
        "content": message.get("content"),
        "tool_calls": message.get("tool_calls"),
        "name": message.get("name"),
    }
    return sha256(_safe_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class _StoredMessage:
    row_id: int
    role: str
    content: str
    ordinal: int
    created_at: str


class LosslessContextEngine(ContextEngine):
    """A deterministic, SQLite-backed lossless recall engine for Hermes."""

    threshold_percent = 0.75
    protect_first_n = 1
    protect_last_n = 2

    def __init__(
        self,
        *,
        threshold_percent: float = 0.75,
        protect_first_n: int = 1,
        protect_last_n: int = 2,
        db_path: str | Path | None = None,
    ) -> None:
        self.threshold_percent = float(threshold_percent)
        self.protect_first_n = max(0, int(protect_first_n))
        self.protect_last_n = max(1, int(protect_last_n))
        self.context_length = _DEFAULT_CONTEXT_LENGTH
        self.threshold_tokens = int(self.context_length * self.threshold_percent)
        self.compression_count = 0
        self.last_prompt_tokens = 0
        self.last_completion_tokens = 0
        self.last_total_tokens = 0
        self._db_path_override = Path(db_path) if db_path else None
        self._db_path: Path | None = None
        self._conn: sqlite3.Connection | None = None
        self._session_id = ""
        self._conversation_key = ""
        self._conversation_pk: int | None = None

    @property
    def name(self) -> str:
        return "lossless"

    def is_available(self) -> bool:
        return True

    # ------------------------------------------------------------------
    # Lifecycle / model state
    # ------------------------------------------------------------------

    def update_model(
        self,
        model: str,
        context_length: int,
        base_url: str = "",
        api_key: str = "",
        provider: str = "",
        api_mode: str = "",
    ) -> None:
        self.context_length = int(context_length or _DEFAULT_CONTEXT_LENGTH)
        self.threshold_tokens = int(self.context_length * self.threshold_percent)

    def update_from_response(self, usage: Dict[str, Any]) -> None:
        self.last_prompt_tokens = int(usage.get("prompt_tokens") or 0)
        self.last_completion_tokens = int(usage.get("completion_tokens") or 0)
        self.last_total_tokens = int(
            usage.get("total_tokens")
            or self.last_prompt_tokens + self.last_completion_tokens
        )

    def should_compress(self, prompt_tokens: int | None = None) -> bool:
        tokens = int(prompt_tokens if prompt_tokens is not None else self.last_prompt_tokens)
        return tokens >= self.threshold_tokens

    def should_compress_preflight(self, messages: List[Dict[str, Any]]) -> bool:
        rough_tokens = sum(_estimate_tokens(_content_to_text(msg.get("content"))) for msg in messages)
        return rough_tokens >= self.threshold_tokens and self.has_content_to_compress(messages)

    def has_content_to_compress(self, messages: List[Dict[str, Any]]) -> bool:
        start, end = self._compression_bounds(messages)
        return start < end

    def on_session_start(self, session_id: str, **kwargs: Any) -> None:
        self._session_id = session_id or "unknown-session"
        old_session_id = str(kwargs.get("old_session_id") or "").strip()
        conversation_id = kwargs.get("conversation_id")
        self._conversation_key = str(conversation_id or old_session_id or self._session_id)
        hermes_home = kwargs.get("hermes_home")
        self._ensure_db(hermes_home=hermes_home)
        self._conversation_pk = self._ensure_conversation(
            session_id=self._session_id,
            conversation_key=self._conversation_key,
            parent_session_id=old_session_id or None,
        )

    def on_session_end(self, session_id: str, messages: List[Dict[str, Any]]) -> None:
        if session_id and not self._session_id:
            self.on_session_start(session_id)
        if messages:
            self._ingest_messages(messages)
        if self._conn is not None:
            self._conn.commit()

    def on_session_reset(self) -> None:
        super().on_session_reset()
        self._session_id = ""
        self._conversation_key = ""
        self._conversation_pk = None

    # ------------------------------------------------------------------
    # Compression
    # ------------------------------------------------------------------

    def compress(
        self,
        messages: List[Dict[str, Any]],
        current_tokens: int | None = None,
        focus_topic: str | None = None,
        force: bool = False,
    ) -> List[Dict[str, Any]]:
        if not messages:
            return messages
        if not self._session_id:
            self.on_session_start("lossless-session")
        stored = self._ingest_messages(messages)
        start, end = self._compression_bounds(messages)
        if start >= end:
            return messages

        source_rows = stored[start:end]
        if not source_rows:
            return messages
        summary_id = self._store_summary(source_rows, focus_topic=focus_topic)
        summary_text = self._build_summary_marker(summary_id, source_rows, focus_topic=focus_topic)

        head = [m.copy() for m in messages[:start]]
        tail = [m.copy() for m in messages[end:]]
        summary_role = self._summary_role(
            previous_role=head[-1].get("role") if head else None,
            next_role=tail[0].get("role") if tail else None,
        )
        compressed = head + [{"role": summary_role, "content": summary_text}] + tail
        self.compression_count += 1
        self.last_prompt_tokens = -1
        self.last_total_tokens = 0
        return compressed

    def _compression_bounds(self, messages: Sequence[Dict[str, Any]]) -> tuple[int, int]:
        if len(messages) <= 3:
            return len(messages), len(messages)
        # Always keep the system prompt if present, plus protect_first_n normal messages.
        start = 1 if messages and messages[0].get("role") == "system" else 0
        non_system_seen = 0
        index = start
        while index < len(messages) and non_system_seen < self.protect_first_n:
            non_system_seen += 1
            index += 1
        start = index
        end = max(start, len(messages) - self.protect_last_n)
        return start, end

    def _summary_role(self, previous_role: Any, next_role: Any) -> str:
        for role in ("assistant", "user"):
            if role != previous_role and role != next_role:
                return role
        return "assistant"

    def _build_summary_marker(
        self,
        summary_id: str,
        source_rows: Sequence[_StoredMessage],
        *,
        focus_topic: str | None = None,
    ) -> str:
        earliest = source_rows[0].created_at
        latest = source_rows[-1].created_at
        source_ids = [f"msg_{row.row_id}" for row in source_rows]
        bullets = "\n".join(
            f"- {row.role}: {_truncate(row.content, 180)}" for row in source_rows[:8]
        )
        if len(source_rows) > 8:
            bullets += f"\n- ... {len(source_rows) - 8} additional source message(s)"
        focus_line = f"\nFocus hint: {focus_topic}" if focus_topic else ""
        return (
            f"## LOSSLESS CONTEXT SUMMARY ({summary_id})\n"
            f"Earlier turns were compacted out of the active prompt, but their "
            f"raw contents were persisted losslessly. Use lcm_grep to find details, "
            f"lcm_describe to inspect an ID, and lcm_expand to recover this span.\n"
            f"Source messages: {', '.join(source_ids)}\n"
            f"Time range: {earliest} → {latest}{focus_line}\n\n"
            f"Preview:\n{bullets}\n\n"
            "--- END LOSSLESS CONTEXT SUMMARY — respond to the live user message below ---"
        )

    # ------------------------------------------------------------------
    # Tool surface
    # ------------------------------------------------------------------

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "lcm_grep",
                "description": (
                    "Search losslessly persisted conversation messages and summaries. "
                    "Use this when needed details may have been compacted out of active context."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "Regex or full-text query."},
                        "mode": {"type": "string", "enum": ["regex", "full_text"], "default": "regex"},
                        "scope": {"type": "string", "enum": ["messages", "summaries", "both"], "default": "both"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50},
                        "allConversations": {"type": "boolean", "default": False},
                    },
                    "required": ["pattern"],
                },
            },
            {
                "name": "lcm_describe",
                "description": "Describe a persisted LCM item by ID, e.g. msg_123 or sum_abcd.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "allConversations": {"type": "boolean", "default": False},
                    },
                    "required": ["id"],
                },
            },
            {
                "name": "lcm_expand",
                "description": "Recover source messages for one or more lossless summary IDs.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "summaryIds": {"type": "array", "items": {"type": "string"}},
                        "query": {"type": "string"},
                        "includeMessages": {"type": "boolean", "default": False},
                        "tokenCap": {"type": "integer", "minimum": 1, "default": 4000},
                        "allConversations": {"type": "boolean", "default": False},
                    },
                },
            },
            {
                "name": "lcm_status",
                "description": "Show status for the active lossless context engine store.",
                "parameters": {"type": "object", "properties": {}},
            },
        ]

    def handle_tool_call(self, name: str, args: Dict[str, Any], **kwargs: Any) -> str:
        try:
            messages = kwargs.get("messages")
            if isinstance(messages, list) and messages:
                self._ingest_messages(messages)
            if name == "lcm_grep":
                return self._tool_grep(args)
            if name == "lcm_describe":
                return self._tool_describe(args)
            if name == "lcm_expand":
                return self._tool_expand(args)
            if name == "lcm_status":
                return self._tool_status()
            return _json_response({"success": False, "error": f"Unknown context engine tool: {name}"})
        except Exception as exc:  # Tools must fail closed as JSON, not crash the agent loop.
            return _json_response({"success": False, "error": f"{type(exc).__name__}: {exc}"})

    def _tool_grep(self, args: Dict[str, Any]) -> str:
        pattern = str(args.get("pattern") or "").strip()
        if not pattern:
            return _json_response({"success": False, "error": "pattern is required"})
        mode = str(args.get("mode") or "regex")
        scope = str(args.get("scope") or "both")
        limit = max(1, min(200, int(args.get("limit") or 50)))
        all_conversations = bool(args.get("allConversations"))

        rows = self._search_rows(pattern, mode=mode, scope=scope, all_conversations=all_conversations)
        rows = rows[:limit]
        lines = ["## LCM Grep Results", f"Pattern: `{pattern}`", f"Mode: {mode} | Scope: {scope}", ""]
        matches: list[dict[str, Any]] = []
        for row in rows:
            item_id = row["item_id"]
            snippet = _truncate(row["content"], 360)
            matches.append({
                "id": item_id,
                "type": row["type"],
                "role": row.get("role"),
                "created_at": row["created_at"],
                "snippet": snippet,
            })
            lines.append(f"- `{item_id}` ({row['type']}): {snippet}")
        if not matches:
            lines.append("No matches.")
        return _json_response({
            "success": True,
            "total_matches": len(matches),
            "matches": matches,
            "content": "\n".join(lines),
        })

    def _tool_describe(self, args: Dict[str, Any]) -> str:
        item_id = str(args.get("id") or "").strip()
        if not item_id:
            return _json_response({"success": False, "error": "id is required"})
        item = self._describe_item(item_id, all_conversations=bool(args.get("allConversations")))
        if item is None:
            return _json_response({"success": False, "error": f"Not found: {item_id}"})
        return _json_response({"success": True, "item": item, "content": self._format_item(item)})

    def _tool_expand(self, args: Dict[str, Any]) -> str:
        summary_ids = [str(s).strip() for s in (args.get("summaryIds") or []) if str(s).strip()]
        query = str(args.get("query") or "").strip()
        all_conversations = bool(args.get("allConversations"))
        if not summary_ids and query:
            summary_ids = [
                row["item_id"]
                for row in self._search_rows(
                    query,
                    mode="full_text",
                    scope="summaries",
                    all_conversations=all_conversations,
                )[:5]
            ]
        if not summary_ids:
            return _json_response({"success": False, "error": "Provide summaryIds or query"})

        include_messages = bool(args.get("includeMessages"))
        token_cap = max(1, int(args.get("tokenCap") or 4000))
        char_cap = token_cap * _CHARS_PER_TOKEN
        sections: list[str] = []
        expanded: list[str] = []
        used_chars = 0
        for summary_id in summary_ids:
            summary = self._describe_summary(summary_id, all_conversations=all_conversations)
            if not summary:
                continue
            expanded.append(summary_id)
            section_lines = [f"## {summary_id}", summary["content"]]
            if include_messages:
                sources = self._source_messages_for_summary(summary_id)
                section_lines.append("\nSource messages:")
                for msg in sources:
                    section_lines.append(f"- `{msg['id']}` {msg['role']}: {msg['content']}")
            section = "\n".join(section_lines)
            remaining = char_cap - used_chars
            if remaining <= 0:
                break
            if len(section) > remaining:
                section = section[: max(0, remaining - 30)] + "\n[truncated by tokenCap]"
                sections.append(section)
                used_chars = char_cap
                break
            sections.append(section)
            used_chars += len(section)
        return _json_response({
            "success": True,
            "expanded_summary_ids": expanded,
            "truncated": used_chars >= char_cap,
            "content": "\n\n".join(sections) if sections else "No matching summaries found.",
        })

    def _tool_status(self) -> str:
        conn = self._ensure_db()
        cur = conn.execute("SELECT COUNT(*) FROM conversations")
        conversations = int(cur.fetchone()[0])
        cur = conn.execute("SELECT COUNT(*) FROM messages")
        messages = int(cur.fetchone()[0])
        cur = conn.execute("SELECT COUNT(*) FROM summaries")
        summaries = int(cur.fetchone()[0])
        return _json_response({
            "success": True,
            "engine": self.name,
            "db_path": str(self._db_path or ""),
            "session_id": self._session_id,
            "conversation_key": self._conversation_key,
            "conversation_count": conversations,
            "message_count": messages,
            "summary_count": summaries,
            "compression_count": self.compression_count,
            "threshold_tokens": self.threshold_tokens,
            "context_length": self.context_length,
        })

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _resolve_db_path(self, hermes_home: Any = None) -> Path:
        if self._db_path_override is not None:
            return self._db_path_override
        if hermes_home:
            home = Path(str(hermes_home)).expanduser()
        elif os.getenv("HERMES_HOME"):
            home = Path(os.environ["HERMES_HOME"]).expanduser()
        elif get_hermes_home is not None:
            home = Path(get_hermes_home())
        else:
            home = Path.home() / ".hermes"
        return home / "context_engines" / "lossless" / "lossless_context.db"

    def _ensure_db(self, hermes_home: Any = None) -> sqlite3.Connection:
        db_path = self._resolve_db_path(hermes_home)
        if self._conn is not None and self._db_path == db_path:
            return self._conn
        if self._conn is not None:
            self._conn.close()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        self._conn = conn
        self._db_path = db_path
        self._init_schema(conn)
        return conn

    def _init_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_key TEXT NOT NULL UNIQUE,
                session_id TEXT NOT NULL,
                parent_session_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                session_id TEXT NOT NULL,
                ordinal INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                content_json TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(conversation_id, ordinal, content_hash)
            );
            CREATE INDEX IF NOT EXISTS idx_lossless_messages_conversation
                ON messages(conversation_id, id);
            CREATE TABLE IF NOT EXISTS summaries (
                summary_id TEXT PRIMARY KEY,
                conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                session_id TEXT NOT NULL,
                content TEXT NOT NULL,
                source_count INTEGER NOT NULL,
                token_count INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS summary_sources (
                summary_id TEXT NOT NULL REFERENCES summaries(summary_id) ON DELETE CASCADE,
                message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
                source_order INTEGER NOT NULL,
                PRIMARY KEY(summary_id, message_id)
            );
            """
        )
        conn.commit()

    def _ensure_conversation(
        self,
        *,
        session_id: str,
        conversation_key: str,
        parent_session_id: str | None = None,
    ) -> int:
        conn = self._ensure_db()
        now = _utc_now()
        conn.execute(
            """
            INSERT INTO conversations(conversation_key, session_id, parent_session_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(conversation_key) DO UPDATE SET
                session_id=excluded.session_id,
                updated_at=excluded.updated_at
            """,
            (conversation_key, session_id, parent_session_id, now, now),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id FROM conversations WHERE conversation_key = ?",
            (conversation_key,),
        ).fetchone()
        return int(row["id"])

    def _current_conversation_pk(self) -> int:
        if self._conversation_pk is None:
            self.on_session_start(self._session_id or "lossless-session")
        assert self._conversation_pk is not None
        return self._conversation_pk

    def _ingest_messages(self, messages: Sequence[Dict[str, Any]]) -> list[_StoredMessage]:
        conn = self._ensure_db()
        conversation_id = self._current_conversation_pk()
        stored: list[_StoredMessage] = []
        for ordinal, message in enumerate(messages):
            if not isinstance(message, dict):
                continue
            role = str(message.get("role") or "unknown")
            content = _content_to_text(message.get("content"))
            if not content.strip() and not message.get("tool_calls"):
                continue
            content_json = _safe_json(message.get("content"))
            content_hash = _hash_message(message, ordinal)
            created_at = _utc_now()
            conn.execute(
                """
                INSERT OR IGNORE INTO messages(
                    conversation_id, session_id, ordinal, role, content,
                    content_json, content_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conversation_id,
                    self._session_id or "lossless-session",
                    ordinal,
                    role,
                    content,
                    content_json,
                    content_hash,
                    created_at,
                ),
            )
            row = conn.execute(
                """
                SELECT id, role, content, ordinal, created_at
                FROM messages
                WHERE conversation_id = ? AND ordinal = ? AND content_hash = ?
                """,
                (conversation_id, ordinal, content_hash),
            ).fetchone()
            if row:
                stored.append(
                    _StoredMessage(
                        row_id=int(row["id"]),
                        role=str(row["role"]),
                        content=str(row["content"]),
                        ordinal=int(row["ordinal"]),
                        created_at=str(row["created_at"]),
                    )
                )
        conn.commit()
        return stored

    def _store_summary(
        self,
        source_rows: Sequence[_StoredMessage],
        *,
        focus_topic: str | None = None,
    ) -> str:
        conn = self._ensure_db()
        conversation_id = self._current_conversation_pk()
        digest = sha256(
            (str(conversation_id) + ":" + ":".join(str(row.row_id) for row in source_rows)).encode("utf-8")
        ).hexdigest()[:16]
        summary_id = f"sum_{digest}"
        content = self._build_summary_marker(summary_id, source_rows, focus_topic=focus_topic)
        now = _utc_now()
        conn.execute(
            """
            INSERT OR REPLACE INTO summaries(
                summary_id, conversation_id, session_id, content,
                source_count, token_count, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary_id,
                conversation_id,
                self._session_id or "lossless-session",
                content,
                len(source_rows),
                _estimate_tokens(content),
                now,
            ),
        )
        for index, row in enumerate(source_rows):
            conn.execute(
                """
                INSERT OR IGNORE INTO summary_sources(summary_id, message_id, source_order)
                VALUES (?, ?, ?)
                """,
                (summary_id, row.row_id, index),
            )
        conn.commit()
        return summary_id

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def _conversation_filter(self, all_conversations: bool) -> tuple[str, tuple[Any, ...]]:
        if all_conversations:
            return "", ()
        return "WHERE conversation_id = ?", (self._current_conversation_pk(),)

    def _search_rows(
        self,
        pattern: str,
        *,
        mode: str,
        scope: str,
        all_conversations: bool,
    ) -> list[dict[str, Any]]:
        conn = self._ensure_db()
        rows: list[dict[str, Any]] = []
        where, params = self._conversation_filter(all_conversations)
        if scope in {"messages", "both"}:
            for row in conn.execute(
                f"SELECT id, role, content, created_at FROM messages {where} ORDER BY id DESC",
                params,
            ):
                content = str(row["content"])
                if self._text_matches(content, pattern, mode):
                    rows.append({
                        "item_id": f"msg_{row['id']}",
                        "type": "message",
                        "role": row["role"],
                        "content": content,
                        "created_at": row["created_at"],
                    })
        if scope in {"summaries", "both"}:
            for row in conn.execute(
                f"SELECT summary_id, content, created_at FROM summaries {where} ORDER BY created_at DESC",
                params,
            ):
                content = str(row["content"])
                if self._text_matches(content, pattern, mode):
                    rows.append({
                        "item_id": row["summary_id"],
                        "type": "summary",
                        "role": "assistant",
                        "content": content,
                        "created_at": row["created_at"],
                    })
        # Prefer raw messages over generated summaries when both match the same
        # query: the whole point of a lossless engine is that callers can land
        # directly on original evidence, then expand summaries when needed.
        rows.sort(key=lambda item: (0 if item["type"] == "message" else 1, item["created_at"]), reverse=False)
        return rows

    def _text_matches(self, text: str, pattern: str, mode: str) -> bool:
        if mode == "full_text":
            return _matches_full_text(text, pattern)
        try:
            return re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE) is not None
        except re.error:
            return pattern.casefold() in text.casefold()

    def _describe_item(self, item_id: str, *, all_conversations: bool) -> dict[str, Any] | None:
        if item_id.startswith("msg_"):
            try:
                row_id = int(item_id[4:])
            except ValueError:
                return None
            where_extra = "" if all_conversations else " AND conversation_id = ?"
            params: tuple[Any, ...] = (row_id,) if all_conversations else (row_id, self._current_conversation_pk())
            row = self._ensure_db().execute(
                f"""
                SELECT id, conversation_id, session_id, ordinal, role, content, created_at
                FROM messages WHERE id = ?{where_extra}
                """,
                params,
            ).fetchone()
            if not row:
                return None
            return {
                "id": f"msg_{row['id']}",
                "type": "message",
                "conversation_id": row["conversation_id"],
                "session_id": row["session_id"],
                "ordinal": row["ordinal"],
                "role": row["role"],
                "content": row["content"],
                "created_at": row["created_at"],
            }
        if item_id.startswith("sum_"):
            return self._describe_summary(item_id, all_conversations=all_conversations)
        return None

    def _describe_summary(self, summary_id: str, *, all_conversations: bool) -> dict[str, Any] | None:
        where_extra = "" if all_conversations else " AND conversation_id = ?"
        params: tuple[Any, ...] = (summary_id,) if all_conversations else (summary_id, self._current_conversation_pk())
        row = self._ensure_db().execute(
            f"""
            SELECT summary_id, conversation_id, session_id, content, source_count, token_count, created_at
            FROM summaries WHERE summary_id = ?{where_extra}
            """,
            params,
        ).fetchone()
        if not row:
            return None
        return {
            "id": row["summary_id"],
            "type": "summary",
            "conversation_id": row["conversation_id"],
            "session_id": row["session_id"],
            "content": row["content"],
            "source_count": row["source_count"],
            "token_count": row["token_count"],
            "created_at": row["created_at"],
            "source_message_ids": [msg["id"] for msg in self._source_messages_for_summary(summary_id)],
        }

    def _source_messages_for_summary(self, summary_id: str) -> list[dict[str, Any]]:
        rows = self._ensure_db().execute(
            """
            SELECT m.id, m.role, m.content, m.ordinal, m.created_at
            FROM summary_sources ss
            JOIN messages m ON m.id = ss.message_id
            WHERE ss.summary_id = ?
            ORDER BY ss.source_order ASC
            """,
            (summary_id,),
        ).fetchall()
        return [
            {
                "id": f"msg_{row['id']}",
                "role": row["role"],
                "content": row["content"],
                "ordinal": row["ordinal"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def _format_item(self, item: dict[str, Any]) -> str:
        header = f"## {item['id']} ({item['type']})"
        content = str(item.get("content") or "")
        if len(content) > _MAX_CONTENT_CHARS:
            content = content[:_MAX_CONTENT_CHARS] + "\n[truncated]"
        return f"{header}\n{content}"

    def get_status(self) -> Dict[str, Any]:
        base = super().get_status()
        base.update(
            {
                "engine": self.name,
                "db_path": str(self._db_path or self._resolve_db_path()),
                "session_id": self._session_id,
                "conversation_key": self._conversation_key,
            }
        )
        return base


__all__ = ["LosslessContextEngine"]
