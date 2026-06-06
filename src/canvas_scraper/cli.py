"""Command-line interface for Canvas Scraper."""

import logging
import sys
from pathlib import Path

import click
from tqdm import tqdm

from .api.client import CanvasClient
from .config import Config
from .generators.pdf_generator import PdfGenerator
from .models.content import ModuleContent
from .processors.html_processor import HtmlProcessor
from .processors.image_processor import ImageProcessor
from .scrapers.file_scraper import FileScraper
from .scrapers.module_scraper import ModuleScraper
from .scrapers.page_scraper import PageScraper


def setup_logging(verbose: bool) -> None:
    """Configure logging based on verbosity level."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stderr)],
    )
    # Quiet down some noisy loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("weasyprint").setLevel(logging.WARNING)
    logging.getLogger("fontTools").setLevel(logging.WARNING)


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose output")
@click.option("--env-file", type=click.Path(exists=True), help="Path to .env file")
@click.pass_context
def cli(ctx: click.Context, verbose: bool, env_file: str | None) -> None:
    """Canvas Course Scraper - Extract Canvas LMS content to PDF.

    Use the commands below to list courses, modules, and generate PDFs
    from your Canvas LMS content.
    """
    setup_logging(verbose)
    ctx.ensure_object(dict)

    # Store common options
    ctx.obj["verbose"] = verbose
    ctx.obj["env_file"] = Path(env_file) if env_file else None


def get_client(ctx: click.Context) -> CanvasClient:
    """Get or create Canvas client from context."""
    if "client" not in ctx.obj:
        try:
            config = Config.from_env(ctx.obj.get("env_file"))
            config.validate()
            ctx.obj["client"] = CanvasClient(config)
        except ValueError as e:
            click.echo(f"Configuration error: {e}", err=True)
            click.echo("Make sure your .env file contains CANVAS_API_URL and CANVAS_API_TOKEN")
            sys.exit(1)
    return ctx.obj["client"]


@cli.command("test-connection")
@click.pass_context
def test_connection(ctx: click.Context) -> None:
    """Test the connection to Canvas API."""
    click.echo("Testing Canvas API connection...")

    client = get_client(ctx)
    result = client.test_connection()

    if result["success"]:
        click.echo(f"✓ Connected successfully!")
        click.echo(f"  API URL: {result['api_url']}")
        click.echo(f"  User: {result['user_name']} (ID: {result['user_id']})")
    else:
        click.echo(f"✗ Connection failed: {result['error']}", err=True)
        sys.exit(1)


@cli.command("list-courses")
@click.option(
    "--state",
    type=click.Choice(["active", "completed", "all"]),
    default="active",
    help="Filter courses by enrollment state",
)
@click.pass_context
def list_courses(ctx: click.Context, state: str) -> None:
    """List all available courses."""
    client = get_client(ctx)

    click.echo(f"Fetching {state} courses...")

    try:
        courses = list(client.get_courses(enrollment_state=state if state != "all" else None))

        if not courses:
            click.echo("No courses found.")
            return

        click.echo(f"\nFound {len(courses)} course(s):\n")

        # Table header
        click.echo(f"{'ID':<12} {'Name':<50} {'Code':<15}")
        click.echo("-" * 80)

        for course in courses:
            course_id = str(course.id)
            name = getattr(course, "name", "Unnamed")[:48]
            code = getattr(course, "course_code", "")[:13]
            click.echo(f"{course_id:<12} {name:<50} {code:<15}")

    except Exception as e:
        click.echo(f"Error fetching courses: {e}", err=True)
        sys.exit(1)


@cli.command("list-modules")
@click.argument("course_id", type=int)
@click.pass_context
def list_modules(ctx: click.Context, course_id: int) -> None:
    """List all modules in a course.

    COURSE_ID is the Canvas course ID (shown by list-courses command).
    """
    client = get_client(ctx)

    click.echo(f"Fetching modules for course {course_id}...")

    try:
        course = client.get_course(course_id)
        click.echo(f"Course: {course.name}\n")

        modules = list(client.get_modules(course_id))

        if not modules:
            click.echo("No modules found in this course.")
            return

        click.echo(f"{'ID':<12} {'Position':<10} {'Name':<50}")
        click.echo("-" * 75)

        for module in modules:
            module_id = str(module.id)
            position = str(getattr(module, "position", 0))
            name = module.name[:48]
            click.echo(f"{module_id:<12} {position:<10} {name:<50}")

    except Exception as e:
        click.echo(f"Error fetching modules: {e}", err=True)
        sys.exit(1)


@cli.command("scrape")
@click.argument("course_id", type=int)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default="output",
    help="Output directory for PDFs",
)
@click.option(
    "--modules",
    "-m",
    multiple=True,
    type=int,
    help="Specific module IDs to scrape (can be repeated)",
)
@click.option(
    "--single-pdf",
    is_flag=True,
    help="Generate a single PDF for the entire course",
)
@click.option(
    "--embed-images/--no-embed-images",
    default=True,
    help="Embed images in PDF (default: True)",
)
@click.pass_context
def scrape(
    ctx: click.Context,
    course_id: int,
    output: str,
    modules: tuple[int, ...],
    single_pdf: bool,
    embed_images: bool,
) -> None:
    """Scrape a course and generate PDFs.

    COURSE_ID is the Canvas course ID to scrape.

    Examples:

        # Scrape entire course to PDFs (one per module)
        canvas-scraper scrape 12345

        # Scrape specific modules
        canvas-scraper scrape 12345 --modules 111 --modules 222

        # Generate single PDF for entire course
        canvas-scraper scrape 12345 --single-pdf

        # Custom output directory
        canvas-scraper scrape 12345 --output ./my-pdfs
    """
    client = get_client(ctx)

    try:
        # Get course info
        course = client.get_course(course_id)
        course_name = course.name
        click.echo(f"Scraping course: {course_name}")

        # Set up output directory
        output_dir = Path(output) / _sanitize_dirname(course_name)
        output_dir.mkdir(parents=True, exist_ok=True)
        click.echo(f"Output directory: {output_dir}")

        # Initialize components
        page_scraper = PageScraper(client)
        file_scraper = FileScraper(client, output_dir / "files")
        module_scraper = ModuleScraper(client, page_scraper, file_scraper)
        html_processor = HtmlProcessor(client.config.api_url)
        image_processor = ImageProcessor(client, output_dir / ".image_cache")
        pdf_generator = PdfGenerator(output_dir)

        # Get modules to scrape
        if modules:
            module_ids = set(modules)
            all_modules = [m for m in module_scraper.get_modules(course_id) if m.id in module_ids]
            if not all_modules:
                click.echo("No matching modules found.", err=True)
                sys.exit(1)
        else:
            all_modules = list(module_scraper.get_modules(course_id))

        if not all_modules:
            click.echo("No modules found in this course.")
            return

        click.echo(f"Found {len(all_modules)} module(s) to scrape\n")

        # Scrape each module
        scraped_modules: list[ModuleContent] = []

        for module_info in tqdm(all_modules, desc="Scraping modules"):
            tqdm.write(f"Scraping: {module_info.name}")

            # Scrape full module content
            module_content = module_scraper.scrape_module(course_id, module_info.id)

            # Process HTML in each item
            for item in tqdm(
                module_content.items,
                desc="  Processing items",
                leave=False,
            ):
                if item.html_content:
                    # Clean HTML
                    item.html_content = html_processor.process(
                        item.html_content, course_id
                    )
                    # Process images
                    item.html_content = image_processor.process_html(
                        item.html_content, embed_images=embed_images
                    )

            scraped_modules.append(module_content)

        # Generate PDFs
        click.echo("\nGenerating PDFs...")

        if single_pdf:
            # Single PDF for entire course
            pdf_path = pdf_generator.generate_course_pdf(
                scraped_modules, course_name
            )
            click.echo(f"✓ Generated: {pdf_path}")
        else:
            # One PDF per module
            for module in tqdm(scraped_modules, desc="Generating PDFs"):
                pdf_path = pdf_generator.generate_module_pdf(
                    module, course_name
                )
                tqdm.write(f"✓ Generated: {pdf_path.name}")

        click.echo(f"\n✓ Complete! PDFs saved to: {output_dir}")

    except Exception as e:
        logging.exception("Scrape failed")
        click.echo(f"Error during scrape: {e}", err=True)
        sys.exit(1)


def _sanitize_dirname(name: str) -> str:
    """Sanitize a string for use as directory name."""
    import re

    sanitized = re.sub(r'[<>:"/\\|?*]', "_", name)
    sanitized = re.sub(r"[\s_]+", "_", sanitized)
    sanitized = sanitized.strip("_. ")
    return sanitized[:100] or "course"


def _parse_selection(selection: str, max_index: int) -> list[int]:
    """Parse user selection like '1,3,5-7' into list of 0-based indices.

    Args:
        selection: User input string (e.g., "1,3,5-7" or "all")
        max_index: Maximum valid index (1-based, inclusive)

    Returns:
        List of 0-based indices

    Raises:
        ValueError: If selection format is invalid or indices out of range
    """
    if selection.strip().lower() == "all":
        return list(range(max_index))

    indices: set[int] = set()
    parts = selection.split(",")

    for part in parts:
        part = part.strip()
        if not part:
            continue

        if "-" in part:
            # Range like "5-7"
            range_parts = part.split("-")
            if len(range_parts) != 2:
                raise ValueError(f"Invalid range format: '{part}'")
            try:
                start = int(range_parts[0].strip())
                end = int(range_parts[1].strip())
            except ValueError:
                raise ValueError(f"Invalid range format: '{part}'")

            if start > end:
                raise ValueError(f"Invalid range: {start} > {end}")
            if start < 1 or end > max_index:
                raise ValueError(f"Range {start}-{end} out of bounds (1-{max_index})")

            for i in range(start, end + 1):
                indices.add(i - 1)  # Convert to 0-based
        else:
            # Single number
            try:
                num = int(part)
            except ValueError:
                raise ValueError(f"Invalid number: '{part}'")

            if num < 1 or num > max_index:
                raise ValueError(f"Number {num} out of bounds (1-{max_index})")
            indices.add(num - 1)  # Convert to 0-based

    return sorted(indices)


def _display_courses(courses: list) -> None:
    """Display numbered list of courses.

    Args:
        courses: List of course objects with id, name, and course_code attributes
    """
    click.echo("\nAvailable courses:")
    for i, course in enumerate(courses, start=1):
        name = getattr(course, "name", "Unnamed")
        course_id = course.id
        code = getattr(course, "course_code", "")
        if code:
            click.echo(f"  [{i}] {name} ({code}) (ID: {course_id})")
        else:
            click.echo(f"  [{i}] {name} (ID: {course_id})")
    click.echo()


@cli.command("download")
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default="output",
    help="Output directory for PDFs",
)
@click.option(
    "--state",
    type=click.Choice(["active", "completed", "all"]),
    default="active",
    help="Filter courses by enrollment state",
)
@click.option(
    "--single-pdf",
    is_flag=True,
    help="Generate a single PDF for each course (instead of one per module)",
)
@click.option(
    "--embed-images/--no-embed-images",
    default=True,
    help="Embed images in PDF (default: True)",
)
@click.pass_context
def download(
    ctx: click.Context,
    output: str,
    state: str,
    single_pdf: bool,
    embed_images: bool,
) -> None:
    """Interactively select and download multiple courses.

    Lists all available courses and prompts you to select which ones to download.
    Each course is saved to its own subdirectory.

    Examples:

        # Interactive download with default settings
        canvas-scraper download

        # Include completed courses
        canvas-scraper download --state all

        # Generate single PDF per course
        canvas-scraper download --single-pdf

        # Custom output directory
        canvas-scraper download --output ./my-courses
    """
    client = get_client(ctx)

    click.echo("Fetching courses...")

    try:
        courses = list(client.get_courses(enrollment_state=state if state != "all" else None))

        if not courses:
            click.echo("No courses found.")
            return

        _display_courses(courses)

        # Prompt for selection
        selection = click.prompt(
            "Enter course numbers to download (e.g., 1,3,5-7) or 'all'",
            type=str,
        )

        try:
            selected_indices = _parse_selection(selection, len(courses))
        except ValueError as e:
            click.echo(f"Invalid selection: {e}", err=True)
            sys.exit(1)

        if not selected_indices:
            click.echo("No courses selected.")
            return

        selected_courses = [courses[i] for i in selected_indices]
        click.echo(f"\nDownloading {len(selected_courses)} course(s)...\n")

        # Process each selected course
        for idx, course in enumerate(selected_courses, start=1):
            course_id = course.id
            course_name = course.name

            click.echo(f"[{idx}/{len(selected_courses)}] Scraping: {course_name}")

            # Set up output directory for this course
            output_dir = Path(output) / _sanitize_dirname(course_name)
            output_dir.mkdir(parents=True, exist_ok=True)

            # Initialize components
            page_scraper = PageScraper(client)
            file_scraper = FileScraper(client, output_dir / "files")
            module_scraper = ModuleScraper(client, page_scraper, file_scraper)
            html_processor = HtmlProcessor(client.config.api_url)
            image_processor = ImageProcessor(client, output_dir / ".image_cache")
            pdf_generator = PdfGenerator(output_dir)

            # Get modules
            all_modules = list(module_scraper.get_modules(course_id))

            if not all_modules:
                click.echo(f"  No modules found in course. Skipping.")
                continue

            click.echo(f"  Found {len(all_modules)} module(s)")

            # Scrape each module
            scraped_modules: list[ModuleContent] = []

            for module_info in tqdm(all_modules, desc="  Scraping modules", leave=False):
                module_content = module_scraper.scrape_module(course_id, module_info.id)

                # Process HTML in each item
                for item in module_content.items:
                    if item.html_content:
                        item.html_content = html_processor.process(
                            item.html_content, course_id
                        )
                        item.html_content = image_processor.process_html(
                            item.html_content, embed_images=embed_images
                        )

                scraped_modules.append(module_content)

            # Generate PDFs
            if single_pdf:
                pdf_path = pdf_generator.generate_course_pdf(scraped_modules, course_name)
                click.echo(f"  Generated: {pdf_path.name}")
            else:
                for module in scraped_modules:
                    pdf_path = pdf_generator.generate_module_pdf(module, course_name)

            click.echo(f"✓ Complete! PDFs saved to: {output_dir}\n")

        click.echo(f"✓ All downloads complete!")

    except Exception as e:
        logging.exception("Download failed")
        click.echo(f"Error during download: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
