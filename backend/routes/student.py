from datetime import datetime, timezone
import json
from redis_client import redis_client
from redis.exceptions import RedisError
import os
from flask import request, session, current_app, send_file
from flask_restful import Resource
from model import db, User, Examination, Slot, Booking
from kombu.exceptions import OperationalError
from routes.worker import celery
from routes.tasks import export_examination_history


class StudentDashboard(Resource):

    def get(self):
        if "user_id" not in session:
            return ({"message": "Please log in."}, 401)
        current_user = User.query.filter_by(id=session["user_id"]).first()
        current_time = datetime.now(timezone.utc).replace(tzinfo=None)
        if current_user is None or current_user.status != "Active":
            session.clear()
            return ({"message": "Please log in with an active account."}, 401)
        if current_user.role != "Student":
            return ({"message": "Access denied."}, 403)
        if current_user.student is None:
            return ({"message": "Student profile not found."}, 401)
        bookings = Booking.query.filter(Booking.student_id == current_user.student.id).all()
        open_exams = Examination.query.filter(
            Examination.archived.is_(False),
            Examination.status == "Booking Open",
            Examination.booking_start <= current_time,
            Examination.booking_end > current_time,
        ).all()
        slots = Slot.query.filter(
            Slot.exam_id.in_([e.id for e in open_exams]),
            Slot.status == "Available",
            Slot.start > current_time,
        ).all()
        return {
            "counts": {
                "available_examinations": len(open_exams),
                "available_slots": sum(
                    (
                        s.examiner.user.status == "Active"
                        and sum((booking.status != "Cancelled" for booking in s.bookings))
                        < s.capacity
                        for s in slots
                    )
                ),
                "upcoming_examinations": sum(
                    (b.status == "Booked" and b.slot.start > current_time for b in bookings)
                ),
                "booked_slots": sum((b.status == "Booked" for b in bookings)),
                "published_results": sum(
                    (
                        b.status == "Completed" and b.slot.exam.published_at is not None
                        for b in bookings
                    )
                ),
            }
        }


