# Canvas Course Scraper

Download your Canvas LMS courses as PDFs — with cover pages, tables of contents, and embedded images.

## Quick Start

**1. Install system dependencies**

macOS:
```bash
brew install pango
```

Ubuntu/Debian:
```bash
sudo apt-get install libpango-1.0-0 libpangocairo-1.0-0
```

Windows — install the GTK runtime from [gtk.org/download/windows](https://gtk.org/download/windows/). The all-in-one installer is the easiest option.

**2. Install the tool**

```bash
git clone <repo-url>
cd canvas-scraper
pip install -e .
```

**3. Run it**

```bash
canvas-scraper
```

That's it. On first launch it will ask for your Canvas URL and API token, test the connection, and save your credentials. After that, use the arrow-key menu to browse your courses and download them as PDFs.

---

## Getting Your API Token

1. Log in to Canvas
2. Go to **Account → Settings**
3. Scroll to **Approved Integrations**
4. Click **+ New Access Token**
5. Give it a name, set an expiry, and copy the token

The setup wizard will ask for this token the first time you run `canvas-scraper`.

---

## Interactive Menu

```
canvas-scraper
```

Launches the full menu:

```
Main menu
❯ Browse & download courses
  ─────────────────────────
  Test connection
  Update credentials
  ─────────────────────────
  Exit
```

From **Browse & download courses** you can:
- Select a course with arrow keys
- Choose to download all modules or pick specific ones with checkboxes
- Set the output format (one PDF per module, or a single PDF for the whole course)
- Choose an output directory
- Start the download with a progress bar

Credentials are saved to `~/.canvas_scraper/credentials.json` and reused automatically on every future run.

---

## Output

PDFs are saved to `output/<course-name>/` by default:

```
output/
└── My_Course_Name/
    ├── 01_Module_One.pdf
    ├── 02_Module_Two.pdf
    └── files/
```

---

## Command Reference

For scripting or automation, all actions are also available as direct commands:

```bash
# Reconfigure credentials
canvas-scraper setup

# List courses
canvas-scraper list-courses
canvas-scraper list-courses --state all        # include completed

# List modules in a course
canvas-scraper list-modules <course_id>

# Scrape a course (one PDF per module)
canvas-scraper scrape <course_id>

# Single PDF for the whole course
canvas-scraper scrape <course_id> --single-pdf

# Specific modules only
canvas-scraper scrape <course_id> --modules 123 --modules 456

# Custom output directory
canvas-scraper scrape <course_id> --output ./my-pdfs

# Verbose output
canvas-scraper -v scrape <course_id>
```

---

## What Gets Scraped

| Content type | What's included |
|---|---|
| Page | Full HTML content with images |
| Assignment | Description / instructions |
| Discussion | Topic message |
| Quiz | Description (questions may be restricted by your institution) |
| File | Linked files; images embedded directly |
| External URL | Link displayed |
| SubHeader | Section divider |

---

## Troubleshooting

**"No saved credentials found"**  
Run `canvas-scraper setup` to enter your Canvas URL and API token.

**"401 Unauthorized"**  
Your token may be expired. Generate a new one in Canvas settings, then run `canvas-scraper setup` to update it.

**"403 Forbidden"**  
You don't have access to that course or content.

**WeasyPrint / font errors**  
Make sure the system dependencies above are installed (`pango` on macOS, `libpango` on Linux).

---

## License

MIT
