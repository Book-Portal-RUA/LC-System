# GEP Student Assessment System

A Django rebuild of the General English Program's Excel-based student
tracking workbook: students, scores, attendance, midterm/final exams,
computed grade records, printable report cards, and a reusable comment
bank — as a proper multi-user, database-backed system instead of a
spreadsheet.

## Tech stack

Django 5.1 + Django templates + Bootstrap 5 + HTMX, SQLite for local dev,
Django's built-in auth, WeasyPrint for PDF report cards. No separate
frontend build step, no REST API layer.

## Setup

```bash
python -m venv venv && source venv/bin/activate   # optional but recommended
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo_data
python manage.py runserver
```

Then open `http://127.0.0.1:8000/`.

### System dependencies (for PDF export)

WeasyPrint needs Pango, Cairo and GDK-PixBuf on the machine that *runs* the
app (not just at `pip install` time). On Debian/Ubuntu:

```bash
apt-get install -y libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 \
    libcairo2 libffi-dev shared-mime-info fonts-liberation fonts-dejavu-core
```

Student and teacher names can include Khmer script. To render Khmer
correctly in exported PDFs, also install a Khmer-capable font, e.g.:

```bash
apt-get install -y fonts-khmeros
```

(The on-screen web UI doesn't need this — it loads Noto Sans Khmer from
Google Fonts in the browser. It only matters for server-side PDF export.)

On macOS: `brew install pango cairo gdk-pixbuf` (Khmer text will generally
render if any Khmer-capable font is installed system-wide, e.g. via
`brew install --cask font-noto-sans-khmer`).

## Login

The seed command creates:

| Role    | Username      | Password       |
|---------|---------------|----------------|
| Admin   | `admin`       | `admin12345`   |
| Teacher | `tom.peterson`| `teacher12345` |

**Change these before deploying anywhere beyond your own machine.**

## Verifying this against your original workbook

The seed command loads the real Term 1 / Level 1 roster and scores from
your workbook (Kim Lihour, Kong Seila, Koe Pheara, Jet Chanda — including
their actual quiz/homework/CP/assignment/attendance/exam numbers), not
placeholder data. Open Score Record after seeding and you should see:

| Student     | Total | Grade | Final Result |
|-------------|-------|-------|--------------|
| Kim Lihour  | 100.0 | A+    | Promotion    |
| Kong Seila  | 60.8  | D-    | Promotion    |
| Jet Chanda  | 56.2  | F     | Make Up      |
| Koe Pheara  | 49.5  | F     | Repetition   |

These match the original spreadsheet's computed values to the decimal —
a direct check that the grading engine is a faithful port, not a
reinterpretation. Run `python manage.py test` to re-verify this (and
permission scoping, and every page's status code) automatically any time
you change the code — it uses Django's isolated test database, so it never
touches your real data.

## Key design decisions worth knowing about

A few things were resolved by reading the actual numbers in your workbook
rather than guessing, since the written grading legend didn't spell out
every edge case:

- **Attendance %** is calculated against a fixed "planned class days" number
  per class+term (`ClassGroup.total_class_days`, editable from the Classes
  admin page), not against however many days happen to be recorded so far.
  A day with no attendance taken yet is treated as fully present. This
  matches the original: with only 2 of 10 planned days marked, the sheet's
  attendance % was still computed out of 10, not out of 2.
- **Absence penalty weighting**: a full Absence costs a full day, an Excused
  absence costs half a day, and a Tardy costs a quarter-day, all against
  that fixed planned-days total. This is reverse-engineered from your
  workbook's real numbers (e.g. 1 Absent + 1 Excused out of 10 planned days
  → 85%, not 80% or 90%) and is implemented in `gep/grading.py`.
- **Ungraded items don't count as zero.** A Quiz/Homework/CP/Assignment item
  with no score entered yet for a student is excluded from that student's
  average rather than treated as a 0 — so a partially-graded gradebook
  doesn't unfairly tank anyone's percentage. An explicitly entered `0` does
  count, exactly as in the original sheet.
- **Quiz/CP/Homework/Assignment weights live in the database**
  (`ScoreCategory.weight_percent`), editable from Django admin, while
  Attendance/Midterm/Final weights (10/30/35) are fixed constants in
  `grading.py` since they aren't backed by their own category row in the
  data model.
- **Score Record, Report Card, and Final Result are computed on every
  request** from Score/AttendanceRecord/ExamResult rows — nothing is
  cached or stored, so a grade can never drift out of sync with what's
  actually been entered. If you have enough data that this becomes slow,
  the natural next step is a cached snapshot rebuilt by a signal or a
  management command, not a change to the formulas themselves.
- **HTMX is used for**: inline score-cell editing (Quiz/CP/HW/Assignment
  grids), click-to-cycle attendance marking, live student search, Comment
  Bank category filtering, and class switching. The class switcher works by
  re-requesting the *current* page with a new `?class_id=`, then using
  `hx-select` to swap in just the `#page-content` region — so it doesn't
  need a dedicated endpoint per page.
- **A class can have more than one teacher** (`TeacherAssignment` is a
  many-to-many join table), per the spec's open assumption. Tighten this to
  one-per-class if you'd rather, in `gep/models.py`.
- **Student ID and Teacher ID are auto-sequential** (`0001`, `0002`, ... and
  `TLC001`, `TLC002`, ...) and not exposed as editable form fields.
- The original workbook's "OR" sheet (a combined Level 1 + Level 2 rollup)
  was left out, per the spec — it was mostly unused in the source data.
  If you need it later, it would be a cross-term aggregation view built on
  top of `compute_class_ranking()` in `gep/grading.py`, not a new table.

## Project structure

```
config/            Django project settings/urls
gep/
  models.py        All data models
  grading.py        Grading engine (weights, formulas, ranking) — computed, not stored
  mixins.py         ClassScopedViewMixin / class_scoped — enforces Teacher/Admin data isolation
  forms.py          ModelForms (auto-Bootstrap-styled)
  views.py          All page views
  urls.py           All routes
  admin.py          Django admin registrations for every model
  tests.py          Automated tests incl. grading-accuracy checks against the source workbook
  management/commands/seed_demo_data.py   Seeds real Term 1/Level 1 data + full Comment Bank
  templates/gep/    All page templates + HTMX partials (files prefixed with _)
  static/gep/css/   Custom design tokens layered on Bootstrap
```

## Production notes

This ships with development-friendly defaults: `DEBUG` is on by default in
`config/settings.py`, `ALLOWED_HOSTS = ['*']`, and a hardcoded
`SECRET_KEY`. Before deploying anywhere reachable by others: set `DEBUG =
False`, set `ALLOWED_HOSTS` to your real domain, move `SECRET_KEY` to an
environment variable, run `python manage.py collectstatic`, and put it
behind a real web server (gunicorn/uwsgi + nginx) rather than
`runserver`. Swapping SQLite for PostgreSQL needs no code changes — just
update `DATABASES` in `config/settings.py`, since the ORM usage here is
database-agnostic throughout.
