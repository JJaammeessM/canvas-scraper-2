"""Scraper for Canvas files and attachments."""

import logging
import re
from pathlib import Path
from typing import Any

from ..api.client import CanvasClient

logger = logging.getLogger(__name__)


class FileScraper:
    """Handles downloading files from Canvas."""

    # File extensions that can be embedded in PDFs
    EMBEDDABLE_IMAGES = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}
    EMBEDDABLE_DOCUMENTS = {".pdf"}

    def __init__(self, client: CanvasClient, download_dir: Path):
        """Initialize the file scraper.

        Args:
            client: Canvas API client.
            download_dir: Directory to store downloaded files.
        """
        self.client = client
        self.download_dir = download_dir
        self.download_dir.mkdir(parents=True, exist_ok=True)

    def download_file(self, file_id: int, filename: str | None = None) -> Path | None:
        """Download a file by ID.

        Args:
            file_id: The Canvas file ID.
            filename: Optional filename to use (otherwise uses original name).

        Returns:
            Path to downloaded file, or None if download failed.
        """
        try:
            file_obj = self.client.get_file(file_id)
            original_name = getattr(file_obj, "filename", f"file_{file_id}")

            if filename:
                dest_name = filename
            else:
                dest_name = self._sanitize_filename(original_name)

            destination = self.download_dir / dest_name

            # Avoid re-downloading if file exists
            if destination.exists():
                logger.debug(f"File already exists: {destination}")
                return destination

            return self.client.download_file(file_id, destination)

        except Exception as e:
            logger.warning(f"Failed to download file {file_id}: {e}")
            return None

    def download_from_url(self, url: str, filename: str | None = None) -> Path | None:
        """Download a file from a URL.

        Args:
            url: The URL to download from.
            filename: Optional filename to use.

        Returns:
            Path to downloaded file, or None if download failed.
        """
        try:
            if not filename:
                # Try to extract filename from URL
                filename = self._extract_filename_from_url(url)

            filename = self._sanitize_filename(filename)
            destination = self.download_dir / filename

            # Avoid re-downloading if file exists
            if destination.exists():
                logger.debug(f"File already exists: {destination}")
                return destination

            return self.client.download_url(url, destination)

        except Exception as e:
            logger.warning(f"Failed to download from URL {url}: {e}")
            return None

    def extract_file_id_from_url(self, url: str) -> int | None:
        """Extract file ID from a Canvas file URL.

        Args:
            url: Canvas file URL.

        Returns:
            File ID or None if not found.
        """
        # Pattern: /files/12345 or /files/12345/download
        match = re.search(r"/files/(\d+)", url)
        if match:
            return int(match.group(1))
        return None

    def is_embeddable_image(self, path: Path) -> bool:
        """Check if a file is an embeddable image.

        Args:
            path: Path to the file.

        Returns:
            True if the file can be embedded as an image.
        """
        return path.suffix.lower() in self.EMBEDDABLE_IMAGES

    def is_embeddable_document(self, path: Path) -> bool:
        """Check if a file is an embeddable document.

        Args:
            path: Path to the file.

        Returns:
            True if the file can be embedded as a document.
        """
        return path.suffix.lower() in self.EMBEDDABLE_DOCUMENTS

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize a filename for safe filesystem use.

        Args:
            filename: Original filename.

        Returns:
            Sanitized filename.
        """
        # Remove or replace problematic characters
        sanitized = re.sub(r'[<>:"/\\|?*]', "_", filename)
        # Remove leading/trailing whitespace and dots
        sanitized = sanitized.strip(". ")
        # Ensure we have a filename
        if not sanitized:
            sanitized = "unnamed_file"
        return sanitized

    def _extract_filename_from_url(self, url: str) -> str:
        """Extract filename from URL.

        Args:
            url: URL to extract filename from.

        Returns:
            Extracted filename or default name.
        """
        # Remove query parameters
        clean_url = url.split("?")[0]
        # Get the last path component
        parts = clean_url.rstrip("/").split("/")
        if parts:
            filename = parts[-1]
            if "." in filename:
                return filename
        return "downloaded_file"

    def get_file_info(self, file_id: int) -> dict[str, Any] | None:
        """Get metadata about a file.

        Args:
            file_id: The Canvas file ID.

        Returns:
            Dict with file metadata or None.
        """
        try:
            file_obj = self.client.get_file(file_id)
            return {
                "id": file_obj.id,
                "filename": getattr(file_obj, "filename", ""),
                "display_name": getattr(file_obj, "display_name", ""),
                "content_type": getattr(file_obj, "content-type", ""),
                "size": getattr(file_obj, "size", 0),
                "url": getattr(file_obj, "url", ""),
            }
        except Exception as e:
            logger.warning(f"Failed to get file info for {file_id}: {e}")
            return None
