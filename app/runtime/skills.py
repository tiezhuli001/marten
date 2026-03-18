from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from shutil import which
from typing import Any

from app.core.config import Settings


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    path: Path
    instructions: str
    metadata: dict[str, object]


class SkillLoader:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.shared_skills_dir = settings.resolved_skills_root_dir

    def discover(self, workspace: Path | None = None) -> dict[str, Skill]:
        locations: list[Path] = []
        if self.shared_skills_dir.exists():
            locations.append(self.shared_skills_dir)
        if workspace is not None:
            workspace_skills_dir = workspace / "skills"
            if workspace_skills_dir.exists():
                locations.append(workspace_skills_dir)

        discovered: dict[str, Skill] = {}
        for base_dir in locations:
            for skill_dir in sorted(path for path in base_dir.iterdir() if path.is_dir()):
                skill_path = skill_dir / "SKILL.md"
                if not skill_path.exists():
                    continue
                skill = self._load_skill(skill_path)
                if self._is_eligible(skill):
                    discovered[skill.name] = skill
        return discovered

    def resolve(self, names: list[str], workspace: Path | None = None) -> list[Skill]:
        available = self.discover(workspace)
        return [available[name] for name in names if name in available]

    def render_skill_catalog(self, names: list[str], workspace: Path | None = None) -> str:
        skills = self.resolve(names, workspace)
        if not skills:
            return "No eligible skills are configured."
        lines = []
        for skill in skills:
            lines.append(f"- {skill.name}: {skill.description}")
            lines.append(f"  path={skill.path}")
        return "\n".join(lines)

    def _load_skill(self, path: Path) -> Skill:
        content = path.read_text(encoding="utf-8")
        metadata: dict[str, object] = {}
        body = content
        if content.startswith("---\n"):
            _, frontmatter, body = content.split("---\n", 2)
            metadata = self._parse_frontmatter(frontmatter)
        name = str(metadata.get("name") or path.parent.name)
        description = str(metadata.get("description") or "No description provided.")
        return Skill(
            name=name,
            description=description,
            path=path,
            instructions=body.strip(),
            metadata=metadata,
        )

    def _parse_frontmatter(self, frontmatter: str) -> dict[str, object]:
        lines = frontmatter.splitlines()
        parsed: dict[str, object] = {}
        index = 0
        while index < len(lines):
            raw_line = lines[index]
            line = raw_line.strip()
            index += 1
            if not line or line.startswith("#") or ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if key == "metadata":
                metadata_value, index = self._consume_json_block(lines, index, value)
                parsed[key] = metadata_value
                continue
            parsed[key] = value.strip("'\"")
        return parsed

    def _consume_json_block(
        self,
        lines: list[str],
        start_index: int,
        initial_value: str,
    ) -> tuple[dict[str, object], int]:
        if initial_value:
            return self._parse_json_object(initial_value), start_index

        buffer: list[str] = []
        brace_depth = 0
        index = start_index
        while index < len(lines):
            candidate = lines[index].strip()
            if not candidate:
                index += 1
                if buffer and brace_depth <= 0:
                    break
                continue
            if not buffer and not candidate.startswith("{"):
                break
            buffer.append(candidate)
            brace_depth += candidate.count("{") - candidate.count("}")
            index += 1
            if buffer and brace_depth <= 0:
                break
        return self._parse_json_object(" ".join(buffer)), index

    def _parse_json_object(self, raw: str) -> dict[str, object]:
        try:
            loaded = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return loaded if isinstance(loaded, dict) else {}

    def _is_eligible(self, skill: Skill) -> bool:
        openclaw_meta = self._openclaw_metadata(skill)
        if openclaw_meta.get("always") is True:
            return True
        supported_os = openclaw_meta.get("os")
        if isinstance(supported_os, list) and supported_os:
            current_os = self._current_os_name()
            if current_os not in {str(item) for item in supported_os}:
                return False

        requires = openclaw_meta.get("requires")
        if not isinstance(requires, dict):
            return True

        bins = self._as_string_list(requires.get("bins"))
        if bins and any(which(binary) is None for binary in bins):
            return False

        any_bins = self._as_string_list(requires.get("anyBins"))
        if any_bins and all(which(binary) is None for binary in any_bins):
            return False

        required_env = self._as_string_list(requires.get("env"))
        if required_env and any(not os.getenv(env_name) for env_name in required_env):
            return False

        required_config = self._as_string_list(requires.get("config"))
        if required_config and any(not getattr(self.settings, config_name, None) for config_name in required_config):
            return False

        return True

    def _openclaw_metadata(self, skill: Skill) -> dict[str, Any]:
        metadata = skill.metadata.get("metadata")
        if not isinstance(metadata, dict):
            return {}
        openclaw_meta = metadata.get("openclaw")
        return openclaw_meta if isinstance(openclaw_meta, dict) else {}

    def _as_string_list(self, value: object) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []

    def _current_os_name(self) -> str:
        if sys.platform.startswith("darwin"):
            return "darwin"
        if sys.platform.startswith("linux"):
            return "linux"
        if sys.platform.startswith("win"):
            return "win32"
        return sys.platform
