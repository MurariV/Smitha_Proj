from redis_client import redis_client
from datetime import datetime, timezone
from flask import request, session
from flask_restful import Resource
from model import db, User, Examination, Slot, Booking, Evaluation


class ExaminerDashboard(Resource):

    def get(self):
        if "user_id" not in session:
            return ({"message": "Please log in."}, 401)
        current_user = User.query.filter_by(id=session["user_id"]).first()
        current_time = datetime.now(timezone.utc).replace(tzinfo=None)
        if current_user is None or current_user.status != "Active":
            session.clear()
            return ({"message": "Please log in with an active account."}, 401)
        if current_user.role != "Examiner":
            return ({"message": "Access denied."}, 403)
        if current_user.examiner is None:
            return ({"message": "Examiner profile not found."}, 401)
        exams = Examination.query.filter(
            Examination.examiners.any(id=current_user.examiner.id)
        ).all()
        slots = Slot.query.filter(Slot.examiner_id == current_user.examiner.id).all()
        bookings = (
            Booking.query.join(Slot)
            .filter(Slot.examiner_id == current_user.examiner.id, Booking.status != "Cancelled")
            .all()
        )
        return {
            "counts": {
                "assigned_examinations": len(exams),
                "created_slots": len(slots),
                "booked_students": len(bookings),
                "pending_evaluations": sum(
                    (b.status == "Booked" and b.slot.start <= current_time for b in bookings)
                ),
            }
        }


class ExaminerSlots(Resource):

    def get(self):
        if "user_id" not in session:
            return ({"message": "Please log in."}, 401)
        current_user = User.query.filter_by(id=session["user_id"]).first()
        if current_user is None or current_user.status != "Active":
            session.clear()
            return ({"message": "Please log in with an active account."}, 401)
        if current_user.role != "Examiner":
            return ({"message": "Access denied."}, 403)
        if current_user.examiner is None:
            return ({"message": "Examiner profile not found."}, 401)
        items = []
        for s in Slot.query.filter(Slot.examiner_id == current_user.examiner.id).order_by(
            Slot.start
        ):
            items.append(
                {
                    "id": s.id,
                    "exam_id": s.exam_id,
                    "examination": s.exam.name,
                    "course": s.exam.course.name,
                    "examiner_id": s.examiner_id,
                    "examiner": s.examiner.name,
                    "start": s.start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "end": s.end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "capacity": s.capacity,
                    "booked": sum((booking.status != "Cancelled" for booking in s.bookings)),
                    "available_seats": max(
                        0,
                        s.capacity - sum((booking.status != "Cancelled" for booking in s.bookings)),
                    ),
                    "status": s.status,
                    "meeting_link": s.meeting_link,
                    "location": s.location,
                    "booking_end": s.exam.booking_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "reschedule_history": s.reschedule_history,
                }
            )
        return {"items": items}

    def post(self):
        if "user_id" not in session:
            return ({"message": "Please log in."}, 401)
        db.session.execute(db.text("BEGIN IMMEDIATE"))
        current_user = User.query.filter_by(id=session["user_id"]).first()
        current_time = datetime.now(timezone.utc).replace(tzinfo=None)
        if current_user is None or current_user.status != "Active":
            session.clear()
            return ({"message": "Please log in with an active account."}, 401)
        if current_user.role != "Examiner":
            return ({"message": "Access denied."}, 403)
        if current_user.examiner is None:
            return ({"message": "Examiner profile not found."}, 401)
        data = request.get_json()
        if not isinstance(data, dict):
            return ({"message": "A JSON object is required."}, 400)
        exam_id = data.get("exam_id", "")
        if isinstance(exam_id, bool) or not isinstance(exam_id, int) or (not 1 <= exam_id <= 10000):
            return ({"message": "Invalid exam id."}, 400)
        exam = Examination.query.filter_by(id=exam_id).first_or_404()
        if current_user.examiner not in exam.examiners:
            return ({"message": "You are not assigned to this examination."}, 403)
        if (
            exam.archived
            or exam.course.status != "Active"
            or exam.status != "Slot Creation"
            or (not exam.slot_creation_start <= current_time < exam.slot_creation_end)
        ):
            return (
                {"message": "Examiner slot creation is closed or outside its configured period."},
                409,
            )
        slot = Slot(exam=exam, examiner_id=current_user.examiner.id)
        start = data.get("start", "")
        try:
            start = datetime.fromisoformat(start.replace("Z", "+00:00"))
            if start.tzinfo is None:
                raise ValueError()
            start = start.astimezone(timezone.utc).replace(tzinfo=None)
        except (AttributeError, TypeError, ValueError):
            return ({"message": "Invalid start date and time."}, 400)
        end = data.get("end", "")
        try:
            end = datetime.fromisoformat(end.replace("Z", "+00:00"))
            if end.tzinfo is None:
                raise ValueError()
            end = end.astimezone(timezone.utc).replace(tzinfo=None)
        except (AttributeError, TypeError, ValueError):
            return ({"message": "Invalid end date and time."}, 400)
        if (
            start <= current_time
            or start < slot.exam.booking_end
            or (end - start).total_seconds() != slot.exam.duration * 60
        ):
            return (
                {
                    "message": "Slot must be in the future, after booking closes, and match the examination duration."
                },
                400,
            )
        examiner_conflict = Slot.query.filter(
            Slot.examiner_id == current_user.examiner.id,
            Slot.status != "Cancelled",
            Slot.start < end,
            Slot.end > start,
        )
        if examiner_conflict.first():
            return ({"message": "This examiner already has an overlapping examination slot."}, 409)
        slot.start, slot.end = (start, end)
        capacity = data.get("capacity", "")
        if (
            isinstance(capacity, bool)
            or not isinstance(capacity, int)
            or (not 1 <= capacity <= 500)
        ):
            return ({"message": "Invalid capacity."}, 400)
        slot.capacity = capacity
        location = data.get("location", "")
        if not isinstance(location, str) or len(location.strip()) > 200:
            return ({"message": "Invalid location."}, 400)
        location = location.strip()
        slot.location = location
        meeting_link = data.get("meeting_link", "")
        if not isinstance(meeting_link, str) or len(meeting_link.strip()) > 500:
            return ({"message": "Invalid meeting link."}, 400)
        meeting_link = meeting_link.strip()
        slot.meeting_link = meeting_link
        if slot.meeting_link and (not slot.meeting_link.startswith(("https://", "http://"))):
            return ({"message": "Use an http:// or https:// meeting link."}, 400)
        db.session.add(slot)
        db.session.flush()
        db.session.commit()
        redis_client.delete("admin_dashboard")
        redis_client.delete(f"examination_slots_{slot.exam_id}")
        return (
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
            },
            201,
        )


