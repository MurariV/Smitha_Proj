from kombu.exceptions import OperationalError
from redis_client import redis_client
from redis.exceptions import RedisError
from datetime import timedelta
import json
import re
from datetime import datetime, timezone
from flask import request, session, current_app
from flask_restful import Resource
from werkzeug.security import generate_password_hash
from model import (
    db,
    User,
    Student,
    Examiner,
    Course,
    Examination,
    Rubric,
    Slot,
    Booking,
    Evaluation,
)

EXAM_TYPES = ("Viva", "Practical", "Project Demo", "Assessment")
EXAM_STATUSES = ("Draft", "Slot Creation", "Booking Open", "Closed", "Completed")


class AdminDashboard(Resource):

    def get(self):
        if "user_id" not in session:
            return ({"message": "Please log in."}, 401)
        current_user = User.query.filter_by(id=session["user_id"]).first()
        if current_user is None or current_user.status != "Active":
            session.clear()
            return ({"message": "Please log in with an active account."}, 401)
        if current_user.role != "Admin":
            return ({"message": "Access denied."}, 403)
        cached = redis_client.get("admin_dashboard")
        if cached:
            return json.loads(cached), 200
        counts = {
            "courses": Course.query.count(),
            "examinations": Examination.query.count(),
            "students": Student.query.count(),
            "examiners": Examiner.query.count(),
            "slots": Slot.query.count(),
            "bookings": Booking.query.count(),
        }
        dashboard = {"counts": counts}
        redis_client.setex("admin_dashboard", 120, json.dumps(dashboard))
        return dashboard, 200


class AdminCourses(Resource):

    def get(self):
        if "user_id" not in session:
            return ({"message": "Please log in."}, 401)
        current_user = User.query.filter_by(id=session["user_id"]).first()
        if current_user is None or current_user.status != "Active":
            session.clear()
            return ({"message": "Please log in with an active account."}, 401)
        if current_user.role != "Admin":
            return ({"message": "Access denied."}, 403)
        items = []
        for c in Course.query.order_by(Course.id.desc()):
            items.append(
                {
                    "id": c.id,
                    "code": c.code,
                    "name": c.name,
                    "description": c.description,
                    "status": c.status,
                }
            )
        return {"items": items}

    def post(self):
        if "user_id" not in session:
            return ({"message": "Please log in."}, 401)
        current_user = User.query.filter_by(id=session["user_id"]).first()
        if current_user is None or current_user.status != "Active":
            session.clear()
            return ({"message": "Please log in with an active account."}, 401)
        if current_user.role != "Admin":
            return ({"message": "Access denied."}, 403)
        data = request.get_json()
        if not isinstance(data, dict):
            return ({"message": "A JSON object is required."}, 400)
        code = data.get("code", "")
        if not isinstance(code, str) or len(code.strip()) > 30 or (not code.strip()):
            return ({"message": "Invalid code."}, 400)
        code = code.strip()
        name = data.get("name", "")
        if not isinstance(name, str) or len(name.strip()) > 150 or (not name.strip()):
            return ({"message": "Invalid name."}, 400)
        name = name.strip()
        description = data.get("description", "")
        if not isinstance(description, str) or len(description.strip()) > 3000:
            return ({"message": "Invalid description."}, 400)
        description = description.strip()
        course = Course(code=code.upper(), name=name, description=description)
        db.session.add(course)
        db.session.flush()
        db.session.commit()
        redis_client.delete("admin_dashboard")
        return (
            {
                "id": course.id,
                "code": course.code,
                "name": course.name,
                "description": course.description,
                "status": course.status,
            },
            201,
        )


class CourseDetails(Resource):

    def put(self, ident):
        if "user_id" not in session:
            return ({"message": "Please log in."}, 401)
        db.session.execute(db.text("BEGIN IMMEDIATE"))
        current_user = User.query.filter_by(id=session["user_id"]).first()
        if current_user is None or current_user.status != "Active":
            session.clear()
            return ({"message": "Please log in with an active account."}, 401)
        if current_user.role != "Admin":
            return ({"message": "Access denied."}, 403)
        course = Course.query.filter_by(id=ident).first_or_404()
        data = request.get_json()
        if not isinstance(data, dict):
            return ({"message": "A JSON object is required."}, 400)
        code = data.get("code", "")
        if not isinstance(code, str) or len(code.strip()) > 30 or (not code.strip()):
            return ({"message": "Invalid code."}, 400)
        code = code.strip()
        course.code = code.upper()
        name = data.get("name", "")
        if not isinstance(name, str) or len(name.strip()) > 150 or (not name.strip()):
            return ({"message": "Invalid name."}, 400)
        name = name.strip()
        course.name = name
        description = data.get("description", "")
        if not isinstance(description, str) or len(description.strip()) > 3000:
            return ({"message": "Invalid description."}, 400)
        description = description.strip()
        course.description = description
        if data.get("status") not in ("Active", "Archived"):
            return ({"message": "Invalid course status."}, 400)
        if data["status"] == "Archived" and course.status != "Archived":
            return (
                {"message": "Use the Archive action so active examinations can be checked."},
                400,
            )
        course.status = data["status"]
        db.session.commit()
        for exam in Examination.query.filter_by(course_id=course.id).all():
            redis_client.delete(f"examination_{exam.id}")
            redis_client.delete(f"examination_slots_{exam.id}")
        return {"message": "Course updated."}

    def delete(self, ident):
        if "user_id" not in session:
            return ({"message": "Please log in."}, 401)
        db.session.execute(db.text("BEGIN IMMEDIATE"))
        current_user = User.query.filter_by(id=session["user_id"]).first()
        if current_user is None or current_user.status != "Active":
            session.clear()
            return ({"message": "Please log in with an active account."}, 401)
        if current_user.role != "Admin":
            return ({"message": "Access denied."}, 403)
        course = Course.query.filter_by(id=ident).first_or_404()
        if Examination.query.filter(
            Examination.course_id == ident,
            Examination.archived.is_(False),
            Examination.status != "Completed",
        ).first():
            return (
                {
                    "message": "Complete or archive the course's examinations before archiving this course."
                },
                409,
            )
        course.status = "Archived"
        db.session.commit()
        for exam in Examination.query.filter_by(course_id=course.id).all():
            redis_client.delete(f"examination_{exam.id}")
            redis_client.delete(f"examination_slots_{exam.id}")
        return {"message": "Course updated."}


