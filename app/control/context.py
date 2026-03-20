from __future__ import annotations

from pathlib import Path

from app.control.session_registry import SessionRegistryService


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
        updated_session = self.sessions.update_session_payload(
            session_id,
            {
                "short_memory_summary": trimmed[-1],
                "short_memory_entries": trimmed,
            },
        )
        self._write_memory_artifact(updated_session, trimmed)

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

    def _write_memory_artifact(self, session, entries: list[str]) -> None:  # noqa: ANN001
        artifact_path = self._artifact_path(session)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(
            self._render_memory_markdown(session, entries),
            encoding="utf-8",
        )

    def _artifact_path(self, session) -> Path:  # noqa: ANN001
        root = self.sessions.settings.project_root / "artifacts" / "memory"
        if session.session_type == "user_session":
            return root / "sessions" / f"{session.session_id}.md"
        agent_segment = session.agent_id or "unknown-agent"
        return root / "agents" / agent_segment / f"{session.session_id}.md"

    def _render_memory_markdown(self, session, entries: list[str]) -> str:  # noqa: ANN001
        if session.session_type == "user_session":
            header = "# Session Memory"
            metadata = [
                f"- Session ID: {session.session_id}",
                f"- User ID: {session.user_id or 'n/a'}",
                f"- Source: {session.source or 'n/a'}",
                f"- Active Agent: {session.payload.get('active_agent') or 'n/a'}",
            ]
        else:
            header = "# Agent Memory"
            metadata = [
                f"- Session ID: {session.session_id}",
                f"- Agent ID: {session.agent_id or 'n/a'}",
                f"- User ID: {session.user_id or 'n/a'}",
                f"- Source: {session.source or 'n/a'}",
            ]
        memory_lines = "\n".join(f"- {item}" for item in entries)
        return (
            f"{header}\n\n"
            "## Metadata\n"
            f"{'\n'.join(metadata)}\n\n"
            "## Recent Entries\n"
            f"{memory_lines}\n"
        )


class ContextAssemblyService:
    def __init__(
        self,
        sessions: SessionRegistryService,
        memory: SessionMemoryStore | None = None,
    ) -> None:
        self.sessions = sessions
        self.memory = memory or SessionMemoryStore(sessions)

    def build_main_agent_input(
        self,
        user_session_id: str,
        content: str,
    ) -> str:
        return self._compose(
            session_id=user_session_id,
            current_input=content,
            heading="Current User Request",
        )

    def build_agent_input(
        self,
        *,
        session_id: str | None,
        current_input: str,
        heading: str = "Current Context",
    ) -> str:
        if not session_id:
            return current_input
        return self._compose(
            session_id=session_id,
            current_input=current_input,
            heading=heading,
        )

    def record_short_memory(
        self,
        session_id: str,
        summary: str,
    ) -> None:
        self.memory.append(session_id, summary)

    def collect_short_memory(self, session_id: str | None) -> list[str]:
        return self.memory.list(session_id)

    def _compose(
        self,
        *,
        session_id: str,
        current_input: str,
        heading: str,
    ) -> str:
        memories = self.collect_short_memory(session_id)
        sections: list[str] = []
        if memories:
            sections.append(
                "Short Memory:\n" + "\n".join(f"- {item}" for item in memories)
            )
        sections.append(f"{heading}:\n{current_input}")
        return "\n\n".join(section for section in sections if section.strip())
