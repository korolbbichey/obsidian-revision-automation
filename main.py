"""CLI entrypoint for the Obsidian Revision Notes Generator."""

import json
import os
import time
from pathlib import Path
from typing import Optional

import typer
import yaml
from dotenv import load_dotenv
from google import genai
from google.genai.errors import APIError, ClientError, ServerError
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from generator.hierarchy import generate_hierarchy
from generator.notes import generate_and_verify_note
from generator.writer import build_vault_paths, safe_name, write_hub_note, write_leaf_note

load_dotenv()

app = typer.Typer(help="Auto-generate structured A-Level revision notes into an Obsidian vault.")
console = Console()

CONFIG_DIR = Path(__file__).parent / "config"
CACHE_DIR = Path(__file__).parent / ".cache"


def _load_settings() -> dict:
    """Load model settings from config/settings.yaml."""
    settings_path = CONFIG_DIR / "settings.yaml"
    if not settings_path.exists():
        console.print("[red]config/settings.yaml not found[/red]")
        raise typer.Exit(1)
    with open(settings_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_subjects() -> list[dict]:
    """Load subject definitions from config/subjects.yaml."""
    subjects_path = CONFIG_DIR / "subjects.yaml"
    if not subjects_path.exists():
        console.print("[red]config/subjects.yaml not found[/red]")
        raise typer.Exit(1)
    with open(subjects_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("subjects", [])


def _get_vault_path() -> Path:
    """Read the vault path from environment and validate it."""
    vault_path = os.environ.get("OBSIDIAN_VAULT_PATH")
    if not vault_path:
        console.print(
            "[red]OBSIDIAN_VAULT_PATH not set. "
            "Check your .env file (see .env.example).[/red]"
        )
        raise typer.Exit(1)
    path = Path(vault_path)
    if not path.is_dir():
        console.print(f"[red]Vault path does not exist: {path}[/red]")
        raise typer.Exit(1)
    return path


def _get_client() -> genai.Client:
    """Create a Google GenAI client, validating the API key."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        console.print(
            "[red]GEMINI_API_KEY not set. "
            "Copy .env.example to .env and add your key.[/red]"
        )
        raise typer.Exit(1)
    return genai.Client(api_key=api_key)


def _hierarchy_cache_path(subject_name: str) -> Path:
    """Return the path to the cached hierarchy JSON for a subject."""
    slug = subject_name.lower().replace(" ", "_")
    return CACHE_DIR / f"{slug}_hierarchy.json"


def _load_cached_hierarchy(subject_name: str) -> dict | None:
    """Load a cached hierarchy from disk, or return None if not found."""
    path = _hierarchy_cache_path(subject_name)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        console.log(f"[cyan]Loaded cached hierarchy for {subject_name}[/cyan]")
        return data
    except (json.JSONDecodeError, OSError):
        return None


def _save_hierarchy_cache(subject_name: str, hierarchy: dict) -> None:
    """Save a hierarchy dict to the cache directory."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _hierarchy_cache_path(subject_name)
    path.write_text(json.dumps(hierarchy, indent=2, ensure_ascii=False), encoding="utf-8")
    console.log(f"[cyan]Cached hierarchy to {path.name}[/cyan]")


def _api_call_with_retry(func, *args, max_retries: int = 3, **kwargs):
    """Wrap an API call with exponential backoff for rate limits."""
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except ClientError as exc:
            if "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc):
                wait = 2 ** (attempt + 1)
                console.log(f"[yellow]Rate limited, waiting {wait}s…[/yellow]")
                time.sleep(wait)
            else:
                console.log(f"[red]API error: {exc}[/red]")
                raise
        except (APIError, ServerError) as exc:
            console.log(f"[red]API error: {exc}[/red]")
            raise
    console.log("[red]Max retries exceeded for rate limit[/red]")
    return None


def _process_subject(
    client: genai.Client,
    subject: dict,
    vault_root: Path,
    settings: dict,
    overwrite: bool,
    refresh_hierarchy: bool = False,
) -> None:
    """Generate hierarchy and notes for a single subject."""
    subject_name = subject["name"]
    syllabus = subject.get("syllabus", "")

    if not syllabus.strip():
        console.print(f"[red]No syllabus text for {subject_name} — skipping[/red]")
        return

    console.rule(f"[bold]{subject_name}[/bold]")

    # Step 1: Load cached hierarchy or generate a new one
    hierarchy = None
    if not refresh_hierarchy:
        hierarchy = _load_cached_hierarchy(subject_name)

    if hierarchy is None:
        console.print("[bold]Generating topic hierarchy…[/bold]")
        try:
            hierarchy = _api_call_with_retry(
                generate_hierarchy,
                client,
                subject_name,
                syllabus,
                settings["hierarchy_model"],
            )
        except (ValueError, APIError) as exc:
            console.print(f"[red]Failed to generate hierarchy for {subject_name}: {exc}[/red]")
            return

        if hierarchy is None:
            console.print(f"[red]Hierarchy generation failed for {subject_name} — skipping[/red]")
            return

        _save_hierarchy_cache(subject_name, hierarchy)

    # Step 2: Write hub notes and generate leaf notes
    chapters = hierarchy["chapters"]
    chapter_titles = [ch["title"] for ch in chapters]

    # Subject hub
    subject_dir = vault_root / safe_name(subject_name)
    subject_hub = subject_dir / f"{safe_name(subject_name)}.md"
    write_hub_note(vault_root, subject_hub, subject_name, chapter_titles, "Chapters", overwrite)

    # Count total subtopics for progress
    total_subtopics = sum(
        len(topic["subtopics"])
        for ch in chapters
        for topic in ch["topics"]
    )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(f"Generating notes for {subject_name}", total=total_subtopics)

        for chapter in chapters:
            chapter_title = chapter["title"]
            topic_titles = [t["title"] for t in chapter["topics"]]

            # Chapter hub
            chapter_dir = subject_dir / safe_name(chapter_title)
            chapter_hub = chapter_dir / f"{safe_name(chapter_title)}.md"
            write_hub_note(
                vault_root, chapter_hub, chapter_title, topic_titles, "Topics", overwrite
            )

            for topic in chapter["topics"]:
                topic_title = topic["title"]
                subtopics = topic["subtopics"]

                # Topic hub
                topic_dir = chapter_dir / safe_name(topic_title)
                topic_hub = topic_dir / f"{safe_name(topic_title)}.md"
                write_hub_note(
                    vault_root, topic_hub, topic_title, subtopics, "Subtopics", overwrite
                )

                for subtopic in subtopics:
                    progress.update(task, description=f"[cyan]{subtopic}[/cyan]")

                    paths = build_vault_paths(
                        vault_root, subject_name, chapter_title, topic_title, subtopic
                    )
                    leaf_path = paths["leaf"]

                    if leaf_path.exists() and not overwrite:
                        console.log(
                            f"[dim]Skipping (exists): "
                            f"{leaf_path.relative_to(vault_root)}[/dim]"
                        )
                        progress.advance(task)
                        continue

                    try:
                        note_content, needs_review = _api_call_with_retry(
                            generate_and_verify_note,
                            client,
                            subject_name,
                            chapter_title,
                            topic_title,
                            subtopic,
                            syllabus,
                            settings["notes_model"],
                        )
                        if note_content is None:
                            console.log(
                                f"[red]Skipping '{subtopic}' — API call failed[/red]"
                            )
                            progress.advance(task)
                            continue

                        write_leaf_note(
                            vault_root, leaf_path, note_content, needs_review, overwrite
                        )

                    except Exception as exc:
                        console.log(f"[red]Error generating '{subtopic}': {exc}[/red]")

                    progress.advance(task)
                    time.sleep(settings.get("api_delay_seconds", 0.3))

    console.print(f"[bold green]Done: {subject_name}[/bold green]")


@app.command()
def generate(
    subject: Optional[str] = typer.Option(None, help="Subject name to generate notes for"),
    all_subjects: bool = typer.Option(False, "--all", help="Generate notes for all subjects"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite existing files"),
    refresh_hierarchy: bool = typer.Option(False, "--refresh-hierarchy", help="Regenerate the topic hierarchy (ignores cache)"),
) -> None:
    """Generate revision notes for one or all configured subjects."""
    if not subject and not all_subjects:
        console.print("[red]Specify --subject or --all[/red]")
        raise typer.Exit(1)

    settings = _load_settings()
    subjects = _load_subjects()
    vault_root = _get_vault_path()
    client = _get_client()

    if all_subjects:
        targets = subjects
    else:
        targets = [s for s in subjects if s["name"] == subject]
        if not targets:
            available = ", ".join(s["name"] for s in subjects)
            console.print(f"[red]Subject '{subject}' not found. Available: {available}[/red]")
            raise typer.Exit(1)

    for subj in targets:
        _process_subject(client, subj, vault_root, settings, overwrite, refresh_hierarchy)


@app.command()
def list() -> None:
    """List all configured subjects."""
    subjects = _load_subjects()
    if not subjects:
        console.print("[yellow]No subjects configured in config/subjects.yaml[/yellow]")
        return
    console.print("[bold]Configured subjects:[/bold]")
    for s in subjects:
        console.print(
            f"  • {s['name']} ({s.get('exam_board', '?')} — {s.get('specification_code', '?')})"
        )


if __name__ == "__main__":
    app()
