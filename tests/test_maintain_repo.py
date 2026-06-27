"""Unit tests for the repository maintenance/audit helpers."""
import json

import maintain_repo as maint


# ---------------------------------------------------------------------------
# Filesystem scanners
# ---------------------------------------------------------------------------

class TestScanCore:
    def test_returns_sorted_txt_names_only(self, tmp_path):
        core = tmp_path / "core"
        core.mkdir()
        (core / "b.txt").write_text("x")
        (core / "a.txt").write_text("x")
        (core / "notes.md").write_text("x")  # ignored
        assert maint.scan_core(core) == ["a.txt", "b.txt"]

    def test_missing_dir_returns_empty(self, tmp_path):
        assert maint.scan_core(tmp_path / "core") == []


class TestScanVariants:
    def test_maps_filename_to_variant_folders(self, tmp_path):
        variants = tmp_path / "variants"
        (variants / "nolvus").mkdir(parents=True)
        (variants / "lost_legacy_2").mkdir(parents=True)
        (variants / "nolvus" / "crafting.txt").write_text("x")
        (variants / "lost_legacy_2" / "crafting.txt").write_text("x")
        (variants / "nolvus" / "bows.txt").write_text("x")

        result = maint.scan_variants(variants)
        assert set(result["crafting.txt"]) == {"nolvus", "lost_legacy_2"}
        assert result["bows.txt"] == ["nolvus"]


# ---------------------------------------------------------------------------
# Manifest loading (with template self-generation)
# ---------------------------------------------------------------------------

class TestLoadManifest:
    def test_generates_template_when_missing(self, tmp_path):
        manifest_path = tmp_path / "manifest.json"
        data = maint.load_manifest(manifest_path)
        assert manifest_path.exists()
        assert "_example_variant_script.txt" in data

    def test_reads_existing_manifest(self, tmp_path):
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps({"x.txt": ["nolvus"]}), encoding="utf-8")
        assert maint.load_manifest(manifest_path) == {"x.txt": ["nolvus"]}


# ---------------------------------------------------------------------------
# Audit (compares manifest declarations against the physical filesystem)
# ---------------------------------------------------------------------------

class TestAuditRepository:
    def test_flags_ghost_entry(self, capsys):
        maint.audit_repository({"x.txt": ["nolvus"]}, {})
        assert "GHOST ENTRY" in capsys.readouterr().out

    def test_flags_undocumented_file(self, capsys):
        maint.audit_repository({}, {"x.txt": ["nolvus"]})
        assert "UNDOCUMENTED" in capsys.readouterr().out

    def test_clean_repo_passes(self, capsys):
        maint.audit_repository({"x.txt": ["nolvus"]}, {"x.txt": ["nolvus"]})
        assert "Health Check Passed" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Markdown generation
# ---------------------------------------------------------------------------

class TestGenerateMarkdown:
    def test_writes_core_bullets_and_variant_table(self, tmp_path):
        md_path = tmp_path / "manifest.md"
        maint.generate_markdown(
            manifest_data={"crafting.txt": ["nolvus", "lost_legacy_2"]},
            core_scripts=["backpacks.txt"],
            md_path=md_path,
        )
        text = md_path.read_text(encoding="utf-8")
        assert "# Repository Manifest" in text
        assert "`backpacks.txt`" in text
        assert "`crafting.txt`" in text
        assert "| Script Name | Active Variants |" in text
