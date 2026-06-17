"""Command-line interface for Canvas Scraper."""

import logging
import re
import sys
from concurrent.futures import ThreadPoolExecutor
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
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stderr)],
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("weasyprint").setLevel(logging.WARNING)
    logging.getLogger("fontTools").setLevel(logging.WARNING)


@click.group(invoke_without_command=True)
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose output")
@click.option("--env-file", type=click.Path(exists=True), help="Path to .env file")
@click.pass_context
def cli(ctx: click.Context, verbose: bool, env_file: str | None) -> None:
    """Canvas Course Scraper - Extract Canvas LMS content to PDF.

    Run without a subcommand to launch the interactive menu.
    """
    setup_logging(verbose)
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["env_file"] = Path(env_file) if env_file else None

    if ctx.invoked_subcommand is None:
        ctx.invoke(interactive_mode)


def get_client(ctx: click.Context) -> CanvasClient:
    """Get or create Canvas client from context."""
    if "client" not in ctx.obj:
        try:
            config = Config.from_env(ctx.obj.get("env_file"))
            config.validate()
            ctx.obj["client"] = CanvasClient(config)
        except ValueError as e:
            click.echo(f"Configuration error: {e}", err=True)
            sys.exit(1)
    return ctx.obj["client"]


# ---------------------------------------------------------------------------
# Setup helpers
# ---------------------------------------------------------------------------

def _run_setup() -> "Config | None":
    """Interactive credential setup wizard. Returns saved Config or None if aborted."""
    import questionary

    click.echo("=== Canvas Scraper Setup ===\n")

    api_url = questionary.text(
        "Canvas URL:",
        instruction="(e.g. https://canvas.instructure.com)",
    ).ask()

    if not api_url:
        return None

    api_url = api_url.strip().rstrip("/")

    api_token = questionary.password("Canvas API token:").ask()

    if not api_token:
        return None

    config = Config(api_url=api_url, api_token=api_token.strip())

    try:
        config.validate()
    except ValueError as e:
        click.echo(f"Invalid credentials: {e}")
        return None

    click.echo("\nTesting connection...")
    client = CanvasClient(config)
    result = client.test_connection()

    if result["success"]:
        click.echo(f"Connected as: {result['user_name']}")
    else:
        click.echo(f"Connection failed: {result['error']}")
        if not questionary.confirm("Save credentials anyway?", default=False).ask():
            return None

    config.save()
    click.echo(f"Credentials saved to ~/.canvas_scraper/credentials.json\n")
    return config


# ---------------------------------------------------------------------------
# Interactive mode helpers
# ---------------------------------------------------------------------------

_BACK = object()  # sentinel — avoids collision with questionary's None cancellation


def _print_header(subtitle: str = "") -> None:
    click.echo("Canvas Scraper" + (f"  ·  {subtitle}" if subtitle else ""))
    click.echo("─" * 50)
    click.echo()


def _interactive_course(client: CanvasClient, course: object) -> None:
    """Navigate into a course: select modules and download."""
    import questionary

    course_id = course.id  # type: ignore[attr-defined]
    course_name = course.name  # type: ignore[attr-defined]

    click.clear()
    _print_header(course_name)
    click.echo("Fetching modules...")

    try:
        modules = list(client.get_modules(course_id))
    except Exception as e:
        click.echo(f"Error fetching modules: {e}")
        click.pause()
        return

    if not modules:
        click.echo("No modules found in this course.")
        click.pause()
        return

    click.clear()
    _print_header(course_name)

    action = questionary.select(
        f"{len(modules)} module(s) available",
        choices=[
            "Download all modules",
            "Select specific modules",
            questionary.Separator(),
            questionary.Choice("← Back", value=_BACK),
        ],
    ).ask()

    if action is None or action is _BACK:
        return

    if action == "Download all modules":
        selected_modules = modules
    else:
        click.clear()
        _print_header(course_name)
        choices = [questionary.Choice(title=m.name, value=m) for m in modules]
        selected_modules = questionary.checkbox(
            "Select modules  (space = toggle, a = all, enter = confirm):",
            choices=choices,
        ).ask()

        if not selected_modules:
            return

    click.clear()
    _print_header(course_name)

    output_format = questionary.select(
        "Output format:",
        choices=["One PDF per module", "Single PDF for entire course"],
    ).ask()

    if output_format is None:
        return

    output_dir = questionary.text("Output directory:", default="output").ask()
    if output_dir is None:
        return

    embed_choice = questionary.confirm("Embed images in PDF?", default=True).ask()
    if embed_choice is None:
        return

    single_pdf = output_format == "Single PDF for entire course"

    click.echo(f"\nDownloading {len(selected_modules)} module(s) from: {course_name}")
    if not questionary.confirm("Proceed?", default=True).ask():
        return

    click.clear()
    _do_scrape(
        client=client,
        course_id=course_id,
        course_name=course_name,
        module_ids={m.id for m in selected_modules},
        output=output_dir,
        single_pdf=single_pdf,
        embed_images=embed_choice,
    )
    click.pause()


