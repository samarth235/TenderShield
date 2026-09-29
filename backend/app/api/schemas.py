"""Request bodies for the public API."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    method: Optional[Literal["pattern", "llm", "auto"]] = Field(
        None, description="Rule extractor; defaults to TS_EXTRACTOR (pattern)")
    actor: str = "system"


class ExtractRequest(BaseModel):
    method: Optional[Literal["pattern", "llm", "auto"]] = None


class CounterfactualRequest(BaseModel):
    remove: list[str] = Field(..., min_length=1, description="Evidence ids to remove, e.g. ['E1']")
    actor: str = "auditor"
    record: bool = Field(True, description="Persist the run and log it in the audit trail")


class DispositionRequest(BaseModel):
    decision: Literal["VERIFIED", "DISMISSED", "FURTHER_REVIEW"]
    auditor: str = Field(..., min_length=1)
    notes: str = ""


class FinalizeRequest(BaseModel):
    auditor: str = Field(..., min_length=1)
    note: str = ""


class TamperRequest(BaseModel):
    document_id: Optional[str] = None


class VersionReviewRequest(BaseModel):
    decision: Literal["ACCEPT", "REQUEST_VERIFICATION", "FLAG_FOR_INVESTIGATION"]
    auditor: str = Field(..., min_length=1)
    notes: str = ""
    finalize: bool = Field(True, description="On ACCEPT, seal a new evidence snapshot that commits the new version")


class ExplainRequest(BaseModel):
    method: Optional[Literal["auto", "llm", "template"]] = Field(
        None, description="auto = Claude when credentials are configured, else the rule-based template")
    from_version: Optional[int] = Field(None, description="Defaults to the version the new one was compared against")


class BidderRecord(BaseModel):
    vendor_id: Optional[str] = None
    name: str
    gstin: Optional[str] = None
    registered_address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    directors: list[dict] = Field(default_factory=list)
    amount_cr: Optional[float] = None
    submitted_at: Optional[str] = None
    facts: dict[str, Any] = Field(default_factory=dict, description="metric -> declared value (see /api/meta/metrics)")


class BiddersUpload(BaseModel):
    bidders: list[BidderRecord]
