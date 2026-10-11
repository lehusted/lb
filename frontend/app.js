"use strict";

const form = document.querySelector("#lookup");
const companyInput = document.querySelector("#company");
const yearInput = document.querySelector("#year");
const status = document.querySelector("#lookup-status");
const candidates = document.querySelector("#candidates");
const matches = document.querySelector("#matches");
const results = document.querySelector("#results");
const numberFormat = new Intl.NumberFormat("da-DK", { maximumFractionDigits: 20 });
const warnings = {
  employees_unavailable: "Antal ansatte i virksomheden er ikke tilgængeligt.",
  address_unavailable: "Virksomhedens adresse er ikke tilgængelig.",
  industry_missing: "Virksomheden har ingen branchekode, så branchestatistik kan ikke hentes.",
  statistics_timeout: "Branchestatistikken svarede ikke i tide. Prøv igen.",
  statistics_unavailable: "Branchestatistikken er ikke tilgængelig for denne branchekode og dette år, eller datakilden kunne ikke levere et gyldigt svar.",
  statistics_values_unavailable: "Nogle tal i branchestatistikken er ikke tilgængelige.",
};

function setBusy(busy) {
  form.setAttribute("aria-busy", String(busy));
  document.querySelectorAll("input, button").forEach(control => { control.disabled = busy; });
}

function setStatus(message, error = false) {
  status.textContent = message;
  status.classList.toggle("error", error);
  if (error) status.focus();
}

async function request(path) {
  let response;
  try {
    response = await fetch("/api" + path, { cache: "no-store" });
  } catch {
    throw new Error("Der kunne ikke oprettes forbindelse til tjenesten. Prøv igen.");
  }
  const data = await response.json().catch(() => null);
  if (response.status === 409 && Array.isArray(data?.candidates)) return data;
  if (!response.ok) {
    const errors = {
      404: "Ingen virksomhed blev fundet.",
      422: "Kontrollér firmanavn, CVR-nummer og årstal, og prøv igen.",
      502: "Virksomhedsoplysningerne kunne ikke hentes fra datakilden. Prøv igen.",
      504: "Datakilden til virksomhedsoplysninger svarede ikke i tide. Prøv igen.",
    };
    throw new Error(errors[response.status] || "Søgningen kunne ikke gennemføres. Prøv igen.");
  }
  if (data === null) throw new Error("Svaret fra tjenesten kunne ikke læses. Prøv igen.");
  return data;
}

function showDetails(id, rows) {
  const list = document.querySelector(id);
  list.replaceChildren();
  for (const [label, value] of rows) {
    const term = document.createElement("dt");
    const description = document.createElement("dd");
    term.textContent = label;
    description.textContent = value === null || value === undefined || value === "" ? "Ikke tilgængelig" :
      typeof value === "number" ? numberFormat.format(value) : value;
    list.append(term, description);
  }
}

function showCandidates(companies) {
  for (const company of companies) {
    const row = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = company.name + " · CVR " + company.cvr + (company.status ? " · " + company.status : "");
    button.addEventListener("click", () => lookup("/companies/" + encodeURIComponent(company.cvr) + "?year=" + yearInput.value));
    row.append(button);
    matches.append(row);
  }
  candidates.hidden = false;
  setStatus("Flere virksomheder matcher. Vælg en virksomhed.");
}

function showResult(data) {
  const company = data.company;
  const statistics = data.industry_statistics ?? {};
  document.querySelector("#company-title").textContent = company.name;
  showDetails("#company-details", [
    ["CVR-nummer", company.cvr],
    ["Adresse", company.address],
    ["Primær branche (DB25)", company.industry_code_db25],
    ["Ansatte (senest indberettet)", company.employees],
  ]);
  document.querySelector("#statistics-title").textContent = "Branchestatistik · " + data.year;
  showDetails("#statistics-details", [
    ["Branche (DB07)", statistics.industry_code_db07],
    ["Arbejdssteder ultimo november", statistics.workplaces],
    ["Job ultimo november", statistics.jobs],
    ["Fuldtidsbeskæftigede", statistics.full_time_employment],
    ["Årlig lønsum (mio. kr.)", statistics.payroll_million_dkk],
  ]);
  const messages = data.warnings.map(code => warnings[code] || "Nogle oplysninger er ikke tilgængelige.");
  document.querySelector("#result-notice").textContent = messages.join(" ");
  results.hidden = false;
  setStatus(data.status === "partial" ? "Virksomheden er fundet. Nogle oplysninger mangler." : "Virksomhedsoplysninger og branchestatistik er hentet.");
  document.querySelector("#company-title").focus();
}

async function lookup(path) {
  if (!form.reportValidity()) return;
  candidates.hidden = true;
  results.hidden = true;
  matches.replaceChildren();
  setBusy(true);
  setStatus("Henter virksomhedsoplysninger og branchestatistik…");
  try {
    const data = await request(path);
    if (data.candidates) showCandidates(data.candidates);
    else showResult(data);
  } catch (error) {
    setStatus(error instanceof TypeError ? "Svaret fra tjenesten kunne ikke behandles. Prøv igen." : error.message, true);
  } finally {
    setBusy(false);
    if (!candidates.hidden) matches.querySelector("button").focus();
  }
}

for (const [input, message] of [
  [companyInput, "Indtast et firmanavn på 2–200 tegn eller et CVR-nummer."],
  [yearInput, "Vælg et helt årstal mellem 2008 og 2024."],
]) {
  input.addEventListener("input", () => input.setCustomValidity(""));
  input.addEventListener("invalid", () => {
    if (!input.validity.customError) input.setCustomValidity(message);
  });
}

form.addEventListener("submit", async event => {
  event.preventDefault();
  const query = companyInput.value.trim();
  const numeric = /^[0-9]+$/.test(query);
  if (query.length < 2 || (numeric && query.length !== 8)) {
    companyInput.setCustomValidity(numeric ? "Et CVR-nummer skal indeholde præcis 8 cifre." : "Indtast mindst to tegn.");
    companyInput.reportValidity();
    return;
  }
  const path = numeric ? "/companies/" + query + "?year=" + yearInput.value :
    "/companies?" + new URLSearchParams({ name: query, year: yearInput.value });
  await lookup(path);
});