class AdminUsers(Resource):

    def get(self):
        if "user_id" not in session:
            return ({"message": "Please log in."}, 401)
        current_user = User.query.filter_by(id=session["user_id"]).first()
        if current_user is None or current_user.status != "Active":
            session.clear()
            return ({"message": "Please log in with an active account."}, 401)
        if current_user.role != "Admin":
            return ({"message": "Access denied."}, 403)
        role = request.args.get("role", "Student")
        if role not in ("Student", "Examiner"):
            return ({"message": "Role must be Student or Examiner."}, 400)
        profile = Student if role == "Student" else Examiner
        query = User.query.join(profile).filter(User.role == role).order_by(User.id.desc())
        q = request.args.get("q", "")
        if q:
            matches = profile.name.ilike(f"%{q}%") | User.email.ilike(f"%{q}%")
            if role == "Student":
                matches = matches | Student.roll_number.ilike(f"%{q}%")
            query = query.filter(matches)
        items = []
        for u in query:
            items.append(
                {
                    "id": u.id,
                    "email": u.email,
                    "role": u.role,
                    "status": u.status,
                    "name": (
                        (u.student or u.examiner).name
                        if u.student or u.examiner
                        else "Administrator"
                    ),
                    "department": (
                        (u.student or u.examiner).department if u.student or u.examiner else ""
                    ),
                    "phone": (u.student or u.examiner).phone if u.student or u.examiner else "",
                    "student_id": u.student.id if u.student else None,
                    "examiner_id": u.examiner.id if u.examiner else None,
                    "roll_number": u.student.roll_number if u.student else None,
                }
            )
        return {"items": items}

    def post(self):
        if "user_id" not in session:
            return ({"message": "Please log in."}, 401)
        current_user = User.query.filter_by(id=session["user_id"]).first()
        if current_user is None or current_user.status != "Active":
            session.clear()
            return ({"message": "Please log in with an active account."}, 401)
        if current_user.role != "Admin":
            return ({"message": "Access denied."}, 403)
        data = request.get_json()
        if not isinstance(data, dict):
            return ({"message": "A JSON object is required."}, 400)
        email = data.get("email", "")
        if not isinstance(email, str) or not re.fullmatch(
            "[^@\\s]+@[^@\\s]+\\.[^@\\s]+", email.strip()
        ):
            return ({"message": "Enter a valid email address."}, 400)
        email = email.strip().lower()
        password = data.get("password", "")
        if not isinstance(password, str) or not password:
            return ({"message": "Password is required."}, 400)
        user = User(role="Examiner", email=email, password=generate_password_hash(password))
        name = data.get("name", "")
        if not isinstance(name, str) or len(name.strip()) > 120 or (not name.strip()):
            return ({"message": "Invalid name."}, 400)
        name = name.strip()
        department = data.get("department", "")
        if (
            not isinstance(department, str)
            or len(department.strip()) > 100
            or (not department.strip())
        ):
            return ({"message": "Invalid department."}, 400)
        department = department.strip()
        phone = data.get("phone", "")
        if not isinstance(phone, str) or len(phone.strip()) > 30 or (not phone.strip()):
            return ({"message": "Invalid phone."}, 400)
        phone = phone.strip()
        user.examiner = Examiner(name=name, department=department, phone=phone)
        db.session.add(user)
        db.session.flush()
        db.session.commit()
        redis_client.delete("admin_dashboard")
        return (
            {
                "id": user.id,
                "email": user.email,
                "role": user.role,
                "status": user.status,
                "name": (
                    (user.student or user.examiner).name
                    if user.student or user.examiner
                    else "Administrator"
                ),
                "department": (
                    (user.student or user.examiner).department
                    if user.student or user.examiner
                    else ""
                ),
                "phone": (
                    (user.student or user.examiner).phone if user.student or user.examiner else ""
                ),
                "student_id": user.student.id if user.student else None,
                "examiner_id": user.examiner.id if user.examiner else None,
                "roll_number": user.student.roll_number if user.student else None,
            },
            201,
        )


