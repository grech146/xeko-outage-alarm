#!/usr/bin/env python3
"""Fixtures for check.py against a fake n8n and a fake ntfy on this machine. Nothing real is called.
Usage: python3 outage-alarm/test_check.py   (exit 0 = every case passed)
"""

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
GOOD = json.load(open(os.path.join(HERE, "watch.json")))[0]["known_good"]
STATE = {}


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body):
        self.send_response(code)
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def do_GET(self):
        STATE["gets"] += 1
        plan = STATE["get_plan"]
        code = plan.pop(0) if len(plan) > 1 else plan[0]
        if code == "html":
            self.send_response(200)
            self.end_headers()
            return self.wfile.write(b"<html>offline</html>")
        if code != 200:
            return self._send(code, {"message": "Workspace offline"})
        self._send(200, {"active": STATE["active"], "versionId": STATE["version"],
                         "activeVersionId": STATE["version"] if STATE["active"] else None})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n).decode()
        if self.path.startswith("/api/v1/workflows/") and self.path.endswith("/activate"):
            STATE["activates"] += 1
            if STATE["activate_holds"]:
                STATE["active"] = True
            return self._send(200, {})
        if self.path.startswith("/topic"):
            if STATE["ntfy_down"]:
                return self._send(500, {})
            STATE["buzzes"].append(body)
            return self._send(200, {})
        self._send(404, {})


def run(srv, **case):
    STATE.clear()
    STATE.update(gets=0, activates=0, buzzes=[], get_plan=list(case.get("get_plan", [200])),
                 active=case.get("active", True), version=case.get("version", GOOD),
                 activate_holds=case.get("activate_holds", True), ntfy_down=case.get("ntfy_down", False))
    url = "http://127.0.0.1:{}".format(srv.server_port)
    e = dict(os.environ, N8N_URL=url, N8N_KEY="k", NTFY_TOPIC="topic", NTFY_URL=url, RETRIES="3", RETRY_WAIT="0.1")
    if case.get("dry"):
        e["DRY_RUN"] = "1"
    p = subprocess.run([sys.executable, os.path.join(HERE, "check.py")], env=e, capture_output=True, text=True, timeout=60)
    return p.returncode, dict(STATE)


CASES = [
    ("on: silent", {}, lambda c, s: c == 0 and not s["buzzes"] and s["activates"] == 0),
    ("down every retry: one buzz, names not answering", {"get_plan": [503]},
     lambda c, s: c == 0 and len(s["buzzes"]) == 1 and "not answering" in s["buzzes"][0] and s["gets"] == 3),
    ("a blip that clears within the run: silent", {"get_plan": [503, 503, 200]},
     lambda c, s: c == 0 and not s["buzzes"]),
    ("off, good version: switched on, one buzz saying so", {"active": False},
     lambda c, s: c == 0 and s["activates"] == 1 and len(s["buzzes"]) == 1 and "switched it back ON" in s["buzzes"][0]),
    ("off, other version: NOT switched on, one buzz", {"active": False, "version": "0bad0bad"},
     lambda c, s: c == 0 and s["activates"] == 0 and len(s["buzzes"]) == 1 and "did NOT switch" in s["buzzes"][0]),
    ("off, switch-on does not hold: PROBLEM buzz", {"active": False, "activate_holds": False},
     lambda c, s: c == 0 and s["activates"] == 1 and len(s["buzzes"]) == 1 and "did not hold" in s["buzzes"][0]),
    ("buzz cannot be sent: run fails (exit 1)", {"get_plan": [503], "ntfy_down": True},
     lambda c, s: c == 1),
    ("key refused: one buzz naming the key, no retries", {"get_plan": [401]},
     lambda c, s: c == 0 and len(s["buzzes"]) == 1 and "refused the outage alarm's key" in s["buzzes"][0] and s["gets"] == 1),
    ("a 200 that is not JSON (an error page): treated as down, one buzz", {"get_plan": ["html"]},
     lambda c, s: c == 0 and len(s["buzzes"]) == 1 and "not answering" in s["buzzes"][0]),
    ("dry run, off, good version: no switch-on, no buzz", {"active": False, "dry": True},
     lambda c, s: c == 0 and s["activates"] == 0 and not s["buzzes"]),
]


def main():
    srv = HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    bad = 0
    for name, case, ok in CASES:
        code, s = run(srv, **case)
        good = ok(code, s)
        bad += not good
        print("{}  {}  (exit {}, reads {}, switch-ons {}, buzzes {})".format(
            "PASS" if good else "FAIL", name, code, s["gets"], s["activates"], len(s["buzzes"])))
    print("{} of {} passed".format(len(CASES) - bad, len(CASES)))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