def _interactive_browse(client: CanvasClient) -> None:
    """Browse courses and navigate into one for download."""
    import questionary

    click.clear()
    _print_header()

    state_choice = questionary.select(
        "Which courses to show?",
        choices=["Active", "Completed", "All"],
    ).ask()

    if state_choice is None:
        return

    enrollment_state = {
        "Active": "active",
        "Completed": "completed",
        "All": None,
    }[state_choice]

    click.echo("Fetching courses...")

    try:
        courses = list(client.get_courses(enrollment_state=enrollment_state))  # type: ignore[arg-type]
    except Exception as e:
        click.echo(f"Error fetching courses: {e}")
        click.pause()
        return

    if not courses:
        click.echo("No courses found.")
        click.pause()
        return

    while True:
        click.clear()
        _print_header()

        choices = [
            questionary.Choice(
                title=f"{getattr(c, 'name', 'Unnamed')}  "
                      f"({getattr(c, 'course_code', '')})",
                value=c,
            )
            for c in courses
        ]
        choices += [questionary.Separator(), questionary.Choice("← Back", value=_BACK)]

        selected = questionary.select(
            f"Select a course  ({len(courses)} found):",
            choices=choices,
        ).ask()

        if selected is None or selected is _BACK:
            break

        _interactive_course(client, selected)


def _interactive_download_all(client: CanvasClient) -> None:
    """Prompt for options and download every course at once."""
    import questionary

    click.clear()
    _print_header()

    state_choice = questionary.select(
        "Which courses to download?",
        choices=["Active", "Completed", "All"],
    ).ask()
    if state_choice is None:
        return

    enrollment_state = {"Active": "active", "Completed": "completed", "All": None}[state_choice]

    click.echo("Fetching courses...")
    try:
        courses = list(client.get_courses(enrollment_state=enrollment_state))  # type: ignore[arg-type]
    except Exception as e:
        click.echo(f"Error fetching courses: {e}")
        click.pause()
        return

    if not courses:
        click.echo("No courses found.")
        click.pause()
        return

    click.clear()
    _print_header()
    click.echo(f"Found {len(courses)} course(s).\n")

    output_format = questionary.select(
        "Output format:",
        choices=["One PDF per module", "Single PDF for entire course"],
    ).ask()
    if output_format is None:
        return

    output_dir = questionary.text("Output directory:", default="output").ask()
    if output_dir is None:
        return

    embed_choice = questionary.confirm("Embed images in PDF?", default=True).ask()
    if embed_choice is None:
        return

    single_pdf = output_format == "Single PDF for entire course"

    click.echo(f"\nReady to download all {len(courses)} course(s).")
    if not questionary.confirm("Proceed?", default=True).ask():
        return

    for idx, course in enumerate(courses, start=1):
        click.echo(f"\n[{idx}/{len(courses)}] {course.name}")
        try:
            _do_scrape(
                client=client,
                course_id=course.id,
                course_name=course.name,
                module_ids=None,
                output=output_dir,
                single_pdf=single_pdf,
                embed_images=embed_choice,
            )
        except Exception as e:
            click.echo(f"  Error scraping {course.name}: {e}")

    click.echo("\nAll courses downloaded!")
    click.pause()