class UserDetails(Resource):

    def put(self, ident):
        if "user_id" not in session:
            return ({"message": "Please log in."}, 401)
        db.session.execute(db.text("BEGIN IMMEDIATE"))
        current_user = User.query.filter_by(id=session["user_id"]).first()
        if current_user is None or current_user.status != "Active":
            session.clear()
            return ({"message": "Please log in with an active account."}, 401)
        if current_user.role != "Admin":
            return ({"message": "Access denied."}, 403)
        data = request.get_json()
        if not isinstance(data, dict):
            return ({"message": "A JSON object is required."}, 400)
        user = User.query.filter_by(id=ident).first_or_404()
        if user.role == "Admin":
            return ({"message": "The administrator cannot be removed or deactivated."}, 400)
        status = data.get("status")
        if status not in ("Active", "Inactive"):
            return ({"message": "Invalid account status."}, 400)
        if status == "Inactive":
            if user.role == "Examiner":
                pending = Booking.query.join(Slot).filter(
                    Slot.examiner_id == user.examiner.id, Booking.status == "Booked"
                )
            else:
                pending = Booking.query.filter(
                    Booking.student_id == user.student.id, Booking.status == "Booked"
                )
            if pending.first():
                return (
                    {
                        "message": "Resolve or reassign this user's active bookings before deactivating the account."
                    },
                    409,
                )
        profile = user.student if user.role == "Student" else user.examiner
        name = data.get("name", "")
        if not isinstance(name, str) or len(name.strip()) > 120 or (not name.strip()):
            return ({"message": "Invalid name."}, 400)
        name = name.strip()
        profile.name = name
        department = data.get("department", "")
        if (
            not isinstance(department, str)
            or len(department.strip()) > 100
            or (not department.strip())
        ):
            return ({"message": "Invalid department."}, 400)
        department = department.strip()
        profile.department = department
        phone = data.get("phone", "")
        if not isinstance(phone, str) or len(phone.strip()) > 30 or (not phone.strip()):
            return ({"message": "Invalid phone."}, 400)
        phone = phone.strip()
        profile.phone = phone
        user.status = status
        db.session.commit()
        if user.role == "Examiner":
            for exam in Examination.query.all():
                redis_client.delete(f"examination_{exam.id}")
                redis_client.delete(f"examination_slots_{exam.id}")
        return {
            "id": user.id,
            "email": user.email,
            "role": user.role,
            "status": user.status,
            "name": (
                (user.student or user.examiner).name
                if user.student or user.examiner
                else "Administrator"
            ),
            "department": (
                (user.student or user.examiner).department if user.student or user.examiner else ""
            ),
            "phone": (user.student or user.examiner).phone if user.student or user.examiner else "",
            "student_id": user.student.id if user.student else None,
            "examiner_id": user.examiner.id if user.examiner else None,
            "roll_number": user.student.roll_number if user.student else None,
        }


