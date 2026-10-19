# ringbridge

**Turn incoming messages into a real phone call, for free, with no admin rights.**

When you're on shift you can't stare at Teams all day, and a chat notification is easy to miss.
ringbridge watches for new messages and **rings your phone** until you react: a real incoming
call in the Linphone app, or a loud repeating alert.

- **No admin access needed.** It reads the desktop notifications your apps already show.
  No Teams/Slack admin, no Azure app registration, no API keys.
- **Free.** The default channel is a Linphone-to-Linphone SIP call (free accounts, no per-minute cost).
- **Keeps ringing until you react.** Answer or decline the call (or tap a button), and it stops.
  Optionally, using your computer counts as "I'm on it" too.
- **Pluggable.** Sources (Teams, Slack, webhooks, ...) and channels (SIP call, ntfy, Pushover,
  Telegram via CallMeBot) are small modules, with fallback between channels.
- **Private.** Only "New Teams message from <sender>" leaves your machine, never the message text.

```
 Teams / Slack popup ─┐                             ┌─► SIP call (Linphone app)  ─┐
                      ├─► source ─► dispatcher ─────┤                             ├─► your phone rings
 HTTP webhook ────────┘   (match)   shift hours     └─► fallback: ntfy / Pushover ─┘
                                    cooldown
                                    ack: answer / decline
```

## Requirements

- Linux desktop with a freedesktop notification server (tested on Ubuntu 24.04 / GNOME)
- Python 3.11+ with `python3-dbus` and `python3-gi` (for desktop notification sources)
- `baresip` (for the SIP call channel)

```bash
sudo apt install python3-dbus python3-gi baresip
```

## Quick start

```bash
git clone https://github.com/<you>/ringbridge.git
cd ringbridge
./install.sh                        # first run creates ~/.config/ringbridge/config.toml
$EDITOR ~/.config/ringbridge/config.toml
python3 -m ringbridge check         # validate config and dependencies
python3 -m ringbridge test          # ring your phone once
./install.sh                        # second run installs and starts the systemd user service
```

Your real config lives in `~/.config/ringbridge/config.toml` (mode 600), outside the repo.
Only `config.example.toml` is tracked by git.

### Setting up the SIP call (Linphone, free)