class ExaminerSlotDetails(Resource):

    def put(self, ident):
        if "user_id" not in session:
            return ({"message": "Please log in."}, 401)
        db.session.execute(db.text("BEGIN IMMEDIATE"))
        current_user = User.query.filter_by(id=session["user_id"]).first()
        current_time = datetime.now(timezone.utc).replace(tzinfo=None)
        if current_user is None or current_user.status != "Active":
            session.clear()
            return ({"message": "Please log in with an active account."}, 401)
        if current_user.role != "Examiner":
            return ({"message": "Access denied."}, 403)
        if current_user.examiner is None:
            return ({"message": "Examiner profile not found."}, 401)
        slot = Slot.query.filter_by(id=ident).first_or_404()
        if slot.examiner_id != current_user.examiner.id:
            return ({"message": "You can manage only your own examination slots."}, 403)
        if (
            slot.exam.archived
            or slot.exam.course.status != "Active"
            or slot.exam.status != "Slot Creation"
            or (not slot.exam.slot_creation_start <= current_time < slot.exam.slot_creation_end)
        ):
            return (
                {"message": "Examiner slot creation is closed or outside its configured period."},
                409,
            )
        if (
            current_time >= slot.exam.booking_start
            or slot.bookings
            or slot.status in ("Cancelled", "Completed")
        ):
            return (
                {
                    "message": "Slots can be changed only before student booking starts and before any booking is made."
                },
                409,
            )
        data = request.get_json()
        if not isinstance(data, dict):
            return ({"message": "A JSON object is required."}, 400)
        start = data.get("start", "")
        try:
            start = datetime.fromisoformat(start.replace("Z", "+00:00"))
            if start.tzinfo is None:
                raise ValueError()
            start = start.astimezone(timezone.utc).replace(tzinfo=None)
        except (AttributeError, TypeError, ValueError):
            return ({"message": "Invalid start date and time."}, 400)
        end = data.get("end", "")
        try:
            end = datetime.fromisoformat(end.replace("Z", "+00:00"))
            if end.tzinfo is None:
                raise ValueError()
            end = end.astimezone(timezone.utc).replace(tzinfo=None)
        except (AttributeError, TypeError, ValueError):
            return ({"message": "Invalid end date and time."}, 400)
        if (
            start <= current_time
            or start < slot.exam.booking_end
            or (end - start).total_seconds() != slot.exam.duration * 60
        ):
            return (
                {
                    "message": "Slot must be in the future, after booking closes, and match the examination duration."
                },
                400,
            )
        examiner_conflict = Slot.query.filter(
            Slot.examiner_id == current_user.examiner.id,
            Slot.status != "Cancelled",
            Slot.start < end,
            Slot.end > start,
        )
        if slot.id:
            examiner_conflict = examiner_conflict.filter(Slot.id != slot.id)
        if examiner_conflict.first():
            return ({"message": "This examiner already has an overlapping examination slot."}, 409)
        slot.start, slot.end = (start, end)
        capacity = data.get("capacity", "")
        if (
            isinstance(capacity, bool)
            or not isinstance(capacity, int)
            or (not 1 <= capacity <= 500)
        ):
            return ({"message": "Invalid capacity."}, 400)
        slot.capacity = capacity
        location = data.get("location", "")
        if not isinstance(location, str) or len(location.strip()) > 200:
            return ({"message": "Invalid location."}, 400)
        location = location.strip()
        slot.location = location
        meeting_link = data.get("meeting_link", "")
        if not isinstance(meeting_link, str) or len(meeting_link.strip()) > 500:
            return ({"message": "Invalid meeting link."}, 400)
        meeting_link = meeting_link.strip()
        slot.meeting_link = meeting_link
        if slot.meeting_link and (not slot.meeting_link.startswith(("https://", "http://"))):
            return ({"message": "Use an http:// or https:// meeting link."}, 400)
        db.session.commit()
        redis_client.delete(f"examination_slots_{slot.exam_id}")
        return {"message": "Slot updated."}

    def delete(self, ident):
        if "user_id" not in session:
            return ({"message": "Please log in."}, 401)
        db.session.execute(db.text("BEGIN IMMEDIATE"))
        current_user = User.query.filter_by(id=session["user_id"]).first()
        current_time = datetime.now(timezone.utc).replace(tzinfo=None)
        if current_user is None or current_user.status != "Active":
            session.clear()
            return ({"message": "Please log in with an active account."}, 401)
        if current_user.role != "Examiner":
            return ({"message": "Access denied."}, 403)
        if current_user.examiner is None:
            return ({"message": "Examiner profile not found."}, 401)
        slot = Slot.query.filter_by(id=ident).first_or_404()
        if slot.examiner_id != current_user.examiner.id:
            return ({"message": "You can manage only your own examination slots."}, 403)
        if (
            slot.exam.archived
            or slot.exam.course.status != "Active"
            or slot.exam.status != "Slot Creation"
            or (not slot.exam.slot_creation_start <= current_time < slot.exam.slot_creation_end)
        ):
            return (
                {"message": "Examiner slot creation is closed or outside its configured period."},
                409,
            )
        if (
            current_time >= slot.exam.booking_start
            or slot.bookings
            or slot.status in ("Cancelled", "Completed")
        ):
            return (
                {
                    "message": "Slots can be changed only before student booking starts and before any booking is made."
                },
                409,
            )
        slot.status = "Cancelled"
        db.session.commit()
        redis_client.delete(f"examination_slots_{slot.exam_id}")
        return {"message": "Slot updated."}


