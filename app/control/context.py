from __future__ import annotations

from typing import Iterable

from app.services.session_registry import SessionRegistryService


class ContextAssemblyService:
    def __init__(
        self,
        sessions: SessionRegistryService,
    ) -> None:
        self.sessions = sessions

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
        self.sessions.append_short_memory(session_id, summary)

    def collect_short_memory(self, session_id: str | None) -> list[str]:
        return self.sessions.list_short_memory(session_id)

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
