from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import install_rules as installer
from scripts.manage_project import DEFAULT_CONFIG, ManagerError


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="axiom-install-")
        self.root = Path(self.tmp.name).resolve()
        self.output = io.StringIO()
        self.redirect = contextlib.redirect_stdout(self.output)
        self.redirect.__enter__()

    def tearDown(self):
        self.redirect.__exit__(None, None, None)
        self.tmp.cleanup()

    def install(self):
        installer.install(self.root, write=True)

    def test_preview_does_not_create_any_file(self):
        installer.install(self.root)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_install_standalone_runtime_and_single_rule_block(self):
        self.install()
        text = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertEqual(text.count(installer.BEGIN), 1)
        self.assertIn("中文 Commit", text)
        self.assertEqual((self.root / ".axiom-manager/manage.py").read_bytes(), (installer.ROOT / "scripts/manage_project.py").read_bytes())
        config = json.loads((self.root / ".axiom-manager/config.json").read_text())
        self.assertFalse(config["auto_push"])

    def test_repeated_install_is_unchanged_and_has_no_backup(self):
        self.install()
        before = {p.relative_to(self.root): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob("*") if p.is_file()}
        self.install()
        after = {p.relative_to(self.root): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertIn("unchanged", self.output.getvalue())

    def test_reporter_crlf_bom_and_original_bytes_survive_install_uninstall(self):
        original = b"\xef\xbb\xbf# Existing\r\n\r\n<!-- Axiom-reporter:begin -->\r\nkeep\r\n<!-- Axiom-reporter:end -->"
        path = self.root / "AGENTS.md"
        path.write_bytes(original)
        self.install()
        self.assertTrue(path.read_bytes().startswith(original))
        backups = list((self.root / ".axiom-manager/backups").rglob("AGENTS.md"))
        self.assertEqual(backups[0].read_bytes(), original)
        installer.uninstall(self.root, write=True)
        self.assertEqual(path.read_bytes(), original)

    def test_update_replaces_only_own_block(self):
        self.install()
        path = self.root / "AGENTS.md"
        path.write_text("before\n" + installer.BEGIN + "\nold\n" + installer.END + "\nafter\n", encoding="utf-8")
        self.install()
        text = path.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("before\n"))
        self.assertTrue(text.endswith("after\n"))
        self.assertNotIn("\nold\n", text)

    def test_bad_markers_rejected_without_writes(self):
        for text in (installer.BEGIN, installer.END, installer.END + "\n" + installer.BEGIN,
                     installer.BEGIN + "\n" + installer.END + "\n" + installer.BEGIN):
            with self.subTest(text=text):
                (self.root / "AGENTS.md").write_text(text)
                with self.assertRaises(ManagerError):
                    self.install()
                self.assertEqual((self.root / "AGENTS.md").read_text(), text)
                self.assertFalse((self.root / ".axiom-manager").exists())

    def test_uninstall_preview_and_repeat(self):
        self.install()
        installer.uninstall(self.root)
        self.assertTrue((self.root / "AGENTS.md").exists())
        installer.uninstall(self.root, write=True)
        self.assertFalse((self.root / "AGENTS.md").exists())
        self.assertFalse((self.root / ".axiom-manager/manage.py").exists())
        installer.uninstall(self.root, write=True)

    def test_custom_config_survives_update_and_uninstall(self):
        self.install()
        path = self.root / ".axiom-manager/config.json"
        config = dict(DEFAULT_CONFIG, auto_push=True, checks=[["{python}", "-V"]])
        content = json.dumps(config).encode()
        path.write_bytes(content)
        self.install()
        self.assertEqual(path.read_bytes(), content)
        installer.uninstall(self.root, write=True)
        self.assertEqual(path.read_bytes(), content)
        self.assertTrue((self.root / ".axiom-manager/install-state.json").exists())

    def test_preexisting_config_is_not_deleted(self):
        path = self.root / ".axiom-manager/config.json"
        path.parent.mkdir()
        path.write_text(json.dumps(DEFAULT_CONFIG))
        self.install()
        installer.uninstall(self.root, write=True)
        self.assertTrue(path.exists())

    def test_modified_runtime_not_overwritten_or_removed(self):
        self.install()
        path = self.root / ".axiom-manager/manage.py"
        path.write_text("# user customization\n")
        with self.assertRaisesRegex(ManagerError, "本地修改"):
            self.install()
        installer.uninstall(self.root, write=True)
        self.assertEqual(path.read_text(), "# user customization\n")

    def test_corrupt_state_rejected(self):
        self.install()
        path = self.root / ".axiom-manager/install-state.json"
        path.write_text('{"schema": 1, "files": {"../../outside": "x"}}')
        before = (self.root / "AGENTS.md").read_bytes()
        with self.assertRaises(ManagerError):
            installer.uninstall(self.root, write=True)
        self.assertEqual((self.root / "AGENTS.md").read_bytes(), before)

    def test_transaction_rolls_back_partial_write(self):
        original = b"# Keep me\n"
        (self.root / "AGENTS.md").write_bytes(original)
        real = installer.atomic_write
        calls = 0

        def fail_once(path, data):
            nonlocal calls
            if path == self.root / ".axiom-manager/manage.py":
                calls += 1
                if calls == 1:
                    raise OSError("simulated disk failure")
            return real(path, data)

        with patch.object(installer, "atomic_write", side_effect=fail_once):
            with self.assertRaises(OSError):
                self.install()
        self.assertEqual((self.root / "AGENTS.md").read_bytes(), original)
        self.assertFalse((self.root / ".axiom-manager/manage.py").exists())
        self.assertFalse((self.root / ".axiom-manager-install.lock").exists())

    def test_symlink_cannot_write_outside(self):
        with tempfile.TemporaryDirectory() as outside:
            try:
                (self.root / ".axiom-manager").symlink_to(outside, target_is_directory=True)
            except OSError:
                if os.name != "nt":
                    raise
                import _winapi
                _winapi.CreateJunction(outside, str(self.root / ".axiom-manager"))
            with self.assertRaises(ManagerError):
                self.install()
            self.assertEqual(list(Path(outside).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
