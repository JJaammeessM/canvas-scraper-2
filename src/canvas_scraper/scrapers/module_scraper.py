"""Orchestrates scraping of entire modules."""

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterator

from ..api.client import CanvasClient
from ..models.content import ContentType, ModuleContent, ModuleItemContent
from .file_scraper import FileScraper
from .page_scraper import PageScraper

logger = logging.getLogger(__name__)


class ModuleScraper:
    """Orchestrates scraping of Canvas modules and their content."""

    def __init__(
        self,
        client: CanvasClient,
        page_scraper: PageScraper,
        file_scraper: FileScraper,
    ):
        """Initialize the module scraper.

        Args:
            client: Canvas API client.
            page_scraper: Scraper for wiki pages.
            file_scraper: Scraper for files.
        """
        self.client = client
        self.page_scraper = page_scraper
        self.file_scraper = file_scraper

    def get_modules(self, course_id: int) -> Iterator[ModuleContent]:
        """Get all modules in a course.

        Args:
            course_id: The Canvas course ID.

        Yields:
            ModuleContent objects (without items populated).
        """
        for module in self.client.get_modules(course_id):
            yield ModuleContent.from_api_module(module)

    def scrape_module(self, course_id: int, module_id: int) -> ModuleContent:
        """Scrape a complete module with all its content.

        Args:
            course_id: The Canvas course ID.
            module_id: The module ID.

        Returns:
            ModuleContent with all items and their HTML content.
        """
        # Get module info
        course = self.client.get_course(course_id)
        module = course.get_module(module_id)
        module_content = ModuleContent.from_api_module(module)

        items = list(self.client.get_module_items(course_id, module_id))
        if not items:
            return module_content

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {
                executor.submit(self._scrape_module_item, course_id, item): i
                for i, item in enumerate(items)
            }
            position_results: dict[int, ModuleItemContent | None] = {}
            for future in as_completed(futures):
                position = futures[future]
                position_results[position] = future.result()

        # Restore original item order
        module_content.items = [
            position_results[i]
            for i in range(len(items))
            if position_results.get(i) is not None
        ]
        return module_content

    def _scrape_module_item(self, course_id: int, item) -> ModuleItemContent | None:
        """Scrape content for a single module item.

        Args:
            course_id: The Canvas course ID.
            item: Canvas API module item object.

        Returns:
            ModuleItemContent with HTML content, or None if scraping failed.
        """
        try:
            item_content = ModuleItemContent.from_api_item(item)

            # Get HTML content based on item type
            html_content = self._get_item_html(course_id, item, item_content.content_type)
            item_content.html_content = html_content

            return item_content

        except Exception as e:
            logger.warning(f"Failed to scrape module item {item.id}: {e}")
            return None

    def _get_item_html(self, course_id: int, item, content_type: ContentType) -> str:
        """Get HTML content for a module item based on its type.

        Args:
            course_id: The Canvas course ID.
            item: Canvas API module item object.
            content_type: The type of content.

        Returns:
            HTML string for the item.
        """
        if content_type == ContentType.PAGE:
            return self._get_page_html(course_id, item)

        elif content_type == ContentType.ASSIGNMENT:
            return self._get_assignment_html(course_id, item)

        elif content_type == ContentType.DISCUSSION:
            return self._get_discussion_html(course_id, item)

        elif content_type == ContentType.QUIZ:
            return self._get_quiz_html(course_id, item)

        elif content_type == ContentType.FILE:
            return self._get_file_html(item)

        elif content_type == ContentType.EXTERNAL_URL:
            return self._get_external_url_html(item)

        elif content_type == ContentType.SUB_HEADER:
            return self._get_subheader_html(item)

        elif content_type == ContentType.EXTERNAL_TOOL:
            return self._get_external_tool_html(item)

        else:
            logger.warning(f"Unknown content type: {content_type}")
            return f"<p><em>Content type not supported: {content_type.value}</em></p>"

    def _get_page_html(self, course_id: int, item) -> str:
        """Get HTML from a wiki page item."""
        page_url = getattr(item, "page_url", None)
        if not page_url:
            # Try to extract from URL
            url = getattr(item, "url", "")
            match = re.search(r"/pages/([^/?#]+)", url)
            if match:
                page_url = match.group(1)

        if page_url:
            page = self.page_scraper.scrape_page(course_id, page_url)
            if page:
                return page.body

        return f"<p><em>Page content unavailable: {item.title}</em></p>"

    def _get_assignment_html(self, course_id: int, item) -> str:
        """Get HTML from an assignment item."""
        content_id = getattr(item, "content_id", None)
        if not content_id:
            url = getattr(item, "url", "")
            content_id = self.page_scraper.extract_content_id_from_url(url, "assignments")

        if content_id:
            html = self.page_scraper.get_assignment_content(course_id, content_id)
            if html:
                return f"<div class='assignment-content'>{html}</div>"

        return f"<p><em>Assignment: {item.title}</em></p>"

    def _get_discussion_html(self, course_id: int, item) -> str:
        """Get HTML from a discussion item."""
        content_id = getattr(item, "content_id", None)
        if not content_id:
            url = getattr(item, "url", "")
            content_id = self.page_scraper.extract_content_id_from_url(url, "discussion_topics")

        if content_id:
            html = self.page_scraper.get_discussion_content(course_id, content_id)
            if html:
                return f"<div class='discussion-content'>{html}</div>"

        return f"<p><em>Discussion: {item.title}</em></p>"

    def _get_quiz_html(self, course_id: int, item) -> str:
        """Get HTML from a quiz item."""
        content_id = getattr(item, "content_id", None)
        if not content_id:
            url = getattr(item, "url", "")
            content_id = self.page_scraper.extract_content_id_from_url(url, "quizzes")

        if content_id:
            html = self.page_scraper.get_quiz_content(course_id, content_id)
            if html:
                return f"<div class='quiz-content'>{html}</div>"

        return f"<p><em>Quiz: {item.title}</em></p>"

    def _get_file_html(self, item) -> str:
        """Get HTML for a file item."""
        content_id = getattr(item, "content_id", None)
        url = getattr(item, "url", "")

        if content_id:
            file_info = self.file_scraper.get_file_info(content_id)
            if file_info:
                filename = file_info.get("display_name") or file_info.get("filename", "File")
                content_type = file_info.get("content_type", "")

                # For images, we'll handle embedding later in the processor
                if content_type.startswith("image/"):
                    return f'<p><img data-file-id="{content_id}" alt="{filename}" /></p>'

                return f'<p><a href="{url}" data-file-id="{content_id}">{filename}</a></p>'

        return f"<p><em>File: {item.title}</em></p>"

    def _get_external_url_html(self, item) -> str:
        """Get HTML for an external URL item."""
        external_url = getattr(item, "external_url", "")
        return f'<p><a href="{external_url}" target="_blank">{item.title}</a> (External Link)</p>'

    def _get_subheader_html(self, item) -> str:
        """Get HTML for a subheader item."""
        return ""  # Subheaders are just dividers, title is used in template

    def _get_external_tool_html(self, item) -> str:
        """Get HTML for an external tool item."""
        url = getattr(item, "external_url", "") or getattr(item, "url", "")
        return f"<p><em>External Tool: {item.title}</em></p>"