class ExaminerBookings(Resource):

    def get(self):
        if "user_id" not in session:
            return ({"message": "Please log in."}, 401)
        current_user = User.query.filter_by(id=session["user_id"]).first()
        if current_user is None or current_user.status != "Active":
            session.clear()
            return ({"message": "Please log in with an active account."}, 401)
        if current_user.role != "Examiner":
            return ({"message": "Access denied."}, 403)
        if current_user.examiner is None:
            return ({"message": "Examiner profile not found."}, 401)
        query = Booking.query.join(Slot).filter(Slot.examiner_id == current_user.examiner.id)
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
                        if item.evaluation
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


class EvaluateStudent(Resource):

    def post(self, ident):
        if "user_id" not in session:
            return ({"message": "Please log in."}, 401)
        db.session.execute(db.text("BEGIN IMMEDIATE"))
        current_user = User.query.filter_by(id=session["user_id"]).first()
        current_time = datetime.now(timezone.utc).replace(tzinfo=None)
        if current_user is None or current_user.status != "Active":
            session.clear()
            return ({"message": "Please log in with an active account."}, 401)
        if current_user.role != "Examiner":
            return ({"message": "Access denied."}, 403)
        if current_user.examiner is None:
            return ({"message": "Examiner profile not found."}, 401)
        data = request.get_json()
        if not isinstance(data, dict):
            return ({"message": "A JSON object is required."}, 400)
        booking = Booking.query.filter_by(id=ident).first_or_404()
        if booking.slot.examiner_id != current_user.examiner.id:
            return ({"message": "You may evaluate only students booked into your own slots."}, 403)
        if (
            booking.status != "Booked"
            or booking.evaluation
            or booking.slot.status in ("Cancelled", "Completed")
        ):
            return (
                {"message": "This booking cannot be evaluated or has already been submitted."},
                409,
            )
        if booking.slot.start > current_time:
            return ({"message": "Evaluation can begin only when the examination slot starts."}, 409)
        exam = booking.slot.exam
        if exam.published_at:
            return ({"message": "Published results are immutable."}, 409)
        if not exam.rubrics or abs(sum((r.weightage for r in exam.rubrics)) - 100) > 0.001:
            return (
                {"message": "Add an evaluation rubric with weightages totaling 100% first."},
                409,
            )
        scores = data.get("scores")
        if not isinstance(scores, list) or any((not isinstance(s, dict) for s in scores)):
            return ({"message": "Scores must contain one mark for every rubric criterion."}, 400)
        ids = []
        for score in scores:
            rubric_id = score.get("rubric_id", "")
            if (
                isinstance(rubric_id, bool)
                or not isinstance(rubric_id, int)
                or (not 1 <= rubric_id <= 10000)
            ):
                return ({"message": "Invalid rubric id."}, 400)
            ids.append(rubric_id)
        if len(ids) != len(set(ids)) or set(ids) != {r.id for r in exam.rubrics}:
            return ({"message": "Submit each rubric criterion exactly once."}, 400)
        remarks = data.get("remarks", "")
        if not isinstance(remarks, str) or len(remarks.strip()) > 5000:
            return ({"message": "Invalid remarks."}, 400)
        remarks = remarks.strip()
        evaluation = Evaluation(
            booking=booking, examiner_id=current_user.examiner.id, remarks=remarks, total_marks=0
        )
        criteria = {r.id: r for r in exam.rubrics}
        total = 0
        awarded = []
        for score in scores:
            criterion = criteria[score["rubric_id"]]
            marks = score.get("marks", "")
            if (
                isinstance(marks, bool)
                or not isinstance(marks, (int, float))
                or (not 0 <= marks <= criterion.maximum_marks)
            ):
                return ({"message": "Invalid marks."}, 400)
            awarded.append(
                {
                    "rubric_id": criterion.id,
                    "criterion": criterion.name,
                    "marks": marks,
                    "maximum_marks": criterion.maximum_marks,
                    "weightage": criterion.weightage,
                }
            )
            total += (
                marks / criterion.maximum_marks * criterion.weightage / 100 * exam.maximum_marks
            )
        evaluation.total_marks = round(total, 2)
        evaluation.scores = awarded
        booking.status, booking.completed_at = ("Completed", current_time)
        db.session.add(evaluation)
        db.session.commit()
        return ({"message": "Evaluation submitted.", "total_marks": evaluation.total_marks}, 201)


