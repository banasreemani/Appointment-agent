"""Deterministic Telegram responses for validated BrightCare intents."""

from datetime import time

from intent_parser import FAQType, Intent, IntentResult


GREETING_RESPONSE = "Hello! Welcome to BrightCare Clinic. How can I help you?"
BOOKING_CLARIFICATION_RESPONSE = "What date and time would you like the appointment?"
AFFIRM_RESPONSE = "I understand that as a confirmation."
DECLINE_RESPONSE = "Understood."
OTHER_RESPONSE = (
    "I can help with BrightCare Clinic appointments, opening hours, location, "
    "parking, walk-ins, and cancellations."
)
INTENT_ERROR_RESPONSE = (
    "Sorry, I couldn't understand that request. Could you try again?"
)

FAQ_RESPONSES = {
    FAQType.LOCATION: "BrightCare Clinic is located at 12 Orchard Rd.",
    FAQType.HOURS: "We're open Monday to Friday, 9:00am to 6:00pm.",
    FAQType.WALK_INS: (
        "BrightCare Clinic is appointment-only and does not accept walk-ins."
    ),
    FAQType.PARKING: "Yes, parking is available on-site.",
    FAQType.CANCELLATION: (
        "To cancel an appointment, please message the clinic."
    ),
}


def _format_time(value: time) -> str:
    period = "am" if value.hour < 12 else "pm"
    display_hour = value.hour % 12 or 12
    return f"{display_hour}:{value.minute:02d}{period}"


def response_for_intent(result: IntentResult) -> str:
    """Map a validated intent to fixed application-owned response text."""
    if result.intent == Intent.GREETING:
        return GREETING_RESPONSE

    if result.intent == Intent.FAQ:
        return FAQ_RESPONSES[result.faq_type]

    if result.intent == Intent.BOOKING:
        if result.requested_date is None or result.requested_time is None:
            return BOOKING_CLARIFICATION_RESPONSE
        weekday = result.requested_date.strftime("%A")
        appointment_time = _format_time(result.requested_time)
        return (
            "I understood that you'd like to book an appointment for "
            f"{weekday} at {appointment_time}."
        )

    if result.intent == Intent.AFFIRM:
        return AFFIRM_RESPONSE

    if result.intent == Intent.DECLINE:
        return DECLINE_RESPONSE

    return OTHER_RESPONSE
