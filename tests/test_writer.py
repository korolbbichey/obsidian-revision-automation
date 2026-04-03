"""Tests for generator.writer — covers safe_name, file creation, wikilinks,
template structure, and REVIEW flag behaviour."""

from pathlib import Path

import pytest

from generator.writer import build_vault_paths, safe_name, write_hub_note, write_leaf_note


class TestSafeName:
    def test_strips_forbidden_characters(self):
        assert safe_name('Test/File:Name?With*Bad"Chars<>|') == "TestFileNameWithBadChars"

    def test_preserves_spaces(self):
        assert safe_name("A-Level Mathematics") == "A-Level Mathematics"

    def test_preserves_hyphens_and_dots(self):
        assert safe_name("Topic 1.2 - Sub") == "Topic 1.2 - Sub"

    def test_empty_string(self):
        assert safe_name("") == ""

    def test_backslash_stripped(self):
        assert safe_name("path\\to\\file") == "pathtofile"

    def test_no_truncation(self):
        long_name = "A" * 300
        assert safe_name(long_name) == long_name


class TestWriteHubNote:
    def test_creates_file_with_links(self, tmp_path):
        hub_path = tmp_path / "Subject" / "Subject.md"
        children = ["Chapter 1", "Chapter 2"]
        result = write_hub_note(tmp_path, hub_path, "Subject", children, "Chapters")

        assert result is True
        assert hub_path.exists()

        content = hub_path.read_text(encoding="utf-8")
        assert "# Subject" in content
        assert "## Chapters" in content
        assert "- [[Chapter 1]]" in content
        assert "- [[Chapter 2]]" in content

    def test_skips_existing_without_overwrite(self, tmp_path):
        hub_path = tmp_path / "Subject.md"
        hub_path.parent.mkdir(parents=True, exist_ok=True)
        hub_path.write_text("existing", encoding="utf-8")

        result = write_hub_note(tmp_path, hub_path, "Subject", ["Ch1"], "Chapters", overwrite=False)
        assert result is False
        assert hub_path.read_text(encoding="utf-8") == "existing"

    def test_overwrites_when_flag_set(self, tmp_path):
        hub_path = tmp_path / "Subject.md"
        hub_path.parent.mkdir(parents=True, exist_ok=True)
        hub_path.write_text("old content", encoding="utf-8")

        result = write_hub_note(tmp_path, hub_path, "Subject", ["Ch1"], "Chapters", overwrite=True)
        assert result is True
        assert "[[Ch1]]" in hub_path.read_text(encoding="utf-8")

    def test_hub_has_no_content_beyond_links(self, tmp_path):
        hub_path = tmp_path / "Hub.md"
        write_hub_note(tmp_path, hub_path, "Hub", ["A", "B"], "Topics")

        content = hub_path.read_text(encoding="utf-8")
        lines = [l.strip() for l in content.strip().splitlines() if l.strip()]
        # Should only contain: title, heading, and link lines
        assert lines == ["# Hub", "## Topics", "- [[A]]", "- [[B]]"]


class TestWriteLeafNote:
    def test_creates_file_with_content(self, tmp_path):
        leaf_path = tmp_path / "Note.md"
        note_content = "# Subtopic\n\nPart of: [[Topic]]\ntags: [revision]\n\n---\n\nContent here."

        result = write_leaf_note(tmp_path, leaf_path, note_content)
        assert result is True
        assert leaf_path.exists()
        assert leaf_path.read_text(encoding="utf-8") == note_content

    def test_review_flag_in_frontmatter(self, tmp_path):
        leaf_path = tmp_path / "Note.md"
        note_content = "# Subtopic\n\nContent here."

        write_leaf_note(tmp_path, leaf_path, note_content, needs_review=True)
        content = leaf_path.read_text(encoding="utf-8")

        assert "review: true" in content
        assert "review_reason:" in content

    def test_no_review_flag_when_passing(self, tmp_path):
        leaf_path = tmp_path / "Note.md"
        note_content = "# Subtopic\n\nContent here."

        write_leaf_note(tmp_path, leaf_path, note_content, needs_review=False)
        content = leaf_path.read_text(encoding="utf-8")

        assert "review:" not in content

    def test_skips_existing_without_overwrite(self, tmp_path):
        leaf_path = tmp_path / "Note.md"
        leaf_path.write_text("old", encoding="utf-8")

        result = write_leaf_note(tmp_path, leaf_path, "new content", overwrite=False)
        assert result is False
        assert leaf_path.read_text(encoding="utf-8") == "old"


class TestBuildVaultPaths:
    def test_returns_correct_paths(self, tmp_path):
        paths = build_vault_paths(
            tmp_path, "A-Level Maths", "Pure", "Algebra", "Surds"
        )
        assert paths["subject_hub"] == tmp_path / "A-Level Maths" / "A-Level Maths.md"
        assert paths["chapter_hub"] == tmp_path / "A-Level Maths" / "Pure" / "Pure.md"
        assert paths["topic_hub"] == tmp_path / "A-Level Maths" / "Pure" / "Algebra" / "Algebra.md"
        assert paths["leaf"] == tmp_path / "A-Level Maths" / "Pure" / "Algebra" / "Surds.md"

    def test_strips_unsafe_characters_from_paths(self, tmp_path):
        paths = build_vault_paths(
            tmp_path, "Sub/ject", "Ch:apter", "To?pic", 'Sub*"topic'
        )
        assert paths["subject_hub"] == tmp_path / "Subject" / "Subject.md"
        assert paths["leaf"].name == "Subtopic.md"

    def test_wikilink_text_matches_filename(self, tmp_path):
        """Subtopic filenames must exactly match the wikilink text."""
        subtopic = "Laws of Indices"
        paths = build_vault_paths(tmp_path, "Maths", "Pure", "Algebra", subtopic)
        assert paths["leaf"].stem == subtopic