class CreateExamination(Resource):

    def post(self):
        if "user_id" not in session:
            return ({"message": "Please log in."}, 401)
        current_user = User.query.filter_by(id=session["user_id"]).first()
        if current_user is None or current_user.status != "Active":
            session.clear()
            return ({"message": "Please log in with an active account."}, 401)
        if current_user.role != "Admin":
            return ({"message": "Access denied."}, 403)
        exam = Examination()
        data = request.get_json()
        if not isinstance(data, dict):
            return ({"message": "A JSON object is required."}, 400)
        course_id = data.get("course_id", "")
        if (
            isinstance(course_id, bool)
            or not isinstance(course_id, int)
            or (not 1 <= course_id <= 10000)
        ):
            return ({"message": "Invalid course id."}, 400)
        course = Course.query.filter_by(id=course_id).first_or_404()
        if course.status != "Active":
            return ({"message": "Choose an active course."}, 409)
        exam.course_id = course.id
        name = data.get("name", "")
        if not isinstance(name, str) or len(name.strip()) > 160 or (not name.strip()):
            return ({"message": "Invalid name."}, 400)
        name = name.strip()
        exam.name = name
        exam_type = data.get("exam_type", "")
        if not isinstance(exam_type, str) or len(exam_type.strip()) > 30 or (not exam_type.strip()):
            return ({"message": "Invalid exam type."}, 400)
        exam_type = exam_type.strip()
        exam.exam_type = exam_type
        if exam.exam_type not in EXAM_TYPES:
            return ({"message": "Invalid examination type."}, 400)
        duration = data.get("duration", "")
        if (
            isinstance(duration, bool)
            or not isinstance(duration, int)
            or (not 5 <= duration <= 480)
        ):
            return ({"message": "Invalid duration."}, 400)
        exam.duration = duration
        maximum_marks = data.get("maximum_marks", "")
        if (
            isinstance(maximum_marks, bool)
            or not isinstance(maximum_marks, (int, float))
            or (not 1 <= maximum_marks <= 1000)
        ):
            return ({"message": "Invalid maximum marks."}, 400)
        exam.maximum_marks = maximum_marks
        instructions = data.get("instructions", "")
        if not isinstance(instructions, str) or len(instructions.strip()) > 5000:
            return ({"message": "Invalid instructions."}, 400)
        instructions = instructions.strip()
        exam.instructions = instructions
        slot_creation_start = data.get("slot_creation_start", "")
        try:
            slot_creation_start = datetime.fromisoformat(slot_creation_start.replace("Z", "+00:00"))
            if slot_creation_start.tzinfo is None:
                raise ValueError()
            slot_creation_start = slot_creation_start.astimezone(timezone.utc).replace(tzinfo=None)
        except (AttributeError, TypeError, ValueError):
            return ({"message": "Invalid slot creation start date and time."}, 400)
        exam.slot_creation_start = slot_creation_start
        slot_creation_end = data.get("slot_creation_end", "")
        try:
            slot_creation_end = datetime.fromisoformat(slot_creation_end.replace("Z", "+00:00"))
            if slot_creation_end.tzinfo is None:
                raise ValueError()
            slot_creation_end = slot_creation_end.astimezone(timezone.utc).replace(tzinfo=None)
        except (AttributeError, TypeError, ValueError):
            return ({"message": "Invalid slot creation end date and time."}, 400)
        exam.slot_creation_end = slot_creation_end
        booking_start = data.get("booking_start", "")
        try:
            booking_start = datetime.fromisoformat(booking_start.replace("Z", "+00:00"))
            if booking_start.tzinfo is None:
                raise ValueError()
            booking_start = booking_start.astimezone(timezone.utc).replace(tzinfo=None)
        except (AttributeError, TypeError, ValueError):
            return ({"message": "Invalid booking start date and time."}, 400)
        exam.booking_start = booking_start
        booking_end = data.get("booking_end", "")
        try:
            booking_end = datetime.fromisoformat(booking_end.replace("Z", "+00:00"))
            if booking_end.tzinfo is None:
                raise ValueError()
            booking_end = booking_end.astimezone(timezone.utc).replace(tzinfo=None)
        except (AttributeError, TypeError, ValueError):
            return ({"message": "Invalid booking end date and time."}, 400)
        exam.booking_end = booking_end
        if (
            not exam.slot_creation_start
            < exam.slot_creation_end
            <= exam.booking_start
            < exam.booking_end
        ):
            return (
                {"message": "Timeline must be: slot creation start < end <= booking start < end."},
                400,
            )
        ids = data.get("examiner_ids")
        if not isinstance(ids, list) or not ids or any((type(i) is not int for i in ids)):
            return ({"message": "Assign at least one examiner."}, 400)
        examiners = (
            Examiner.query.join(User)
            .filter(Examiner.id.in_(ids), User.role == "Examiner", User.status == "Active")
            .all()
        )
        if len(examiners) != len(set(ids)):
            return ({"message": "All assigned examiners must be active examiner accounts."}, 400)
        exam.examiners = examiners
        db.session.add(exam)
        db.session.flush()
        db.session.commit()
        redis_client.delete("admin_dashboard")
        return (
            {
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
                    exam.published_at.strftime("%Y-%m-%dT%H:%M:%SZ") if exam.published_at else None
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
            },
            201,
        )


