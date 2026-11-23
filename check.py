#!/usr/bin/env python3
"""Questionnaire outage alarm (BL-303 a). Runs from GitHub's scheduler, OUTSIDE n8n.

Every run, for each workflow in watch.json: is the n8n account answering, and is the workflow switched on?
  - answering and on            -> silent
  - not answering               -> retried within the run; still down -> buzz Ben's phone
  - answering, OFF, and the version is the recorded known-good one -> switch it back on, re-read, buzz
  - answering, OFF, any other version -> buzz "off, NOT switched on"; a failed change is left off on purpose
Never creates an n8n execution: API reads and the switch-on only. Standard library only.

Settings come from the environment (GitHub secrets): N8N_URL, N8N_KEY, NTFY_TOPIC. Optional: NTFY_URL
(default https://ntfy.sh), DRY_RUN=1 (decide and print, never switch on or buzz), RETRIES, RETRY_WAIT.
Exit 1 if a buzz could not be sent, so GitHub's own failure email is the last line of defence.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))


def env(name, default=None):
    v = os.environ.get(name, default)
    if v is None:
        raise SystemExit("STOPPED: setting {} is missing".format(name))
    return v


def n8n(path, method="GET"):
    req = urllib.request.Request(env("N8N_URL").rstrip("/") + "/api/v1" + path, method=method,
                                 data=b"" if method == "POST" else None,
                                 headers={"X-N8N-API-KEY": env("N8N_KEY"), "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode() or "{}")


def read(wf_id, retries, wait):
    """The workflow record, or the last error text after every retry failed."""
    last = None
    for i in range(retries):
        try:
            return n8n("/workflows/" + wf_id), None
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            last = "HTTP {}".format(e.code) if isinstance(e, urllib.error.HTTPError) else str(e)[:120]
            if last in ("HTTP 401", "HTTP 403"):
                break
            if i < retries - 1:
                time.sleep(wait)
    return None, last


def decide(wf, rec, err):
    """What to do, as (action, message). action: none | buzz | switch_on."""
    if rec is None and err in ("HTTP 401", "HTTP 403"):
        return "buzz", "[xeko] PROBLEM: n8n refused the outage alarm's key ({}), so the {} is NOT being watched. Replace the key.".format(
            err, wf["name"])
    if rec is None:
        return "buzz", "[xeko] PROBLEM: n8n is not answering, so the {} may be down ({}). Checked from outside n8n.".format(
            wf["name"], err)
    if rec.get("active"):
        return "none", "{}: on".format(wf["name"])
    if rec.get("versionId") == wf["known_good"]:
        return "switch_on", None
    return "buzz", ("[xeko] PROBLEM: the {} is switched OFF and its version ({}) is not the recorded good one, "
                    "so the alarm did NOT switch it back on. Check it by hand.").format(wf["name"], str(rec.get("versionId"))[:8])


def buzz(text):
    url = os.environ.get("NTFY_URL", "https://ntfy.sh").rstrip("/") + "/" + env("NTFY_TOPIC")
    urllib.request.urlopen(urllib.request.Request(url, data=text.encode(), method="POST"), timeout=30).read()


def main():
    dry = os.environ.get("DRY_RUN") == "1"
    retries = int(os.environ.get("RETRIES", "4"))
    wait = float(os.environ.get("RETRY_WAIT", "20"))
    watch = json.load(open(os.path.join(HERE, "watch.json")))
    failed_buzz = False
    for wf in watch:
        rec, err = read(wf["id"], retries, wait)
        action, msg = decide(wf, rec, err)
        if action == "switch_on":
            if dry:
                msg = "DRY RUN: would switch the {} back on".format(wf["name"])
                action = "none"
            else:
                try:
                    n8n("/workflows/{}/activate".format(wf["id"]), "POST")
                    after, err2 = read(wf["id"], retries, wait)
                except urllib.error.URLError as e:
                    after, err2 = None, str(e)[:120]
                ok = bool(after and after.get("active") and after.get("activeVersionId") == wf["known_good"])
                msg = ("[xeko] The {} was found switched OFF; the alarm switched it back ON (version {}). Nothing for you "
                       "unless this repeats.").format(wf["name"], wf["known_good"][:8]) if ok else (
                       "[xeko] PROBLEM: the {} is switched OFF and switching it back on did not hold ({}). Check it by hand."
                       ).format(wf["name"], err2 or "still off")
                action = "buzz"
        print(json.dumps({"workflow": wf["name"], "action": action, "message": msg}), flush=True)
        if action == "buzz" and not dry:
            try:
                buzz(msg)
            except Exception as e:  # noqa: BLE001 - any failure to buzz must fail the run
                print("BUZZ FAILED: {}".format(e), file=sys.stderr)
                failed_buzz = True
    sys.exit(1 if failed_buzz else 0)


if __name__ == "__main__":
    main()