class StudentBookings(Resource):

    def post(self):
        if "user_id" not in session:
            return ({"message": "Please log in."}, 401)
        db.session.execute(db.text("BEGIN IMMEDIATE"))
        current_user = User.query.filter_by(id=session["user_id"]).first()
        current_time = datetime.now(timezone.utc).replace(tzinfo=None)
        if current_user is None or current_user.status != "Active":
            session.clear()
            return ({"message": "Please log in with an active account."}, 401)
        if current_user.role != "Student":
            return ({"message": "Access denied."}, 403)
        if current_user.student is None:
            return ({"message": "Student profile not found."}, 401)
        data = request.get_json()
        if not isinstance(data, dict):
            return ({"message": "A JSON object is required."}, 400)
        slot_id = data.get("slot_id", "")
        if isinstance(slot_id, bool) or not isinstance(slot_id, int) or (not 1 <= slot_id <= 10000):
            return ({"message": "Invalid slot id."}, 400)
        slot = Slot.query.filter_by(id=slot_id).first_or_404()
        if (
            slot.exam.archived
            or slot.exam.course.status != "Active"
            or slot.exam.status != "Booking Open"
            or (not slot.exam.booking_start <= current_time < slot.exam.booking_end)
        ):
            return ({"message": "Student booking is closed or outside its configured period."}, 409)
        if (
            not slot.exam.rubrics
            or abs(sum((r.weightage for r in slot.exam.rubrics)) - 100) > 0.001
        ):
            return (
                {"message": "Add an evaluation rubric with weightages totaling 100% first."},
                409,
            )
        if (
            slot.examiner.user.status != "Active"
            or slot.status not in ("Available", "Full")
            or slot.start <= current_time
        ):
            return ({"message": "This examination slot is not available."}, 409)
        if Booking.query.filter(
            Booking.student_id == current_user.student.id,
            Booking.exam_id == slot.exam_id,
            Booking.status != "Cancelled",
        ).first():
            return ({"message": "You already have a booking for this examination."}, 409)
        if sum((booking.status != "Cancelled" for booking in slot.bookings)) >= slot.capacity:
            return ({"message": "This slot is full. Choose another slot."}, 409)
        overlap = Booking.query.join(Slot).filter(
            Booking.student_id == current_user.student.id,
            Booking.status != "Cancelled",
            Slot.start < slot.end,
            Slot.end > slot.start,
        )
        if overlap.first():
            return ({"message": "You already have a booking that overlaps this time."}, 409)
        booking = Booking(student_id=current_user.student.id, exam_id=slot.exam_id, slot=slot)
        db.session.add(booking)
        db.session.flush()
        if slot.status not in ("Cancelled", "Completed"):
            slot.status = (
                "Full"
                if sum((booking.status != "Cancelled" for booking in slot.bookings))
                >= slot.capacity
                else "Available"
            )
        db.session.commit()
        redis_client.delete("admin_dashboard")
        redis_client.delete(f"examination_slots_{slot.exam_id}")
        return (
            {
                "id": booking.id,
                "student_id": booking.student_id,
                "student": booking.student.name,
                "roll_number": booking.student.roll_number,
                "student_email": booking.student.user.email,
                "exam_id": booking.exam_id,
                "slot_id": booking.slot_id,
                "status": booking.status,
                "booked_at": booking.booked_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "completed_at": (
                    booking.completed_at.strftime("%Y-%m-%dT%H:%M:%SZ")
                    if booking.completed_at
                    else None
                ),
                "slot": {
                    "id": booking.slot.id,
                    "exam_id": booking.slot.exam_id,
                    "examination": booking.slot.exam.name,
                    "course": booking.slot.exam.course.name,
                    "examiner_id": booking.slot.examiner_id,
                    "examiner": booking.slot.examiner.name,
                    "start": booking.slot.start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "end": booking.slot.end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "capacity": booking.slot.capacity,
                    "booked": sum(
                        (booking.status != "Cancelled" for booking in booking.slot.bookings)
                    ),
                    "available_seats": max(
                        0,
                        booking.slot.capacity
                        - sum((booking.status != "Cancelled" for booking in booking.slot.bookings)),
                    ),
                    "status": booking.slot.status,
                    "meeting_link": booking.slot.meeting_link,
                    "location": booking.slot.location,
                    "booking_end": booking.slot.exam.booking_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "reschedule_history": booking.slot.reschedule_history,
                },
                "published": booking.slot.exam.published_at is not None,
                "maximum_marks": booking.slot.exam.maximum_marks,
                "reschedule_history": booking.reschedule_history,
                "evaluation": (
                    {
                        "id": booking.evaluation.id,
                        "total_marks": booking.evaluation.total_marks,
                        "remarks": booking.evaluation.remarks,
                        "evaluated_at": booking.evaluation.evaluated_at.strftime(
                            "%Y-%m-%dT%H:%M:%SZ"
                        ),
                        "examiner_id": booking.evaluation.examiner_id,
                        "scores": booking.evaluation.scores,
                    }
                    if booking.evaluation and booking.slot.exam.published_at
                    else None
                ),
            },
            201,
        )

    def get(self):
        if "user_id" not in session:
            return ({"message": "Please log in."}, 401)
        current_user = User.query.filter_by(id=session["user_id"]).first()
        if current_user is None or current_user.status != "Active":
            session.clear()
            return ({"message": "Please log in with an active account."}, 401)
        if current_user.role != "Student":
            return ({"message": "Access denied."}, 403)
        if current_user.student is None:
            return ({"message": "Student profile not found."}, 401)
        query = Booking.query.filter(Booking.student_id == current_user.student.id)
        if request.args.get("exam_id"):
            try:
                query = query.filter(Booking.exam_id == int(request.args["exam_id"]))
            except ValueError:
                return ({"message": "Invalid examination ID."}, 400)
        values = []
        for item in query.order_by(Booking.id.desc()):
            values.append(
                {
                    "id": item.id,
                    "student_id": item.student_id,
                    "student": item.student.name,
                    "roll_number": item.student.roll_number,
                    "student_email": item.student.user.email,
                    "exam_id": item.exam_id,
                    "slot_id": item.slot_id,
                    "status": item.status,
                    "booked_at": item.booked_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "completed_at": (
                        item.completed_at.strftime("%Y-%m-%dT%H:%M:%SZ")
                        if item.completed_at
                        else None
                    ),
                    "slot": {
                        "id": item.slot.id,
                        "exam_id": item.slot.exam_id,
                        "examination": item.slot.exam.name,
                        "course": item.slot.exam.course.name,
                        "examiner_id": item.slot.examiner_id,
                        "examiner": item.slot.examiner.name,
                        "start": item.slot.start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "end": item.slot.end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "capacity": item.slot.capacity,
                        "booked": sum(
                            (booking.status != "Cancelled" for booking in item.slot.bookings)
                        ),
                        "available_seats": max(
                            0,
                            item.slot.capacity
                            - sum(
                                (booking.status != "Cancelled" for booking in item.slot.bookings)
                            ),
                        ),
                        "status": item.slot.status,
                        "meeting_link": item.slot.meeting_link,
                        "location": item.slot.location,
                        "booking_end": item.slot.exam.booking_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "reschedule_history": item.slot.reschedule_history,
                    },
                    "published": item.slot.exam.published_at is not None,
                    "maximum_marks": item.slot.exam.maximum_marks,
                    "reschedule_history": item.reschedule_history,
                    "evaluation": (
                        {
                            "id": item.evaluation.id,
                            "total_marks": item.evaluation.total_marks,
                            "remarks": item.evaluation.remarks,
                            "evaluated_at": item.evaluation.evaluated_at.strftime(
                                "%Y-%m-%dT%H:%M:%SZ"
                            ),
                            "examiner_id": item.evaluation.examiner_id,
                            "scores": item.evaluation.scores,
                        }
                        if item.evaluation and item.slot.exam.published_at
                        else None
                    ),
                }
            )
        search = request.args.get("q", "").lower()
        return {
            "items": [
                item
                for item in values
                if not search
                or search
                in " ".join(
                    [
                        str(item["id"]),
                        item["student"],
                        item["roll_number"] or "",
                        item["slot"]["examination"],
                        item["slot"]["examiner"],
                    ]
                ).lower()
            ]
        }


