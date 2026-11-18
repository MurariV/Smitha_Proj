import csv
import os
from datetime import datetime, timedelta, timezone
from model import Student, Booking, Evaluation, Slot, User
from routes.worker import celery
from routes.mail import send_email
from routes.extensions import create_task_app

app = create_task_app()


@celery.task
def send_monthly_report():
    with app.app_context():
        india = timezone(timedelta(hours=5, minutes=30))
        end = datetime.now(india).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start = (end - timedelta(days=1)).replace(day=1)
        month = start.strftime("%B %Y")
        start = start.astimezone(timezone.utc).replace(tzinfo=None)
        end = end.astimezone(timezone.utc).replace(tzinfo=None)

        evaluations = Evaluation.query.filter(
            Evaluation.evaluated_at >= start, Evaluation.evaluated_at < end
        ).all()
        workload = {}
        for evaluation in evaluations:
            name = evaluation.examiner.name
            workload[name] = workload.get(name, 0) + 1

        report = {
            "month": month,
            "examinations_conducted": Slot.query.filter(
                Slot.start >= start, Slot.start < end, Slot.status == "Completed"
            )
            .with_entities(Slot.exam_id)
            .distinct()
            .count(),
            "students_evaluated": len({item.booking.student_id for item in evaluations}),
            "completed_bookings": Booking.query.filter(
                Booking.completed_at >= start,
                Booking.completed_at < end,
                Booking.status == "Completed",
            ).count(),
            "pending_evaluations": Booking.query.join(Slot)
            .filter(Booking.status == "Booked", Slot.start < end)
            .count(),
            "examiner_workload": [
                {"name": name, "evaluations": count}
                for name, count in sorted(workload.items(), key=lambda item: -item[1])
            ],
        }
        admin = User.query.filter_by(role="Admin").first()
        if admin is None:
            raise ValueError("Run app.py once to create the Admin before sending reports.")
        send_email(
            receiver=admin.email,
            subject=f"Exortal | Examination report - {month}",
            template_name="monthly_report.html",
            report=report,
        )
    return "Monthly Report Sent"


@celery.task
def daily_reminders():
    with app.app_context():
        india = timezone(timedelta(hours=5, minutes=30))
        current = datetime.now(timezone.utc).replace(tzinfo=None)
        end = datetime.now(india).replace(hour=0, minute=0, second=0, microsecond=0)
        end = (end + timedelta(days=2)).astimezone(timezone.utc).replace(tzinfo=None)
        bookings = (
            Booking.query.join(Slot)
            .filter(
                Booking.status == "Booked",
                Slot.status.not_in(["Cancelled", "Completed"]),
                Slot.start >= current,
                Slot.start < end,
            )
            .all()
        )
        for booking in bookings:
            scheduled = booking.slot.start.replace(tzinfo=timezone.utc).astimezone(india)
            send_email(
                receiver=booking.student.user.email,
                subject=f"Exortal | Reminder: {booking.slot.exam.name}",
                template_name="reminder.html",
                student_name=booking.student.name,
                examination_name=booking.slot.exam.name,
                examiner_name=booking.slot.examiner.name,
                duration=booking.slot.exam.duration,
                location=booking.slot.location,
                meeting_link=booking.slot.meeting_link,
                instructions=booking.slot.exam.instructions,
                scheduled=scheduled.strftime("%d %B %Y, %I:%M %p"),
            )
    return "Reminder Emails Sent"


@celery.task
def export_examination_history(student_id):
    with app.app_context():
        student = Student.query.filter_by(id=student_id).first()
        if student is None:
            raise ValueError("Student not found.")

        bookings = Booking.query.filter_by(student_id=student_id).order_by(Booking.id).all()
        folder = os.path.join(app.instance_path, "exports")
        os.makedirs(folder, exist_ok=True)
        filename = f"Examination_History_{student_id}_{export_examination_history.request.id}.csv"
        india = timezone(timedelta(hours=5, minutes=30))

        with open(os.path.join(folder, filename), "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow(
                [
                    "Student ID",
                    "Examination Name",
                    "Course",
                    "Examination Date",
                    "Examiner",
                    "Marks Obtained",
                    "Booking Status",
                ]
            )
            for booking in bookings:
                date = booking.slot.start.replace(tzinfo=timezone.utc).astimezone(india)
                marks = ""
                if booking.slot.exam.published_at and booking.evaluation:
                    marks = booking.evaluation.total_marks
                row = [
                    student.id,
                    booking.slot.exam.name,
                    booking.slot.exam.course.name,
                    date.strftime("%Y-%m-%d %H:%M"),
                    booking.slot.examiner.name,
                    marks,
                    booking.status,
                ]
                # Prevent names entered by users from becoming spreadsheet formulas.
                writer.writerow(
                    [
                        (
                            "'" + value
                            if isinstance(value, str)
                            and value.lstrip().startswith(("=", "+", "-", "@"))
                            else value
                        )
                        for value in row
                    ]
                )
    return filename
