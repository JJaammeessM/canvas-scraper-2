# Canvas Course Scraper

Download your Canvas LMS courses as PDFs — with cover pages, tables of contents, and embedded images.

## Quick Start

### Step 1 — Install Python

**macOS**
1. Go to [python.org/downloads](https://www.python.org/downloads/)
2. Download the latest Python 3 installer and run it

**Windows**
1. Go to [python.org/downloads](https://www.python.org/downloads/)
2. Download the latest Python 3 installer
3. Run it — make sure to tick **"Add Python to PATH"** before clicking Install

**Ubuntu/Debian**
```bash
sudo apt-get install python3 python3-pip
```

---

### Step 2 — Install system dependencies

**macOS**
```bash
brew install pango
```
> Don't have Homebrew? Install it from [brew.sh](https://brew.sh)

**Windows**
Install the GTK runtime from [gtk.org/download/windows](https://gtk.org/download/windows/). The all-in-one installer is the easiest option.

**Ubuntu/Debian**
```bash
sudo apt-get install libpango-1.0-0 libpangocairo-1.0-0
```

---

### Step 3 — Download this repo

**Option A — Download as ZIP (no Git required)**
1. Go to [github.com/JJaammeessM/canvas-scraper-2](https://github.com/JJaammeessM/canvas-scraper-2)
2. Click the green **Code** button → **Download ZIP**
3. Unzip the downloaded file

**Option B — Clone with Git**
```bash
git clone https://github.com/JJaammeessM/canvas-scraper-2.git
```

---

### Step 4 — Install the tool

Open a terminal in the folder you downloaded/unzipped, then run:

**macOS / Linux**
```bash
pip3 install -e .
```

**Windows**
```
pip install -e .
```

---

### Step 5 — Run it

**macOS / Linux**
```bash
canvas-scraper
```

**Windows**
```
canvas-scraper
```

On first launch it will ask for your Canvas URL and API token, test the connection, and save your credentials. After that, use the arrow-key menu to browse your courses and download them as PDFs.

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

Running `canvas-scraper` launches the full arrow-key menu:

```
Canvas Scraper
──────────────────────────────────────────────────

Logged in as: Jane Smith

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
Make sure the system dependencies from Step 2 are installed.

**`canvas-scraper` not found after install (Windows)**  
Try closing and reopening the terminal. If it still doesn't work, run `python -m canvas_scraper` instead.

---

## License

MIT