class ExaminationDetails(Resource):

    def put(self, ident):
        if "user_id" not in session:
            return ({"message": "Please log in."}, 401)
        db.session.execute(db.text("BEGIN IMMEDIATE"))
        current_user = User.query.filter_by(id=session["user_id"]).first()
        if current_user is None or current_user.status != "Active":
            session.clear()
            return ({"message": "Please log in with an active account."}, 401)
        if current_user.role != "Admin":
            return ({"message": "Access denied."}, 403)
        exam = Examination.query.filter_by(id=ident).first_or_404()
        if exam.published_at or Booking.query.filter(Booking.exam_id == ident).first():
            return (
                {
                    "message": "Booked examinations are protected. Use slot rescheduling or examiner reassignment for exceptions."
                },
                409,
            )
        data = request.get_json()
        if not isinstance(data, dict):
            return ({"message": "A JSON object is required."}, 400)
        course_id = data.get("course_id", "")
        if (
            isinstance(course_id, bool)
            or not isinstance(course_id, int)
            or (not 1 <= course_id <= 10000)
        ):
            return ({"message": "Invalid course id."}, 400)
        course = Course.query.filter_by(id=course_id).first_or_404()
        if course.status != "Active":
            return ({"message": "Choose an active course."}, 409)
        exam.course_id = course.id
        name = data.get("name", "")
        if not isinstance(name, str) or len(name.strip()) > 160 or (not name.strip()):
            return ({"message": "Invalid name."}, 400)
        name = name.strip()
        exam.name = name
        exam_type = data.get("exam_type", "")
        if not isinstance(exam_type, str) or len(exam_type.strip()) > 30 or (not exam_type.strip()):
            return ({"message": "Invalid exam type."}, 400)
        exam_type = exam_type.strip()
        exam.exam_type = exam_type
        if exam.exam_type not in EXAM_TYPES:
            return ({"message": "Invalid examination type."}, 400)
        duration = data.get("duration", "")
        if (
            isinstance(duration, bool)
            or not isinstance(duration, int)
            or (not 5 <= duration <= 480)
        ):
            return ({"message": "Invalid duration."}, 400)
        exam.duration = duration
        maximum_marks = data.get("maximum_marks", "")
        if (
            isinstance(maximum_marks, bool)
            or not isinstance(maximum_marks, (int, float))
            or (not 1 <= maximum_marks <= 1000)
        ):
            return ({"message": "Invalid maximum marks."}, 400)
        exam.maximum_marks = maximum_marks
        instructions = data.get("instructions", "")
        if not isinstance(instructions, str) or len(instructions.strip()) > 5000:
            return ({"message": "Invalid instructions."}, 400)
        instructions = instructions.strip()
        exam.instructions = instructions
        slot_creation_start = data.get("slot_creation_start", "")
        try:
            slot_creation_start = datetime.fromisoformat(slot_creation_start.replace("Z", "+00:00"))
            if slot_creation_start.tzinfo is None:
                raise ValueError()
            slot_creation_start = slot_creation_start.astimezone(timezone.utc).replace(tzinfo=None)
        except (AttributeError, TypeError, ValueError):
            return ({"message": "Invalid slot creation start date and time."}, 400)
        exam.slot_creation_start = slot_creation_start
        slot_creation_end = data.get("slot_creation_end", "")
        try:
            slot_creation_end = datetime.fromisoformat(slot_creation_end.replace("Z", "+00:00"))
            if slot_creation_end.tzinfo is None:
                raise ValueError()
            slot_creation_end = slot_creation_end.astimezone(timezone.utc).replace(tzinfo=None)
        except (AttributeError, TypeError, ValueError):
            return ({"message": "Invalid slot creation end date and time."}, 400)
        exam.slot_creation_end = slot_creation_end
        booking_start = data.get("booking_start", "")
        try:
            booking_start = datetime.fromisoformat(booking_start.replace("Z", "+00:00"))
            if booking_start.tzinfo is None:
                raise ValueError()
            booking_start = booking_start.astimezone(timezone.utc).replace(tzinfo=None)
        except (AttributeError, TypeError, ValueError):
            return ({"message": "Invalid booking start date and time."}, 400)
        exam.booking_start = booking_start
        booking_end = data.get("booking_end", "")
        try:
            booking_end = datetime.fromisoformat(booking_end.replace("Z", "+00:00"))
            if booking_end.tzinfo is None:
                raise ValueError()
            booking_end = booking_end.astimezone(timezone.utc).replace(tzinfo=None)
        except (AttributeError, TypeError, ValueError):
            return ({"message": "Invalid booking end date and time."}, 400)
        exam.booking_end = booking_end
        if (
            not exam.slot_creation_start
            < exam.slot_creation_end
            <= exam.booking_start
            < exam.booking_end
        ):
            return (
                {"message": "Timeline must be: slot creation start < end <= booking start < end."},
                400,
            )
        ids = data.get("examiner_ids")
        if not isinstance(ids, list) or not ids or any((type(i) is not int for i in ids)):
            return ({"message": "Assign at least one examiner."}, 400)
        examiners = (
            Examiner.query.join(User)
            .filter(Examiner.id.in_(ids), User.role == "Examiner", User.status == "Active")
            .all()
        )
        if len(examiners) != len(set(ids)):
            return ({"message": "All assigned examiners must be active examiner accounts."}, 400)
        slots = Slot.query.filter(Slot.exam_id == exam.id, Slot.status != "Cancelled").all()
        if any((s.examiner_id not in ids for s in slots)):
            return (
                {
                    "message": "Reassign or remove an examiner's slots before removing their assignment."
                },
                409,
            )
        if any(
            (
                s.start < exam.booking_end
                or (s.end - s.start).total_seconds() != exam.duration * 60
                for s in slots
            )
        ):
            return ({"message": "The new timeline or duration conflicts with existing slots."}, 409)
        exam.examiners = examiners
        db.session.commit()
        redis_client.delete(f"examination_{exam.id}")
        redis_client.delete(f"examination_slots_{exam.id}")
        return {"message": "Examination updated."}

    def delete(self, ident):
        if "user_id" not in session:
            return ({"message": "Please log in."}, 401)
        db.session.execute(db.text("BEGIN IMMEDIATE"))
        current_user = User.query.filter_by(id=session["user_id"]).first()
        if current_user is None or current_user.status != "Active":
            session.clear()
            return ({"message": "Please log in with an active account."}, 401)
        if current_user.role != "Admin":
            return ({"message": "Access denied."}, 403)
        exam = Examination.query.filter_by(id=ident).first_or_404()
        if Booking.query.filter(Booking.exam_id == ident, Booking.status == "Booked").first():
            return ({"message": "Resolve active bookings before archiving an examination."}, 409)
        exam.archived = True
        db.session.commit()
        redis_client.delete(f"examination_{exam.id}")
        redis_client.delete(f"examination_slots_{exam.id}")
        return {"message": "Examination updated."}


