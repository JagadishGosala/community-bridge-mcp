"""Tool input and output models (SPEC §8).

Inputs are strict, flat and closed (extra="forbid" -> additionalProperties: false).
Free text is trimmed before length checks (A-06, A-07).
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationInfo, field_validator

from cb.money import parse_amount

Id = Annotated[str, StringConstraints(pattern=r"^[a-z0-9_]{1,64}$")]
Amount = Annotated[str, StringConstraints(pattern=r"^[0-9]{1,7}(\.[0-9]{1,2})?$")]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Money = Annotated[str, StringConstraints(pattern=r"^[0-9]+\.[0-9]{2}$")]
Purpose = Literal["RENT", "UTILITIES", "TRANSPORTATION", "OTHER"]
Status = Literal["PENDING", "APPROVED", "REJECTED", "PAID"]
Role = Literal["CASE_WORKER", "PROGRAM_MANAGER", "FINANCE"]


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


# --- inputs --------------------------------------------------------------------------


class WhoamiInput(_Input):
    pass


class ListParticipantsInput(_Input):
    pass


class ListFundsInput(_Input):
    pass


class GetFundingSummaryInput(_Input):
    fund_id: Id | None = None


class CreateRequestInput(_Input):
    participant_id: Id
    fund_id: Id
    purpose: Purpose
    amount: Amount
    description: Text | None = Field(default=None, validate_default=True)

    @field_validator("amount")
    @classmethod
    def _amount_is_valid(cls, value: str) -> str:
        parse_amount(value)  # REQ-15 regex (ASCII digits) and range
        return value

    @field_validator("description")
    @classmethod
    def _other_requires_description(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None and info.data.get("purpose") == "OTHER":
            raise ValueError("description is required when purpose is OTHER")
        return value

    @property
    def amount_cents(self) -> int:
        return parse_amount(self.amount)


class ApproveRequestInput(_Input):
    request_id: Id


class RejectRequestInput(_Input):
    request_id: Id
    reason: Text


class RecordPaymentInput(_Input):
    request_id: Id


class GetRequestInput(_Input):
    request_id: Id


class ListRequestsInput(_Input):
    status: Status | None = None
    fund_id: Id | None = None


# --- outputs -------------------------------------------------------------------------


class WhoamiOutput(BaseModel):
    staff_id: Id
    staff_name: str
    role: Role
    nonprofit_id: Id
    nonprofit_name: str


class Participant(BaseModel):
    id: Id
    display_name: str


class ParticipantsOutput(BaseModel):
    participants: list[Participant]


class Fund(BaseModel):
    id: Id
    name: str
    allocation: Money


class FundsOutput(BaseModel):
    funds: list[Fund]


class FundSummary(BaseModel):
    fund_id: Id
    fund_name: str
    allocation: Money
    committed: Money
    paid: Money
    available: Money


class FundingSummaryOutput(BaseModel):
    funds: list[FundSummary]


class Payment(BaseModel):
    id: Id
    amount: Money
    recorded_by: Id
    recorded_at: str


class Request(BaseModel):
    id: Id
    participant_id: Id
    fund_id: Id
    purpose: Purpose
    description: str | None
    amount: Money
    status: Status
    created_by: Id
    created_at: str
    decided_by: Id | None
    decided_at: str | None
    rejection_reason: str | None
    payment: Payment | None


class RequestsOutput(BaseModel):
    requests: list[Request]
