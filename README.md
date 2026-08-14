# BrightCare Clinic Calendar Connectivity Test

This minimal milestone verifies that a Google service account can read upcoming
events from the clinic's Google Calendar. It does not implement booking logic,
Telegram, email, an LLM, or broader application architecture.

## Prerequisites

- Python 3.9 or newer
- A Google Cloud project with the Google Calendar API enabled
- A service account and its downloaded JSON credential file
- A Google Calendar shared with the service account's email address with at
  least permission to view event details

Keep the downloaded JSON file outside this repository. Never commit it.

## Set up

Create and activate a virtual environment in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install the dependencies:

```powershell
python -m pip install -r requirements.txt
```

Set the environment variables for the current PowerShell session. Replace both
placeholder values with your own calendar ID and absolute credential path:

```powershell
$env:GOOGLE_CALENDAR_ID = "your-calendar-id@group.calendar.google.com"
$env:GOOGLE_SERVICE_ACCOUNT_FILE = "C:\absolute\path\to\service-account.json"
```

The calendar ID is available in Google Calendar under **Settings and sharing**,
then **Integrate calendar**. The service account email is in the downloaded JSON
file under `client_email`; share the calendar with that email before testing.

`.env.example` documents the required variable names. The script reads the
process environment directly and does not automatically load `.env` files.

## Run the connectivity test

With the virtual environment active and both variables set:

```powershell
python calendar_test.py
```

On success, the script prints a connection message followed by up to five
upcoming events. An empty calendar is also a successful connection. Configuration
problems and Google API errors are written to standard error and return a nonzero
exit code.