class ExaminationStatus(Resource):

    def post(self, ident):
        if "user_id" not in session:
            return ({"message": "Please log in."}, 401)
        db.session.execute(db.text("BEGIN IMMEDIATE"))
        current_user = User.query.filter_by(id=session["user_id"]).first()
        current_time = datetime.now(timezone.utc).replace(tzinfo=None)
        if current_user is None or current_user.status != "Active":
            session.clear()
            return ({"message": "Please log in with an active account."}, 401)
        if current_user.role != "Admin":
            return ({"message": "Access denied."}, 403)
        exam = Examination.query.filter_by(id=ident).first_or_404()
        data = request.get_json()
        if not isinstance(data, dict):
            return ({"message": "A JSON object is required."}, 400)
        status = data.get("status", "")
        if not isinstance(status, str) or len(status.strip()) > 30 or (not status.strip()):
            return ({"message": "Invalid status."}, 400)
        status = status.strip()
        if status not in EXAM_STATUSES or exam.archived or exam.published_at:
            return ({"message": "This examination cannot be changed to that status."}, 400)
        if status == "Slot Creation" and (
            not exam.slot_creation_start <= current_time < exam.slot_creation_end
        ):
            return (
                {"message": "The configured slot creation period is not currently active."},
                409,
            )
        if status == "Booking Open":
            if not exam.booking_start <= current_time < exam.booking_end:
                return (
                    {"message": "The configured student booking period is not currently active."},
                    409,
                )
            if not exam.rubrics or abs(sum((r.weightage for r in exam.rubrics)) - 100) > 0.001:
                return (
                    {"message": "Add an evaluation rubric with weightages totaling 100% first."},
                    409,
                )
        if status == "Completed":
            if Booking.query.filter(Booking.exam_id == ident, Booking.status == "Booked").first():
                return (
                    {
                        "message": "All booked students must be evaluated before completing the examination."
                    },
                    409,
                )
            for slot in Slot.query.filter(Slot.exam_id == ident, Slot.status != "Cancelled"):
                slot.status = "Completed"
        if (
            status in ("Draft", "Slot Creation")
            and Booking.query.filter(
                Booking.exam_id == ident, Booking.status != "Cancelled"
            ).first()
        ):
            return (
                {
                    "message": "An examination with bookings cannot return to draft or slot creation."
                },
                409,
            )
        exam.status = status
        db.session.commit()
        redis_client.delete(f"examination_{exam.id}")
        redis_client.delete(f"examination_slots_{exam.id}")
        return {"message": f"Examination is now {status}."}


class UpdateRubrics(Resource):

    def put(self, ident):
        if "user_id" not in session:
            return ({"message": "Please log in."}, 401)
        db.session.execute(db.text("BEGIN IMMEDIATE"))
        current_user = User.query.filter_by(id=session["user_id"]).first()
        if current_user is None or current_user.status != "Active":
            session.clear()
            return ({"message": "Please log in with an active account."}, 401)
        if current_user.role != "Admin":
            return ({"message": "Access denied."}, 403)
        exam = Examination.query.filter_by(id=ident).first_or_404()
        if exam.published_at or Booking.query.filter(Booking.exam_id == ident).first():
            return (
                {
                    "message": "Rubrics are locked after the first booking to preserve assessment history."
                },
                409,
            )
        data = request.get_json()
        if not isinstance(data, dict):
            return ({"message": "A JSON object is required."}, 400)
        criteria = data.get("criteria")
        if not isinstance(criteria, list) or not 1 <= len(criteria) <= 30:
            return ({"message": "Provide between 1 and 30 rubric criteria."}, 400)
        rows = []
        for row in criteria:
            if not isinstance(row, dict):
                return ({"message": "Invalid rubric criterion."}, 400)
            name = row.get("name", "")
            if not isinstance(name, str) or len(name.strip()) > 120 or (not name.strip()):
                return ({"message": "Invalid name."}, 400)
            name = name.strip()
            maximum_marks = row.get("maximum_marks", "")
            if (
                isinstance(maximum_marks, bool)
                or not isinstance(maximum_marks, (int, float))
                or (not 1 <= maximum_marks <= 1000)
            ):
                return ({"message": "Invalid maximum marks."}, 400)
            weightage = row.get("weightage", "")
            if (
                isinstance(weightage, bool)
                or not isinstance(weightage, (int, float))
                or (not 0.01 <= weightage <= 100)
            ):
                return ({"message": "Invalid weightage."}, 400)
            description = row.get("description", "")
            if not isinstance(description, str) or len(description.strip()) > 1000:
                return ({"message": "Invalid description."}, 400)
            description = description.strip()
            rows.append(
                Rubric(
                    name=name,
                    maximum_marks=maximum_marks,
                    weightage=weightage,
                    description=description,
                )
            )
        if abs(sum((row.weightage for row in rows)) - 100) > 0.001:
            return ({"message": "Rubric weightages must total exactly 100%."}, 400)
        exam.rubrics = rows
        db.session.commit()
        redis_client.delete(f"examination_{exam.id}")
        redis_client.delete(f"examination_rubrics_{exam.id}")
        return {"message": "Rubric saved."}


class AdminSlots(Resource):

    def get(self):
        if "user_id" not in session:
            return ({"message": "Please log in."}, 401)
        current_user = User.query.filter_by(id=session["user_id"]).first()
        if current_user is None or current_user.status != "Active":
            session.clear()
            return ({"message": "Please log in with an active account."}, 401)
        if current_user.role != "Admin":
            return ({"message": "Access denied."}, 403)
        items = []
        for s in Slot.query.order_by(Slot.start.desc()):
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


