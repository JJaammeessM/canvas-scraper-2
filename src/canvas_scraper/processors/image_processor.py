"""Image processing for Canvas content."""

import base64
import hashlib
import logging
import re
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from PIL import Image

from ..api.client import CanvasClient

logger = logging.getLogger(__name__)


class ImageProcessor:
    """Processes and embeds images from Canvas content."""

    # Maximum image dimensions for PDF embedding
    MAX_WIDTH = 800
    MAX_HEIGHT = 1000

    # Supported image formats
    SUPPORTED_FORMATS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}

    def __init__(self, client: CanvasClient, cache_dir: Path):
        """Initialize the image processor.

        Args:
            client: Canvas API client for authenticated downloads.
            cache_dir: Directory to cache downloaded images.
        """
        self.client = client
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._image_cache: dict[str, str] = {}  # URL -> base64 data

    def process_html(self, html: str, embed_images: bool = True) -> str:
        """Process HTML and handle all images.

        Args:
            html: HTML content with image tags.
            embed_images: Whether to embed images as base64.

        Returns:
            HTML with processed images.
        """
        if not html:
            return ""

        soup = BeautifulSoup(html, "html.parser")

        for img in soup.find_all("img"):
            src = img.get("src", "")
            if not src:
                continue

            try:
                if embed_images:
                    # Convert to base64 data URI
                    data_uri = self._get_image_as_data_uri(src)
                    if data_uri:
                        img["src"] = data_uri
                else:
                    # Download to local file and update path
                    local_path = self._download_image(src)
                    if local_path:
                        img["src"] = str(local_path)

            except Exception as e:
                logger.warning(f"Failed to process image {src}: {e}")
                # Keep original src or add placeholder
                img["alt"] = img.get("alt", "") + " (Image could not be loaded)"

        return str(soup)

    def _get_image_as_data_uri(self, url: str) -> str | None:
        """Download image and convert to base64 data URI.

        Args:
            url: Image URL.

        Returns:
            Data URI string or None.
        """
        # Check cache first
        if url in self._image_cache:
            return self._image_cache[url]

        # Handle data URIs (already embedded)
        if url.startswith("data:"):
            return url

        try:
            # Download image
            image_data = self._fetch_image(url)
            if not image_data:
                return None

            # Process and resize if needed
            processed_data, mime_type = self._process_image_data(image_data, url)
            if not processed_data:
                return None

            # Convert to base64
            b64_data = base64.b64encode(processed_data).decode("utf-8")
            data_uri = f"data:{mime_type};base64,{b64_data}"

            # Cache the result
            self._image_cache[url] = data_uri

            return data_uri

        except Exception as e:
            logger.warning(f"Failed to convert image to data URI: {url}: {e}")
            return None

    def _download_image(self, url: str) -> Path | None:
        """Download image to cache directory.

        Args:
            url: Image URL.

        Returns:
            Path to downloaded image or None.
        """
        if url.startswith("data:"):
            # Extract and save data URI
            return self._save_data_uri(url)

        try:
            # Generate cache filename from URL hash
            url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
            ext = self._get_extension(url) or ".png"
            cache_path = self.cache_dir / f"{url_hash}{ext}"

            if cache_path.exists():
                return cache_path

            # Download
            image_data = self._fetch_image(url)
            if not image_data:
                return None

            # Process and save
            processed_data, _ = self._process_image_data(image_data, url)
            if processed_data:
                cache_path.write_bytes(processed_data)
                return cache_path

        except Exception as e:
            logger.warning(f"Failed to download image: {url}: {e}")

        return None

    def _fetch_image(self, url: str) -> bytes | None:
        """Fetch image data from URL.

        Args:
            url: Image URL.

        Returns:
            Image data as bytes or None.
        """
        try:
            # Use authenticated request for Canvas URLs
            if self.client.config.api_url in url:
                return self.client.fetch_authenticated(url)
            else:
                # For external URLs, try without auth first
                import requests

                response = requests.get(url, timeout=30)
                response.raise_for_status()
                return response.content

        except Exception as e:
            logger.debug(f"Failed to fetch image: {url}: {e}")
            return None

    def _process_image_data(self, data: bytes, url: str) -> tuple[bytes | None, str]:
        """Process image data - resize if needed.

        Args:
            data: Raw image data.
            url: Original URL (for extension detection).

        Returns:
            Tuple of (processed data, mime type).
        """
        ext = self._get_extension(url)

        # Handle SVG separately (don't process with PIL)
        if ext == ".svg":
            return data, "image/svg+xml"

        # Detect SVG by magic bytes (Canvas may serve SVGs without .svg extension)
        stripped = data.lstrip()
        if stripped.startswith(b"<svg") or (stripped.startswith(b"<?xml") and b"<svg" in stripped[:512]):
            return data, "image/svg+xml"

        try:
            # Open with PIL
            img = Image.open(BytesIO(data))

            # Convert RGBA to RGB for JPEG
            if img.mode == "RGBA" and ext in (".jpg", ".jpeg"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3])
                img = background

            # Resize if too large
            if img.width > self.MAX_WIDTH or img.height > self.MAX_HEIGHT:
                img.thumbnail((self.MAX_WIDTH, self.MAX_HEIGHT), Image.Resampling.LANCZOS)

            # Save to bytes
            output = BytesIO()

            if ext in (".jpg", ".jpeg"):
                if img.mode != "RGB":
                    img = img.convert("RGB")
                img.save(output, format="JPEG", quality=85, optimize=True)
                mime_type = "image/jpeg"
            elif ext == ".gif":
                img.save(output, format="GIF")
                mime_type = "image/gif"
            elif ext == ".webp":
                img.save(output, format="WEBP", quality=85)
                mime_type = "image/webp"
            else:
                # Default to PNG
                img.save(output, format="PNG", optimize=True)
                mime_type = "image/png"

            return output.getvalue(), mime_type

        except Exception as e:
            logger.warning(f"Failed to process image at {url}: {e}")
            # Return original data with guessed mime type
            mime_type = self._guess_mime_type(ext)
            return data, mime_type

    def _save_data_uri(self, data_uri: str) -> Path | None:
        """Save a data URI to a file.

        Args:
            data_uri: Data URI string.

        Returns:
            Path to saved file or None.
        """
        try:
            # Parse data URI: data:mime/type;base64,data
            match = re.match(r"data:([^;]+);base64,(.+)", data_uri)
            if not match:
                return None

            mime_type = match.group(1)
            b64_data = match.group(2)

            # Determine extension
            ext = {
                "image/png": ".png",
                "image/jpeg": ".jpg",
                "image/gif": ".gif",
                "image/webp": ".webp",
                "image/svg+xml": ".svg",
            }.get(mime_type, ".png")

            # Generate filename from hash
            data_hash = hashlib.md5(b64_data.encode()).hexdigest()[:12]
            cache_path = self.cache_dir / f"{data_hash}{ext}"

            if not cache_path.exists():
                cache_path.write_bytes(base64.b64decode(b64_data))

            return cache_path

        except Exception as e:
            logger.warning(f"Failed to save data URI: {e}")
            return None

    def _get_extension(self, url: str) -> str | None:
        """Get file extension from URL.

        Args:
            url: URL string.

        Returns:
            Extension including dot, or None.
        """
        parsed = urlparse(url)
        path = parsed.path.lower()

        for ext in self.SUPPORTED_FORMATS:
            if path.endswith(ext):
                return ext

        # Check for format parameter (Canvas sometimes uses this)
        if "format=" in parsed.query:
            if "png" in parsed.query:
                return ".png"
            if "jpg" in parsed.query or "jpeg" in parsed.query:
                return ".jpg"

        return None

    def _guess_mime_type(self, ext: str | None) -> str:
        """Guess MIME type from extension.

        Args:
            ext: File extension.

        Returns:
            MIME type string.
        """
        return {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".svg": "image/svg+xml",
        }.get(ext or "", "image/png")

    def clear_cache(self) -> None:
        """Clear the image cache."""
        self._image_cache.clear()
        # Optionally clear disk cache
        for file in self.cache_dir.glob("*"):
            try:
                file.unlink()
            except Exception:
                pass
