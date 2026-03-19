from __future__ import annotations

from app.services.session_registry import SessionRegistryService


class SessionMemoryStore:
    _SHORT_MEMORY_LIMIT = 5

    def __init__(self, sessions: SessionRegistryService) -> None:
        self.sessions = sessions

    def append(self, session_id: str, summary: str) -> None:
        normalized = " ".join(summary.strip().split())
        if not normalized:
            return
        session = self.sessions.get_session(session_id)
        current_entries = session.payload.get("short_memory_entries")
        entries = (
            [str(item).strip() for item in current_entries if isinstance(item, str) and str(item).strip()]
            if isinstance(current_entries, list)
            else []
        )
        entries.append(normalized[:500])
        trimmed = entries[-self._SHORT_MEMORY_LIMIT :]
        self.sessions.update_session_payload(
            session_id,
            {
                "short_memory_summary": trimmed[-1],
                "short_memory_entries": trimmed,
            },
        )

    def list(self, session_id: str | None) -> list[str]:
        if not session_id:
            return []
        chain = self.sessions.list_session_chain(session_id)
        summaries: list[str] = []
        for session in chain:
            raw_entries = session.payload.get("short_memory_entries")
            if isinstance(raw_entries, list):
                for item in raw_entries:
                    if isinstance(item, str) and item.strip():
                        summaries.append(item.strip())
                continue
            summary = session.payload.get("short_memory_summary")
            if isinstance(summary, str) and summary.strip():
                summaries.append(summary.strip())
        return summaries