class RescheduleSlot(Resource):

    def put(self, ident):
        if "user_id" not in session:
            return ({"message": "Please log in."}, 401)
        db.session.execute(db.text("BEGIN IMMEDIATE"))
        current_user = User.query.filter_by(id=session["user_id"]).first()
        current_time = datetime.now(timezone.utc).replace(tzinfo=None)
        if current_user is None or current_user.status != "Active":
            session.clear()
            return ({"message": "Please log in with an active account."}, 401)
        if current_user.role != "Admin":
            return ({"message": "Access denied."}, 403)
        data = request.get_json()
        if not isinstance(data, dict):
            return ({"message": "A JSON object is required."}, 400)
        reason = data.get("reason", "")
        if not isinstance(reason, str) or len(reason.strip()) > 1000 or (not reason.strip()):
            return ({"message": "Invalid reason."}, 400)
        reason = reason.strip()
        slot = Slot.query.filter_by(id=ident).first_or_404()
        if (
            slot.status in ("Completed", "Cancelled")
            or slot.exam.published_at
            or any((b.evaluation for b in slot.bookings))
        ):
            return ({"message": "Cancelled, completed, or evaluated slots cannot be changed."}, 409)
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
        examiner_id = data.get("examiner_id", "")
        if (
            isinstance(examiner_id, bool)
            or not isinstance(examiner_id, int)
            or (not 1 <= examiner_id <= 10000)
        ):
            return ({"message": "Invalid examiner id."}, 400)
        examiner = Examiner.query.filter_by(id=examiner_id).first_or_404()
        capacity = data.get("capacity", "")
        if (
            isinstance(capacity, bool)
            or not isinstance(capacity, int)
            or (not 1 <= capacity <= 500)
        ):
            return ({"message": "Invalid capacity."}, 400)
        if examiner.user.status != "Active" or examiner not in slot.exam.examiners:
            return ({"message": "Choose an active examiner assigned to this examination."}, 400)
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
        if capacity < sum((booking.status != "Cancelled" for booking in slot.bookings)):
            return ({"message": "Capacity cannot be below the number of booked students."}, 409)
        examiner_conflict = Slot.query.filter(
            Slot.examiner_id == examiner.id,
            Slot.status != "Cancelled",
            Slot.start < end,
            Slot.end > start,
        )
        examiner_conflict = examiner_conflict.filter(Slot.id != slot.id)
        if examiner_conflict.first():
            return ({"message": "This examiner already has an overlapping examination slot."}, 409)
        if [b.student_id for b in slot.bookings if b.status != "Cancelled"]:
            query = Booking.query.join(Slot).filter(
                Booking.student_id.in_(
                    [b.student_id for b in slot.bookings if b.status != "Cancelled"]
                ),
                Booking.status != "Cancelled",
                Slot.status != "Cancelled",
                Slot.start < end,
                Slot.end > start,
            )
            query = query.filter(Slot.id != slot.id)
            if query.first():
                return ({"message": "A student has another booking that overlaps this time."}, 409)
        previous = {
            "start": slot.start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end": slot.end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "examiner_id": slot.examiner_id,
            "capacity": slot.capacity,
        }
        slot.start, slot.end, slot.examiner_id, slot.capacity = (start, end, examiner.id, capacity)
        meeting_link = data.get("meeting_link", "")
        if not isinstance(meeting_link, str) or len(meeting_link.strip()) > 500:
            return ({"message": "Invalid meeting link."}, 400)
        meeting_link = meeting_link.strip()
        slot.meeting_link = meeting_link
        if slot.meeting_link and (not slot.meeting_link.startswith(("https://", "http://"))):
            return ({"message": "Meeting link must begin with https:// or http://."}, 400)
        location = data.get("location", "")
        if not isinstance(location, str) or len(location.strip()) > 200:
            return ({"message": "Invalid location."}, 400)
        location = location.strip()
        slot.location = location
        if slot.status not in ("Cancelled", "Completed"):
            slot.status = (
                "Full"
                if sum((booking.status != "Cancelled" for booking in slot.bookings))
                >= slot.capacity
                else "Available"
            )
        slot.reschedule_history = slot.reschedule_history + [
            {
                "changed_at": current_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "reason": reason,
                "previous": previous,
                "updated": {
                    "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "examiner_id": examiner.id,
                    "capacity": capacity,
                },
            }
        ]
        db.session.commit()
        redis_client.delete(f"examination_slots_{slot.exam_id}")
        return {"message": "Slot updated."}


class AdminBookings(Resource):

    def get(self):
        if "user_id" not in session:
            return ({"message": "Please log in."}, 401)
        current_user = User.query.filter_by(id=session["user_id"]).first()
        if current_user is None or current_user.status != "Active":
            session.clear()
            return ({"message": "Please log in with an active account."}, 401)
        if current_user.role != "Admin":
            return ({"message": "Access denied."}, 403)
        query = Booking.query
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


