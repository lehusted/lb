const queries = [
  'up{job="lb-interview-case"}',
  'histogram_quantile(0.95, sum by (le) (rate(api_request_duration_seconds_bucket{job="lb-interview-case",path=~"/companies.*"}[5m])))',
  '100 * sum(rate(api_requests_total{job="lb-interview-case",path=~"/companies.*",outcome="error"}[5m])) / sum(rate(api_requests_total{job="lb-interview-case",path=~"/companies.*"}[5m]))',
  'histogram_quantile(0.95, sum by (le, source) (rate(downstream_request_duration_seconds_bucket{job="lb-interview-case"}[5m])))',
  '100 * sum by (source) (rate(downstream_requests_total{job="lb-interview-case",outcome="error"}[5m])) / sum by (source) (rate(downstream_requests_total{job="lb-interview-case"}[5m]))',
];
const status = document.getElementById("monitoring-status");
const table = document.getElementById("monitoring-metrics");
const updated = document.getElementById("monitoring-updated");

async function query(expression, time) {
  const params = new URLSearchParams({ query: expression, time, timeout: "3s" });
  const response = await fetch("/monitorering/query?" + params, {
    cache: "no-store", signal: AbortSignal.timeout(4000),
  });
  if (!response.ok) throw new Error("Prometheus is unavailable");
  const payload = await response.json();
  if (payload.status !== "success" || payload.data?.resultType !== "vector" ||
      !Array.isArray(payload.data.result)) throw new Error("Invalid Prometheus response");
  return payload.data.result;
}

function format(sample, unit) {
  const raw = sample?.value?.[1];
  const value = typeof raw === "string" && raw.trim() ? Number(raw) : NaN;
  if (!Number.isFinite(value) || value < 0) return "Ingen målinger";
  return (unit === "ms" ? value * 1000 : value).toLocaleString("da-DK", {
    minimumFractionDigits: unit === "%" ? 1 : 0, maximumFractionDigits: 1,
  }) + " " + unit;
}

async function refresh() {
  let message;
  try {
    const time = String(Date.now() / 1000);
    const [availability, apiP95, apiErrors, sourceP95, sourceErrors] =
      await Promise.all(queries.map(expression => query(expression, time)));
    for (const source of ["api", "cvr", "statbank"]) {
      const p95 = source === "api" ? apiP95[0] : sourceP95.find(sample => sample.metric?.source === source);
      const errors = source === "api" ? apiErrors[0] : sourceErrors.find(sample => sample.metric?.source === source);
      document.getElementById(source + "-p95").textContent = format(p95, "ms");
      document.getElementById(source + "-errors").textContent = format(errors, "%");
    }
    const available = availability[0]?.value?.[1];
    message = available === "1" ? "API-metrikker kan hentes." : available === "0" ?
      "API-metrikker kan ikke hentes. Tallene viser tidligere kald i perioden." : "Afventer API-målinger.";
    status.classList.toggle("error", available === "0");
    table.classList.toggle("is-stale", available !== "1");
    updated.textContent = new Date().toLocaleString("da-DK");
  } catch {
    message = "Monitoreringen kunne ikke opdateres. Viste tal kan være forældede; prøver automatisk igen.";
    status.classList.add("error");
    table.classList.add("is-stale");
  } finally {
    if (status.textContent !== message) status.textContent = message;
    setTimeout(refresh, 5000);
  }
}

refresh();
