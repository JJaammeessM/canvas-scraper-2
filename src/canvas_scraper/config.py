"""Configuration management for Canvas Scraper."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class Config:
    """Application configuration."""

    api_url: str
    api_token: str
    output_dir: Path = Path("output")

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> "Config":
        """Load configuration from environment variables.

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

        if not api_url:
            raise ValueError("CANVAS_API_URL not set in environment")
        if not api_token:
            raise ValueError("CANVAS_API_TOKEN not set in environment")

        # Remove trailing slash from URL
        api_url = api_url.rstrip("/")

        return cls(api_url=api_url, api_token=api_token)

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
