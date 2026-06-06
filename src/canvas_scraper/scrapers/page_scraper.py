"""Scraper for Canvas wiki pages."""

import logging
import re
from typing import Any

from ..api.client import CanvasClient
from ..models.content import PageContent

logger = logging.getLogger(__name__)


class PageScraper:
    """Scrapes wiki page content from Canvas."""

    def __init__(self, client: CanvasClient):
        """Initialize the page scraper.

        Args:
            client: Canvas API client.
        """
        self.client = client

    def scrape_page(self, course_id: int, page_url: str) -> PageContent | None:
        """Scrape a wiki page by URL.

        Args:
            course_id: The Canvas course ID.
            page_url: The page URL slug.

        Returns:
            PageContent with the page data, or None if not found.
        """
        try:
            page = self.client.get_page(course_id, page_url)
            return PageContent(
                title=page.title,
                body=getattr(page, "body", "") or "",
                url=page_url,
                created_at=getattr(page, "created_at", None),
                updated_at=getattr(page, "updated_at", None),
            )
        except Exception as e:
            logger.warning(f"Failed to scrape page {page_url}: {e}")
            return None

    def scrape_page_from_url(self, full_url: str) -> PageContent | None:
        """Scrape a page from a full Canvas URL.

        Args:
            full_url: Full Canvas URL to the page.

        Returns:
            PageContent with the page data, or None if not found.
        """
        # Extract course_id and page_url from URL
        # Format: https://instance/courses/123/pages/page-slug
        match = re.search(r"/courses/(\d+)/pages/([^/?#]+)", full_url)
        if not match:
            logger.warning(f"Could not parse page URL: {full_url}")
            return None

        course_id = int(match.group(1))
        page_url = match.group(2)

        return self.scrape_page(course_id, page_url)

    def get_assignment_content(self, course_id: int, assignment_id: int) -> str:
        """Get HTML content from an assignment.

        Args:
            course_id: The Canvas course ID.
            assignment_id: The assignment ID.

        Returns:
            HTML description of the assignment.
        """
        try:
            assignment = self.client.get_assignment(course_id, assignment_id)
            return getattr(assignment, "description", "") or ""
        except Exception as e:
            logger.warning(f"Failed to get assignment {assignment_id}: {e}")
            return ""

    def get_discussion_content(self, course_id: int, topic_id: int) -> str:
        """Get HTML content from a discussion topic.

        Args:
            course_id: The Canvas course ID.
            topic_id: The discussion topic ID.

        Returns:
            HTML message from the discussion.
        """
        try:
            topic = self.client.get_discussion_topic(course_id, topic_id)
            return getattr(topic, "message", "") or ""
        except Exception as e:
            logger.warning(f"Failed to get discussion {topic_id}: {e}")
            return ""

    def get_quiz_content(self, course_id: int, quiz_id: int) -> str:
        """Get HTML content from a quiz.

        Args:
            course_id: The Canvas course ID.
            quiz_id: The quiz ID.

        Returns:
            HTML description of the quiz.
        """
        try:
            quiz = self.client.get_quiz(course_id, quiz_id)
            return getattr(quiz, "description", "") or ""
        except Exception as e:
            logger.warning(f"Failed to get quiz {quiz_id}: {e}")
            return ""

    def extract_content_id_from_url(self, url: str, content_type: str) -> int | None:
        """Extract content ID from a Canvas URL.

        Args:
            url: The Canvas URL.
            content_type: Type of content (assignments, discussion_topics, quizzes, etc.)

        Returns:
            The extracted ID or None.
        """
        pattern = rf"/{content_type}/(\d+)"
        match = re.search(pattern, url)
        if match:
            return int(match.group(1))
        return None
