# 0020. Crash reports: always local, sent only through an issue you review

**Status:** Accepted, 2026-10-08

## Context
Once Marginalia runs as an app with no terminal, an uncaught exception or a crash in Qt or
`ctypes` leaves no trace. The roadmap asked for opt-in crash reporting. The app sees your
screen and your questions, so anything that leaves the machine must be minimal and visible.

## Decision
- `crash.CrashReporter.install()` hooks `sys.excepthook` and `threading.excepthook` (Qt slot
  exceptions arrive at `sys.excepthook` too) and turns on `faulthandler` into
  `<log dir>/crashes/fatal.log` for fatal signals. `main` installs it as soon as the config is read.
- Every uncaught error becomes a JSON report in `<log dir>/crashes/`: version, OS, Python and
  Qt versions, where, the traceback, and the last 40 lines of the JSON log (metrics only; ADR
  0014 keeps question and answer text out of logs). A fatal dump is turned into a report on the
  next launch.
- **Sending is opt-in** (Settings: "Offer to report crashes", off by default). When on, the
  next launch shows the latest unsent report and offers **Report…**, which opens a GitHub
  issue **pre-filled in your browser**. You read and edit it, and nothing leaves until you press
  Submit there. "Not now" stops asking about those reports.

## Consequences
- No crash service, no account, no DSN, no third party processing data, nothing to audit but
  a URL. Reports reach the maintainer only through someone choosing to file them.
- GitHub caps URL length, so the issue carries at most ~6000 characters; the rest is in the local
  file, which the notice can open.
- The repository is private today, so only collaborators can file issues; that's fine for now and
  changes by itself when it is made public.

## Alternatives considered
- **Sentry (or similar).** Automatic and aggregated, which matters at scale; but a third party
  receiving tracebacks from a screen-reading app, an account and a DSN baked into builds, and a
  dependency, for an app with a handful of users. Revisit with real users.
- **Email the report.** Needs a mail client configured, and shows less than an issue.
- **Upload automatically when opted in.** Opt-in once is not consent to every future report's
  contents; a reviewed issue is.