class CancelBooking(Resource):

    def post(self, ident):
        if "user_id" not in session:
            return ({"message": "Please log in."}, 401)
        db.session.execute(db.text("BEGIN IMMEDIATE"))
        current_user = User.query.filter_by(id=session["user_id"]).first()
        current_time = datetime.now(timezone.utc).replace(tzinfo=None)
        if current_user is None or current_user.status != "Active":
            session.clear()
            return ({"message": "Please log in with an active account."}, 401)
        if current_user.role != "Student":
            return ({"message": "Access denied."}, 403)
        if current_user.student is None:
            return ({"message": "Student profile not found."}, 401)
        booking = Booking.query.filter_by(id=ident).first_or_404()
        if booking.student_id != current_user.student.id:
            return ({"message": "This booking does not belong to you."}, 403)
        if (
            booking.status != "Booked"
            or current_time >= booking.slot.exam.booking_end
            or current_time >= booking.slot.start
        ):
            return (
                {
                    "message": "Bookings can be cancelled only before the booking deadline and examination start."
                },
                409,
            )
        booking.status = "Cancelled"
        db.session.flush()
        if booking.slot.status not in ("Cancelled", "Completed"):
            booking.slot.status = (
                "Full"
                if sum((booking.status != "Cancelled" for booking in booking.slot.bookings))
                >= booking.slot.capacity
                else "Available"
            )
        db.session.commit()
        redis_client.delete(f"examination_slots_{booking.exam_id}")
        return {"message": "Booking cancelled. The seat is available again."}


