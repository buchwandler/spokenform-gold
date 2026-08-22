import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from spokenform_gold import cli
from spokenform_gold.config import (
    ConfigError,
    PathsConfig,
    ProjectConfig,
    RuntimePaths,
    load_config,
    resolve_runtime_paths,
)


class ConfigTests(unittest.TestCase):
    def _write_config(self, root: Path, body: str) -> Path:
        path = root / "config.toml"
        path.write_text(body, encoding="utf-8")
        return path

    def test_valid_config_resolves_relative_paths_from_config_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "project"
            root.mkdir()
            config_path = self._write_config(
                root,
                '[paths]\nsource_cache = "../cache"\nwork = "../work"\n',
            )
            config = load_config(config_path, explicit=True)

            self.assertEqual(config.path, config_path.resolve())
            self.assertEqual(config.paths.source_cache, (root.parent / "cache").resolve())
            self.assertEqual(config.paths.work, (root.parent / "work").resolve())

    def test_absolute_and_tilde_paths_are_expanded(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            absolute = root / "absolute-cache"
            config_path = self._write_config(
                root,
                f'[paths]\nsource_cache = "{absolute}"\nwork = "~/spokenform-work"\n',
            )
            config = load_config(config_path, explicit=True)

            self.assertEqual(config.paths.source_cache, absolute.resolve())
            self.assertEqual(config.paths.work, (Path.home() / "spokenform-work").resolve())

    def test_loaded_relative_paths_do_not_depend_on_later_working_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as other:
            root = Path(tmpdir) / "project"
            root.mkdir()
            config_path = self._write_config(root, '[paths]\nwork = "../work"\n')
            config = load_config(config_path, explicit=True)
            original = Path.cwd()
            try:
                os.chdir(other)
                self.assertEqual(config.paths.work, (root.parent / "work").resolve())
            finally:
                os.chdir(original)

    def test_missing_default_config_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = load_config(Path(tmpdir) / "missing.toml", explicit=False)
            self.assertEqual(config, ProjectConfig(path=None, paths=PathsConfig(None, None)))

    def test_explicit_missing_config_fails_clearly(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "missing.toml"
            with self.assertRaisesRegex(ConfigError, r"config file not found:.*missing.toml"):
                load_config(path, explicit=True)

    def test_invalid_toml_fails_clearly(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_config(Path(tmpdir), "[paths\nwork = 'broken'\n")
            with self.assertRaisesRegex(ConfigError, "invalid TOML"):
                load_config(path, explicit=True)

    def test_unknown_path_key_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_config(
                Path(tmpdir), '[paths]\nsource_cashe = "../cache"\n'
            )
            with self.assertRaisesRegex(ConfigError, "unknown key.*source_cashe"):
                load_config(path, explicit=True)

    def test_precedence_config_only(self):
        config = ProjectConfig(
            path=Path("/project/config.toml"),
            paths=PathsConfig(Path("/config-cache"), Path("/config-work")),
        )
        result = resolve_runtime_paths(
            config=config,
            source_cache=None,
            work_root=None,
            environ={},
        )
        self.assertEqual(result, RuntimePaths(Path("/config-cache"), Path("/config-work")))

    def test_environment_overrides_config_and_can_be_mixed(self):
        config = ProjectConfig(
            path=Path("/project/config.toml"),
            paths=PathsConfig(Path("/config-cache"), Path("/config-work")),
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            old = Path.cwd()
            try:
                os.chdir(tmpdir)
                result = resolve_runtime_paths(
                    config=config,
                    source_cache=None,
                    work_root=None,
                    environ={"SPOKENFORM_GOLD_WORK": "env-work"},
                )
            finally:
                os.chdir(old)
        self.assertEqual(result.source_cache, Path("/config-cache"))
        self.assertEqual(result.work_root, (Path(tmpdir) / "env-work").resolve())

    def test_cli_overrides_environment_and_config(self):
        config = ProjectConfig(
            path=Path("/project/config.toml"),
            paths=PathsConfig(Path("/config-cache"), Path("/config-work")),
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            old = Path.cwd()
            try:
                os.chdir(tmpdir)
                result = resolve_runtime_paths(
                    config=config,
                    source_cache=Path("cli-cache"),
                    work_root=Path("cli-work"),
                    environ={
                        "SPOKENFORM_GOLD_SOURCE_CACHE": "env-cache",
                        "SPOKENFORM_GOLD_WORK": "env-work",
                    },
                )
            finally:
                os.chdir(old)
        self.assertEqual(result.source_cache, (Path(tmpdir) / "cli-cache").resolve())
        self.assertEqual(result.work_root, (Path(tmpdir) / "cli-work").resolve())

    def test_cli_integration_preserves_explicit_path_form(self):
        summary = {"records": 0, "exclusions": 0, "work_root": "/work"}
        with tempfile.TemporaryDirectory() as tmpdir, mock.patch.object(
            cli, "run_upstream_ingestion", return_value=summary
        ) as ingest, mock.patch.object(
            cli, "default_config_path", return_value=Path(tmpdir) / "absent.toml"
        ), mock.patch.dict(os.environ, {}, clear=True):
            result = cli.main(
                [
                    "ingest-upstreams",
                    "--source-cache",
                    str(Path(tmpdir) / "cache"),
                    "--work-root",
                    str(Path(tmpdir) / "work"),
                    "--sources",
                    "async_tn",
                ]
            )

        self.assertEqual(result, 0)
        self.assertEqual(ingest.call_args.args[:2], (Path(tmpdir) / "cache", Path(tmpdir) / "work"))

    def test_cli_integration_uses_config_without_path_flags(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = self._write_config(
                root,
                '[paths]\nsource_cache = "cache"\nwork = "work"\n',
            )
            summary = {"records": 0, "exclusions": 0, "work_root": str(root / "work")}
            with mock.patch.object(
                cli, "run_upstream_ingestion", return_value=summary
            ) as ingest, mock.patch.dict(os.environ, {}, clear=True):
                result = cli.main(
                    ["--config", str(config_path), "ingest-upstreams", "--sources", "async_tn"]
                )

            self.assertEqual(result, 0)
            self.assertEqual(
                ingest.call_args.args[:2], ((root / "cache").resolve(), (root / "work").resolve())
            )

    def test_cli_missing_paths_is_actionable(self):
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir, mock.patch.object(
            cli, "default_config_path", return_value=Path(tmpdir) / "absent.toml"
        ), mock.patch.dict(os.environ, {}, clear=True), contextlib.redirect_stderr(stderr):
            result = cli.main(["ingest-upstreams", "--sources", "async_tn"])

        self.assertEqual(result, 2)
        self.assertIn("source cache is not configured", stderr.getvalue())
        self.assertIn("--source-cache PATH", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_cli_missing_work_root_is_actionable(self):
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = self._write_config(
                Path(tmpdir), '[paths]\nsource_cache = "cache"\n'
            )
            with mock.patch.dict(os.environ, {}, clear=True), contextlib.redirect_stderr(stderr):
                result = cli.main(
                    ["--config", str(config_path), "ingest-upstreams", "--sources", "async_tn"]
                )

        self.assertEqual(result, 2)
        self.assertIn("work root is not configured", stderr.getvalue())
        self.assertIn("--work-root PATH", stderr.getvalue())

    def test_cli_explicit_missing_config_is_actionable(self):
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir, contextlib.redirect_stderr(stderr):
            result = cli.main(
                ["--config", str(Path(tmpdir) / "missing.toml"), "ingest-upstreams"]
            )

        self.assertEqual(result, 2)
        self.assertIn("config file not found", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
