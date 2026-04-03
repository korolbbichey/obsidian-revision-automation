"""Generates spec-complete revision notes for each subtopic and verifies coverage."""

import time

from google import genai
from rich.console import Console

console = Console()


LEAF_NOTE_PROMPT = """You are generating a formal A-Level revision note for the subtopic "{subtopic}" which is part of the topic "{topic}" in the chapter "{chapter}" of {subject}.

Cover every point in the specification below. Do not omit any bullet point. Do not add content that is not in the specification.

Write in formal academic English. No filler, no encouragement, no padding. Be concise but complete.

Use LaTeX inline notation ($...$) for all formulas and mathematical expressions.
Use fenced code blocks for all pseudocode and algorithm representations.

Follow this template exactly:

# {subtopic}

Part of: [[{topic}]]
tags: [revision, {subject_slug}, {chapter_slug}]

---

## Specification Points
Bullet list of every spec point this subtopic covers, verbatim or closely paraphrased from the official specification.

## Key Definitions
Term: precise formal definition.
(Only include terms the spec requires students to define.)

## Rules & Formulas
All formulas in LaTeX. State any conditions on their validity.
$formula$ — brief label of what it gives.
For Computer Science: include pseudocode in a code block where relevant.

## Conditions & Special Cases
Any constraints, domain restrictions, exceptions, or edge cases the specification requires students to know.

## Worked Example
One concise worked example. Steps numbered. No commentary beyond what is needed to follow the working. Final answer clearly stated.

## Examiner Notes
2–3 points on how this subtopic is assessed: command words used, common errors that lose marks, mark scheme expectations.

Specification text for this subtopic's chapter:
{spec_text}
"""


VERIFY_PROMPT = """Compare this revision note against the specification points.

Specification points:
{spec_points}

Generated note:
{note_content}

List any specification points that are missing or inaccurately covered.
If everything is covered accurately, respond with only: PASS
"""


def generate_leaf_note(
    client: genai.Client,
    subject: str,
    chapter: str,
    topic: str,
    subtopic: str,
    spec_text: str,
    model: str,
) -> str:
    """Generate the markdown content for a single leaf (subtopic) note.

    Args:
        client: Google GenAI client.
        subject: Subject display name.
        chapter: Chapter title.
        topic: Parent topic title.
        subtopic: Subtopic title (this note's title).
        spec_text: Relevant specification text for the chapter.
        model: Model ID for note generation.

    Returns:
        Markdown string for the leaf note.
    """
    subject_slug = _slugify(subject)
    chapter_slug = _slugify(chapter)

    prompt = LEAF_NOTE_PROMPT.format(
        subtopic=subtopic,
        topic=topic,
        chapter=chapter,
        subject=subject,
        subject_slug=subject_slug,
        chapter_slug=chapter_slug,
        spec_text=spec_text,
    )

    response = client.models.generate_content(
        model=model,
        contents=prompt,
    )
    return response.text.strip()


def verify_note(
    client: genai.Client,
    note_content: str,
    spec_points: str,
    model: str,
) -> str:
    """Run a verification pass on a generated note.

    Args:
        client: Google GenAI client.
        note_content: The generated markdown note.
        spec_points: The specification text to verify against.
        model: Model ID for the cheap verification call.

    Returns:
        "PASS" if the note covers everything, otherwise a string listing gaps.
    """
    prompt = VERIFY_PROMPT.format(
        spec_points=spec_points,
        note_content=note_content,
    )

    response = client.models.generate_content(
        model=model,
        contents=prompt,
    )
    return response.text.strip()


def generate_and_verify_note(
    client: genai.Client,
    subject: str,
    chapter: str,
    topic: str,
    subtopic: str,
    spec_text: str,
    notes_model: str,
    verify_model: str = "gemini-2.0-flash",
) -> tuple[str, bool]:
    """Generate a leaf note and verify it against the spec.

    If verification fails, regenerates once. If it still fails, returns the
    note with needs_review=True.

    Args:
        client: Google GenAI client.
        subject: Subject display name.
        chapter: Chapter title.
        topic: Parent topic title.
        subtopic: Subtopic title.
        spec_text: Specification text for the chapter.
        notes_model: Model for note generation.
        verify_model: Model for verification pass.

    Returns:
        Tuple of (note_content, needs_review).
    """
    note_content = generate_leaf_note(
        client, subject, chapter, topic, subtopic, spec_text, notes_model
    )

    result = verify_note(client, note_content, spec_text, verify_model)

    if result.strip().upper() == "PASS":
        return note_content, False

    console.log(
        f"[yellow]Verification failed for '{subtopic}', regenerating…[/yellow]"
    )
    console.log(f"[dim]Gaps: {result}[/dim]")

    # Regenerate once
    time.sleep(0.3)
    note_content = generate_leaf_note(
        client, subject, chapter, topic, subtopic, spec_text, notes_model
    )

    result = verify_note(client, note_content, spec_text, verify_model)

    if result.strip().upper() == "PASS":
        return note_content, False

    console.log(
        f"[red]Verification still failed for '{subtopic}' — flagging for review[/red]"
    )
    console.log(f"[dim]Gaps: {result}[/dim]")
    return note_content, True


def _slugify(text: str) -> str:
    """Convert a title to a lowercase slug for tags."""
    return text.lower().replace(" ", "-").replace("–", "-").replace("—", "-")
