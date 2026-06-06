# Canvas Course Scraper

Extract Canvas LMS course content and compile it into PDFs.

## Features

- Connect to Canvas LMS via API
- Scrape course modules including:
  - Wiki pages
  - Assignments (descriptions)
  - Discussions
  - Quizzes (descriptions)
  - Files and images
- Generate professional PDFs with:
  - Cover page
  - Table of contents
  - Preserved formatting
  - Embedded images
- One PDF per module or single PDF per course

## Installation

1. Clone this repository:
   ```bash
   cd canvas-scraper
   ```

2. Create a virtual environment and install:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -e .
   ```

3. Configure your Canvas credentials:
   ```bash
   cp .env.example .env
   # Edit .env with your Canvas URL and API token
   ```

## Getting Your API Token

1. Log in to Canvas
2. Go to Account → Settings
3. Scroll to "Approved Integrations"
4. Click "+ New Access Token"
5. Enter a purpose and expiration date
6. Copy the generated token to your `.env` file

## Usage

### Test Connection

```bash
python -m canvas_scraper test-connection
```

### List Your Courses

```bash
python -m canvas_scraper list-courses

# Include completed courses
python -m canvas_scraper list-courses --state all
```

### List Modules in a Course

```bash
python -m canvas_scraper list-modules <course_id>
```

### Scrape a Course

```bash
# Scrape entire course (one PDF per module)
python -m canvas_scraper scrape <course_id>

# Scrape to custom output directory
python -m canvas_scraper scrape <course_id> --output ./my-pdfs

# Scrape specific modules only
python -m canvas_scraper scrape <course_id> --modules 123 --modules 456

# Generate single PDF for entire course
python -m canvas_scraper scrape <course_id> --single-pdf

# Verbose output for debugging
python -m canvas_scraper -v scrape <course_id>
```

## Output

PDFs are saved to `output/<course_name>/` by default:

```
output/
└── My_Course_Name/
    ├── 01_Module_One.pdf
    ├── 02_Module_Two.pdf
    └── files/
        └── (downloaded files)
```

## Content Types

| Type | What's Included |
|------|----------------|
| Page | Full HTML content with images |
| Assignment | Description/instructions |
| Discussion | Topic message |
| Quiz | Description (questions may be restricted) |
| File | Link to file (images embedded) |
| External URL | Link displayed |
| SubHeader | Section divider |

## Troubleshooting

### "CANVAS_API_TOKEN not set"
Make sure you've created a `.env` file with your credentials.

### "401 Unauthorized"
Your API token may be expired or invalid. Generate a new one in Canvas settings.

### "403 Forbidden"
You may not have access to the requested course or content.

### WeasyPrint Errors
WeasyPrint requires some system dependencies. On macOS:
```bash
brew install pango
```

On Ubuntu/Debian:
```bash
sudo apt-get install libpango-1.0-0 libpangocairo-1.0-0
```

## Development

Install development dependencies:
```bash
pip install -e ".[dev]"
```

Run tests:
```bash
pytest
```

Format code:
```bash
black src/
ruff check src/
```

## License

MIT License
