# BrightCare Clinic Appointment Agent

BrightCare is a Telegram bot that answers a small set of clinic FAQs and books
30-minute appointments in Google Calendar. Gemini converts each message into a
validated structured intent; application code—not the model—applies business
hours, checks availability, manages the confirmation flow, creates the Calendar
event, and sends the confirmation email.

## Features

- Accepts appointment requests in natural language through Telegram.
- Answers fixed FAQs about location, hours, parking, walk-ins, and cancellation.
- Checks Google Calendar availability and suggests the next free slot on the
  same day when the requested time is busy.
- Re-checks availability immediately before inserting an event.
- Validates the patient's email address and sends a confirmation over SMTP.

## Prerequisites

- Python 3.10 or newer
- A Telegram bot token
- A Gemini API key and model name
- A Google Cloud service account with access to the clinic calendar
- An SMTP account that supports authenticated STARTTLS connections

## Installation

From the repository root, create a virtual environment and install the
dependencies. In PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Copy the environment template:

```powershell
Copy-Item .env.example .env
```

Then replace every placeholder in `.env` with the values prepared in the
integration setup below. The application loads this project-root `.env`
automatically and does not overwrite variables already present in the process
environment. Both `.env` and JSON credential files are ignored by Git; do not
commit either one.

## Integration setup

### Telegram

1. In Telegram, open `@BotFather` and run `/newbot`.
2. Follow the prompts to choose the bot's name and username.
3. Copy the token issued by BotFather into `TELEGRAM_BOT_TOKEN`.

The application uses long polling, so no public URL or Telegram webhook is
required for local development.

### Gemini

1. Create an API key in Google AI Studio for a project allowed to use the
   Gemini API.
2. Set `LLM_API_KEY` to that key.
3. Set `LLM_MODEL` to the Gemini model available to that project. The value in
   `.env.example` is the model this project was configured to use.

Gemini is used only for schema-constrained intent extraction. Automatic tool
calling is disabled, and the returned JSON is validated locally before any
booking action occurs.

### Google Calendar

1. Create or select a Google Cloud project and enable the Google Calendar API.
2. Create a service account and download a JSON key for it. Keep the file
   outside this repository.
3. In Google Calendar, open the target calendar's **Settings and sharing** and
   share it with the service account's `client_email`. Grant **Make changes to
   events** access because the bot reads availability and creates events.
4. Under **Integrate calendar**, copy the calendar ID into
   `GOOGLE_CALENDAR_ID`.
5. Put the absolute path to the downloaded key in
   `GOOGLE_SERVICE_ACCOUNT_FILE`. Forward slashes are convenient in a Windows
   `.env` file, for example `C:/keys/brightcare-service-account.json`.
6. Set `CLINIC_TIMEZONE` to an IANA timezone name such as `Asia/Kolkata`.

You can verify Calendar access without running Telegram:

```powershell
python calendar_test.py
python verify_calendar_availability.py "2026-08-17 14:00"
```

The first command lists up to five upcoming events. The second checks a slot
using the clinic-local `YYYY-MM-DD HH:MM` format. To test event creation, use the
interactive command below; it creates a real event only after a `y` confirmation:

```powershell
python verify_calendar_booking.py "2026-08-17 15:00" patient@example.com
```

### Confirmation email (SMTP)

Set the following values for an SMTP provider that supports STARTTLS:

```dotenv
EMAIL_SMTP_HOST="smtp.gmail.com"
EMAIL_SMTP_PORT="587"
EMAIL_SMTP_USERNAME="sender@example.com"
EMAIL_SMTP_PASSWORD="smtp-password-or-app-password"
EMAIL_FROM_ADDRESS="sender@example.com"
```

For Gmail, enable two-step verification and use an app password rather than the
normal account password. Other providers may require a provider-specific SMTP
password, and the from address must be one the authenticated account is allowed
to send as.

## Run the bot

With the virtual environment active and `.env` configured:

```powershell
python run_telegram_bot.py
```

The process logs that long polling has started. Open the bot in Telegram, send
`/start`, and try a message such as:

```text
Book an appointment next Monday at 2pm
```

Keep the process running while using the bot; press `Ctrl+C` to stop it.

To test Gemini intent extraction independently:

```powershell
python verify_intent.py "Book next Monday at 2pm"
```

To run the unit test suite (external services are replaced with test doubles):

```powershell
python -m unittest discover -s tests -v
```

## Design

The Telegram layer delegates free-form messages to Gemini and receives a strict
`IntentResult` containing only the intent and any extracted date, time, email,
or FAQ category. A deterministic workflow keyed by Telegram user ID then owns
all state transitions and side effects. Calendar availability, booking rules,
email validation, fixed FAQ answers, and SMTP delivery remain in ordinary Python
modules so the model cannot invent policy or directly operate an integration.

## Assumptions

- The clinic operates Monday through Friday, 9:00am–6:00pm, in one configured
  timezone.
- Every appointment lasts 30 minutes and starts on an hour or half-hour boundary.
- When a slot is busy, only later slots on the same day are considered.
- One service account and one Google Calendar represent the clinic schedule.
- A booking records the patient's email in the event description; it does not
  add the patient as a Calendar attendee. The separate SMTP message is the
  confirmation.
- Conversation state is local memory keyed by Telegram user ID. It is lost when
  the process restarts and is not shared across multiple bot instances.
- The bot is a local/single-process long-polling service. All integrations need
  outbound internet access.
- Calendar availability checking and event insertion are separate API calls.
  The final re-check narrows, but cannot eliminate, the concurrency race.
- Cancellation requests return clinic instructions; automated cancellation or
  rescheduling is outside the current scope.

## What I would improve with more time

- Store conversation and booking state in a durable database so restarts and
  multiple workers are safe.
- Add idempotency and a stronger reservation/locking strategy around Calendar
  writes to prevent duplicate or concurrent bookings.
- Deploy behind a Telegram webhook with health checks, structured telemetry,
  retry policies, and secret management instead of relying on a local process.
- Add automated cancellation and rescheduling flows, configurable clinic hours,
  holidays, appointment types, and multi-calendar/provider support.
- Reduce sensitive-data exposure in logs and event descriptions, define a data
  retention policy, and add user authorization and abuse controls.
- Add end-to-end integration tests in a sandbox calendar and mailbox, plus
  behavioral evaluations for ambiguous language and relative-date extraction.
