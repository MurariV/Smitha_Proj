from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Index, text

db = SQLAlchemy()
examiner_assignments = db.Table(
    "examiner_assignments",
    db.Column("exam_id", db.Integer, db.ForeignKey("examination.id"), primary_key=True),
    db.Column("examiner_id", db.Integer, db.ForeignKey("examiner.id"), primary_key=True),
)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(254), nullable=False, unique=True)
    password = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(16), nullable=False)
    status = db.Column(db.String(16), nullable=False, default="Active")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    student = db.relationship(
        "Student", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    examiner = db.relationship(
        "Examiner", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    __table_args__ = (
        db.CheckConstraint("role IN ('Admin','Examiner','Student')"),
        db.CheckConstraint("status IN ('Active','Inactive')"),
        Index("only_one_admin", "role", unique=True, sqlite_where=text("role = 'Admin'")),
    )


class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, unique=True)
    roll_number = db.Column(db.String(40), nullable=False, unique=True)
    name = db.Column(db.String(120), nullable=False)
    department = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    export_task_id = db.Column(db.String(36))
    user = db.relationship(User, back_populates="student")


class Examiner(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, unique=True)
    name = db.Column(db.String(120), nullable=False)
    department = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    user = db.relationship(User, back_populates="examiner")


class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(30), nullable=False, unique=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    status = db.Column(db.String(16), nullable=False, default="Active")


class Examination(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("course.id"), nullable=False)
    name = db.Column(db.String(160), nullable=False)
    exam_type = db.Column(db.String(30), nullable=False)
    duration = db.Column(db.Integer, nullable=False)
    maximum_marks = db.Column(db.Float, nullable=False)
    slot_creation_start = db.Column(db.DateTime, nullable=False)
    slot_creation_end = db.Column(db.DateTime, nullable=False)
    booking_start = db.Column(db.DateTime, nullable=False)
    booking_end = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(30), nullable=False, default="Draft")
    instructions = db.Column(db.Text, nullable=False, default="")
    published_at = db.Column(db.DateTime)
    archived = db.Column(db.Boolean, nullable=False, default=False)
    course = db.relationship(Course)
    examiners = db.relationship(Examiner, secondary=examiner_assignments)
    rubrics = db.relationship("Rubric", order_by="Rubric.id", cascade="all, delete-orphan")
    __table_args__ = (
        db.CheckConstraint("duration > 0 AND maximum_marks > 0"),
        db.CheckConstraint(
            "slot_creation_start < slot_creation_end AND slot_creation_end <= booking_start AND booking_start < booking_end"
        ),
    )


class Rubric(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey("examination.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    maximum_marks = db.Column(db.Float, nullable=False)
    weightage = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    __table_args__ = (
        db.CheckConstraint("maximum_marks > 0 AND weightage > 0 AND weightage <= 100"),
    )


class Slot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey("examination.id"), nullable=False, index=True)
    examiner_id = db.Column(db.Integer, db.ForeignKey("examiner.id"), nullable=False, index=True)
    start = db.Column(db.DateTime, nullable=False, index=True)
    end = db.Column(db.DateTime, nullable=False)
    capacity = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="Available")
    meeting_link = db.Column(db.String(500), nullable=False, default="")
    location = db.Column(db.String(200), nullable=False, default="")
    reschedule_history = db.Column(db.JSON, nullable=False, default=list)
    exam = db.relationship(Examination)
    examiner = db.relationship(Examiner)
    bookings = db.relationship("Booking", back_populates="slot")
    __table_args__ = (db.CheckConstraint("capacity > 0 AND start < end"),)


class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False, index=True)
    exam_id = db.Column(db.Integer, db.ForeignKey("examination.id"), nullable=False, index=True)
    slot_id = db.Column(db.Integer, db.ForeignKey("slot.id"), nullable=False, index=True)
    booked_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    status = db.Column(db.String(20), nullable=False, default="Booked")
    reschedule_history = db.Column(db.JSON, nullable=False, default=list)
    student = db.relationship(Student)
    slot = db.relationship(Slot, back_populates="bookings")
    evaluation = db.relationship("Evaluation", uselist=False, back_populates="booking")
    __table_args__ = (
        Index(
            "one_live_booking_per_examination",
            "student_id",
            "exam_id",
            unique=True,
            sqlite_where=text("status != 'Cancelled'"),
        ),
    )


class Evaluation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey("booking.id"), nullable=False, unique=True)
    examiner_id = db.Column(db.Integer, db.ForeignKey("examiner.id"), nullable=False)
    total_marks = db.Column(db.Float, nullable=False)
    remarks = db.Column(db.Text, nullable=False, default="")
    evaluated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    status = db.Column(db.String(20), nullable=False, default="Submitted")
    booking = db.relationship(Booking, back_populates="evaluation")
    scores = db.Column(db.JSON, nullable=False, default=list)
    examiner = db.relationship(Examiner)