def _interactive_select_courses(client: CanvasClient) -> None:
    """Checkbox-select a subset of courses, then download them."""
    import questionary

    click.clear()
    _print_header()

    state_choice = questionary.select(
        "Which courses to show?",
        choices=["Active", "Completed", "All"],
    ).ask()
    if state_choice is None:
        return

    enrollment_state = {"Active": "active", "Completed": "completed", "All": None}[state_choice]

    click.echo("Fetching courses...")
    try:
        courses = list(client.get_courses(enrollment_state=enrollment_state))  # type: ignore[arg-type]
    except Exception as e:
        click.echo(f"Error fetching courses: {e}")
        click.pause()
        return

    if not courses:
        click.echo("No courses found.")
        click.pause()
        return

    click.clear()
    _print_header()

    choices = [
        questionary.Choice(
            title=f"{getattr(c, 'name', 'Unnamed')}  ({getattr(c, 'course_code', '')})",
            value=c,
        )
        for c in courses
    ]
    selected_courses = questionary.checkbox(
        f"Select courses  (space = toggle, a = all, enter = confirm)  [{len(courses)} found]:",
        choices=choices,
    ).ask()

    if not selected_courses:
        return

    click.clear()
    _print_header()
    click.echo(f"{len(selected_courses)} course(s) selected.\n")

    output_format = questionary.select(
        "Output format:",
        choices=["One PDF per module", "Single PDF for entire course"],
    ).ask()
    if output_format is None:
        return

    output_dir = questionary.text("Output directory:", default="output").ask()
    if output_dir is None:
        return

    embed_choice = questionary.confirm("Embed images in PDF?", default=True).ask()
    if embed_choice is None:
        return

    single_pdf = output_format == "Single PDF for entire course"

    click.echo(f"\nReady to download {len(selected_courses)} course(s).")
    if not questionary.confirm("Proceed?", default=True).ask():
        return

    for idx, course in enumerate(selected_courses, start=1):
        click.echo(f"\n[{idx}/{len(selected_courses)}] {course.name}")
        try:
            _do_scrape(
                client=client,
                course_id=course.id,
                course_name=course.name,
                module_ids=None,
                output=output_dir,
                single_pdf=single_pdf,
                embed_images=embed_choice,
            )
        except Exception as e:
            click.echo(f"  Error scraping {course.name}: {e}")

    click.echo("\nSelected courses downloaded!")
    click.pause()


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@cli.command("setup")
def setup_cmd() -> None:
    """Configure and save Canvas API credentials."""
    _run_setup()


@cli.command("interactive")
@click.pass_context
def interactive_mode(ctx: click.Context) -> None:
    """Launch the interactive menu to browse and download courses."""
    import questionary

    # Ensure credentials exist
    config = Config.load()
    if not config and ctx.obj.get("env_file") is None:
        click.echo("No saved credentials found. Let's set them up first.\n")
        config = _run_setup()
        if not config:
            click.echo("Setup cancelled.")
            return

    try:
        client = get_client(ctx) if ctx.obj.get("env_file") else CanvasClient(config)  # type: ignore[arg-type]
        result = client.test_connection()
        user_label = result["user_name"] if result["success"] else "(connection failed)"
    except Exception as e:
        click.echo(f"Connection error: {e}\n")
        if not questionary.confirm("Continue anyway?", default=False).ask():
            return
        user_label = ""

    try:
        while True:
            click.clear()
            _print_header()
            if user_label:
                click.echo(f"Logged in as: {user_label}\n")

            action = questionary.select(
                "Main menu",
                choices=[
                    "Browse & download courses",
                    "Select multiple courses",
                    "Download all courses",
                    questionary.Separator(),
                    "Test connection",
                    "Update credentials",
                    questionary.Separator(),
                    "Exit",
                ],
            ).ask()

            if action is None or action == "Exit":
                click.clear()
                click.echo("Goodbye!")
                break

            elif action == "Browse & download courses":
                _interactive_browse(client)

            elif action == "Select multiple courses":
                _interactive_select_courses(client)

            elif action == "Download all courses":
                _interactive_download_all(client)

            elif action == "Test connection":
                result = client.test_connection()
                click.clear()
                _print_header()
                if result["success"]:
                    click.echo(f"Connected as: {result['user_name']}  (ID: {result['user_id']})")
                    user_label = result["user_name"]
                else:
                    click.echo(f"Failed: {result['error']}")
                click.pause()

            elif action == "Update credentials":
                new_config = _run_setup()
                if new_config:
                    client = CanvasClient(new_config)
                    result = client.test_connection()
                    user_label = result["user_name"] if result["success"] else user_label

    except KeyboardInterrupt:
        click.echo("\nGoodbye!")


