"use strict";

const form = document.querySelector("#lookup");
const companyInput = document.querySelector("#company");
const yearInput = document.querySelector("#year");
const status = document.querySelector("#lookup-status");
const candidates = document.querySelector("#candidates");
const matches = document.querySelector("#matches");
const results = document.querySelector("#results");
const numberFormat = new Intl.NumberFormat("da-DK", { maximumFractionDigits: 20 });

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
    response = await fetch(`/api${path}`, { cache: "no-store" });
  } catch {
    throw new Error("Der kunne ikke oprettes forbindelse til tjenesten. Prøv igen.");
  }
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const errors = {
      404: "Virksomheden blev ikke fundet.",
      422: "Søgningen kunne ikke gennemføres. Kontrollér dine oplysninger, og prøv igen.",
      502: "En datakilde er utilgængelig eller returnerede ugyldige data. Prøv igen.",
      504: "En datakilde svarede ikke i tide. Prøv igen.",
    };
    if (data?.detail === "No verified DB25 -> DB07 mapping for this company") {
      errors[422] = "Branchestatistik understøttes endnu ikke for virksomhedens branche.";
    } else if (data?.detail === "Company has no industry code") {
      errors[422] = "Virksomheden har ingen branchekode, så branchestatistik kan ikke hentes.";
    }
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

async function enrich(cvr, year) {
  if (!form.reportValidity()) return;
  results.hidden = true;
  setBusy(true);
  setStatus("Henter virksomhedsoplysninger og branchestatistik…");
  try {
    const data = await request(`/companies/${encodeURIComponent(cvr)}?year=${encodeURIComponent(year)}`);
    const company = data.company;
    const statistics = data.industry_statistics;
    document.querySelector("#company-title").textContent = company.name;
    showDetails("#company-details", [
      ["CVR-nummer", company.cvr],
      ["Adresse", company.address],
      ["Primær branche (DB25)", company.industry_code_db25],
      ["Ansatte i virksomheden", company.employees],
    ]);
    document.querySelector("#statistics-title").textContent = `Branchestatistik · ${statistics.year}`;
    showDetails("#statistics-details", [
      ["Branche (DB07)", statistics.industry_code_db07],
      ["Arbejdssteder", statistics.workplaces],
      ["Job", statistics.jobs],
      ["Fuldtidsbeskæftigede", statistics.full_time_employment],
      ["Årlig lønsum (mio. kr.)", statistics.payroll_million_dkk],
    ]);
    candidates.hidden = true;
    results.hidden = false;
    setStatus("Virksomhedsoplysningerne er hentet.");
    document.querySelector("#company-title").focus();
  } catch (error) {
    setStatus(error instanceof TypeError ? "Svaret fra tjenesten kunne ikke behandles. Prøv igen." : error.message, true);
  } finally {
    setBusy(false);
  }
}

for (const [input, message] of [
  [companyInput, "Indtast et firmanavn eller et CVR-nummer (mindst to tegn)."],
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
  const year = yearInput.value;
  const numeric = /^[0-9]+$/.test(query);
  if (query.length < 2 || (numeric && query.length !== 8)) {
    companyInput.setCustomValidity(numeric ? "Et CVR-nummer skal indeholde præcis 8 cifre." : "Indtast mindst to tegn.");
    companyInput.reportValidity();
    return;
  }
  candidates.hidden = true;
  results.hidden = true;
  matches.replaceChildren();
  if (numeric) {
    await enrich(query, year);
    return;
  }
  setBusy(true);
  setStatus("Søger efter virksomheder…");
  try {
    const companies = await request(`/companies?${new URLSearchParams({ name: query })}`);
    for (const company of companies) {
      const row = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = `${company.name} · CVR ${company.cvr}${company.status ? ` · ${company.status}` : ""}`;
      button.addEventListener("click", () => enrich(company.cvr, yearInput.value));
      row.append(button);
      matches.append(row);
    }
    candidates.hidden = companies.length === 0;
    setStatus(companies.length ? "Vælg en virksomhed for at hente dens oplysninger." : "Ingen virksomheder fundet.");
    if (companies.length) matches.querySelector("button").focus();
  } catch (error) {
    setStatus(error instanceof TypeError ? "Svaret fra tjenesten kunne ikke behandles. Prøv igen." : error.message, true);
  } finally {
    setBusy(false);
  }
});
