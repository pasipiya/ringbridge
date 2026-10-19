"""Real incoming call on a SIP softphone (e.g. Linphone app), placed with baresip."""

import os
import queue
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time

from ringbridge.channels.base import Channel, Outcome, register

BARESIP_CONFIG = """\
module_path\t/usr/lib/baresip/modules
sip_listen\t0.0.0.0:0
sip_cafile\t/etc/ssl/certs/ca-certificates.crt
audio_player\tpulse,
audio_source\tausine,440
audio_alert\tpulse,
module\tg711.so
module\topus.so
module\tausine.so
module\tpulse.so
module\tstun.so
module\tsrtp.so
module_app\taccount.so
module_app\tmenu.so
"""

DECLINE_CODES = {486, 600, 603}         # busy / declined on the phone: a deliberate reaction
RETRY_CODES = {408, 480, 487, 500, 503}  # phone not reachable right now: call again


def classify_close(line):
    """Map a baresip 'session closed: <code> <reason>' line to declined / retry / failed."""
    m = re.search(r"session closed:\s*(\d{3})", line)
    if not m:
        return "retry"
    code = int(m.group(1))
    if code in DECLINE_CODES:
        return "declined"
    if code in RETRY_CODES:
        return "retry"
    return "failed"  # e.g. 403 bad password, 404 unknown account: calling again won't help


@register
class SipChannel(Channel):
    name = "sip"
    required = ("username", "password", "call_to")

    def check(self):
        problems = super().check()
        for tool in ("baresip", "stdbuf"):
            if not shutil.which(tool):
                problems.append(f"[channels.sip] '{tool}' not found (sudo apt install baresip)")
        return problems

    def alert(self, text, ctx):
        max_calls = self.cfg.get("max_calls", 10)
        for n in range(1, max_calls + 1):
            self.log.info("Call %d/%d to %s: %s", n, max_calls, self.cfg["call_to"], text)
            result, detail = self.call_once(ctx)
            if result in ("answered", "declined", "laptop activity"):
                self.log.info("Acknowledged (%s)", result)
                return Outcome.ACKNOWLEDGED
            if result == "failed":
                self.log.error("Call failed: %s", detail)
                if "488" in detail:
                    self.log.error("488 = the phone rejected the audio settings; "
                                   "try media_encryption = \"srtp-mand\" or \"none\" in [channels.sip]")
                return Outcome.FAILED
            self.log.info("No answer (%s)", detail)
            if n < max_calls and ctx.wait(self.cfg.get("pause_seconds", 15)):
                self.log.info("Acknowledged (laptop activity)")
                return Outcome.ACKNOWLEDGED
        return Outcome.UNACKNOWLEDGED

    def call_once(self, ctx):
        """Place one call. Returns (result, detail), result in answered/declined/laptop activity/retry/failed."""
        domain = self.cfg.get("domain", "sip.linphone.org")
        transport = self.cfg.get("transport", "tls")
        ring = self.cfg.get("ring_seconds", 30)
        # Linphone for iOS rejects unencrypted audio with "488 Not acceptable here"
        enc = self.cfg.get("media_encryption", "srtp-mand")
        mediaenc = f";mediaenc={enc}" if enc and enc != "none" else ""
        workdir = tempfile.mkdtemp(prefix="ringbridge_sip_")
        try:
            with open(os.path.join(workdir, "config"), "w") as f:
                f.write(BARESIP_CONFIG)
            fd = os.open(os.path.join(workdir, "accounts"), os.O_WRONLY | os.O_CREAT, 0o600)
            with open(fd, "w") as f:
                f.write(f"<sip:{self.cfg['username']}@{domain};transport={transport}>"
                        f";auth_pass={self.cfg['password']};regint=0{mediaenc}\n")
            proc = subprocess.Popen(
                # stdbuf: baresip block-buffers stdout on a pipe, so progress would only show at exit
                ["stdbuf", "-oL", "baresip", "-f", workdir,
                 "-e", f"/dial sip:{self.cfg['call_to']}@{domain}", "-t", str(ring + 5)],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        except OSError as e:
            shutil.rmtree(workdir, ignore_errors=True)
            return "failed", f"cannot start baresip: {e}"

        lines = queue.Queue()
        threading.Thread(target=lambda: [lines.put(l) for l in proc.stdout], daemon=True).start()
        result, detail = "retry", "rang out"
        progressed = False
        deadline = time.monotonic() + ring
        try:
            while proc.poll() is None or not lines.empty():
                try:
                    line = lines.get(timeout=1).strip()
                except queue.Empty:
                    line = ""
                low = line.lower()
                if "sip progress" in low:
                    progressed = True
                    self.log.info("  %s", line.split("SIP Progress:")[-1].strip())
                elif "call established" in low:
                    result, detail = "answered", line
                    time.sleep(3)  # let the tone play briefly, then hang up
                    break
                elif "session closed" in low:
                    result, detail = classify_close(line), line
                    break
                if time.monotonic() > deadline:
                    break
                if ctx.laptop_active():
                    result, detail = "laptop activity", ""
                    break
            else:
                if not progressed:
                    # baresip exited without the server ever answering: network/TLS/config problem
                    result, detail = "failed", "no response from SIP server"
        finally:
            if proc.poll() is None:
                proc.send_signal(signal.SIGINT)  # baresip hangs up / cancels cleanly
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
            shutil.rmtree(workdir, ignore_errors=True)
        return result, detail
