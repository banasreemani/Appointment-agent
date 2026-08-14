"""Structured natural-language intent extraction for BrightCare Clinic."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from enum import Enum
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from google import genai
from google.genai import errors, types
from pydantic import (
    BaseModel,
    ConfigDict,
    ValidationError,
    field_validator,
    model_validator,
)

from environment_config import required_environment_variable


SYSTEM_PROMPT = """You are an intent parser for BrightCare Clinic.
Return structured information only using the supplied schema.
Classify exactly one intent: GREETING, BOOKING, FAQ, AFFIRM, DECLINE, or OTHER.
For FAQ, classify exactly one of LOCATION, HOURS, WALK_INS, PARKING, or CANCELLATION.
For BOOKING, extract any requested date, requested time, and email that are present.
Resolve relative dates only from the explicit clinic reference datetime in the input.
An unqualified weekday means its next occurrence on or after the reference clinic date.
Only populate fields relevant to the selected intent.
Leave unknown optional fields null.
Do not determine availability, choose alternatives, book appointments, execute actions,
invent calendar or business information, answer unrelated questions, or send email.
Business and scheduling decisions belong exclusively to deterministic application code.
"""


class Intent(str, Enum):
    GREETING = "GREETING"
    BOOKING = "BOOKING"
    FAQ = "FAQ"
    AFFIRM = "AFFIRM"
    DECLINE = "DECLINE"
    OTHER = "OTHER"


class FAQType(str, Enum):
    LOCATION = "LOCATION"
    HOURS = "HOURS"
    WALK_INS = "WALK_INS"
    PARKING = "PARKING"
    CANCELLATION = "CANCELLATION"


class IntentResult(BaseModel):
    """Validated, action-free interpretation of one user message."""

    model_config = ConfigDict(extra="forbid")

    intent: Intent
    requested_date: date | None = None
    requested_time: time | None = None
    email: str | None = None
    faq_type: FAQType | None = None

    @field_validator("requested_time", mode="after")
    @classmethod
    def normalize_requested_time(cls, value: time | None) -> time | None:
        if value is None:
            return None
        return value.replace(tzinfo=None)

    @model_validator(mode="after")
    def validate_intent_fields(self) -> "IntentResult":
        booking_fields = (self.requested_date, self.requested_time, self.email)
        if self.intent != Intent.BOOKING and any(
            value is not None for value in booking_fields
        ):
            raise ValueError("Booking fields are only valid for BOOKING intent")

        if self.intent == Intent.FAQ and self.faq_type is None:
            raise ValueError("FAQ intent requires faq_type")
        if self.intent != Intent.FAQ and self.faq_type is not None:
            raise ValueError("faq_type is only valid for FAQ intent")
        return self


@dataclass(frozen=True)
class IntentConfig:
    api_key: str
    model: str
    clinic_timezone: ZoneInfo


class IntentExtractionError(RuntimeError):
    """Raised when no safe, validated intent can be returned."""


def load_intent_config() -> IntentConfig:
    """Load Gemini and clinic-time settings from the centralized environment."""
    api_key = required_environment_variable("LLM_API_KEY")
    model = required_environment_variable("LLM_MODEL")
    timezone_name = required_environment_variable("CLINIC_TIMEZONE")
    try:
        clinic_timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as error:
        raise ValueError(f"Unknown clinic timezone: {timezone_name}") from error
    return IntentConfig(api_key, model, clinic_timezone)


def build_gemini_client(config: IntentConfig) -> genai.Client:
    """Create the official Gemini client without exposing its API key."""
    return genai.Client(api_key=config.api_key)


def clinic_reference_datetime(
    reference_datetime: datetime, clinic_timezone: ZoneInfo
) -> datetime:
    """Normalize an explicit reference datetime into the clinic timezone."""
    if reference_datetime.tzinfo is None or reference_datetime.utcoffset() is None:
        raise ValueError("Reference datetime must be timezone-aware")
    return reference_datetime.astimezone(clinic_timezone)


def build_extraction_input(message: str, reference_datetime: datetime) -> str:
    """Build the user input containing the explicit temporal reference."""
    return (
        f"Clinic reference datetime: {reference_datetime.isoformat()}\n"
        f"Clinic weekday: {reference_datetime:%A}\n"
        f"Clinic timezone: {reference_datetime.tzinfo}\n"
        f"User message: {message}"
    )


def _validate_response(response: Any) -> IntentResult:
    response_text = getattr(response, "text", None)
    if not response_text:
        raise IntentExtractionError("The LLM returned no structured intent.")
    return IntentResult.model_validate_json(response_text)


def extract_intent(
    message: str,
    reference_datetime: datetime,
    clinic_timezone: ZoneInfo,
    client: Any,
    model: str,
) -> IntentResult:
    """Extract and locally validate one intent without executing any action."""
    if not message.strip():
        raise IntentExtractionError("A non-empty user message is required.")

    clinic_reference = clinic_reference_datetime(
        reference_datetime,
        clinic_timezone,
    )
    extraction_input = build_extraction_input(message.strip(), clinic_reference)

    try:
        response = client.models.generate_content(
            model=model,
            contents=extraction_input,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_json_schema=IntentResult.model_json_schema(),
                automatic_function_calling=types.AutomaticFunctionCallingConfig(
                    disable=True,
                ),
            ),
        )
        return _validate_response(response)
    except IntentExtractionError:
        raise
    except (errors.APIError, ValidationError, ValueError, TypeError) as error:
        raise IntentExtractionError(
            "The LLM did not return a valid structured intent."
        ) from error
