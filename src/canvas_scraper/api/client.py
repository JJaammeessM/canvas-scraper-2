"""Canvas API client wrapper."""

import logging
from pathlib import Path
from typing import Any, Iterator

import requests
from canvasapi import Canvas
from canvasapi.course import Course
from canvasapi.exceptions import CanvasException
from canvasapi.module import Module, ModuleItem
from canvasapi.paginated_list import PaginatedList

from ..config import Config
from .rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class CanvasClient:
    """Wrapper around the Canvas API with rate limiting and error handling."""

    def __init__(self, config: Config):
        """Initialize the Canvas client.

        Args:
            config: Application configuration with API credentials.
        """
        self.config = config
        self.canvas = Canvas(config.api_url, config.api_token)
        self.rate_limiter = RateLimiter()
        self._session = requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {config.api_token}"})

    def test_connection(self) -> dict[str, Any]:
        """Test the connection to Canvas.

        Returns:
            Dict with connection status and user info.

        Raises:
            CanvasException: If connection fails.
        """
        try:
            user = self.canvas.get_current_user()
            return {
                "success": True,
                "user_id": user.id,
                "user_name": user.name,
                "api_url": self.config.api_url,
            }
        except CanvasException as e:
            return {
                "success": False,
                "error": str(e),
                "api_url": self.config.api_url,
            }

    def get_courses(self, enrollment_state: str = "active") -> Iterator[Course]:
        """Get all courses for the current user.

        Args:
            enrollment_state: Filter by enrollment state (active, completed, etc.)

        Yields:
            Course objects.
        """
        self.rate_limiter.wait_if_needed()
        courses: PaginatedList = self.canvas.get_courses(enrollment_state=enrollment_state)

        for course in courses:
            self.rate_limiter.wait_if_needed()
            yield course

    def get_course(self, course_id: int) -> Course:
        """Get a specific course.

        Args:
            course_id: The Canvas course ID.

        Returns:
            Course object.
        """
        self.rate_limiter.wait_if_needed()
        return self.canvas.get_course(course_id)

    def get_modules(self, course_id: int) -> Iterator[Module]:
        """Get all modules for a course.

        Args:
            course_id: The Canvas course ID.

        Yields:
            Module objects.
        """
        course = self.get_course(course_id)
        self.rate_limiter.wait_if_needed()
        modules: PaginatedList = course.get_modules()

        for module in modules:
            self.rate_limiter.wait_if_needed()
            yield module

    def get_module_items(self, course_id: int, module_id: int) -> Iterator[ModuleItem]:
        """Get all items in a module.

        Args:
            course_id: The Canvas course ID.
            module_id: The module ID.

        Yields:
            ModuleItem objects.
        """
        course = self.get_course(course_id)
        self.rate_limiter.wait_if_needed()
        module = course.get_module(module_id)
        self.rate_limiter.wait_if_needed()
        items: PaginatedList = module.get_module_items()

        for item in items:
            self.rate_limiter.wait_if_needed()
            yield item

    def get_page(self, course_id: int, page_url: str) -> Any:
        """Get a wiki page by URL.

        Args:
            course_id: The Canvas course ID.
            page_url: The page URL slug.

        Returns:
            Page object with title and body.
        """
        course = self.get_course(course_id)
        self.rate_limiter.wait_if_needed()
        return course.get_page(page_url)

    def get_assignment(self, course_id: int, assignment_id: int) -> Any:
        """Get an assignment.

        Args:
            course_id: The Canvas course ID.
            assignment_id: The assignment ID.

        Returns:
            Assignment object.
        """
        course = self.get_course(course_id)
        self.rate_limiter.wait_if_needed()
        return course.get_assignment(assignment_id)

    def get_discussion_topic(self, course_id: int, topic_id: int) -> Any:
        """Get a discussion topic.

        Args:
            course_id: The Canvas course ID.
            topic_id: The topic ID.

        Returns:
            DiscussionTopic object.
        """
        course = self.get_course(course_id)
        self.rate_limiter.wait_if_needed()
        return course.get_discussion_topic(topic_id)

    def get_quiz(self, course_id: int, quiz_id: int) -> Any:
        """Get a quiz.

        Args:
            course_id: The Canvas course ID.
            quiz_id: The quiz ID.

        Returns:
            Quiz object.
        """
        course = self.get_course(course_id)
        self.rate_limiter.wait_if_needed()
        return course.get_quiz(quiz_id)

    def get_file(self, file_id: int) -> Any:
        """Get file metadata.

        Args:
            file_id: The file ID.

        Returns:
            File object with download URL.
        """
        self.rate_limiter.wait_if_needed()
        return self.canvas.get_file(file_id)

    def download_file(self, file_id: int, destination: Path) -> Path:
        """Download a file to the specified destination.

        Args:
            file_id: The Canvas file ID.
            destination: Path to save the file.

        Returns:
            Path to the downloaded file.
        """
        file_obj = self.get_file(file_id)
        download_url = file_obj.url

        self.rate_limiter.wait_if_needed()
        response = self._session.get(download_url, stream=True)
        response.raise_for_status()

        destination.parent.mkdir(parents=True, exist_ok=True)
        with open(destination, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        return destination

    def download_url(self, url: str, destination: Path) -> Path:
        """Download content from a URL with authentication.

        Args:
            url: The URL to download.
            destination: Path to save the file.

        Returns:
            Path to the downloaded file.
        """
        self.rate_limiter.wait_if_needed()
        response = self._session.get(url, stream=True)
        response.raise_for_status()

        destination.parent.mkdir(parents=True, exist_ok=True)
        with open(destination, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        return destination

    def fetch_authenticated(self, url: str) -> bytes:
        """Fetch content from a URL with authentication.

        Args:
            url: The URL to fetch.

        Returns:
            Response content as bytes.
        """
        self.rate_limiter.wait_if_needed()
        response = self._session.get(url)
        response.raise_for_status()
        return response.content