class StudentHistory(Resource):

    def get(self):
        if "user_id" not in session:
            return ({"message": "Please log in."}, 401)
        current_user = User.query.filter_by(id=session["user_id"]).first()
        if current_user is None or current_user.status != "Active":
            session.clear()
            return ({"message": "Please log in with an active account."}, 401)
        if current_user.role != "Student":
            return ({"message": "Access denied."}, 403)
        if current_user.student is None:
            return ({"message": "Student profile not found."}, 401)
        query = Booking.query.filter(Booking.student_id == current_user.student.id)
        if request.args.get("exam_id"):
            try:
                query = query.filter(Booking.exam_id == int(request.args["exam_id"]))
            except ValueError:
                return ({"message": "Invalid examination ID."}, 400)
        values = []
        for item in query.order_by(Booking.id.desc()):
            values.append(
                {
                    "id": item.id,
                    "student_id": item.student_id,
                    "student": item.student.name,
                    "roll_number": item.student.roll_number,
                    "student_email": item.student.user.email,
                    "exam_id": item.exam_id,
                    "slot_id": item.slot_id,
                    "status": item.status,
                    "booked_at": item.booked_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "completed_at": (
                        item.completed_at.strftime("%Y-%m-%dT%H:%M:%SZ")
                        if item.completed_at
                        else None
                    ),
                    "slot": {
                        "id": item.slot.id,
                        "exam_id": item.slot.exam_id,
                        "examination": item.slot.exam.name,
                        "course": item.slot.exam.course.name,
                        "examiner_id": item.slot.examiner_id,
                        "examiner": item.slot.examiner.name,
                        "start": item.slot.start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "end": item.slot.end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "capacity": item.slot.capacity,
                        "booked": sum(
                            (booking.status != "Cancelled" for booking in item.slot.bookings)
                        ),
                        "available_seats": max(
                            0,
                            item.slot.capacity
                            - sum(
                                (booking.status != "Cancelled" for booking in item.slot.bookings)
                            ),
                        ),
                        "status": item.slot.status,
                        "meeting_link": item.slot.meeting_link,
                        "location": item.slot.location,
                        "booking_end": item.slot.exam.booking_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "reschedule_history": item.slot.reschedule_history,
                    },
                    "published": item.slot.exam.published_at is not None,
                    "maximum_marks": item.slot.exam.maximum_marks,
                    "reschedule_history": item.reschedule_history,
                    "evaluation": (
                        {
                            "id": item.evaluation.id,
                            "total_marks": item.evaluation.total_marks,
                            "remarks": item.evaluation.remarks,
                            "evaluated_at": item.evaluation.evaluated_at.strftime(
                                "%Y-%m-%dT%H:%M:%SZ"
                            ),
                            "examiner_id": item.evaluation.examiner_id,
                            "scores": item.evaluation.scores,
                        }
                        if item.evaluation and item.slot.exam.published_at
                        else None
                    ),
                }
            )
        search = request.args.get("q", "").lower()
        return {
            "items": [
                item
                for item in values
                if not search
                or search
                in " ".join(
                    [
                        str(item["id"]),
                        item["student"],
                        item["roll_number"] or "",
                        item["slot"]["examination"],
                        item["slot"]["examiner"],
                    ]
                ).lower()
            ]
        }


class StudentExports(Resource):

    def post(self):
        if "user_id" not in session:
            return ({"message": "Please log in."}, 401)
        db.session.execute(db.text("BEGIN IMMEDIATE"))
        current_user = User.query.filter_by(id=session["user_id"]).first()
        if current_user is None or current_user.status != "Active":
            session.clear()
            return ({"message": "Please log in with an active account."}, 401)
        if current_user.role != "Student":
            return ({"message": "Access denied."}, 403)
        if current_user.student is None:
            return ({"message": "Student profile not found."}, 401)
        profile = current_user.student
        try:
            task = export_examination_history.delay(profile.id)
        except (OperationalError, RedisError, OSError):
            current_app.logger.exception("Unable to queue the CSV export.")
            return ({"message": "The CSV job could not be queued. Please retry."}, 503)
        profile.export_task_id = task.id
        db.session.commit()
        return ({"id": task.id, "status": "Queued"}, 202)

    def get(self):
        if "user_id" not in session:
            return ({"message": "Please log in."}, 401)
        current_user = User.query.filter_by(id=session["user_id"]).first()
        if current_user is None or current_user.status != "Active":
            session.clear()
            return ({"message": "Please log in with an active account."}, 401)
        if current_user.role != "Student":
            return ({"message": "Access denied."}, 403)
        if current_user.student is None:
            return ({"message": "Student profile not found."}, 401)
        profile = current_user.student
        if not profile.export_task_id:
            return {"items": []}
        try:
            state = celery.AsyncResult(profile.export_task_id).state
        except (RedisError, OSError):
            current_app.logger.exception("Unable to read the CSV job status.")
            return ({"message": "The CSV job status is unavailable. Please retry."}, 503)
        status = "Queued"
        error = None
        if state == "SUCCESS":
            status = "Completed"
        elif state in ("FAILURE", "REVOKED"):
            status = "Failed"
            error = "CSV export failed. Check the worker terminal and retry."
        return {"items": [{"id": profile.export_task_id, "status": status, "error": error}]}


