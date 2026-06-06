"""Configuration management for Canvas Scraper."""

import json
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_CREDENTIALS_PATH = Path.home() / ".canvas_scraper" / "credentials.json"


@dataclass
class Config:
    """Application configuration."""

    api_url: str
    api_token: str
    output_dir: Path = Path("output")

    @classmethod
    def load(cls) -> "Config | None":
        """Load saved credentials from ~/.canvas_scraper/credentials.json."""
        if not _CREDENTIALS_PATH.exists():
            return None
        try:
            data = json.loads(_CREDENTIALS_PATH.read_text())
            return cls(api_url=data["api_url"], api_token=data["api_token"])
        except (KeyError, json.JSONDecodeError, OSError):
            return None

    def save(self) -> None:
        """Save credentials to ~/.canvas_scraper/credentials.json."""
        _CREDENTIALS_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CREDENTIALS_PATH.write_text(
            json.dumps({"api_url": self.api_url, "api_token": self.api_token}, indent=2)
        )

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> "Config":
        """Load configuration from environment variables, falling back to saved credentials.

        Args:
            env_file: Optional path to .env file. Defaults to .env in current directory.

        Returns:
            Config instance with loaded values.

        Raises:
            ValueError: If required configuration is missing.
        """
        if env_file:
            load_dotenv(env_file)
        else:
            load_dotenv()

        api_url = os.getenv("CANVAS_API_URL")
        api_token = os.getenv("CANVAS_API_TOKEN")

        if api_url and api_token:
            return cls(api_url=api_url.rstrip("/"), api_token=api_token)

        # Fall back to saved credentials
        saved = cls.load()
        if saved:
            return saved

        missing = []
        if not api_url:
            missing.append("CANVAS_API_URL")
        if not api_token:
            missing.append("CANVAS_API_TOKEN")
        raise ValueError(
            f"Missing configuration: {', '.join(missing)}. "
            "Run 'canvas-scraper setup' to configure credentials."
        )

    def validate(self) -> bool:
        """Validate the configuration.

        Returns:
            True if configuration is valid.

        Raises:
            ValueError: If configuration is invalid.
        """
        if not self.api_url.startswith(("http://", "https://")):
            raise ValueError(f"Invalid API URL: {self.api_url}")

        if len(self.api_token) < 10:
            raise ValueError("API token appears to be invalid (too short)")

        return True
