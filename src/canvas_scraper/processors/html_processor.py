"""HTML processing and cleaning for Canvas content."""

import logging
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Comment

logger = logging.getLogger(__name__)


class HtmlProcessor:
    """Processes and cleans HTML content from Canvas."""

    # Tags to remove entirely (including content)
    REMOVE_TAGS = {"script", "style", "noscript", "iframe", "object", "embed", "form"}

    # Attributes to remove from all elements
    REMOVE_ATTRS = {
        "onclick",
        "onload",
        "onerror",
        "onmouseover",
        "onmouseout",
        "onfocus",
        "onblur",
        "data-api-endpoint",
        "data-api-returntype",
    }

    # Canvas-specific classes that indicate interactive elements
    CANVAS_INTERACTIVE_CLASSES = {
        "instructure_file_link_holder",
        "instructure_video_link",
        "instructure_audio_link",
        "media_comment",
    }

    def __init__(self, base_url: str):
        """Initialize the HTML processor.

        Args:
            base_url: Base URL for the Canvas instance.
        """
        self.base_url = base_url.rstrip("/")

    def process(self, html: str, course_id: int | None = None) -> str:
        """Process HTML content for PDF generation.

        Args:
            html: Raw HTML content.
            course_id: Optional course ID for URL resolution.

        Returns:
            Cleaned HTML suitable for PDF generation.
        """
        if not html:
            return ""

        soup = BeautifulSoup(html, "html.parser")

        # Remove unwanted tags
        self._remove_unwanted_tags(soup)

        # Remove comments
        self._remove_comments(soup)

        # Clean attributes
        self._clean_attributes(soup)

        # Convert relative URLs to absolute
        self._fix_urls(soup, course_id)

        # Clean up Canvas-specific markup
        self._clean_canvas_markup(soup)

        # Fix common HTML issues
        self._fix_html_issues(soup)

        return str(soup)

    def _remove_unwanted_tags(self, soup: BeautifulSoup) -> None:
        """Remove script, style, and other unwanted tags."""
        for tag_name in self.REMOVE_TAGS:
            for tag in soup.find_all(tag_name):
                tag.decompose()

    def _remove_comments(self, soup: BeautifulSoup) -> None:
        """Remove HTML comments."""
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()

    def _clean_attributes(self, soup: BeautifulSoup) -> None:
        """Remove problematic attributes from all elements."""
        for tag in soup.find_all(True):
            # Remove event handlers and Canvas-specific data attributes
            attrs_to_remove = []
            for attr in tag.attrs:
                if attr in self.REMOVE_ATTRS or attr.startswith("on"):
                    attrs_to_remove.append(attr)

            for attr in attrs_to_remove:
                del tag[attr]

    def _fix_urls(self, soup: BeautifulSoup, course_id: int | None) -> None:
        """Convert relative URLs to absolute."""
        # Fix image sources
        for img in soup.find_all("img"):
            src = img.get("src", "")
            if src:
                img["src"] = self._make_absolute_url(src, course_id)

        # Fix link hrefs
        for a in soup.find_all("a"):
            href = a.get("href", "")
            if href and not href.startswith(("#", "mailto:", "tel:")):
                a["href"] = self._make_absolute_url(href, course_id)

        # Fix video/audio sources
        for source in soup.find_all("source"):
            src = source.get("src", "")
            if src:
                source["src"] = self._make_absolute_url(src, course_id)

    def _make_absolute_url(self, url: str, course_id: int | None) -> str:
        """Convert a relative URL to absolute.

        Args:
            url: The URL to convert.
            course_id: Optional course ID for course-relative URLs.

        Returns:
            Absolute URL.
        """
        if not url:
            return url

        # Already absolute
        if url.startswith(("http://", "https://", "data:")):
            return url

        # Canvas internal paths
        if url.startswith("/"):
            return f"{self.base_url}{url}"

        # Course-relative paths
        if course_id and not urlparse(url).netloc:
            return f"{self.base_url}/courses/{course_id}/{url}"

        return urljoin(self.base_url, url)

    def _clean_canvas_markup(self, soup: BeautifulSoup) -> None:
        """Clean Canvas-specific HTML markup."""
        # Remove empty paragraphs
        for p in soup.find_all("p"):
            if not p.get_text(strip=True) and not p.find_all(["img", "br"]):
                p.decompose()

        # Clean up Canvas file link holders
        for holder in soup.find_all(class_="instructure_file_link_holder"):
            # Keep the actual link, remove the wrapper
            link = holder.find("a")
            if link:
                holder.replace_with(link)
            else:
                holder.decompose()

        # Remove Canvas equella links placeholders
        for span in soup.find_all("span", class_="instructure_equella_link"):
            span.decompose()

        # Clean up MathJax/LaTeX spans (keep the content)
        for span in soup.find_all("span", class_=re.compile(r"MathJax|math-tex")):
            # Keep text content
            text = span.get_text()
            span.replace_with(text)

    def _fix_html_issues(self, soup: BeautifulSoup) -> None:
        """Fix common HTML issues."""
        # Ensure images have alt text
        for img in soup.find_all("img"):
            if not img.get("alt"):
                img["alt"] = "Image"

        # Remove empty links
        for a in soup.find_all("a"):
            if not a.get_text(strip=True) and not a.find_all(["img"]):
                a.decompose()

        # Fix tables without proper structure
        for table in soup.find_all("table"):
            # Ensure table has tbody
            if not table.find("tbody"):
                rows = table.find_all("tr", recursive=False)
                if rows:
                    tbody = soup.new_tag("tbody")
                    for row in rows:
                        tbody.append(row.extract())
                    table.append(tbody)

    def extract_image_urls(self, html: str) -> list[str]:
        """Extract all image URLs from HTML.

        Args:
            html: HTML content.

        Returns:
            List of image URLs.
        """
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        urls = []

        for img in soup.find_all("img"):
            src = img.get("src", "")
            if src and not src.startswith("data:"):
                urls.append(src)

        return urls

    def extract_file_ids(self, html: str) -> list[int]:
        """Extract Canvas file IDs from HTML.

        Args:
            html: HTML content.

        Returns:
            List of file IDs.
        """
        if not html:
            return []

        file_ids = []

        # Look for data-file-id attributes
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all(attrs={"data-file-id": True}):
            try:
                file_ids.append(int(tag["data-file-id"]))
            except (ValueError, TypeError):
                pass

        # Look for file IDs in URLs
        pattern = r"/files/(\d+)"
        for match in re.finditer(pattern, html):
            try:
                file_ids.append(int(match.group(1)))
            except ValueError:
                pass

        return list(set(file_ids))  # Remove duplicates
