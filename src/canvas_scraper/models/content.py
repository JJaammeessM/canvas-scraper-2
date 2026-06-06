"""Data models for Canvas content."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ContentType(Enum):
    """Types of content that can be scraped from Canvas."""

    PAGE = "Page"
    FILE = "File"
    ASSIGNMENT = "Assignment"
    DISCUSSION = "Discussion"
    QUIZ = "Quiz"
    EXTERNAL_URL = "ExternalUrl"
    EXTERNAL_TOOL = "ExternalTool"
    SUB_HEADER = "SubHeader"


@dataclass
class PageContent:
    """Represents a Canvas wiki page."""

    title: str
    body: str  # HTML content
    url: str
    created_at: str | None = None
    updated_at: str | None = None


@dataclass
class ModuleItemContent:
    """Represents a single item within a module."""

    id: int
    title: str
    content_type: ContentType
    position: int
    html_content: str = ""
    url: str | None = None
    external_url: str | None = None
    file_path: str | None = None
    indent: int = 0
    raw_data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api_item(cls, item: Any) -> "ModuleItemContent":
        """Create from Canvas API module item object.

        Args:
            item: Canvas API module item object.

        Returns:
            ModuleItemContent instance.
        """
        content_type = ContentType(item.type) if item.type in [e.value for e in ContentType] else ContentType.PAGE

        return cls(
            id=item.id,
            title=item.title,
            content_type=content_type,
            position=getattr(item, "position", 0),
            url=getattr(item, "url", None),
            external_url=getattr(item, "external_url", None),
            indent=getattr(item, "indent", 0),
            raw_data=item.__dict__.get("_attrs", {}),
        )


@dataclass
class ModuleContent:
    """Represents a Canvas module with all its items."""

    id: int
    name: str
    position: int
    items: list[ModuleItemContent] = field(default_factory=list)
    state: str = "active"

    @classmethod
    def from_api_module(cls, module: Any) -> "ModuleContent":
        """Create from Canvas API module object.

        Args:
            module: Canvas API module object.

        Returns:
            ModuleContent instance.
        """
        return cls(
            id=module.id,
            name=module.name,
            position=getattr(module, "position", 0),
            state=getattr(module, "state", "active"),
        )
