"""Project-local runtime path configuration."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.10
    import tomli as tomllib


_CONFIG_FILENAME = "config.toml"
_PATH_KEYS = {"source_cache", "work"}


class ConfigError(ValueError):
    """Raised for invalid or incomplete runtime configuration."""


@dataclass(frozen=True)
class PathsConfig:
    source_cache: Path | None
    work: Path | None


@dataclass(frozen=True)
class ProjectConfig:
    path: Path | None
    paths: PathsConfig


@dataclass(frozen=True)
class RuntimePaths:
    source_cache: Path | None
    work_root: Path | None


def default_config_path() -> Path:
    """Return the project-local config path for the current invocation."""

    return Path.cwd() / _CONFIG_FILENAME


def _normalise_path(value: str | Path, *, base: Path) -> Path:
    if isinstance(value, str) and not value.strip():
        raise ConfigError("configured path must not be empty")
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    return candidate.resolve(strict=False)


def _config_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def load_config(path: Path | None, *, explicit: bool) -> ProjectConfig:
    """Load a project config, allowing an absent non-explicit default."""

    if path is None:
        return ProjectConfig(path=None, paths=PathsConfig(None, None))

    config_path = _config_path(path)
    if not config_path.exists():
        if explicit:
            raise ConfigError(f"config file not found: {config_path}")
        return ProjectConfig(path=None, paths=PathsConfig(None, None))
    if not config_path.is_file():
        raise ConfigError(f"config path is not a file: {config_path}")

    try:
        with config_path.open("rb") as handle:
            payload = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in config file {config_path}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"could not read config file {config_path}: {exc}") from exc

    raw_paths = payload.get("paths", {})
    if not isinstance(raw_paths, dict):
        raise ConfigError(f"[paths] must be a table in config file {config_path}")
    unknown = sorted(set(raw_paths) - _PATH_KEYS)
    if unknown:
        names = ", ".join(unknown)
        raise ConfigError(f"unknown key(s) under [paths] in {config_path}: {names}")

    values: dict[str, Path | None] = {}
    for key in _PATH_KEYS:
        value = raw_paths.get(key)
        if value is None:
            values[key] = None
            continue
        if not isinstance(value, str):
            raise ConfigError(f"[paths].{key} must be a string in {config_path}")
        values[key] = _normalise_path(value, base=config_path.parent)

    return ProjectConfig(
        path=config_path,
        paths=PathsConfig(values["source_cache"], values["work"]),
    )


def _override_path(value: str | Path | None) -> Path | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return _normalise_path(value, base=Path.cwd())


def _select_path(
    cli_value: Path | None,
    env_name: str,
    config_value: Path | None,
    environ: Mapping[str, str],
) -> Path | None:
    if cli_value is not None:
        return _override_path(cli_value)
    env_value = environ.get(env_name)
    if env_value:
        return _override_path(env_value)
    return config_value


def resolve_runtime_paths(
    *,
    config: ProjectConfig,
    source_cache: Path | None,
    work_root: Path | None,
    environ: Mapping[str, str] | None = None,
) -> RuntimePaths:
    """Resolve CLI, environment, and TOML values in documented precedence."""

    environment = os.environ if environ is None else environ
    return RuntimePaths(
        source_cache=_select_path(
            source_cache,
            "SPOKENFORM_GOLD_SOURCE_CACHE",
            config.paths.source_cache,
            environment,
        ),
        work_root=_select_path(
            work_root,
            "SPOKENFORM_GOLD_WORK",
            config.paths.work,
            environment,
        ),
    )


def require_runtime_paths(paths: RuntimePaths) -> RuntimePaths:
    """Raise an actionable error when ingestion paths are unresolved."""

    if paths.source_cache is None:
        raise ConfigError(
            "source cache is not configured\n\n"
            "Set one of:\n"
            "  --source-cache PATH\n"
            "  SPOKENFORM_GOLD_SOURCE_CACHE\n"
            "  [paths].source_cache in config.toml"
        )
    if paths.work_root is None:
        raise ConfigError(
            "work root is not configured\n\n"
            "Set one of:\n"
            "  --work-root PATH\n"
            "  SPOKENFORM_GOLD_WORK\n"
            "  [paths].work in config.toml"
        )
    return paths
