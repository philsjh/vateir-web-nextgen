"""
Clean up training data after a legacy import.

  1. Mark scheduled sessions older than 4 weeks as COMPLETED.
  2. Create blank published reports for completed sessions missing a report.
  3. Mark any training request as COMPLETED where the student already
     holds the target rating (or higher).

Usage:
    python manage.py clean_training
    python manage.py clean_training --dry-run
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Complete stale sessions and graduate students who already hold the target rating"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview changes without writing to the database",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no changes will be made"))

        self._complete_stale_sessions(dry_run)
        self._close_outstanding_reports(dry_run)
        self._graduate_students(dry_run)

        self.stdout.write(self.style.SUCCESS("Done."))

    def _complete_stale_sessions(self, dry_run):
        """Mark scheduled sessions older than 4 weeks as COMPLETED."""
        from datetime import timedelta
        from django.utils import timezone
        from apps.training.models import TrainingSession, SessionStatus

        cutoff = timezone.now() - timedelta(weeks=4)
        stale = TrainingSession.objects.filter(
            status=SessionStatus.SCHEDULED,
            session_date__lt=cutoff,
        )
        count = stale.count()

        if not dry_run and count:
            # Use update() to skip the save() hook which touches training_request
            stale.update(status=SessionStatus.COMPLETED)

        self.stdout.write(f"  Sessions marked completed: {count}")

    def _close_outstanding_reports(self, dry_run):
        """Create blank published reports for completed sessions older than 4 weeks that have no report."""
        from datetime import timedelta
        from django.utils import timezone
        from apps.training.models import TrainingSession, SessionStatus, SessionReport

        cutoff = timezone.now() - timedelta(weeks=4)
        missing_report = TrainingSession.objects.filter(
            status=SessionStatus.COMPLETED,
            session_date__lt=cutoff,
        ).exclude(report__isnull=False)

        count = missing_report.count()

        if not dry_run and count:
            reports = [
                SessionReport(
                    session=session,
                    summary="",
                    is_published=True,
                )
                for session in missing_report
            ]
            SessionReport.objects.bulk_create(reports)

        self.stdout.write(f"  Blank reports created: {count}")

    def _graduate_students(self, dry_run):
        """
        For every active training request, if the student's current rating
        is >= the course's to_rating, mark the request as COMPLETED.
        """
        from apps.training.models import TrainingRequest, TrainingRequestStatus

        active_requests = TrainingRequest.objects.filter(
            status__in=[
                TrainingRequestStatus.WAITING,
                TrainingRequestStatus.ACCEPTED,
                TrainingRequestStatus.IN_PROGRESS,
            ],
            course__isnull=False,
        ).select_related("student", "course")

        graduated = 0
        for tr in active_requests:
            if tr.student.rating >= tr.course.to_rating:
                if not dry_run:
                    tr.status = TrainingRequestStatus.COMPLETED
                    tr.save(update_fields=["status"])
                graduated += 1
                self.stdout.write(
                    f"    {tr.student.vatsim_name} (CID {tr.student.cid}) — "
                    f"rating {tr.student.rating} >= {tr.course.to_rating} "
                    f"({tr.course.name}) → COMPLETED"
                )

        self.stdout.write(f"  Students graduated: {graduated}")
