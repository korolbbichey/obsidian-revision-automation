# Obsidian Revision Notes Generator

A Python CLI tool that auto-generates structured A-Level revision notes directly into an Obsidian vault using Google Gemini (free tier). Notes are linked via wikilinks so that Obsidian's graph view resembles a mind map, radiating outward from a subject root node.

## Features

- Generates a full topic hierarchy from your exam specification text
- Produces spec-complete leaf notes covering every bullet point in the syllabus
- Verification pass checks each note against the specification before writing
- Incremental generation — skips existing files, only generates what's missing
- Wikilink structure designed for Obsidian's graph view (tree shape, no circular links)
- Rich CLI output with progress bars and coloured logging

## Vault Structure

```
{vault}/A-Level Mathematics/
├── A-Level Mathematics.md              ← root hub, links to all chapters
├── Chapter 1 – Proof/
│   ├── Chapter 1 – Proof.md            ← chapter hub, links to topics
│   └── Proof/
│       ├── Proof.md                    ← topic hub, links to subtopics
│       ├── Proof by deduction.md       ← leaf note (full revision content)
│       ├── Proof by exhaustion.md
│       └── ...
├── Chapter 2 – Algebra and Functions/
│   └── ...
└── ...
```

## Prerequisites

- Python 3.11+
- A free Google Gemini API key (get one at [aistudio.google.com](https://aistudio.google.com/apikey))
- An Obsidian vault (any folder on disk)

## Setup

1. **Clone the repository:**
   ```bash
   git clone <repo-url>
   cd obsidian-revision-gen
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables:**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and fill in:
   ```
   GEMINI_API_KEY=your_gemini_api_key_here
   OBSIDIAN_VAULT_PATH=/absolute/path/to/your/obsidian/vault
   ```

4. **Add specification text:**
   Edit `config/subjects.yaml` and paste the full official syllabus text for each subject under the `syllabus` field. The tool depends on this text to generate accurate notes — do not rely on the model's training data.

## Usage

```bash
# Generate notes for one subject
python main.py generate --subject "A-Level Mathematics"

# Generate notes for all configured subjects
python main.py generate --all

# Overwrite existing files (re-generate everything)
python main.py generate --subject "A-Level Mathematics" --overwrite

# List configured subjects
python main.py list
```

### Incremental Updates

Without `--overwrite`, the tool skips any file that already exists. This means you can safely re-run the command to fill in missing notes (e.g. after rate limiting) without regenerating what's already done.

## Configuration

### `config/settings.yaml`

```yaml
hierarchy_model: "gemini-2.0-flash"    # model for generating the topic tree
notes_model: "gemini-2.0-flash"        # model for generating leaf notes
verify_model: "gemini-2.0-flash"       # model for the verification pass
api_delay_seconds: 4                   # delay between subtopics (rate limit)
```

### `config/subjects.yaml`

Define subjects with their exam board, spec code, and full syllabus text. See the file for the expected format.

## Rate Limits

The Gemini free tier allows 15 requests per minute. Each subtopic requires ~3 API calls (generate + verify, possibly regenerate). The default `api_delay_seconds: 4` keeps usage within limits. If you still hit rate limits, the tool retries with exponential backoff up to 3 times before skipping the subtopic.

## Testing

```bash
pytest tests/ -v
```

Tests mock the API client — no real API calls are made.

## Project Structure

```
├── main.py                  ← CLI entrypoint (typer app)
├── generator/
│   ├── hierarchy.py         ← generates topic tree from specification
│   ├── notes.py             ← generates and verifies revision notes
│   └── writer.py            ← writes .md files to vault with wikilinks
├── config/
│   ├── settings.yaml        ← model and rate limit settings
│   └── subjects.yaml        ← subject definitions with syllabus text
├── tests/
│   └── test_writer.py       ← tests for file writing and path handling
├── .env.example             ← template for environment variables
├── requirements.txt
└── CLAUDE.md                ← development instructions
```
## Important note
Due to the deletion of the filename truncation, you can get an error "Errno 22" that represents a filename that is too long. To avoid this issue, on Windows platform, you can run this command in the admin PowerShell:
```
New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force
```
[!WARNING]
If you are unsure about using a PowerShell command, do not. It can break Windows.

## Note Format

Each leaf note follows a strict template:

- **Specification Points** — every spec bullet, verbatim or closely paraphrased
- **Key Definitions** — terms the spec requires students to define
- **Rules & Formulas** — LaTeX formulas with validity conditions
- **Conditions & Special Cases** — constraints, exceptions, edge cases
- **Worked Example** — one concise example with numbered steps
- **Examiner Notes** — how the subtopic is assessed, common errors

Notes that fail the verification pass are written with a `review: true` flag in their YAML frontmatter.