class CompleteSlot(Resource):

    def post(self, ident):
        if "user_id" not in session:
            return ({"message": "Please log in."}, 401)
        db.session.execute(db.text("BEGIN IMMEDIATE"))
        current_user = User.query.filter_by(id=session["user_id"]).first()
        current_time = datetime.now(timezone.utc).replace(tzinfo=None)
        if current_user is None or current_user.status != "Active":
            session.clear()
            return ({"message": "Please log in with an active account."}, 401)
        if current_user.role != "Examiner":
            return ({"message": "Access denied."}, 403)
        if current_user.examiner is None:
            return ({"message": "Examiner profile not found."}, 401)
        slot = Slot.query.filter_by(id=ident).first_or_404()
        if slot.examiner_id != current_user.examiner.id:
            return ({"message": "You can manage only your own examination slots."}, 403)
        if slot.start > current_time or slot.status in ("Cancelled", "Completed"):
            return ({"message": "Only started, active slots may be marked complete."}, 409)
        if any((b.status == "Booked" for b in slot.bookings)):
            return ({"message": "Evaluate all booked students before completing this slot."}, 409)
        slot.status = "Completed"
        db.session.flush()
        remaining = Slot.query.filter(
            Slot.exam_id == slot.exam_id, Slot.status.not_in(["Completed", "Cancelled"])
        ).count()
        if not remaining and current_time >= slot.exam.booking_end:
            slot.exam.status = "Completed"
        db.session.commit()
        redis_client.delete(f"examination_{slot.exam_id}")
        redis_client.delete(f"examination_slots_{slot.exam_id}")
        return {"message": "Slot marked complete."}
