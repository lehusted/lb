"""Response shapes shown in the API documentation."""

from typing import Literal

from pydantic import BaseModel, Field


class Company(BaseModel):
    cvr: str
    name: str
    address: str | None
    industry_code_db25: str | None
    employees: int | None = Field(description="Latest reported count, not a count for the selected year.")
    employees_period: str | None = Field(default=None, description="APICVR does not supply the reporting period.")
    data_period: Literal["current"]


class IndustryStatistics(BaseModel):
    year: int
    industry_code_db07: str = Field(
        description="ERHV1 code queried directly using the current CVR code; classification equivalence is not verified."
    )
    workplaces: int | float | None = Field(description="Workplaces at the end of November, not companies.")
    jobs: int | float | None = Field(description="Jobs at the end of November, not unique people.")
    full_time_employment: int | float | None = Field(description="Employment in full-time equivalents during the year.")
    payroll_million_dkk: int | float | None = Field(description="Annual payroll in millions of DKK.")


class LookupResult(BaseModel):
    year: int = Field(description="Requested statistics year, also retained in partial results.")
    status: Literal["complete", "partial"]
    company: Company
    industry_statistics: IndustryStatistics | None
    warnings: list[str] = Field(description="Unavailable-data reason codes documented in README.")


class Candidate(BaseModel):
    cvr: str
    name: str
    status: str | None


class AmbiguousName(BaseModel):
    message: str
    candidates: list[Candidate]


class ErrorResponse(BaseModel):
    detail: str
