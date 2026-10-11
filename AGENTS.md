# Codex guidelines

- Always use the ponytail skill. Never compromise on security.
- Resolve clarifications and assumptions before implementation; require an explicit GO.
- Write tests only when explicitly requested.
- This is an interview MVP. Prefer the simplest correct implementation.
- Preserve Python, FastAPI, httpx, OpenTelemetry metrics, Prometheus and Docker Compose.
- No database, framework layers, distributed tracing, Collector, Grafana or Kubernetes.
- Keep each Python file small with one clear responsibility.
- Do not silently guess DB25 to DB07 classification mappings; use authoritative data only.
- Preserve source semantics: ERHV1 counts workplaces and jobs, not legal companies.
- Preserve `null` for unavailable company employee counts and missing statistics.
- Keep current CVR data distinct from statistics for the selected historical year.
- Update README's Known Challenges and Design Decisions whenever scope changes.
- Run `pytest -q` after changing application logic.
- Do not commit actual personal CVR response fixtures or contact details.