class RescheduleBooking(Resource):

    def post(self, ident):
        if "user_id" not in session:
            return ({"message": "Please log in."}, 401)
        db.session.execute(db.text("BEGIN IMMEDIATE"))
        current_user = User.query.filter_by(id=session["user_id"]).first()
        current_time = datetime.now(timezone.utc).replace(tzinfo=None)
        if current_user is None or current_user.status != "Active":
            session.clear()
            return ({"message": "Please log in with an active account."}, 401)
        if current_user.role != "Admin":
            return ({"message": "Access denied."}, 403)
        data = request.get_json()
        if not isinstance(data, dict):
            return ({"message": "A JSON object is required."}, 400)
        reason = data.get("reason", "")
        if not isinstance(reason, str) or len(reason.strip()) > 1000 or (not reason.strip()):
            return ({"message": "Invalid reason."}, 400)
        reason = reason.strip()
        booking = Booking.query.filter_by(id=ident).first_or_404()
        slot_id = data.get("slot_id", "")
        if isinstance(slot_id, bool) or not isinstance(slot_id, int) or (not 1 <= slot_id <= 10000):
            return ({"message": "Invalid slot id."}, 400)
        target = Slot.query.filter_by(id=slot_id).first_or_404()
        if booking.status != "Booked" or booking.evaluation or booking.slot.exam.published_at:
            return ({"message": "Only pending, unevaluated bookings may be rescheduled."}, 409)
        if target.id == booking.slot_id or target.exam_id != booking.exam_id:
            return ({"message": "Choose a different slot in the same examination."}, 400)
        if (
            target.status not in ("Available", "Full")
            or target.start <= current_time
            or target.examiner.user.status != "Active"
            or (
                sum((booking.status != "Cancelled" for booking in target.bookings))
                >= target.capacity
            )
        ):
            return ({"message": "The target slot is unavailable or full."}, 409)
        overlap = Booking.query.join(Slot).filter(
            Booking.student_id == booking.student_id,
            Booking.id != booking.id,
            Booking.status != "Cancelled",
            Slot.start < target.end,
            Slot.end > target.start,
        )
        if overlap.first():
            return ({"message": "The student has an overlapping booking."}, 409)
        old = booking.slot
        booking.slot = target
        db.session.flush()
        if old.status not in ("Cancelled", "Completed"):
            old.status = (
                "Full"
                if sum((booking.status != "Cancelled" for booking in old.bookings)) >= old.capacity
                else "Available"
            )
        if target.status not in ("Cancelled", "Completed"):
            target.status = (
                "Full"
                if sum((booking.status != "Cancelled" for booking in target.bookings))
                >= target.capacity
                else "Available"
            )
        booking.reschedule_history = booking.reschedule_history + [
            {
                "changed_at": current_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "previous_slot_id": old.id,
                "slot_id": target.id,
                "reason": reason,
            }
        ]
        db.session.commit()
        redis_client.delete(f"examination_slots_{booking.exam_id}")
        return {"message": "Booking rescheduled."}


class PublishResults(Resource):

    def post(self, ident):
        if "user_id" not in session:
            return ({"message": "Please log in."}, 401)
        db.session.execute(db.text("BEGIN IMMEDIATE"))
        current_user = User.query.filter_by(id=session["user_id"]).first()
        current_time = datetime.now(timezone.utc).replace(tzinfo=None)
        if current_user is None or current_user.status != "Active":
            session.clear()
            return ({"message": "Please log in with an active account."}, 401)
        if current_user.role != "Admin":
            return ({"message": "Access denied."}, 403)
        exam = Examination.query.filter_by(id=ident).first_or_404()
        if exam.status != "Completed" or exam.published_at:
            return (
                {
                    "message": "Complete the examination before publishing. Already published results cannot be republished."
                },
                409,
            )
        completed = Booking.query.filter(
            Booking.exam_id == ident, Booking.status == "Completed"
        ).all()
        if not completed or any((not b.evaluation for b in completed)):
            return (
                {"message": "This examination does not have a complete set of evaluations."},
                409,
            )
        exam.published_at = current_time
        db.session.commit()
        redis_client.delete(f"examination_{exam.id}")
        return {"message": "Results published."}


class AdminReports(Resource):

    def get(self):
        if "user_id" not in session:
            return ({"message": "Please log in."}, 401)
        current_user = User.query.filter_by(id=session["user_id"]).first()
        if current_user is None or current_user.status != "Active":
            session.clear()
            return ({"message": "Please log in with an active account."}, 401)
        if current_user.role != "Admin":
            return ({"message": "Access denied."}, 403)
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
        return report


class MonthlyReport(Resource):

    def post(self):
        if "user_id" not in session:
            return ({"message": "Please log in."}, 401)
        current_user = User.query.filter_by(id=session["user_id"]).first()
        if current_user is None or current_user.status != "Active":
            session.clear()
            return ({"message": "Please log in with an active account."}, 401)
        if current_user.role != "Admin":
            return ({"message": "Access denied."}, 403)
        from routes.tasks import send_monthly_report

        try:
            task = send_monthly_report.delay()
        except (OperationalError, RedisError, OSError):
            current_app.logger.exception("Unable to queue the monthly report.")
            return ({"message": "The monthly report could not be queued. Please retry."}, 503)
        return ({"message": "Monthly report queued.", "task_id": task.id}, 202)
