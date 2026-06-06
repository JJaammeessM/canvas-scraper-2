"""PDF generation using WeasyPrint."""

import logging
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML, CSS

from ..models.content import ModuleContent

logger = logging.getLogger(__name__)

# Get template directory
TEMPLATE_DIR = Path(__file__).parent / "templates"


class PdfGenerator:
    """Generates PDFs from Canvas module content."""

    def __init__(self, output_dir: Path):
        """Initialize the PDF generator.

        Args:
            output_dir: Directory to write generated PDFs.
        """
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Set up Jinja2 environment
        self.env = Environment(
            loader=FileSystemLoader(TEMPLATE_DIR),
            autoescape=True,
        )

        # Load styles
        self._load_styles()

    def _load_styles(self) -> None:
        """Load CSS styles from template file."""
        styles_path = TEMPLATE_DIR / "styles.css"
        if styles_path.exists():
            self.styles = styles_path.read_text()
        else:
            self.styles = ""
            logger.warning("styles.css not found, using empty styles")

    def generate_module_pdf(
        self,
        module: ModuleContent,
        course_name: str | None = None,
        filename: str | None = None,
    ) -> Path:
        """Generate a PDF for a module.

        Args:
            module: Module content with all items.
            course_name: Optional course name for cover page.
            filename: Optional custom filename (without extension).

        Returns:
            Path to the generated PDF file.
        """
        # Generate HTML
        html_content = self._render_module_html(module, course_name)

        # Generate filename
        if not filename:
            # Sanitize module name for filename
            safe_name = self._sanitize_filename(module.name)
            filename = f"{module.position:02d}_{safe_name}"

        output_path = self.output_dir / f"{filename}.pdf"

        # Generate PDF
        self._generate_pdf(html_content, output_path)

        logger.info(f"Generated PDF: {output_path}")
        return output_path

    def generate_course_pdf(
        self,
        modules: list[ModuleContent],
        course_name: str,
        filename: str | None = None,
    ) -> Path:
        """Generate a single PDF for an entire course.

        Args:
            modules: List of module contents.
            course_name: Course name for cover page.
            filename: Optional custom filename.

        Returns:
            Path to the generated PDF file.
        """
        # Combine all modules into one HTML document
        html_content = self._render_course_html(modules, course_name)

        # Generate filename
        if not filename:
            safe_name = self._sanitize_filename(course_name)
            filename = f"{safe_name}_complete"

        output_path = self.output_dir / f"{filename}.pdf"

        # Generate PDF
        self._generate_pdf(html_content, output_path)

        logger.info(f"Generated complete course PDF: {output_path}")
        return output_path

    def _render_module_html(
        self,
        module: ModuleContent,
        course_name: str | None = None,
    ) -> str:
        """Render module content to HTML.

        Args:
            module: Module content.
            course_name: Optional course name.

        Returns:
            Rendered HTML string.
        """
        template = self.env.get_template("module.html")

        return template.render(
            module=module,
            course_name=course_name,
            styles=self.styles,
            generation_date=datetime.now().strftime("%Y-%m-%d %H:%M"),
        )

    def _render_course_html(
        self,
        modules: list[ModuleContent],
        course_name: str,
    ) -> str:
        """Render complete course to HTML.

        Args:
            modules: List of module contents.
            course_name: Course name.

        Returns:
            Rendered HTML string.
        """
        # Use a modified template for complete course
        html_parts = [
            f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{course_name}</title>
    <style>
    {self.styles}
    </style>
</head>
<body>
    <div class="cover-page">
        <h1>{course_name}</h1>
        <p class="course-name">Complete Course Materials</p>
        <p class="date">Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}</p>
    </div>

    <div class="toc">
        <h2>Table of Contents</h2>
        <ul>
"""
        ]

        # Build TOC
        for module in modules:
            html_parts.append(
                f'            <li><a href="#module-{module.id}">{module.name}</a></li>\n'
            )
            for item in module.items:
                indent_class = f"indent-{min(item.indent + 1, 3)}"
                html_parts.append(
                    f'            <li class="{indent_class}"><a href="#item-{item.id}">{item.title}</a></li>\n'
                )

        html_parts.append(
            """        </ul>
    </div>
    <main>
"""
        )

        # Build content
        for module in modules:
            html_parts.append(f'        <section id="module-{module.id}">\n')
            html_parts.append(f"            <h1>{module.name}</h1>\n")

            for item in module.items:
                item_type = item.content_type.value.lower()
                html_parts.append(
                    f'            <div id="item-{item.id}" class="module-item indent-{item.indent} {item_type}">\n'
                )

                if item.content_type.value == "SubHeader":
                    html_parts.append(f"                <h2>{item.title}</h2>\n")
                else:
                    badge = self._get_badge_html(item.content_type.value)
                    html_parts.append(
                        f'                <h3 class="item-title">{item.title}{badge}</h3>\n'
                    )
                    html_parts.append('                <div class="item-content">\n')

                    if item.html_content:
                        html_parts.append(f"                    {item.html_content}\n")
                    elif item.external_url:
                        html_parts.append(
                            f'                    <p class="external-link"><a href="{item.external_url}">{item.external_url}</a></p>\n'
                        )
                    else:
                        html_parts.append(
                            "                    <p><em>No content available</em></p>\n"
                        )

                    html_parts.append("                </div>\n")

                html_parts.append("            </div>\n")

            html_parts.append("        </section>\n")

        html_parts.append(
            """    </main>
</body>
</html>
"""
        )

        return "".join(html_parts)

    def _get_badge_html(self, content_type: str) -> str:
        """Get HTML for content type badge.

        Args:
            content_type: Content type value.

        Returns:
            HTML string for badge.
        """
        badges = {
            "Assignment": '<span class="content-type-badge badge-assignment">Assignment</span>',
            "Quiz": '<span class="content-type-badge badge-quiz">Quiz</span>',
            "Discussion": '<span class="content-type-badge badge-discussion">Discussion</span>',
            "File": '<span class="content-type-badge badge-file">File</span>',
            "ExternalUrl": '<span class="content-type-badge badge-external">External Link</span>',
            "ExternalTool": '<span class="content-type-badge badge-external">External Tool</span>',
        }
        return badges.get(content_type, "")

    def _generate_pdf(self, html_content: str, output_path: Path) -> None:
        """Generate PDF from HTML content.

        Args:
            html_content: Rendered HTML string.
            output_path: Path to write PDF.
        """
        try:
            html = HTML(string=html_content, base_url=str(TEMPLATE_DIR))
            html.write_pdf(output_path)
        except Exception as e:
            logger.error(f"Failed to generate PDF: {e}")
            raise

    def _sanitize_filename(self, name: str) -> str:
        """Sanitize a string for use as filename.

        Args:
            name: Original name.

        Returns:
            Sanitized filename.
        """
        import re

        # Replace problematic characters
        sanitized = re.sub(r'[<>:"/\\|?*]', "_", name)
        # Replace multiple spaces/underscores with single underscore
        sanitized = re.sub(r"[\s_]+", "_", sanitized)
        # Remove leading/trailing underscores
        sanitized = sanitized.strip("_")
        # Limit length
        if len(sanitized) > 100:
            sanitized = sanitized[:100]

        return sanitized or "untitled"
