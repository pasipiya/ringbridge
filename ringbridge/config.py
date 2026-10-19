"""Locate, load and validate the TOML config."""

import os
import stat
import tomllib
from pathlib import Path

from ringbridge.channels import CHANNELS
from ringbridge.schedule import parse_window
from ringbridge.sources import SOURCES


class ConfigError(Exception):
    pass


def default_paths():
    xdg = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return [xdg / "ringbridge" / "config.toml", Path("config.toml")]


def find_config(explicit=None):
    if explicit:
        return Path(explicit)
    if env := os.environ.get("RINGBRIDGE_CONFIG"):
        return Path(env)
    for path in default_paths():
        if path.exists():
            return path
    raise ConfigError("No config found. Copy config.example.toml to ~/.config/ringbridge/config.toml "
                      "(or pass --config).")


def load(path):
    try:
        with open(path, "rb") as f:
            cfg = tomllib.load(f)
    except FileNotFoundError:
        raise ConfigError(f"Config file not found: {path}")
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: {e}")
    cfg.setdefault("schedule", {})
    cfg.setdefault("alert", {})
    cfg.setdefault("channels", {})
    cfg.setdefault("sources", [])
    validate(cfg)
    return cfg


def validate(cfg):
    for w in cfg["schedule"].get("windows", []):
        try:
            parse_window(w)
        except ValueError:
            raise ConfigError(f"[schedule] bad window '{w}', expected 'HH:MM-HH:MM'")

    chain = cfg["alert"].get("channels", [])
    if not chain:
        raise ConfigError("[alert] channels is empty: list at least one channel, e.g. [\"sip\", \"ntfy\"]")
    for name in chain:
        if name not in CHANNELS:
            raise ConfigError(f"[alert] unknown channel '{name}' (known: {', '.join(CHANNELS)})")
        if name not in cfg["channels"]:
            raise ConfigError(f"[alert] channel '{name}' is listed but [channels.{name}] is missing")

    names = set()
    for src in cfg["sources"]:
        if src.get("type") not in SOURCES:
            raise ConfigError(f"[[sources]] unknown type '{src.get('type')}' (known: {', '.join(SOURCES)})")
        name = src.get("name") or src["type"]
        if name in names:
            raise ConfigError(f"[[sources]] duplicate name '{name}'")
        names.add(name)
    if not any(s.get("enabled", True) for s in cfg["sources"]):
        raise ConfigError("No enabled [[sources]]: nothing would ever trigger an alert")


def permission_warning(path):
    """Config holds passwords/tokens: warn if other users can read it."""
    try:
        mode = Path(path).stat().st_mode
    except OSError:
        return None
    if mode & (stat.S_IRGRP | stat.S_IROTH):
        return f"{path} is readable by other users; run: chmod 600 {path}"
    return None
