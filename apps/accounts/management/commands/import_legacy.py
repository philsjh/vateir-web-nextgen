"""
Import data from the legacy VATéir database into the new schema.

Usage:
    python manage.py import_legacy                     # uses data/dump.sql
    python manage.py import_legacy --dump /path/to.sql # custom path
    python manage.py import_legacy --dry-run            # preview only

The command:
  1. Loads dump.sql into a temporary 'vateir_legacy' database
  2. Reads legacy tables and transforms data into the new schema
  3. Creates/updates records in the current database
"""

import subprocess
from datetime import datetime, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connections, connection
from django.utils import timezone


LEGACY_DB_NAME = "vateir_legacy"


class Command(BaseCommand):
    help = "Import legacy VATéir database dump into the new schema"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dump",
            default="data/dump.sql",
            help="Path to the legacy SQL dump file (default: data/dump.sql)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview what would be imported without writing to the database",
        )
        parser.add_argument(
            "--skip-load",
            action="store_true",
            help="Skip loading the dump (use existing vateir_legacy database)",
        )

    def handle(self, *args, **options):
        self.dry_run = options["dry_run"]
        dump_path = options["dump"]

        if self.dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no changes will be made"))

        # Step 1: Load dump into legacy database
        if not options["skip_load"]:
            self._load_dump(dump_path)

        # Step 2: Connect and import
        self._add_legacy_db()
        try:
            self._import_users()
            self._import_training_programmes()
            self._import_competencies()
            self._import_session_types()
            self._import_sessions()
            self._import_session_reports()
            self._import_session_comments()
            self._import_availability()
            self._import_signup_forms()
        finally:
            self._remove_legacy_db()

        self._clean_up_graduated_students()
        self.stdout.write(self.style.SUCCESS("Import complete."))

    # ── Database setup ──────────────────────────────────────────────

    def _get_db_params(self):
        """Extract connection params from the default database config."""
        db = settings.DATABASES["default"]
        return {
            "host": db.get("HOST", "localhost"),
            "port": str(db.get("PORT", 5432)),
            "user": db.get("USER", "postgres"),
        }

    def _load_dump(self, dump_path):
        """Create legacy database and load the SQL dump."""
        params = self._get_db_params()
        env_args = ["-h", params["host"], "-p", params["port"], "-U", params["user"]]

        self.stdout.write(f"Creating database '{LEGACY_DB_NAME}'...")
        # Drop if exists, then create
        subprocess.run(
            ["dropdb", *env_args, "--if-exists", LEGACY_DB_NAME],
            capture_output=True,
        )
        result = subprocess.run(
            ["createdb", *env_args, LEGACY_DB_NAME],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise CommandError(f"Failed to create database: {result.stderr}")

        self.stdout.write(f"Loading dump from {dump_path}...")
        result = subprocess.run(
            ["psql", *env_args, "-d", LEGACY_DB_NAME, "-f", dump_path, "-q"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            # psql may return warnings but still load — only fail on real errors
            if "FATAL" in result.stderr or "could not" in result.stderr:
                raise CommandError(f"Failed to load dump: {result.stderr}")

        self.stdout.write(self.style.SUCCESS("Dump loaded."))

    def _add_legacy_db(self):
        """Add legacy database to Django's connections at runtime."""
        db_config = settings.DATABASES["default"].copy()
        db_config["NAME"] = LEGACY_DB_NAME
        connections.databases["legacy"] = db_config

    def _remove_legacy_db(self):
        """Clean up the runtime connection."""
        if "legacy" in connections.databases:
            try:
                connections["legacy"].close()
            except Exception:
                pass

    def _legacy_cursor(self):
        return connections["legacy"].cursor()

    def _fetch_all(self, query):
        """Execute query on legacy DB and return list of dicts."""
        cursor = self._legacy_cursor()
        cursor.execute(query)
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    # ── Import functions ────────────────────────────────────────────

    def _import_users(self):
        """Import legacy auth_user → accounts.User (CID from username)."""
        from apps.accounts.models import User

        rows = self._fetch_all("SELECT * FROM auth_user")
        created = updated = 0

        for row in rows:
            cid = int(row["username"])
            defaults = {
                "vatsim_name": f"{row['first_name']} {row['last_name']}".strip(),
                "email": row["email"] or "",
                "is_active": row["is_active"],
                "is_superuser": row["is_superuser"],
                "is_staff": row["is_staff"],
            }

            if self.dry_run:
                created += 1
                continue

            user, was_created = User.objects.update_or_create(
                cid=cid,
                defaults={
                    **defaults,
                    "username": str(cid),
                },
            )
            if was_created:
                # Preserve the original date_joined
                User.objects.filter(pk=user.pk).update(date_joined=row["date_joined"])
                created += 1
            else:
                updated += 1

        self.stdout.write(f"  Users: {created} created, {updated} updated")

    def _import_training_programmes(self):
        """Import legacy training_programme → TrainingCourse."""
        from apps.training.models import TrainingCourse

        rows = self._fetch_all("SELECT * FROM training_programme")
        self._programme_map = {}  # legacy id → new course
        created = 0

        for row in rows:
            if self.dry_run:
                self._programme_map[row["id"]] = None
                created += 1
                continue

            course, was_created = TrainingCourse.objects.get_or_create(
                name=row["name"],
                defaults={
                    "from_rating": 1,
                    "to_rating": 2,
                    "description": "",
                    "is_active": True,
                    "display_order": row["id"],
                },
            )
            self._programme_map[row["id"]] = course
            if was_created:
                created += 1

        self.stdout.write(f"  Training Courses: {created} created")

    def _import_competencies(self):
        """Import legacy training_competencies → TrainingCompetency."""
        from apps.training.models import TrainingCompetency

        rows = self._fetch_all("SELECT * FROM training_competencies")
        self._competency_map = {}
        created = 0

        for row in rows:
            course = self._programme_map.get(row["training_programme_id"])
            if self.dry_run or not course:
                self._competency_map[row["id"]] = None
                created += 1
                continue

            comp, was_created = TrainingCompetency.objects.get_or_create(
                course=course,
                name=row["name"] or "Unnamed",
                defaults={
                    "description": row["description"] or "",
                    "is_active": row["enabled"],
                    "display_order": row["id"],
                },
            )
            self._competency_map[row["id"]] = comp
            if was_created:
                created += 1

        self.stdout.write(f"  Competencies: {created} created")

    def _import_session_types(self):
        """Build mapping from legacy session_type ids to new SessionType choices."""
        from apps.training.models import SessionType

        rows = self._fetch_all("SELECT * FROM training_session_types")
        self._session_type_map = {}

        for row in rows:
            name = (row["name"] or "").upper().strip()
            if "CPT" in name or "PRACTICAL TEST" in name:
                mapped = SessionType.CPT
            elif "OTS" in name or "SHOULDER" in name:
                mapped = SessionType.OTS
            elif "SIM" in name or "SWEATBOX" in name:
                mapped = SessionType.SIM
            elif "THEORY" in name:
                mapped = SessionType.THEORY
            else:
                mapped = SessionType.PRACTICAL
            self._session_type_map[row["id"]] = mapped

        self.stdout.write(f"  Session Types: {len(self._session_type_map)} mapped")

    def _import_sessions(self):
        """Import legacy training_sessions → TrainingSession."""
        from apps.accounts.models import User
        from apps.training.models import TrainingSession, SessionStatus

        rows = self._fetch_all("SELECT * FROM training_sessions ORDER BY id")
        self._session_map = {}  # legacy id → new session
        created = skipped = 0

        # Build CID lookup from legacy user ids
        legacy_users = self._fetch_all("SELECT id, username FROM auth_user")
        legacy_user_cid = {u["id"]: int(u["username"]) for u in legacy_users}

        for row in rows:
            student_cid = legacy_user_cid.get(row["student_id"])
            mentor_cid = legacy_user_cid.get(row["mentor_id"])
            if not student_cid or not mentor_cid:
                skipped += 1
                continue

            if self.dry_run:
                self._session_map[row["id"]] = None
                created += 1
                continue

            try:
                student = User.objects.get(cid=student_cid)
                mentor = User.objects.get(cid=mentor_cid)
            except User.DoesNotExist:
                skipped += 1
                continue

            # Determine status
            one_month_ago = timezone.now() - timedelta(days=30)
            if row["cancelled"]:
                status = SessionStatus.CANCELLED
            elif row["closed"] or row["report_submitted"]:
                status = SessionStatus.COMPLETED
            else:
                # Auto-complete old scheduled sessions (older than 1 month)
                session_dt = row["date"]
                if session_dt and timezone.is_naive(session_dt):
                    session_dt = timezone.make_aware(session_dt, timezone.UTC)
                if session_dt and session_dt < one_month_ago:
                    status = SessionStatus.COMPLETED
                else:
                    status = SessionStatus.SCHEDULED

            # Build session datetime
            session_date = row["date"]
            if session_date and row["start_time"]:
                session_date = datetime.combine(session_date.date(), row["start_time"])
                session_date = timezone.make_aware(session_date, timezone.UTC)
            elif session_date:
                if timezone.is_naive(session_date):
                    session_date = timezone.make_aware(session_date, timezone.UTC)

            if not session_date:
                skipped += 1
                continue

            # Duration from start/end time
            duration = 0
            if row["start_time"] and row["end_time"]:
                start_dt = datetime.combine(datetime.today(), row["start_time"])
                end_dt = datetime.combine(datetime.today(), row["end_time"])
                if end_dt > start_dt:
                    duration = int((end_dt - start_dt).total_seconds() / 60)

            # Map session type
            session_type = self._session_type_map.get(row["session_type_id"], "PRACTICAL")

            # Find training request if programme is linked
            training_request = None
            course = self._programme_map.get(row["training_programme_id"])
            if course:
                from apps.training.models import TrainingRequest
                training_request = TrainingRequest.objects.filter(
                    student=student, course=course
                ).first()
                if not training_request:
                    # Create one
                    training_request = TrainingRequest.objects.create(
                        student=student,
                        course=course,
                        requested_rating=course.to_rating,
                        status="COMPLETED" if status == SessionStatus.COMPLETED else "IN_PROGRESS",
                        notes="Imported from legacy system",
                    )

            session = TrainingSession.objects.create(
                training_request=training_request,
                is_adhoc=training_request is None,
                student=student,
                mentor=mentor,
                session_date=session_date,
                duration_minutes=duration,
                session_type=session_type,
                status=status,
                notes=row["general_comments"] or "",
            )
            self._session_map[row["id"]] = session
            created += 1

        self.stdout.write(f"  Sessions: {created} created, {skipped} skipped")

    def _import_session_reports(self):
        """Import legacy training_session_reports → CompetencyRating (grouped into SessionReport)."""
        from apps.training.models import SessionReport, CompetencyRating

        rows = self._fetch_all("SELECT * FROM training_session_reports ORDER BY training_session_id, id")
        reports_created = ratings_created = skipped = 0

        for row in rows:
            session = self._session_map.get(row["training_session_id"])
            competency = self._competency_map.get(row["training_competency_id"])
            if self.dry_run:
                ratings_created += 1
                continue
            if not session or not competency:
                skipped += 1
                continue

            # Get or create the report for this session
            report, was_created = SessionReport.objects.get_or_create(
                session=session,
                defaults={
                    "summary": "",
                    "is_published": True,
                },
            )
            if was_created:
                reports_created += 1

            # Clamp score to 0-5
            score = row["score"] or 0
            score = max(0, min(5, score))

            CompetencyRating.objects.get_or_create(
                report=report,
                competency=competency,
                defaults={
                    "rating": score,
                    "comment": row["report"] or "",
                },
            )
            ratings_created += 1

        self.stdout.write(f"  Reports: {reports_created} created, Ratings: {ratings_created}, {skipped} skipped")

    def _import_session_comments(self):
        """Import legacy training_session_comments → TrainingNote."""
        from apps.accounts.models import User
        from apps.training.models import TrainingNote

        rows = self._fetch_all("SELECT * FROM training_session_comments")
        legacy_users = self._fetch_all("SELECT id, username FROM auth_user")
        legacy_user_cid = {u["id"]: int(u["username"]) for u in legacy_users}
        created = skipped = 0

        for row in rows:
            session = self._session_map.get(row["training_session_id"])
            author_cid = legacy_user_cid.get(row["author_id"])

            if self.dry_run:
                created += 1
                continue
            if not session or not author_cid or not session.training_request:
                skipped += 1
                continue

            try:
                author = User.objects.get(cid=author_cid)
            except User.DoesNotExist:
                skipped += 1
                continue

            TrainingNote.objects.get_or_create(
                training_request=session.training_request,
                author=author,
                content=row["comment"] or "",
                defaults={
                    "is_internal": True,
                },
            )
            created += 1

        self.stdout.write(f"  Notes: {created} created, {skipped} skipped")

    def _import_availability(self):
        """Import legacy training_availability → TrainingAvailability."""
        from apps.accounts.models import User
        from apps.training.models import TrainingAvailability

        rows = self._fetch_all("SELECT * FROM training_availability")
        legacy_users = self._fetch_all("SELECT id, username FROM auth_user")
        legacy_user_cid = {u["id"]: int(u["username"]) for u in legacy_users}
        created = skipped = 0

        for row in rows:
            user_cid = legacy_user_cid.get(row["user_id"])
            if self.dry_run:
                created += 1
                continue
            if not user_cid or not row["date"] or not row["start_time"] or not row["end_time"]:
                skipped += 1
                continue

            try:
                student = User.objects.get(cid=user_cid)
            except User.DoesNotExist:
                skipped += 1
                continue

            TrainingAvailability.objects.get_or_create(
                student=student,
                date=row["date"],
                start_time=row["start_time"],
                end_time=row["end_time"],
                defaults={
                    "notes": row["comments"] or "",
                    "is_booked": row["accepted"],
                },
            )
            created += 1

        self.stdout.write(f"  Availability: {created} created, {skipped} skipped")

    def _import_signup_forms(self):
        """Import legacy training_signup_form → TrainingRequest (waiting list)."""
        from apps.accounts.models import User
        from apps.training.models import TrainingRequest

        rows = self._fetch_all("SELECT * FROM training_signup_form ORDER BY submit_date")
        legacy_users = self._fetch_all("SELECT id, username FROM auth_user")
        legacy_user_cid = {u["id"]: int(u["username"]) for u in legacy_users}
        created = skipped = 0

        for row in rows:
            user_cid = legacy_user_cid.get(row["user_id"])
            if self.dry_run:
                created += 1
                continue
            if not user_cid:
                skipped += 1
                continue

            try:
                student = User.objects.get(cid=user_cid)
            except User.DoesNotExist:
                skipped += 1
                continue

            # Don't duplicate if they already have a request from session import
            if TrainingRequest.objects.filter(student=student).exists():
                skipped += 1
                continue

            notes_parts = []
            if row["experience"]:
                notes_parts.append(f"Experience: {row['experience']}")
            if row["about_me"]:
                notes_parts.append(f"About: {row['about_me']}")
            if row["vatsim_experience"]:
                notes_parts.append(f"VATSIM Experience: {row['vatsim_experience']}")
            if row["days"]:
                notes_parts.append(f"Available Days: {row['days']}")
            if row["times"]:
                notes_parts.append(f"Available Times: {row['times']}")

            TrainingRequest.objects.create(
                student=student,
                requested_rating=2,  # Default to S1, can be updated manually
                status="WAITING",
                position=created,
                notes="\n".join(notes_parts),
            )
            created += 1

        self.stdout.write(f"  Signup Forms → Training Requests: {created} created, {skipped} skipped")

    def _clean_up_graduated_students(self):
        """
        Remove students from training programmes if they already hold
        the target rating. Marks their request as COMPLETED.

        Course name matching (case-insensitive):
          - Contains 'S2' target → student needs rating < 3
          - Contains 'S3' target → student needs rating < 5
          - Contains 'C1' target → student needs rating < 7
        """
        from apps.training.models import TrainingRequest, TrainingCourse

        if self.dry_run:
            self.stdout.write("  Graduated cleanup: skipped (dry run)")
            return

        # Map course name patterns to the minimum rating that means "graduated"
        # VATSIM ratings: 1=OBS, 2=S1, 3=S2, 4=S3, 5=C1, 7=C3
        graduated_rules = []
        for course in TrainingCourse.objects.all():
            name = course.name.upper()
            # Use to_rating: if student already has it, they've graduated
            min_rating = course.to_rating
            if min_rating > 1:
                graduated_rules.append((course, min_rating))

        removed = 0
        for course, min_rating in graduated_rules:
            requests = TrainingRequest.objects.filter(
                course=course,
                student__rating__gte=min_rating,
            ).exclude(status="COMPLETED")

            count = requests.count()
            if count:
                requests.update(status="COMPLETED")
                removed += count

        self.stdout.write(f"  Graduated cleanup: {removed} students marked as COMPLETED")
