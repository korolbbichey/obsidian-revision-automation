"""Generates a topic tree (hierarchy) from the official exam specification."""

import json
import time

from google import genai
from rich.console import Console

console = Console()


HIERARCHY_PROMPT = """You are generating a structured topic hierarchy for A-Level revision notes.

You MUST derive the hierarchy strictly from the official specification text provided below. Do not invent topics that are not in the specification. Do not merge specification points that should be separate notes.

Each subtopic must map 1:1 with a specification sub-bullet. The hierarchy must be complete — every specification point must appear.

Specification text:
{syllabus}

Return a JSON object with this exact schema (raw JSON only — no markdown fences, no commentary):
{{
  "title": "{subject_name}",
  "chapters": [
    {{
      "title": "Chapter Name",
      "topics": [
        {{
          "title": "Topic Name",
          "subtopics": ["Subtopic A", "Subtopic B"]
        }}
      ]
    }}
  ]
}}
"""


def generate_hierarchy(
    client: genai.Client,
    subject_name: str,
    syllabus: str,
    model: str,
) -> dict:
    """Generate the topic hierarchy for a subject from its specification.

    Args:
        client: Google GenAI client.
        subject_name: Display name of the subject.
        syllabus: Full specification text from subjects.yaml.
        model: Model ID for the hierarchy call.

    Returns:
        Parsed JSON dict matching the hierarchy schema.

    Raises:
        ValueError: If the response cannot be parsed as valid JSON after retries.
    """
    prompt = HIERARCHY_PROMPT.format(
        syllabus=syllabus,
        subject_name=subject_name,
    )

    for attempt in range(2):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config={"max_output_tokens": 8000},
            )
            text = response.text.strip()

            # Strip markdown fences if the model wraps them anyway
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                if text.endswith("```"):
                    text = text[: text.rfind("```")]
                text = text.strip()

            hierarchy = json.loads(text)
            _validate_hierarchy(hierarchy)
            console.log(
                f"[green]Hierarchy generated for {subject_name} "
                f"({_count_subtopics(hierarchy)} subtopics)[/green]"
            )
            return hierarchy

        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            if attempt == 0:
                console.log(
                    f"[yellow]JSON parse failed for {subject_name}, retrying… "
                    f"({exc})[/yellow]"
                )
                time.sleep(1)
            else:
                raise ValueError(
                    f"Failed to parse hierarchy JSON for {subject_name} "
                    f"after 2 attempts: {exc}"
                ) from exc

    # Unreachable, but keeps type checkers happy
    raise ValueError("Hierarchy generation failed")


def _validate_hierarchy(data: dict) -> None:
    """Minimal structural validation of the hierarchy dict."""
    if "title" not in data or "chapters" not in data:
        raise KeyError("Hierarchy missing 'title' or 'chapters'")
    for chapter in data["chapters"]:
        if "title" not in chapter or "topics" not in chapter:
            raise KeyError(f"Chapter missing 'title' or 'topics': {chapter}")
        for topic in chapter["topics"]:
            if "title" not in topic or "subtopics" not in topic:
                raise KeyError(f"Topic missing 'title' or 'subtopics': {topic}")
            if not isinstance(topic["subtopics"], list) or not topic["subtopics"]:
                raise ValueError(f"Topic '{topic['title']}' has no subtopics")


def _count_subtopics(hierarchy: dict) -> int:
    """Return total number of subtopics in a hierarchy."""
    return sum(
        len(topic["subtopics"])
        for chapter in hierarchy["chapters"]
        for topic in chapter["topics"]
    )
