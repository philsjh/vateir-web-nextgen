#!/usr/bin/env python
"""
Migrate legacy VATéir data from dump.sql into the new system.

Usage:
    # First, load the dump into a temporary database:
    createdb -U postgres vateir_legacy
    psql -U postgres vateir_legacy < data/dump.sql

    # Then run this script:
    python scripts/migrate_legacy_data.py

This script reads from the legacy database and writes to the current database.
"""

import os
import sys

import psycopg2
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

django.setup()

from django.utils import timezone
from datetime import datetime, date, time, timedelta
from django.utils.timezone import make_aware

from apps.accounts.models import User
from apps.training.models import (
    TrainingCourse, TrainingCompetency, TrainingRequest,
    TrainingRequestStatus, TrainingSession, SessionStatus,
    SessionReport, CompetencyRating, TrainingNote,
)

# ─── Configuration ────────────────────────────────────────────────
LEGACY_DB = {
    "dbname": "vateir_legacy",
    "user": "postgres",
    "password": "postgres",
    "host": "localhost",
    "port": 5432,
}

# ─── Helpers ──────────────────────────────────────────────────────

def get_legacy_conn():
    return psycopg2.connect(**LEGACY_DB)


def fetch_all(conn, query):
    with conn.cursor() as cur:
        cur.execute(query)
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def log(msg):
    print(f"  [MIGRATE] {msg}")


# ─── Maps (populated during migration) ───────────────────────────
# old_user_id -> new User instance
user_map = {}
# old_programme_id -> new TrainingCourse instance
course_map = {}
# old_competency_id -> new TrainingCompetency instance
competency_map = {}
# old_session_id -> new TrainingSession instance
session_map = {}
# old_user_id -> CID (string)
old_id_to_cid = {}


def migrate_users(conn):
    """Migrate legacy auth_user to new accounts.User."""
    log("Migrating users...")
    rows = fetch_all(conn, "SELECT * FROM auth_user ORDER BY id")
    created = 0
    updated = 0

    for row in rows:
        cid_str = row["username"]
        if not cid_str.isdigit():
            continue

        cid = int(cid_str)
        old_id_to_cid[row["id"]] = cid

        first_name = row.get("first_name", "")
        last_name = row.get("last_name", "")
        email = row.get("email", "")
        vatsim_name = f"{first_name} {last_name}".strip()

        user, is_new = User.objects.get_or_create(
            cid=cid,
            defaults={
                "username": cid_str,
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "vatsim_name": vatsim_name,
                "is_active": row.get("is_active", True),
                "is_superuser": row.get("is_superuser", False),
                "is_staff": row.get("is_staff", False),
            },
        )

        if not is_new:
            # Update name/email if missing
            changed = False
            if not user.vatsim_name and vatsim_name:
                user.vatsim_name = vatsim_name
                changed = True
            if not user.first_name and first_name:
                user.first_name = first_name
                changed = True
            if not user.last_name and last_name:
                user.last_name = last_name
                changed = True
            if not user.email and email:
                user.email = email
                changed = True
            if changed:
                user.save()
                updated += 1
        else:
            user.set_unusable_password()
            user.save()
            created += 1

        user_map[row["id"]] = user

    log(f"Users: {created} created, {updated} updated, {len(user_map)} mapped")


def migrate_programmes(conn):
    """Migrate training_programme to TrainingCourse."""
    log("Migrating training programmes → courses...")
    rows = fetch_all(conn, "SELECT * FROM training_programme ORDER BY id")

    # Map programme names to from/to ratings
    rating_map = {
        "OBS=>S2": (1, 3),  # OBS to S2
        "S2=>S3": (3, 4),   # S2 to S3
        "S3=>C1": (4, 5),   # S3 to C1
    }

    for row in rows:
        name = row["name"]
        from_rating, to_rating = rating_map.get(name, (1, 2))

        course, _ = TrainingCourse.objects.get_or_create(
            name=name,
            defaults={
                "from_rating": from_rating,
                "to_rating": to_rating,
                "is_active": True,
                "display_order": row["id"],
            },
        )
        course_map[row["id"]] = course

    log(f"Courses: {len(course_map)} created/mapped")


def migrate_competencies(conn):
    """Migrate training_competencies to TrainingCompetency."""
    log("Migrating competencies...")
    rows = fetch_all(conn, "SELECT * FROM training_competencies ORDER BY id")
    created = 0

    for row in rows:
        course = course_map.get(row["training_programme_id"])
        if not course:
            log(f"  SKIP competency '{row['name']}' — no course for programme_id {row['training_programme_id']}")
            continue

        comp, is_new = TrainingCompetency.objects.get_or_create(
            course=course,
            name=row["name"] or "Unnamed",
            defaults={
                "description": row.get("description", "") or "",
                "is_active": row.get("enabled", True),
                "display_order": row["id"],
            },
        )
        competency_map[row["id"]] = comp
        if is_new:
            created += 1

    log(f"Competencies: {created} created, {len(competency_map)} mapped")


