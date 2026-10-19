"""Command line: `ringbridge run | test | check`."""

import argparse
import logging
import shutil
import signal
import sys
import threading

from ringbridge import __version__
from ringbridge import config as config_mod
from ringbridge.channels import CHANNELS, Outcome
from ringbridge.dispatcher import Dispatcher
from ringbridge.schedule import in_shift
from ringbridge.sources import SOURCES
from ringbridge.sources.desktop import MONITOR

log = logging.getLogger("ringbridge")


def build_sources(cfg, submit):
    sources = []
    for src in cfg["sources"]:
        if src.get("enabled", True):
            sources.append(SOURCES[src["type"]](src.get("name") or src["type"], src, submit))
    return sources


def problems_for(cfg, sources):
    problems = []
    for name in cfg["alert"]["channels"]:
        problems += CHANNELS[name](cfg["channels"][name]).check()
    for source in sources:
        problems += source.check()
    if cfg["alert"].get("ack_on_laptop_activity", False) and not shutil.which("gdbus"):
        problems.append("'gdbus' not found: laptop-activity acknowledgement disabled")
    return problems


def cmd_check(cfg, path):
    sources = build_sources(cfg, lambda e: None)
    print(f"Config:   {path}")
    print(f"Sources:  {', '.join(f'{s.name} ({s.type})' for s in sources)}")
    print(f"Channels: {' -> '.join(cfg['alert']['channels'])}")
    print(f"Shift:    {'active now' if in_shift(cfg['schedule']) else 'not active now'} "
          f"(windows: {cfg['schedule'].get('windows') or 'always'})")
    problems = problems_for(cfg, sources)
    if warning := config_mod.permission_warning(path):
        problems.append(warning)
    for p in problems:
        print(f"  ✗ {p}")
    print("OK" if not problems else f"{len(problems)} problem(s) found")
    return 1 if problems else 0


def cmd_test(cfg, channel=None):
    if channel:
        if channel not in cfg["channels"]:
            print(f"No [channels.{channel}] in config", file=sys.stderr)
            return 2
        cfg["alert"]["channels"] = [channel]
    # You are at the keyboard while testing, so laptop activity must not acknowledge the alert
    dispatcher = Dispatcher(cfg, ack_on_activity=False)
    outcome = dispatcher.alert("Test alert from ringbridge")
    return 0 if outcome is not Outcome.FAILED else 1


def cmd_run(cfg, debug):
    dispatcher = Dispatcher(cfg)
    sources = build_sources(cfg, dispatcher.submit)
    for p in problems_for(cfg, sources):
        log.warning("%s", p)
    MONITOR.debug = debug

    loop = None
    if any(s.needs_glib for s in sources):
        from gi.repository import GLib
        loop = GLib.MainLoop()

    def shutdown(*_):
        log.info("Shutting down")
        dispatcher.stop.set()
        if loop:
            loop.quit()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    for source in sources:
        source.start()
    log.info("ringbridge %s running: %s -> %s (shift active now: %s)", __version__,
             ", ".join(s.name for s in sources), " -> ".join(cfg["alert"]["channels"]),
             in_shift(cfg["schedule"]))
    if loop:
        loop.run()
    else:
        while not dispatcher.stop.wait(1):
            pass
    for source in sources:
        source.stop()
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="ringbridge",
                                     description="Turn incoming messages into a phone call or loud alert.")
    parser.add_argument("-c", "--config", help="config file (default: ~/.config/ringbridge/config.toml)")
    parser.add_argument("-V", "--version", action="version", version=f"ringbridge {__version__}")
    sub = parser.add_subparsers(dest="command")
    run = sub.add_parser("run", help="listen for messages and alert (default)")
    run.add_argument("--debug", action="store_true", help="log every desktop notification")
    test = sub.add_parser("test", help="send one test alert through the channel chain")
    test.add_argument("--channel", help="test only this channel")
    sub.add_parser("check", help="validate config and dependencies")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        path = config_mod.find_config(args.config)
        cfg = config_mod.load(path)
    except config_mod.ConfigError as e:
        print(f"Config error: {e}", file=sys.stderr)
        sys.exit(2)

    if args.command == "check":
        sys.exit(cmd_check(cfg, path))
    if args.command == "test":
        sys.exit(cmd_test(cfg, args.channel))
    sys.exit(cmd_run(cfg, getattr(args, "debug", False)))
