# models.py definerer data strukturerne for API'et, som bruges til at validere og dokumentere input/output.

from typing import Literal

from pydantic import BaseModel, Field

# Company er en klasse, der beskriver den pågældende virksomhed - den sammensætter cvr + navn + adresse + branchekode + antal ansatte + rapporteringsperiode + data periode
class Company(BaseModel):
    cvr: str
    name: str
    address: str | None
    industry_code_db25: str | None
    employees: int | None = Field(description="Latest reported count, not a count for the selected year.")
    employees_period: str | None = Field(default=None, description="APICVR does not supply the reporting period.")
    data_period: Literal["current"]

# IndustryStatistics er en klasse, der beskriver de statistiske data for en branche og sammensætter det med en virksomhed for et givent år
class IndustryStatistics(BaseModel):
    year: int
    industry_codes_db07: list[str] = Field(
        min_length=1,
        description="Historical ERHV1 DB07 source branches selected using DST correspondence; multiple branches are summed."
    )
    workplaces: int | float | None = Field(description="Workplaces at the end of November, not companies.")
    jobs: int | float | None = Field(description="Jobs at the end of November, not unique people.")
    full_time_employment: int | float | None = Field(description="Employment in full-time equivalents during the year.")
    payroll_million_dkk: int | float | None = Field(description="Annual payroll in millions of DKK.")

# LookupResult er en klasse, der beskriver det overordnede resultat af en forespørgsel på en virksomhed - den kombinerer de to ovenstående klasser med et årstal, status og advarsler
class LookupResult(BaseModel):
    year: int = Field(description="Requested statistics year, also retained in partial results.")
    status: Literal["complete", "partial"]
    company: Company
    industry_statistics: IndustryStatistics | None
    warnings: list[str] = Field(description="Unavailable-data reason codes documented in README.")

# Candidate er en klasse, der beskriver en kandidat virksomhed, som returneres, når der er flere virksomheder med samme navn - den sammensætter cvr + navn + status
class Candidate(BaseModel):
    cvr: str
    name: str
    status: str | None

# AmbiguousName er en klasse, der beskriver en fejlmeddelelse, når der er flere virksomheder med samme navn. Formålet er at tage højde for, at der kan være flere kandidater, som brugeren skal vælge imellem. Den sammensætter en fejlmeddelelse + en liste af kandidater
class AmbiguousName(BaseModel):
    message: str
    candidates: list[Candidate]

# ErrorResponse er en klasse, der beskriver en fejlrespons, når en forespørgsel fejler (sikre konsistent struktur for fejlmeddelelser).
class ErrorResponse(BaseModel):
    detail: str