# ---------------------------------------------------------------------------
# Non-interactive commands (kept for scripting / power users)
# ---------------------------------------------------------------------------

@cli.command("test-connection")
@click.pass_context
def test_connection(ctx: click.Context) -> None:
    """Test the connection to Canvas API."""
    click.echo("Testing Canvas API connection...")

    client = get_client(ctx)
    result = client.test_connection()

    if result["success"]:
        click.echo("Connected successfully!")
        click.echo(f"  API URL: {result['api_url']}")
        click.echo(f"  User: {result['user_name']} (ID: {result['user_id']})")
    else:
        click.echo(f"Connection failed: {result['error']}", err=True)
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
@click.option("--output", "-o", type=click.Path(), default="output", help="Output directory")
@click.option("--modules", "-m", multiple=True, type=int, help="Module IDs to scrape")
@click.option("--single-pdf", is_flag=True, help="Single PDF for entire course")
@click.option(
    "--embed-images/--no-embed-images", default=True, help="Embed images in PDF"
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
    """
    client = get_client(ctx)

    try:
        course = client.get_course(course_id)
        _do_scrape(
            client=client,
            course_id=course_id,
            course_name=course.name,
            module_ids=set(modules) if modules else None,
            output=output,
            single_pdf=single_pdf,
            embed_images=embed_images,
        )
    except Exception as e:
        logging.exception("Scrape failed")
        click.echo(f"Error during scrape: {e}", err=True)
        sys.exit(1)


@cli.command("download")
@click.option("--output", "-o", type=click.Path(), default="output", help="Output directory")
@click.option(
    "--state",
    type=click.Choice(["active", "completed", "all"]),
    default="active",
    help="Filter courses by enrollment state",
)
@click.option("--single-pdf", is_flag=True, help="Single PDF per course")
@click.option(
    "--embed-images/--no-embed-images", default=True, help="Embed images in PDF"
)
@click.option("--all", "download_all", is_flag=True, help="Download all courses without prompting")
@click.pass_context
def download(
    ctx: click.Context,
    output: str,
    state: str,
    single_pdf: bool,
    embed_images: bool,
    download_all: bool,
) -> None:
    """Interactively select and download multiple courses (text-prompt mode).

    Use --all to download every course without prompting.
    For the full arrow-key interface, run: canvas-scraper interactive
    """
    client = get_client(ctx)

    click.echo("Fetching courses...")

    try:
        courses = list(client.get_courses(enrollment_state=state if state != "all" else None))

        if not courses:
            click.echo("No courses found.")
            return

        if download_all:
            selected_courses = courses
            click.echo(f"Downloading all {len(selected_courses)} course(s)...\n")
        else:
            _display_courses(courses)

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

        for idx, course in enumerate(selected_courses, start=1):
            click.echo(f"[{idx}/{len(selected_courses)}] Scraping: {course.name}")
            _do_scrape(
                client=client,
                course_id=course.id,
                course_name=course.name,
                module_ids=None,
                output=output,
                single_pdf=single_pdf,
                embed_images=embed_images,
            )

        click.echo("All downloads complete!")

    except Exception as e:
        logging.exception("Download failed")
        click.echo(f"Error during download: {e}", err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Shared scraping logic
# ---------------------------------------------------------------------------

def _do_scrape(
    client: CanvasClient,
    course_id: int,
    course_name: str,
    module_ids: "set[int] | None",
    output: str,
    single_pdf: bool,
    embed_images: bool,
) -> None:
    """Run the full scrape-and-generate pipeline for a single course."""
    click.echo(f"Scraping course: {course_name}")

    output_dir = Path(output) / _sanitize_dirname(course_name)
    output_dir.mkdir(parents=True, exist_ok=True)
    click.echo(f"Output directory: {output_dir}")

    page_scraper = PageScraper(client)
    file_scraper = FileScraper(client, output_dir / "files")
    module_scraper = ModuleScraper(client, page_scraper, file_scraper)
    html_processor = HtmlProcessor(client.config.api_url)
    image_processor = ImageProcessor(client, output_dir / ".image_cache")
    pdf_generator = PdfGenerator(output_dir)

    all_module_infos = list(module_scraper.get_modules(course_id))

    if module_ids:
        all_module_infos = [m for m in all_module_infos if m.id in module_ids]
        if not all_module_infos:
            click.echo("No matching modules found.")
            return

    if not all_module_infos:
        click.echo("No modules found in this course.")
        return

    click.echo(f"Found {len(all_module_infos)} module(s) to scrape\n")

    def _scrape_and_process(module_info: ModuleContent) -> ModuleContent:
        tqdm.write(f"Scraping: {module_info.name}")
        module_content = module_scraper.scrape_module(course_id, module_info.id)
        for item in module_content.items:
            if item.html_content:
                item.html_content = html_processor.process(item.html_content, course_id)
                item.html_content = image_processor.process_html(
                    item.html_content, embed_images=embed_images
                )
        return module_content

    with ThreadPoolExecutor(max_workers=4) as executor:
        scraped_modules = list(
            tqdm(
                executor.map(_scrape_and_process, all_module_infos),
                total=len(all_module_infos),
                desc="Scraping modules",
            )
        )

    click.echo("\nGenerating PDFs...")

    if single_pdf:
        pdf_path = pdf_generator.generate_course_pdf(scraped_modules, course_name)
        click.echo(f"Generated: {pdf_path}")
    else:
        def _generate_pdf(module: ModuleContent) -> Path:
            return pdf_generator.generate_module_pdf(module, course_name)

        with ThreadPoolExecutor(max_workers=4) as executor:
            pdf_paths = list(
                tqdm(
                    executor.map(_generate_pdf, scraped_modules),
                    total=len(scraped_modules),
                    desc="Generating PDFs",
                )
            )
        for p in pdf_paths:
            tqdm.write(f"Generated: {p.name}")

    click.echo(f"\nComplete! PDFs saved to: {output_dir}")


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _sanitize_dirname(name: str) -> str:
    sanitized = re.sub(r'[<>:"/\\|?*]', "_", name)
    sanitized = re.sub(r"[\s_]+", "_", sanitized)
    sanitized = sanitized.strip("_. ")
    return sanitized[:100] or "course"


def _parse_selection(selection: str, max_index: int) -> list[int]:
    if selection.strip().lower() == "all":
        return list(range(max_index))

    indices: set[int] = set()

    for part in selection.split(","):
        part = part.strip()
        if not part:
            continue

        if "-" in part:
            range_parts = part.split("-")
            if len(range_parts) != 2:
                raise ValueError(f"Invalid range format: '{part}'")
            try:
                start, end = int(range_parts[0].strip()), int(range_parts[1].strip())
            except ValueError:
                raise ValueError(f"Invalid range format: '{part}'")
            if start > end:
                raise ValueError(f"Invalid range: {start} > {end}")
            if start < 1 or end > max_index:
                raise ValueError(f"Range {start}-{end} out of bounds (1-{max_index})")
            indices.update(range(start - 1, end))
        else:
            try:
                num = int(part)
            except ValueError:
                raise ValueError(f"Invalid number: '{part}'")
            if num < 1 or num > max_index:
                raise ValueError(f"Number {num} out of bounds (1-{max_index})")
            indices.add(num - 1)

    return sorted(indices)


def _display_courses(courses: list) -> None:
    click.echo("\nAvailable courses:")
    for i, course in enumerate(courses, start=1):
        name = getattr(course, "name", "Unnamed")
        code = getattr(course, "course_code", "")
        suffix = f" ({code})" if code else ""
        click.echo(f"  [{i}] {name}{suffix}  (ID: {course.id})")
    click.echo()


if __name__ == "__main__":
    cli()