You need **two** free accounts: the computer calls *from* one and your phone receives on the other
(an account can't call itself).

1. Create two accounts at <https://subscribe.linphone.org> using the **email** sign-up
   (phone-number sign-up is limited to some countries).
2. Install **Linphone** on your phone (App Store / Play Store), choose *Use a Linphone account*,
   log in with the **phone** account, and allow notifications and microphone.
3. In `config.toml`, under `[channels.sip]`: `username`/`password` = the **computer** account,
   `call_to` = the **phone** account.
4. `python3 -m ringbridge test`. Let the first call ring out (it calls again), then answer or
   decline the next one: ringbridge logs `acknowledged` and stops.

Linphone's server wakes the phone with a push notification ("110 Push sent"), so the app doesn't
need to be open. The first ring can take a few seconds.

## Usage

| Command | What it does |
|---|---|
| `python3 -m ringbridge run` | Listen and alert (what the service runs) |
| `python3 -m ringbridge run --debug` | Also log every desktop notification and which source matched it |
| `python3 -m ringbridge test [--channel sip]` | Send one test alert (laptop activity is ignored while testing) |
| `python3 -m ringbridge check` | Validate config, dependencies and file permissions |

`pip install .` also gives you a `ringbridge` command instead of `python3 -m ringbridge`.

### Background service

`install.sh` installs ringbridge as a systemd **user** service: it runs without a terminal,
starts automatically when you log in, and restarts itself if it crashes.

| Command | What it does |
|---|---|
| `systemctl --user status ringbridge` | Is it running? Look for `active (running)` |
| `journalctl --user -u ringbridge -f` | Follow the logs live |
| `systemctl --user restart ringbridge` | Apply config changes |
| `systemctl --user stop ringbridge` | Stop until next login |
| `systemctl --user start ringbridge` | Start again |
| `systemctl --user disable --now ringbridge` | Stop and don't start at login |
| `systemctl --user enable --now ringbridge` | Start now and at every login |

To run it in a terminal instead (`python3 -m ringbridge run`, Ctrl+C to stop), stop the service
first: otherwise both see the same message and call you at the same time.

### Leaving it running overnight

- Keep the computer **plugged in and the lid open**: suspend stops everything (Ubuntu suspends on
  battery after 30 minutes by default). A locked screen is fine.
- Keep the messaging app open (minimized is fine) and your status off *Do not disturb*.
- On the phone: ringer on, and allow **Linphone** in your Sleep / Do Not Disturb Focus.

## How an alert works

1. A **source** produces an event, e.g. a Teams notification popup.
2. The **dispatcher** drops it if you're outside your shift `windows`, inside `cooldown_seconds`,
   or already being alerted.
3. Each **channel** in `[alert] channels` is tried in order:
   - **acknowledged** (you answered or declined, tapped, or used the computer when
     `ack_on_laptop_activity = true`): done.
   - **unacknowledged** (rang out every time): done, or move on to the next channel if
     `escalate_unacknowledged = true`.
   - **failed** (couldn't deliver, e.g. server unreachable or bad password): the next channel is tried.
4. If every channel fails, ringbridge logs `ALL CHANNELS FAILED` and shows a critical popup on the computer.

## Sources

| Type | Use it for | Notes |
|---|---|---|
| `desktop` | Teams, Slack, any app that shows desktop notifications | `preset = "teams"` / `"slack"`, or your own `match` regexes; `exclude` to ignore some |
| `webhook` | CI, monitoring, scripts, Slack/other services via a tunnel | `POST /alert` with `Authorization: Bearer <token>`, JSON `{"sender": "...", "text": "..."}`; `GET /health` |

```bash
curl -X POST http://127.0.0.1:8787/alert -H "Authorization: Bearer $TOKEN" \
     -d '{"sender": "CI", "text": "deploy failed"}'
```

## Channels

| Channel | Cost | Feels like | iPhone silent mode |
|---|---|---|---|
| `sip`: Linphone call | Free | Real incoming-call screen with ringtone | Vibrates (like any call) |
| `pushover`: emergency priority | $5 one-time | Long alarm, repeats until you acknowledge | Rings (Critical Alerts) |
| `ntfy`: push, re-sent every 30s | Free | Notification sound (short on iPhone) | Silent |
| `callmebot`: Telegram call | Free | Telegram voice call | Vibrates |

CallMeBot needs a one-time authorization (<https://api2.callmebot.com/txt/login.php>), and its
calling account must be able to reach you. It does not work if Telegram has limited your account.

## Desktop source requirements

- The app must actually show a notification: notifications enabled in the app (and, for the Teams
  PWA, Chrome's site permission for teams.microsoft.com).
- Teams doesn't notify while its window is focused or while your status is *Do not disturb*.
- GNOME's own Do Not Disturb is fine: apps still send notifications, they just aren't shown.
- The computer must be on, logged in and online.

## Troubleshooting

| Symptom | Check |
|---|---|
| Nothing happens on a message | `python3 -m ringbridge run --debug`: is the notification seen, and which source matched it? |
| `session closed: 403` / `404` | Wrong computer password / wrong `call_to` account |
| `110 Push sent` but the phone never rings | Open Linphone on the phone once, check notifications are allowed, and add Linphone to your Focus modes |

## Extending

Add a source or channel by subclassing and registering it, then importing the module in the
package `__init__.py`.

```python
# ringbridge/channels/mychannel.py
from ringbridge.channels.base import Channel, Outcome, register

@register
class MyChannel(Channel):
    name = "mychannel"            # [channels.mychannel] in config
    required = ("api_key",)       # checked by `ringbridge check`

    def alert(self, text, ctx):
        ...                        # deliver; use ctx.wait(seconds) between retries
        return Outcome.ACKNOWLEDGED  # or UNACKNOWLEDGED / FAILED
```

```python
# ringbridge/sources/mysource.py
from ringbridge.events import Event
from ringbridge.sources.base import Source, register

@register
class MySource(Source):
    type = "mysource"             # [[sources]] type = "mysource"

    def start(self):               # must not block: start a thread
        ...
        self.submit(Event(source=self.label, sender="who", text="what"))
```

Run the tests with:

```bash
python3 -m unittest discover -s tests -t .
```

## Project layout

```
ringbridge/
  cli.py            run / test / check
  dispatcher.py     schedule, cooldown, channel chain
  schedule.py       shift windows
  activity.py       laptop-activity acknowledgement (GNOME idle monitor)
  sources/          desktop (D-Bus), webhook
  channels/         sip (baresip), ntfy, pushover, callmebot
systemd/            user service template (installed by install.sh)
config.example.toml
```

## License

[MIT](LICENSE)
