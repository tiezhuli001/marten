from pathlib import Path


class StatusService:
    def __init__(self, status_path: str = "docs/status/current-status.md") -> None:
        self.status_path = Path(status_path)

    def read_current_status(self) -> str:
        if not self.status_path.exists():
            return "Status document not found."
        return self.status_path.read_text(encoding="utf-8")