class DownloadHistory(Resource):

    def get(self, ident):
        if "user_id" not in session:
            return ({"message": "Please log in."}, 401)
        current_user = User.query.filter_by(id=session["user_id"]).first()
        if current_user is None or current_user.status != "Active":
            session.clear()
            return ({"message": "Please log in with an active account."}, 401)
        if current_user.role != "Student":
            return ({"message": "Access denied."}, 403)
        if current_user.student is None:
            return ({"message": "Student profile not found."}, 401)
        profile = current_user.student
        if profile.export_task_id != ident:
            return ({"message": "This export does not belong to you."}, 403)
        try:
            ready = celery.AsyncResult(ident).successful()
        except (RedisError, OSError):
            current_app.logger.exception("Unable to read the CSV job status.")
            return ({"message": "The CSV job status is unavailable. Please retry."}, 503)
        if not ready:
            return ({"message": "This export is not ready. Check its status and try again."}, 409)
        path = os.path.join(
            current_app.instance_path, "exports", f"Examination_History_{profile.id}_{ident}.csv"
        )
        if not os.path.isfile(path):
            return ({"message": "The export file is missing. Request a new export."}, 409)
        return send_file(
            path,
            as_attachment=True,
            download_name="Exortal-examination-history.csv",
            mimetype="text/csv",
        )


class AvailableExaminations(Resource):

    def get(self):
        if "user_id" not in session:
            return ({"message": "Please log in."}, 401)
        current_user = User.query.filter_by(id=session["user_id"]).first()
        if current_user is None or current_user.status != "Active":
            session.clear()
            return ({"message": "Please log in with an active account."}, 401)
        if current_user.role not in ["Admin", "Examiner", "Student"]:
            return ({"message": "Access denied."}, 403)
        if current_user.role == "Student" and current_user.student is None:
            return ({"message": "Student profile not found."}, 401)
        if current_user.role == "Examiner" and current_user.examiner is None:
            return ({"message": "Examiner profile not found."}, 401)
        query = Examination.query.order_by(Examination.id.desc())
        if current_user.role == "Student":
            query = query.filter(Examination.archived.is_(False), Examination.status != "Draft")
        elif current_user.role == "Examiner":
            query = query.filter(Examination.examiners.any(id=current_user.examiner.id))
        if request.args.get("q"):
            query = query.filter(Examination.name.ilike(f"%{request.args['q']}%"))
        exams = query.all()
        items = []
        for exam in exams:
            cached = redis_client.get(f"examination_{exam.id}")
            if cached:
                items.append(json.loads(cached))
                continue
            data = {
                "id": exam.id,
                "course_id": exam.course_id,
                "course": exam.course.name,
                "course_code": exam.course.code,
                "name": exam.name,
                "exam_type": exam.exam_type,
                "duration": exam.duration,
                "maximum_marks": exam.maximum_marks,
                "status": exam.status,
                "instructions": exam.instructions,
                "archived": exam.archived,
                "slot_creation_start": exam.slot_creation_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "slot_creation_end": exam.slot_creation_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "booking_start": exam.booking_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "booking_end": exam.booking_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "published_at": (
                    exam.published_at.strftime("%Y-%m-%dT%H:%M:%SZ")
                    if exam.published_at
                    else None
                ),
                "examiners": [
                    {
                        "id": user.id,
                        "user_id": user.user_id,
                        "name": user.name,
                        "department": user.department,
                        "phone": user.phone,
                        "email": user.user.email,
                        "status": user.user.status,
                    }
                    for user in exam.examiners
                ],
                "rubrics": [
                    {
                        "id": rubric.id,
                        "name": rubric.name,
                        "maximum_marks": rubric.maximum_marks,
                        "weightage": rubric.weightage,
                        "description": rubric.description,
                    }
                    for rubric in exam.rubrics
                ],
            }
            redis_client.setex(f"examination_{exam.id}", 120, json.dumps(data))
            items.append(data)
        return {"items": items}


