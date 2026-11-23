# Questionnaire outage alarm

Every 5 minutes, from outside n8n: is the n8n account answering, and is each watched workflow switched on?
If a workflow is off and still on its recorded good version, the alarm switches it back on and buzzes.
Any other problem buzzes and changes nothing. Rules and reasons: `check.py`. Tests: `python3 test_check.py`.

Secrets (repository settings): `N8N_URL`, `N8N_KEY`, `NTFY_TOPIC`.
After any approved change to a watched workflow, update its `known_good` version in `watch.json`.
