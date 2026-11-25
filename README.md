# Questionnaire outage alarm

Every 5 minutes, from outside n8n: is the n8n account answering, and is each watched workflow switched on?
If a workflow is off and still on its recorded good version, the alarm switches it back on and buzzes.
Any other problem buzzes and changes nothing. Rules and reasons: `check.py`. Tests: `python3 test_check.py`.

Secrets (repository settings): `N8N_URL`, `N8N_KEY`, `NTFY_TOPIC`.
After any approved change to a watched workflow, update its `known_good` version in `watch.json`.

Who watches the alarm: a once-a-day n8n check (08:23 Sydney) reads this repository's latest run and buzzes if it is over a day old (the Mac runner does the 5-minute checks; GitHub is the backup), failed, or the schedule is switched off.
