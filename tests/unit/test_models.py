"""Input models (SPEC §6.3 step 1, §8; AC-26, AC-27 at model level, plus AC-24's JSON number)."""

import pytest
from pydantic import ValidationError

from cb import models

VALID_CREATE = {
    "participant_id": "par_bridge_001",
    "fund_id": "fund_bridge_rent",
    "purpose": "RENT",
    "amount": "300.00",
}

# tool -> (input model, minimal valid arguments, expected top-level fields per §8)
INPUTS = {
    "whoami": (models.WhoamiInput, {}, set()),
    "list_participants": (models.ListParticipantsInput, {}, set()),
    "list_funds": (models.ListFundsInput, {}, set()),
    "get_funding_summary": (models.GetFundingSummaryInput, {}, {"fund_id"}),
    "create_request": (
        models.CreateRequestInput,
        VALID_CREATE,
        {"participant_id", "fund_id", "purpose", "amount", "description"},
    ),
    "approve_request": (models.ApproveRequestInput, {"request_id": "req_x"}, {"request_id"}),
    "reject_request": (models.RejectRequestInput, {"request_id": "req_x", "reason": "Duplicate"}, {"request_id", "reason"}),
    "record_payment": (models.RecordPaymentInput, {"request_id": "req_x"}, {"request_id"}),
    "get_request": (models.GetRequestInput, {"request_id": "req_x"}, {"request_id"}),
    "list_requests": (models.ListRequestsInput, {}, {"status", "fund_id"}),
}


def error_fields(exc_info) -> set[str]:
    return {".".join(str(p) for p in e["loc"]) for e in exc_info.value.errors()}


_MISSING = object()


def create(**overrides):
    """CreateRequestInput from VALID_CREATE with overrides; _MISSING drops a field."""
    args = {**VALID_CREATE, **overrides}
    return models.CreateRequestInput.model_validate({k: v for k, v in args.items() if v is not _MISSING})


# --- every model -------------------------------------------------------------


@pytest.mark.parametrize("tool", sorted(INPUTS))
def test_minimal_valid_input_is_accepted(tool):
    model, args, _ = INPUTS[tool]
    model.model_validate(args)


@pytest.mark.parametrize("extra", ["role", "nonprofit_id", "staff_id", "unexpected"])
@pytest.mark.parametrize("tool", sorted(INPUTS))
def test_unknown_field_is_rejected_and_named(tool, extra):
    model, args, _ = INPUTS[tool]
    with pytest.raises(ValidationError) as exc:
        model.model_validate({**args, extra: "x"})
    assert extra in error_fields(exc)


@pytest.mark.parametrize("tool", sorted(INPUTS))
def test_input_schema_is_flat_and_closed(tool):
    model, _, fields = INPUTS[tool]
    schema = model.model_json_schema()
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema.get("properties", {})) == fields


# --- AC-27 ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "extra", [{"role": "PROGRAM_MANAGER"}, {"nonprofit_id": "np_harbor"}], ids=["role", "nonprofit_id"]
)
def test_ac27_create_request_rejects_identity_fields(extra):
    with pytest.raises(ValidationError) as exc:
        models.CreateRequestInput.model_validate({**VALID_CREATE, **extra})
    assert error_fields(exc) == set(extra)


def test_ac27_approve_request_rejects_staff_id():
    with pytest.raises(ValidationError) as exc:
        models.ApproveRequestInput.model_validate({"request_id": "req_x", "staff_id": "stf_bridge_fin"})
    assert error_fields(exc) == {"staff_id"}


# --- ids -----------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["PAR_1", "par-1", "par 1", "", "a" * 65, 123, None], ids=repr)
def test_id_fields_follow_the_id_pattern(bad):
    with pytest.raises(ValidationError) as exc:
        create(participant_id=bad)
    assert "participant_id" in error_fields(exc)
    with pytest.raises(ValidationError) as exc:
        models.GetRequestInput.model_validate({"request_id": bad})
    assert "request_id" in error_fields(exc)


def test_id_of_64_characters_is_accepted():
    create(participant_id="a" * 64)
    models.GetRequestInput.model_validate({"request_id": "a" * 64})


