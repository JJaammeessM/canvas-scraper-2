# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Run Commands

```bash
# Install package (editable mode)
pip install -e .

# Install with dev dependencies
pip install -e ".[dev]"

# Run CLI commands
python -m canvas_scraper test-connection
python -m canvas_scraper list-courses
python -m canvas_scraper list-modules <course_id>
python -m canvas_scraper scrape <course_id>

# Verbose mode
python -m canvas_scraper -v scrape <course_id>

# Run tests
pytest

# Format & lint
black src/
ruff check src/
```

## Architecture

This is a CLI tool that scrapes Canvas LMS courses and generates PDFs. The data flows through a pipeline:

```
Canvas API → Scrapers → Processors → PDF Generator → Output
```

### Key Components

**api/** - Canvas API wrapper with rate limiting
- `CanvasClient` wraps `canvasapi` library, all API calls go through here
- `RateLimiter` respects Canvas `X-Rate-Limit-Remaining` headers

**scrapers/** - Content extraction by type
- `ModuleScraper` orchestrates scraping, delegates to type-specific scrapers
- `PageScraper` handles wiki pages, assignments, discussions, quizzes
- `FileScraper` downloads files with authentication

**processors/** - Content transformation
- `HtmlProcessor` cleans Canvas-specific markup, fixes relative URLs
- `ImageProcessor` downloads images with auth, converts to base64 for embedding

**generators/** - PDF output
- `PdfGenerator` uses WeasyPrint with Jinja2 templates
- Templates in `generators/templates/` control PDF styling

**models/content.py** - Data classes
- `ModuleContent` contains list of `ModuleItemContent`
- `ContentType` enum: Page, File, Assignment, Discussion, Quiz, ExternalUrl, SubHeader

### CLI Entry Point

`cli.py` defines Click commands. The `scrape` command is the main workflow:
1. Initialize all components with shared `CanvasClient`
2. Get modules from `ModuleScraper`
3. For each module item: scrape content → process HTML → process images
4. Generate PDFs (per-module or single course PDF)

## Configuration

Credentials loaded from `.env` via `python-dotenv`:
- `CANVAS_API_URL` - Canvas instance URL
- `CANVAS_API_TOKEN` - API access token

## Code Style

- Line length: 100 (configured in pyproject.toml)
- Uses type hints throughout
- Dataclasses with `from_api_*` factory methods for API object conversion
