from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import install_rules as installer
from scripts import manage_project as manager


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="axiom-layout-")
        self.root = Path(self.tmp.name).resolve()
        self.output = io.StringIO()
        self.stdout = contextlib.redirect_stdout(self.output)
        self.stderr = contextlib.redirect_stderr(self.output)
        self.stdout.__enter__()
        self.stderr.__enter__()
        self.write("README.md", "# Demo\n\n说明。\n")
        self.write("src/app.py", "print('demo')\n")

    def tearDown(self):
        self.stderr.__exit__(None, None, None)
        self.stdout.__exit__(None, None, None)
        self.tmp.cleanup()

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")

    def policy(self):
        return manager.parse_layout((self.root / "AGENTS.md").read_text(encoding="utf-8"))

    def save(self, policy):
        self.write("AGENTS.md", manager.render_layout(policy))

    def init(self):
        manager.initialize_layout(self.root, write=True)

    def rule(self, **extra):
        rule = {"id": "code", "paths": ["src/*.py"], "name_pattern": r"[a-z][a-z0-9_]*\.py",
                "naming": "英文小写下划线 .py 文件名", "purpose": "src 中的程序源代码"}
        rule.update(extra)
        return rule

    def test_missing_rules_are_reported(self):
        with self.assertRaisesRegex(manager.ManagerError, "缺少可检查"):
            manager.audit_layout(self.root)

    def test_init_preview_is_read_only(self):
        before = sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*"))
        manager.initialize_layout(self.root)
        self.assertEqual(before, sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*")))

    def test_init_covers_current_files_with_unique_sources(self):
        self.init()
        sources = manager.audit_layout(self.root, verbose=True)
        self.assertEqual(set(sources), {"AGENTS.md", "README.md", "src/app.py"})
        self.assertIn("src/app.py → AGENTS.md /", self.output.getvalue())

    def test_init_preserves_existing_human_rules_bom_crlf_and_backup(self):
        original = "\ufeff# 原有规则\r\n\r\n源代码统一存放 src/，文件名使用小写英文。".encode("utf-8")
        (self.root / "AGENTS.md").write_bytes(original)
        self.init()
        self.assertTrue((self.root / "AGENTS.md").read_bytes().startswith(original))
        backups = list((self.root / ".axiom-manager/backups").rglob("AGENTS.md"))
        self.assertEqual(backups[0].read_bytes(), original)
        manager.audit_layout(self.root)

    def test_bom_before_policy_marker_is_not_treated_as_missing(self):
        self.init()
        original = b"\xef\xbb\xbf" + (self.root / "AGENTS.md").read_bytes()
        (self.root / "AGENTS.md").write_bytes(original)
        self.init()
        self.assertEqual((self.root / "AGENTS.md").read_bytes(), original)
        manager.audit_layout(self.root)

    def test_init_does_not_overwrite_existing_rules_or_admit_new_file(self):
        self.init()
        before = (self.root / "AGENTS.md").read_bytes()
        self.write("src/new_feature.py", "new")
        self.init()
        self.assertEqual((self.root / "AGENTS.md").read_bytes(), before)
        with self.assertRaisesRegex(manager.ManagerError, "new_feature.py.*没有存放规则出处"):
            manager.audit_layout(self.root)

    def test_new_category_is_admitted_only_after_rule_update(self):
        self.init()
        self.write("reports/result.csv", "value\n1\n")
        with self.assertRaises(manager.ManagerError):
            manager.audit_layout(self.root)
        policy = self.policy()
        policy["rules"].append(self.rule(id="analysis", paths=["reports/*.csv"], name_pattern=r"[a-z_]+\.csv",
                                         naming="英文下划线结果名 .csv", purpose="数据分析任务的结果表", task="数据分析"))
        self.save(policy)
        self.assertEqual(manager.audit_layout(self.root)["reports/result.csv"], "analysis")

    def test_name_and_location_are_checked_independently(self):
        self.init()
        policy = self.policy()
        policy["rules"] = [r for r in policy["rules"] if "src/app.py" not in r["paths"]] + [self.rule()]
        self.save(policy)
        self.write("src/BadName.py", "bad")
        self.write("src/nested/module.py", "nested")
        with self.assertRaises(manager.ManagerError) as error:
            manager.audit_layout(self.root)
        self.assertIn("BadName.py：命名不符合", str(error.exception))
        self.assertIn("nested/module.py：没有存放规则出处", str(error.exception))

    def test_overlapping_rules_require_unique_source(self):
        self.init()
        policy = self.policy()
        policy["rules"].append(self.rule())
        self.save(policy)
        with self.assertRaisesRegex(manager.ManagerError, "同时匹配多条规则"):
            manager.audit_layout(self.root)

    def test_special_task_has_its_own_location_and_naming(self):
        self.init()
        policy = self.policy()
        policy["rules"].append(self.rule(id="ui-evidence", paths=["tests/evidence/ui/*.png"],
                                         name_pattern=r"[a-z_]+_step_[0-9]{2}\.png", naming="功能名_step_两位步骤号.png",
                                         purpose="界面验收任务的截图原件", task="界面验收截图"))
        self.save(policy)
        self.write("tests/evidence/ui/login_step_01.png", "image fixture")
        self.assertEqual(manager.audit_layout(self.root)["tests/evidence/ui/login_step_01.png"], "ui-evidence")
        self.write("login_step_02.png", "wrong location")
        with self.assertRaisesRegex(manager.ManagerError, "login_step_02.png.*没有存放规则出处"):
            manager.audit_layout(self.root)

    def test_ignored_files_are_not_silently_omitted(self):
        self.write(".gitignore", "*.dat\n")
        self.init()
        self.write("new.dat", "not classified")
        with self.assertRaisesRegex(manager.ManagerError, "new.dat.*没有存放规则出处"):
            manager.audit_layout(self.root)

    def test_generated_cache_and_git_database_are_accounted_for(self):
        self.init()
        self.write("src/__pycache__/app.cpython-312.pyc", "cache")
        self.write(".git/objects/data", "git database")
        self.assertEqual(set(manager.audit_layout(self.root)), {"AGENTS.md", "README.md", "src/app.py"})

    def test_bootstrap_escapes_glob_characters_in_real_names(self):
        self.write("src/file[1].py", "literal")
        self.init()
        self.assertIn("src/file[1].py", manager.audit_layout(self.root))
        self.write("src/file1.py", "different")
        with self.assertRaises(manager.ManagerError):
            manager.audit_layout(self.root)

    def test_glob_is_root_anchored_and_double_star_is_recursive(self):
        self.assertTrue(manager.path_matches("src/a.py", "src/*.py"))
        self.assertFalse(manager.path_matches("src/nested/a.py", "src/*.py"))
        self.assertFalse(manager.path_matches("other/src/a.py", "src/*.py"))
        self.assertTrue(manager.path_matches("src/a.py", "src/**/*.py"))
        self.assertTrue(manager.path_matches("src/nested/a.py", "src/**/*.py"))

    def test_broad_exclusions_and_missing_purpose_are_rejected(self):
        self.init()
        for change in ("purpose", "naming", "broad", "exclude-reason", "duplicate-id", "invalid-regex"):
            with self.subTest(change=change):
                policy = self.policy()
                if change in {"purpose", "naming"}:
                    policy["rules"][0][change] = ""
                elif change == "broad":
                    policy["excluded"] = [{"path": "**/*", "reason": "too broad"}]
                elif change == "exclude-reason":
                    policy["excluded"] = [{"path": "reports/**"}]
                elif change == "duplicate-id":
                    policy["rules"].append(dict(policy["rules"][0]))
                else:
                    policy["rules"][0]["name_pattern"] = "["
                self.save(policy)
                with self.assertRaises(manager.ManagerError):
                    manager.audit_layout(self.root)
                # 恢复有效初稿供下一个子场景使用。
                self.save(manager.bootstrap_layout(self.root))

    def test_installer_creates_rules_and_preserves_project_customization(self):
        installer.install(self.root, write=True)
        self.assertIn(".axiom-manager/manage.py", manager.audit_layout(self.root))
        policy = self.policy()
        policy["rules"][0]["purpose"] = "当前项目已核对的具体职责"
        text = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        span = manager.layout_span(text)
        self.write("AGENTS.md", text[:span[0]] + manager.render_layout(policy) + text[span[1]:])
        installer.install(self.root, write=True)
        self.assertEqual(self.policy(), policy)

    def test_invalid_layout_prevents_installer_writes(self):
        original = manager.LAYOUT_BEGIN + "\ninvalid\n"
        self.write("AGENTS.md", original)
        with self.assertRaises(manager.ManagerError):
            installer.install(self.root, write=True)
        self.assertEqual((self.root / "AGENTS.md").read_text(), original)
        self.assertFalse((self.root / ".axiom-manager").exists())

    def test_layout_cli_requires_rules_and_explicit_initialization_write(self):
        self.assertEqual(manager.main(["--project", str(self.root), "layout"]), 1)
        self.assertEqual(manager.main(["--project", str(self.root), "layout", "--init"]), 0)
        self.assertFalse((self.root / "AGENTS.md").exists())
        self.assertEqual(manager.main(["--project", str(self.root), "layout", "--init", "--write"]), 0)
        self.assertEqual(manager.main(["--project", str(self.root), "layout", "--verbose"]), 0)

    def test_inventory_does_not_follow_external_directory_links(self):
        self.init()
        with tempfile.TemporaryDirectory(prefix="axiom-layout-outside-") as outside:
            (Path(outside) / "private.txt").write_text("outside")
            try:
                (self.root / "linked").symlink_to(outside, target_is_directory=True)
            except OSError:
                if os.name != "nt":
                    raise
                import _winapi
                _winapi.CreateJunction(outside, str(self.root / "linked"))
            files = manager.inventory_files(self.root, self.policy()["excluded"])
            self.assertIn("linked", files)
            self.assertFalse(any("private.txt" in name for name in files))


if __name__ == "__main__":
    unittest.main()