# --- amount (AC-24 / AC-25 at model level) ---------------------------------------


@pytest.mark.parametrize("amount", [300, 300.0], ids=repr)
def test_json_number_amount_is_rejected(amount):
    with pytest.raises(ValidationError) as exc:
        create(amount=amount)
    assert error_fields(exc) == {"amount"}


@pytest.mark.parametrize(
    "amount", ["0", "-5", "10.999", "abc", "1e3", "1000000.01", " 300", "", "٣٠٠"], ids=repr
)
def test_invalid_amount_string_is_rejected(amount):
    with pytest.raises(ValidationError) as exc:
        create(amount=amount)
    assert error_fields(exc) == {"amount"}


def test_missing_amount_is_rejected():
    with pytest.raises(ValidationError) as exc:
        create(amount=_MISSING)
    assert "amount" in error_fields(exc)


@pytest.mark.parametrize("amount", ["0.01", "1000000.00", "300", "300.5"])
def test_valid_amount_is_accepted(amount):
    create(amount=amount)


# --- purpose and description (AC-26, A-06, A-07) ------------------------------------


@pytest.mark.parametrize("purpose", ["RENT", "UTILITIES", "TRANSPORTATION"])
def test_description_is_optional_for_non_other_purposes(purpose):
    assert create(purpose=purpose).description is None
    assert create(purpose=purpose, description=None).description is None


@pytest.mark.parametrize("purpose", ["FOOD", "rent", "", None, 1], ids=repr)
def test_ac26_purpose_outside_enum_is_rejected(purpose):
    with pytest.raises(ValidationError) as exc:
        create(purpose=purpose)
    assert "purpose" in error_fields(exc)


@pytest.mark.parametrize("description", [_MISSING, None, "  "], ids=["missing", "null", "blank"])
def test_ac26_other_requires_description(description):
    with pytest.raises(ValidationError) as exc:
        create(purpose="OTHER", description=description)
    assert "description" in error_fields(exc)


def test_ac26_other_with_description_is_accepted():
    assert create(purpose="OTHER", description="Bus pass for job interview").description == (
        "Bus pass for job interview"
    )


def test_description_is_trimmed():
    assert create(description="  Bus pass  ").description == "Bus pass"


@pytest.mark.parametrize("description", ["", "   ", "x" * 501, " " + "x" * 501 + " ", 5], ids=repr)
def test_description_present_must_be_1_to_500_after_trimming(description):
    with pytest.raises(ValidationError) as exc:
        create(description=description)
    assert "description" in error_fields(exc)


def test_description_of_500_after_trimming_is_accepted():
    assert create(description=" " + "x" * 500 + " ").description == "x" * 500


# --- reason (REQ-11, A-07) -----------------------------------------------------------


def reject(**args):
    return models.RejectRequestInput.model_validate({"request_id": "req_x", **args})


@pytest.mark.parametrize("reason", [_MISSING, None, "", "   ", "x" * 501, 5], ids=repr)
def test_reason_must_be_1_to_500_after_trimming(reason):
    with pytest.raises(ValidationError) as exc:
        reject(**({} if reason is _MISSING else {"reason": reason}))
    assert "reason" in error_fields(exc)


def test_reason_is_trimmed():
    assert reject(reason="  Duplicate of earlier request ").reason == "Duplicate of earlier request"


def test_reason_of_500_after_trimming_is_accepted():
    assert reject(reason=" " + "x" * 500 + " ").reason == "x" * 500


# --- list_requests status filter ---------------------------------------------------


@pytest.mark.parametrize("status", ["PENDING", "APPROVED", "REJECTED", "PAID"])
def test_status_filter_accepts_each_status(status):
    models.ListRequestsInput.model_validate({"status": status})


@pytest.mark.parametrize("status", ["DONE", "pending", ""], ids=repr)
def test_status_filter_rejects_other_values(status):
    with pytest.raises(ValidationError) as exc:
        models.ListRequestsInput.model_validate({"status": status})
    assert error_fields(exc) == {"status"}