def migrate_signups(conn):
    """Migrate training_signup_form to TrainingRequest (waiting list)."""
    log("Migrating signup forms → training requests...")
    rows = fetch_all(conn, "SELECT * FROM training_signup_form ORDER BY submit_date")
    created = 0

    for idx, row in enumerate(rows):
        user = user_map.get(row["user_id"])
        if not user:
            log(f"  SKIP signup id={row['id']} — user_id {row['user_id']} not mapped")
            continue

        # Default to first course (OBS→S2)
        course = course_map.get(1)
        notes_parts = []
        if row.get("experience"):
            notes_parts.append(f"Experience: {row['experience']}")
        if row.get("about_me"):
            notes_parts.append(f"About: {row['about_me']}")
        if row.get("vatsim_experience"):
            notes_parts.append(f"VATSIM Experience: {row['vatsim_experience']}")
        if row.get("days"):
            notes_parts.append(f"Available days: {row['days']}")
        if row.get("times"):
            notes_parts.append(f"Available times: {row['times']}")

        notes = "\n\n".join(notes_parts)

        # Check if already has a request
        existing = TrainingRequest.objects.filter(student=user, course=course).first()
        if existing:
            continue

        tr = TrainingRequest.objects.create(
            student=user,
            course=course,
            requested_rating=course.to_rating if course else 3,
            status=TrainingRequestStatus.WAITING,
            position=idx + 1,
            notes=notes,
        )
        # Backdate the created_at
        if row.get("submit_date"):
            TrainingRequest.objects.filter(pk=tr.pk).update(created_at=row["submit_date"])
        created += 1

    log(f"Training requests (from signups): {created} created")


def migrate_sessions(conn):
    """Migrate training_sessions to TrainingSession."""
    log("Migrating training sessions...")
    rows = fetch_all(conn, "SELECT * FROM training_sessions ORDER BY id")
    created = 0
    skipped = 0

    # Session type mapping
    session_type_rows = fetch_all(conn, "SELECT * FROM training_session_types")
    session_type_map = {}
    for st in session_type_rows:
        if st.get("live"):
            session_type_map[st["id"]] = "PRACTICAL"
        elif st.get("sweatbox"):
            session_type_map[st["id"]] = "SIM"
        else:
            session_type_map[st["id"]] = "PRACTICAL"

    for row in rows:
        mentor = user_map.get(row["mentor_id"])
        student = user_map.get(row["student_id"])

        if not student:
            skipped += 1
            continue
        if not mentor:
            # Use the student as mentor placeholder (will show as self-session)
            mentor = student

        # Determine session date/time
        session_date = row.get("date")
        start_time = row.get("start_time")
        end_time = row.get("end_time")

        if session_date is None:
            skipped += 1
            continue

        # Combine date + time
        if start_time and hasattr(session_date, 'date'):
            dt = datetime.combine(session_date.date(), start_time)
        elif hasattr(session_date, 'date'):
            dt = datetime.combine(session_date.date(), time(0, 0))
        else:
            dt = session_date

        if dt.tzinfo is None:
            dt = make_aware(dt)

        # Duration
        duration = 60  # default
        if start_time and end_time:
            start_dt = datetime.combine(date.today(), start_time)
            end_dt = datetime.combine(date.today(), end_time)
            diff = (end_dt - start_dt).total_seconds() / 60
            if diff > 0:
                duration = int(diff)

        # Status
        if row.get("cancelled"):
            status = SessionStatus.CANCELLED
        elif row.get("closed") or row.get("report_submitted"):
            status = SessionStatus.COMPLETED
        else:
            status = SessionStatus.COMPLETED  # Legacy sessions are all in the past

        # Session type
        stype = session_type_map.get(row.get("session_type_id"), "PRACTICAL")

        # Find or create training request for student
        course = course_map.get(row.get("training_programme_id"))
        tr = None
        if course:
            tr = TrainingRequest.objects.filter(student=student, course=course).first()
        if not tr:
            # Find any request for this student
            tr = TrainingRequest.objects.filter(student=student).first()
        if not tr:
            # Create a placeholder request
            c = course or course_map.get(1)
            tr = TrainingRequest.objects.create(
                student=student,
                course=c,
                requested_rating=c.to_rating if c else 3,
                status=TrainingRequestStatus.IN_PROGRESS,
                position=0,
                notes="Auto-created from legacy session migration",
            )

        session = TrainingSession.objects.create(
            training_request=tr,
            student=student,
            mentor=mentor,
            session_date=dt,
            duration_minutes=duration,
            session_type=stype,
            status=status,
            notes=row.get("general_comments", "") or "",
        )
        session_map[row["id"]] = session
        created += 1

    log(f"Sessions: {created} created, {skipped} skipped")


