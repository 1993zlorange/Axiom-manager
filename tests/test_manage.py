from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import install_rules as installer
from scripts import manage_project as manager


class MessageVersionTests(unittest.TestCase):
    def test_chinese_messages_and_breaking_footer(self):
        for text in ("feat: 添加项目检查命令", "fix(install): 修复空目录安装失败", "docs(readme): 补充 Windows 命令",
                     "feat(config)!: 修改推送配置字段\n\nBREAKING CHANGE: 将 push 字段改为 auto_push"):
            manager.validate_message(text)

    def test_bad_messages(self):
        for text in ("update", "feat： 添加命令", "feat: add commands", "fix: 修复问题", "docs: 更新代码",
                     "feat: " + "中" * 80, "feat!: 修改配置字段", "fix: 修复路径错误\n未留空行"):
            with self.subTest(text=text), self.assertRaises(manager.ManagerError):
                manager.validate_message(text)

    def test_semver_ordering_and_build_metadata(self):
        values = ["1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta", "1.0.0-beta", "1.0.0-beta.2", "1.0.0-beta.11", "1.0.0-rc.1", "1.0.0"]
        versions = list(map(manager.Version.parse, values))
        self.assertEqual(sorted(reversed(versions)), versions)
        self.assertEqual(manager.Version.parse("1.0.0+abc"), manager.Version.parse("1.0.0+xyz"))

    def test_invalid_semver(self):
        for value in ("v1.0.0", "01.0.0", "1.0", "1.0.0-beta.01", "1.0.0-", "1.0.0+", "1٢.0.0"):
            with self.subTest(value=value), self.assertRaises(manager.ManagerError):
                manager.Version.parse(value)

    def test_bump_uses_highest_impact_and_zero_major_policy(self):
        v = manager.Version.parse("1.4.2")
        self.assertEqual(manager.infer_bump(["fix: 修复读取错误", "feat: 添加导出命令"], v), "minor")
        messages = ["docs!: 变更配置协议\n\nBREAKING CHANGE: 迁移旧配置"]
        self.assertEqual(manager.infer_bump(messages, v), "major")
        self.assertEqual(manager.infer_bump(messages, manager.Version.parse("0.4.2")), "minor")
        self.assertIsNone(manager.infer_bump(["docs: 补充使用说明"], v))
        self.assertEqual(str(v.bump("minor")), "1.5.0")
        self.assertEqual(str(v.bump("major")), "2.0.0")


class GitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="axiom-git-")
        self.root = Path(self.tmp.name).resolve()
        self.output = io.StringIO()
        self.stdout = contextlib.redirect_stdout(self.output)
        self.stderr = contextlib.redirect_stderr(self.output)
        self.stdout.__enter__()
        self.stderr.__enter__()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Axiom Test")
        self.git("config", "user.email", "axiom@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.git("config", "tag.gpgsign", "false")
        self.git("config", "core.autocrlf", "false")
        self.git("config", "core.quotePath", "false")
        self.write("README.md", "# Demo\n\n实际安装和使用说明。\n")
        self.write("VERSION", "0.1.0\n")
        self.write("CHANGELOG.md", "# 更新日志\n\n## [Unreleased]\n\n### 新增\n\n- 支持项目检查。\n")
        self.config()
        self.git("add", ".")
        self.git("commit", "-m", "feat: 添加项目初始功能")

    def tearDown(self):
        self.stderr.__exit__(None, None, None)
        self.stdout.__exit__(None, None, None)
        self.tmp.cleanup()

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")

    def config(self, **extra):
        value = dict(manager.DEFAULT_CONFIG, checks=[["{python}", "-c", "print('验证成功')"]])
        value.update(extra)
        self.write(manager.CONFIG_PATH, json.dumps(value, ensure_ascii=False))

    def git(self, *args, check=True):
        result = subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if check and result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        return result.stdout.strip()

    def cli(self, *args):
        return manager.main(["--project", str(self.root), *args])

    def save_all(self, message="chore: 调整项目测试配置"):
        self.git("add", ".")
        self.git("commit", "-m", message)

    def commit_change(self, name="feature.txt", message="feat: 添加导出功能"):
        self.write(name, "changed\n")
        return self.cli("commit", "-m", message, "--files", name, "--write")

    def test_check_and_message_cli(self):
        self.assertEqual(self.cli("check"), 0)
        self.assertEqual(self.cli("lint-message", "-m", "docs: 补充安装命令"), 0)
        self.assertEqual(self.cli("lint-message", "-m", "update"), 1)

    def test_preview_commit_does_not_stage_or_create_commit(self):
        self.write("feature.txt", "new\n")
        before = self.git("rev-parse", "HEAD")
        self.assertEqual(self.cli("commit", "-m", "feat: 添加功能文件", "--files", "feature.txt"), 0)
        self.assertEqual(self.git("rev-parse", "HEAD"), before)
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "")

    def test_only_selected_files_are_committed(self):
        self.write("unrelated.txt", "user work\n")
        self.assertEqual(self.commit_change("中文 空格.txt"), 0)
        self.assertEqual(self.git("show", "--pretty=", "--name-only", "--no-renames"), "中文 空格.txt")
        self.assertIn("unrelated.txt", self.git("status", "--short"))

    def test_repeated_commit_skips(self):
        self.assertEqual(self.commit_change(), 0)
        before = self.git("rev-parse", "HEAD")
        self.assertEqual(self.cli("commit", "-m", "feat: 添加导出功能", "--files", "feature.txt", "--write"), 0)
        self.assertEqual(self.git("rev-parse", "HEAD"), before)

    def test_existing_staged_changes_are_preserved(self):
        self.write("user.txt", "keep")
        self.git("add", "user.txt")
        before = manager.git_path(self.root, "index").read_bytes()
        self.assertEqual(self.commit_change(), 1)
        self.assertEqual(manager.git_path(self.root, "index").read_bytes(), before)
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "user.txt")

    def test_failed_checks_do_not_stage(self):
        self.config(checks=[["{python}", "-c", "raise SystemExit(7)"]])
        before = self.git("rev-parse", "HEAD")
        self.assertEqual(self.commit_change(), 1)
        self.assertEqual(self.git("rev-parse", "HEAD"), before)
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "")

    def test_no_checks_requires_explicit_reason(self):
        self.config(checks=[])
        self.assertEqual(self.cli("check"), 1)
        self.assertEqual(self.cli("check", "--no-checks-reason", "纯文档项目，已手动核对示例"), 0)

    def test_failed_git_commit_restores_index_and_files(self):
        self.write("feature.txt", "changed\n")
        saved = manager.git_path(self.root, "index").read_bytes()
        real = manager.git

        def failing(root, *args, **kwargs):
            if args[0] == "commit":
                raise manager.ManagerError("simulated commit failure")
            return real(root, *args, **kwargs)

        with patch.object(manager, "git", side_effect=failing):
            self.assertEqual(self.cli("commit", "-m", "feat: 添加导出功能", "--files", "feature.txt", "--write"), 1)
        self.assertEqual(manager.git_path(self.root, "index").read_bytes(), saved)
        self.assertEqual((self.root / "feature.txt").read_text(), "changed\n")

    def test_deleted_and_renamed_files(self):
        self.write("old.txt", "original")
        self.save_all()
        (self.root / "old.txt").rename(self.root / "new.txt")
        self.assertEqual(self.cli("commit", "-m", "refactor(files): 调整文件名称", "--files", "old.txt", "new.txt", "--write"), 0)
        (self.root / "new.txt").unlink()
        self.assertEqual(self.cli("commit", "-m", "chore(files): 删除过期文件", "--files", "new.txt", "--write"), 0)

    def test_path_escape_and_directory_rejected(self):
        self.write("feature.txt", "new")
        for name in ("../outside", ".git/config", ".GIT/config", ".axiom-manager", "."):
            self.assertEqual(self.cli("commit", "-m", "feat: 添加导出功能", "--files", name, "--write"), 1)

    def test_missing_identity_and_detached_head(self):
        self.git("config", "user.useConfigOnly", "true")
        self.git("config", "user.name", "")
        self.assertEqual(self.commit_change(), 1)
        self.git("config", "user.name", "Axiom Test")
        self.git("checkout", "--detach")
        self.assertEqual(self.cli("commit", "-m", "feat: 添加导出功能", "--files", "feature.txt", "--write"), 1)

    def test_git_operation_and_manager_locks(self):
        lock = manager.git_path(self.root, "MERGE_HEAD")
        lock.write_text("pending")
        self.assertEqual(self.commit_change(), 1)
        lock.unlink()
        lock = manager.git_path(self.root, "axiom-manager.lock")
        lock.write_text("busy")
        self.assertEqual(self.cli("commit", "-m", "feat: 添加导出功能", "--files", "feature.txt", "--write"), 1)

    def test_readme_broken_link_and_code_example_links(self):
        self.write("README.md", "# Demo\n\n[缺失](missing.md)\n")
        self.assertEqual(self.cli("check"), 1)
        self.write("README.md", "# Demo\n\n```md\n[示例](missing.md)\n```\n")
        self.assertEqual(self.cli("check"), 0)

    def test_malformed_config(self):
        for extra in ({"auto_push": "true"}, {"checks": ["pytest"]}, {"remote": "--bad"}, {"schema": 2}):
            self.config(**extra)
            self.assertEqual(self.cli("status"), 1)

    def test_initial_release_preview_and_write(self):
        before = self.git("rev-parse", "HEAD")
        self.assertEqual(self.cli("release"), 0)
        self.assertEqual(self.git("rev-parse", "HEAD"), before)
        self.assertEqual(self.git("tag"), "")
        self.assertEqual(self.cli("release", "--write"), 0)
        self.assertEqual(self.git("tag"), "v0.1.0")
        self.assertEqual(self.git("cat-file", "-t", "v0.1.0"), "tag")
        self.assertIn("## [0.1.0] - ", (self.root / "CHANGELOG.md").read_text(encoding="utf-8"))
        self.assertEqual(self.git("status", "--short"), "")

    def test_feature_release_bumps_minor_once(self):
        self.assertEqual(self.cli("release", "--write"), 0)
        self.assertEqual(self.commit_change(), 0)
        self.write("fix.txt", "fix")
        self.assertEqual(self.cli("commit", "-m", "fix: 修复导出错误", "--files", "fix.txt", "--write"), 0)
        self.assertEqual(self.cli("release", "--write"), 0)
        self.assertEqual((self.root / "VERSION").read_text().strip(), "0.2.0")
        self.assertIn("添加导出功能", (self.root / "CHANGELOG.md").read_text(encoding="utf-8"))

    def test_docs_only_not_automatically_released(self):
        self.assertEqual(self.cli("release", "--write"), 0)
        self.write("README.md", "# Demo\n\n增加文档说明。\n")
        self.assertEqual(self.cli("commit", "-m", "docs: 补充使用说明", "--files", "README.md", "--write"), 0)
        self.assertEqual(self.cli("release", "--write"), 1)
        self.assertEqual(self.git("tag"), "v0.1.0")

    def test_dirty_release_rejected(self):
        self.write("user.txt", "work")
        self.assertEqual(self.cli("release", "--write"), 1)
        self.assertEqual(self.git("tag"), "")

    def test_release_failed_checks_roll_back_version_and_changelog(self):
        self.config(checks=[["{python}", "-c", "raise SystemExit(1)"]])
        self.save_all()
        before = {name: (self.root / name).read_bytes() for name in ("VERSION", "CHANGELOG.md")}
        self.assertEqual(self.cli("release", "--version", "0.2.0", "--write"), 1)
        self.assertEqual(before, {name: (self.root / name).read_bytes() for name in before})
        self.assertEqual(self.git("status", "--short"), "")
        self.assertEqual(self.git("tag"), "")

    def test_tag_failure_can_be_resumed_without_duplicate_commit(self):
        real = manager.git

        def failing(root, *args, **kwargs):
            if args[:2] == ("tag", "-a"):
                raise manager.ManagerError("simulated tag failure")
            return real(root, *args, **kwargs)

        with patch.object(manager, "git", side_effect=failing):
            self.assertEqual(self.cli("release", "--write"), 1)
        before = self.git("rev-parse", "HEAD")
        self.assertEqual(self.cli("release", "--write"), 0)
        self.assertEqual(before, self.git("rev-parse", "HEAD"))
        self.assertEqual(self.git("tag"), "v0.1.0")

    def test_prerelease_and_promotion(self):
        self.assertEqual(self.cli("release", "--version", "0.2.0-beta.1", "--write"), 0)
        self.assertEqual(self.commit_change(), 0)
        self.assertEqual(self.cli("release", "--version", "0.2.0-beta.2", "--write"), 0)
        self.assertEqual(self.cli("release", "--version", "0.2.0", "--write"), 0)
        self.assertEqual((self.root / "VERSION").read_text().strip(), "0.2.0")
        final_notes = (self.root / "CHANGELOG.md").read_text(encoding="utf-8").split("## [0.2.0]", 1)[1].split("## [0.2.0-beta.2]", 1)[0]
        self.assertIn("支持项目检查", final_notes)
        self.assertIn("添加导出功能", final_notes)

    def test_literal_git_pathspec_does_not_select_similar_filename(self):
        self.write("file[1].txt", "selected")
        self.write("file1.txt", "user work")
        self.assertEqual(self.cli("commit", "-m", "feat: 添加指定数据文件", "--files", "file[1].txt", "--write"), 0)
        self.assertEqual(self.git("show", "--pretty=", "--name-only"), "file[1].txt")
        self.assertIn("file1.txt", self.git("status", "--short"))

    def test_initial_commit_without_head(self):
        self.git("update-ref", "-d", "HEAD")
        # 初始化仓库的暂存区仍需保持空，随后由工具明确选择文件。
        manager.git_path(self.root, "index").unlink()
        names = ["README.md", "VERSION", "CHANGELOG.md", manager.CONFIG_PATH]
        self.assertEqual(self.cli("commit", "-m", "feat: 创建项目初始功能", "--files", *names, "--write"), 0)
        self.assertEqual(self.git("rev-list", "--count", "HEAD"), "1")

    def test_npm_lock_version_mismatch_blocks_commit(self):
        (self.root / "VERSION").unlink()
        self.write("package.json", '{"version":"1.0.0"}')
        self.write("package-lock.json", '{"version":"9.0.0"}')
        self.assertEqual(self.cli("check"), 1)

    def test_releasing_without_version_source_creates_version(self):
        (self.root / "VERSION").unlink()
        self.save_all()
        self.assertEqual(self.cli("release", "--write"), 0)
        self.assertEqual((self.root / "VERSION").read_text().strip(), "0.1.0")

    def test_readme_absence_is_reported(self):
        (self.root / "README.md").unlink()
        self.assertEqual(self.cli("check"), 1)

    def test_checks_cannot_silently_change_release_version(self):
        self.config(checks=[["{python}", "-c", "from pathlib import Path; Path('VERSION').write_text('9.0.0\\n')"]])
        self.save_all()
        before = self.git("rev-parse", "HEAD")
        self.assertEqual(self.cli("release", "--version", "0.2.0", "--write"), 1)
        self.assertEqual(self.git("rev-parse", "HEAD"), before)
        self.assertEqual(self.git("tag"), "")
        self.assertEqual((self.root / "VERSION").read_text().strip(), "9.0.0")
        self.assertIn("## [Unreleased]", (self.root / "CHANGELOG.md").read_text(encoding="utf-8"))

    def test_configured_authority_ignores_other_product_version(self):
        self.write("package.json", '{"version":"9.0.0"}')
        self.config(version_file="VERSION")
        self.assertEqual(self.cli("check"), 0)

    def test_npm_lock_updates_preserve_dependency_versions(self):
        (self.root / "VERSION").unlink()
        self.write("package.json", '{"name":"demo","version":"1.2.3"}\n')
        self.write("package-lock.json", json.dumps({"name": "demo", "version": "1.2.3", "packages": {"": {"version": "1.2.3"}, "node_modules/example": {"version": "9.8.7"}}}))
        self.save_all("feat: 添加 npm 项目配置")
        self.assertEqual(self.cli("release", "--version", "1.3.0", "--write"), 0)
        data = json.loads((self.root / "package-lock.json").read_text())
        self.assertEqual(data["version"], "1.3.0")
        self.assertEqual(data["packages"][""]["version"], "1.3.0")
        self.assertEqual(data["packages"]["node_modules/example"]["version"], "9.8.7")

    def test_version_conflict_and_dynamic_toml_are_reported(self):
        self.write("package.json", '{"version":"2.0.0"}')
        self.assertEqual(self.cli("check"), 1)
        (self.root / "package.json").unlink()
        self.write("pyproject.toml", '[project]\nname = "demo"\ndynamic = ["version"]\n')
        self.assertEqual(self.cli("check"), 1)

    def test_toml_preserves_comments_and_other_version_fields(self):
        (self.root / "VERSION").unlink()
        original = '[project]\nname = "demo"\nversion = "0.1.0" # keep\n\n[tool.other]\nversion = "9.0.0"\n'
        self.write("pyproject.toml", original)
        self.save_all()
        self.assertEqual(self.cli("release", "--version", "0.2.0", "--write"), 0)
        text = (self.root / "pyproject.toml").read_text()
        self.assertIn('version = "0.2.0" # keep', text)
        self.assertIn('version = "9.0.0"', text)

    def test_standalone_installed_script_from_another_directory(self):
        installer.install(self.root, write=True)
        script = self.root / ".axiom-manager/manage.py"
        result = subprocess.run([sys.executable, str(script), "--project", str(self.root), "check"], cwd=self.root.parent,
                                capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_installed_workflow_commit_release_and_uninstall(self):
        installer.install(self.root, write=True)
        script = self.root / ".axiom-manager/manage.py"

        def installed(*args):
            result = subprocess.run([sys.executable, str(script), "--project", str(self.root), *args], cwd=self.root.parent,
                                    capture_output=True, text=True, encoding="utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        installed("commit", "-m", "chore(manager): 安装项目提交规则", "--files", "AGENTS.md", ".axiom-manager/manage.py",
                  ".axiom-manager/install-state.json", "--write")
        installed("release", "--write")
        self.assertEqual(self.git("tag"), "v0.1.0")
        self.assertEqual(self.git("status", "--short"), "")
        installer.uninstall(self.root, write=True)
        self.assertFalse(script.exists())
        self.assertFalse((self.root / "AGENTS.md").exists())
        self.assertTrue((self.root / manager.CONFIG_PATH).exists())

    def test_push_to_local_bare_remote_and_retry(self):
        with tempfile.TemporaryDirectory(prefix="axiom-remote-") as temp:
            remote = Path(temp) / "remote.git"
            subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
            self.git("remote", "add", "origin", str(remote))
            before = self.git("rev-parse", "HEAD")
            self.assertEqual(self.cli("push"), 0)
            probe = subprocess.run(["git", "--git-dir", str(remote), "show-ref"], capture_output=True)
            self.assertNotEqual(probe.returncode, 0)
            self.assertEqual(self.cli("release", "--write", "--push"), 0)
            self.assertNotEqual(self.git("rev-parse", "HEAD"), before)
            self.assertEqual(self.cli("push", "--tag", "v0.1.0", "--write"), 0)
            refs = subprocess.run(["git", "--git-dir", str(remote), "show-ref"], check=True, capture_output=True, text=True).stdout
            self.assertIn("refs/heads/main", refs)
            self.assertIn("refs/tags/v0.1.0", refs)

    def test_failed_push_keeps_commit_and_retry_does_not_commit_again(self):
        self.write("feature.txt", "changed")
        self.assertEqual(self.cli("commit", "-m", "feat: 添加导出功能", "--files", "feature.txt", "--write", "--push"), 1)
        before = self.git("rev-parse", "HEAD")
        self.assertEqual(self.git("log", "-1", "--format=%s"), "feat: 添加导出功能")
        self.assertEqual(self.cli("push", "--write"), 1)
        self.assertEqual(self.git("rev-parse", "HEAD"), before)


if __name__ == "__main__":
    unittest.main()