class ExaminationSlots(Resource):

    def get(self, exam_id):
        if "user_id" not in session:
            return ({"message": "Please log in."}, 401)
        current_user = User.query.filter_by(id=session["user_id"]).first()
        if current_user is None or current_user.status != "Active":
            session.clear()
            return ({"message": "Please log in with an active account."}, 401)
        if current_user.role not in ["Admin", "Examiner", "Student"]:
            return ({"message": "Access denied."}, 403)
        if current_user.role == "Student" and current_user.student is None:
            return ({"message": "Student profile not found."}, 401)
        if current_user.role == "Examiner" and current_user.examiner is None:
            return ({"message": "Examiner profile not found."}, 401)
        exam = Examination.query.filter_by(id=exam_id).first_or_404()
        if current_user.role == "Examiner" and current_user.examiner not in exam.examiners:
            return ({"message": "You are not assigned to this examination."}, 403)
        if current_user.role == "Student" and (exam.archived or exam.status == "Draft"):
            return ({"message": "This examination is not available."}, 403)
        cached = redis_client.get(f"examination_slots_{exam_id}")
        if cached:
            return {"items": json.loads(cached)}, 200
        slots = Slot.query.filter_by(exam_id=exam_id).order_by(Slot.start).all()
        items = []
        for slot in slots:
            items.append(
                {
                    "id": slot.id,
                    "exam_id": slot.exam_id,
                    "examination": slot.exam.name,
                    "course": slot.exam.course.name,
                    "examiner_id": slot.examiner_id,
                    "examiner": slot.examiner.name,
                    "start": slot.start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "end": slot.end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "capacity": slot.capacity,
                    "booked": sum((booking.status != "Cancelled" for booking in slot.bookings)),
                    "available_seats": max(
                        0,
                        slot.capacity
                        - sum((booking.status != "Cancelled" for booking in slot.bookings)),
                    ),
                    "status": slot.status,
                    "meeting_link": slot.meeting_link,
                    "location": slot.location,
                    "booking_end": slot.exam.booking_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "reschedule_history": slot.reschedule_history,
                }
            )
        redis_client.setex(f"examination_slots_{exam_id}", 120, json.dumps(items))
        return {"items": items}


class ExaminationRubrics(Resource):

    def get(self, exam_id):
        if "user_id" not in session:
            return ({"message": "Please log in."}, 401)
        current_user = User.query.filter_by(id=session["user_id"]).first()
        if current_user is None or current_user.status != "Active":
            session.clear()
            return ({"message": "Please log in with an active account."}, 401)
        if current_user.role not in ["Admin", "Examiner", "Student"]:
            return ({"message": "Access denied."}, 403)
        if current_user.role == "Student" and current_user.student is None:
            return ({"message": "Student profile not found."}, 401)
        if current_user.role == "Examiner" and current_user.examiner is None:
            return ({"message": "Examiner profile not found."}, 401)
        exam = Examination.query.filter_by(id=exam_id).first_or_404()
        if current_user.role == "Examiner" and current_user.examiner not in exam.examiners:
            return ({"message": "This examination is not assigned to you."}, 403)
        if current_user.role == "Student" and (exam.archived or exam.status == "Draft"):
            return ({"message": "This examination is not available."}, 403)
        cached = redis_client.get(f"examination_rubrics_{exam_id}")
        if cached:
            return {"items": json.loads(cached)}, 200
        items = []
        for rubric in exam.rubrics:
            items.append(
                {
                    "id": rubric.id,
                    "name": rubric.name,
                    "maximum_marks": rubric.maximum_marks,
                    "weightage": rubric.weightage,
                    "description": rubric.description,
                }
            )
        redis_client.setex(f"examination_rubrics_{exam_id}", 120, json.dumps(items))
        return {"items": items}