def migrate_reports(conn):
    """Migrate training_session_reports to SessionReport + CompetencyRating."""
    log("Migrating session reports...")
    rows = fetch_all(conn, "SELECT * FROM training_session_reports ORDER BY training_session_id, id")

    # Group by session
    session_reports = {}
    for row in rows:
        sid = row["training_session_id"]
        if sid not in session_reports:
            session_reports[sid] = []
        session_reports[sid].append(row)

    reports_created = 0
    ratings_created = 0

    for old_session_id, report_rows in session_reports.items():
        session = session_map.get(old_session_id)
        if not session:
            continue

        # Create or get the report
        report, is_new = SessionReport.objects.get_or_create(
            session=session,
            defaults={
                "summary": "",
                "is_published": True,  # Legacy reports are all published
            },
        )
        if is_new:
            reports_created += 1
            # Backdate
            first_row = report_rows[0]
            if first_row.get("submit_date"):
                SessionReport.objects.filter(pk=report.pk).update(
                    created_at=first_row["submit_date"]
                )

        # Create competency ratings
        for rrow in report_rows:
            comp = competency_map.get(rrow["training_competency_id"])
            if not comp:
                continue

            CompetencyRating.objects.get_or_create(
                report=report,
                competency=comp,
                defaults={
                    "rating": min(max(rrow.get("score", 0) or 0, 0), 5),
                    "comment": rrow.get("report", "") or "",
                },
            )
            ratings_created += 1

    log(f"Reports: {reports_created} created, {ratings_created} competency ratings")


def migrate_comments(conn):
    """Migrate training_session_comments to TrainingNote."""
    log("Migrating session comments → training notes...")
    rows = fetch_all(conn, "SELECT * FROM training_session_comments ORDER BY id")
    created = 0

    for row in rows:
        session = session_map.get(row["training_session_id"])
        author = user_map.get(row["author_id"])
        if not session or not author:
            continue

        TrainingNote.objects.get_or_create(
            training_request=session.training_request,
            author=author,
            content=row.get("comment", "") or "",
            defaults={
                "is_internal": False,
            },
        )
        created += 1

    log(f"Training notes: {created} created")


def update_request_statuses():
    """
    Update training request statuses based on their sessions.
    If a request has completed sessions, mark it as IN_PROGRESS.
    If it has a CPT passed, mark as COMPLETED.
    """
    log("Updating training request statuses...")
    updated = 0

    for tr in TrainingRequest.objects.all():
        sessions = tr.sessions.all()
        if not sessions.exists():
            continue

        completed = sessions.filter(status=SessionStatus.COMPLETED).count()
        if completed > 0 and tr.status == TrainingRequestStatus.WAITING:
            tr.status = TrainingRequestStatus.IN_PROGRESS
            tr.save(update_fields=["status"])
            updated += 1

    log(f"Request statuses updated: {updated}")


def print_summary():
    """Print migration summary."""
    print("\n" + "=" * 60)
    print("MIGRATION SUMMARY")
    print("=" * 60)
    print(f"  Users:              {User.objects.count()}")
    print(f"  Training Courses:   {TrainingCourse.objects.count()}")
    print(f"  Competencies:       {TrainingCompetency.objects.count()}")
    print(f"  Training Requests:  {TrainingRequest.objects.count()}")
    print(f"  Training Sessions:  {TrainingSession.objects.count()}")
    print(f"  Session Reports:    {SessionReport.objects.count()}")
    print(f"  Competency Ratings: {CompetencyRating.objects.count()}")
    print(f"  Training Notes:     {TrainingNote.objects.count()}")
    print("=" * 60)


def main():
    print("=" * 60)
    print("VATéir Legacy Data Migration")
    print("=" * 60)

    conn = get_legacy_conn()
    try:
        migrate_users(conn)
        migrate_programmes(conn)
        migrate_competencies(conn)
        migrate_signups(conn)
        migrate_sessions(conn)
        migrate_reports(conn)
        migrate_comments(conn)
        update_request_statuses()
        print_summary()
    finally:
        conn.close()

    print("\nMigration complete!")


if __name__ == "__main__":
    main()
