from flask import Flask
from flask_cors import CORS
from flask_restful import Api
from werkzeug.security import generate_password_hash
from model import User, db
from routes.auth import Login, StudentRegister, SessionCheck, Logout, StudentProfile
from routes.admin import (
    AdminDashboard,
    AdminCourses,
    CourseDetails,
    AdminUsers,
    UserDetails,
    CreateExamination,
    ExaminationDetails,
    ExaminationStatus,
    UpdateRubrics,
    AdminSlots,
    RescheduleSlot,
    AdminBookings,
    RescheduleBooking,
    PublishResults,
    AdminReports,
    MonthlyReport,
)
from routes.examiner import (
    ExaminerDashboard,
    ExaminerSlots,
    ExaminerSlotDetails,
    ExaminerBookings,
    EvaluateStudent,
    CompleteSlot,
)
from routes.student import (
    StudentDashboard,
    StudentBookings,
    CancelBooking,
    StudentHistory,
    StudentExports,
    DownloadHistory,
    AvailableExaminations,
    ExaminationSlots,
    ExaminationRubrics,
)

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///exortal.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = "ExortalSessionKey"
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["PROPAGATE_EXCEPTIONS"] = False

db.init_app(app)
CORS(app, supports_credentials=True, origins=["http://localhost:5173", "http://127.0.0.1:5173"])
api = Api(
    app,
    errors={
        "IntegrityError": {
            "message": "This change conflicts with an existing record.",
            "status": 409,
        },
        "OperationalError": {
            "message": "The database is unavailable. Please retry.",
            "status": 503,
        },
        "ConnectionError": {
            "message": "Redis is unavailable. Changes may already be saved; refresh before retrying.",
            "status": 503,
        },
        "TimeoutError": {
            "message": "Redis timed out. Changes may already be saved; refresh before retrying.",
            "status": 503,
        },
    },
)

with app.app_context():
    db.create_all()
    admin = User.query.filter_by(role="Admin").first()
    if admin is None:
        admin = User(
            email="admin@exam.com",
            password=generate_password_hash("admin123"),
            role="Admin",
            status="Active",
        )
        db.session.add(admin)
        db.session.commit()

api.add_resource(Login, "/api/login")
api.add_resource(StudentRegister, "/api/student/register")
api.add_resource(SessionCheck, "/api/session")
api.add_resource(Logout, "/api/logout")
api.add_resource(StudentProfile, "/api/profile")

api.add_resource(AdminDashboard, "/api/admin/dashboard")
api.add_resource(AdminCourses, "/api/admin/courses")
api.add_resource(CourseDetails, "/api/admin/courses/<int:ident>")
api.add_resource(AdminUsers, "/api/admin/users")
api.add_resource(UserDetails, "/api/admin/users/<int:ident>")
api.add_resource(CreateExamination, "/api/admin/examinations")
api.add_resource(ExaminationDetails, "/api/admin/examinations/<int:ident>")
api.add_resource(ExaminationStatus, "/api/admin/examinations/<int:ident>/status")
api.add_resource(UpdateRubrics, "/api/admin/examinations/<int:ident>/rubrics")
api.add_resource(AdminSlots, "/api/admin/slots")
api.add_resource(RescheduleSlot, "/api/admin/slots/<int:ident>")
api.add_resource(AdminBookings, "/api/admin/bookings")
api.add_resource(RescheduleBooking, "/api/admin/bookings/<int:ident>/reschedule")
api.add_resource(PublishResults, "/api/admin/examinations/<int:ident>/publish")
api.add_resource(AdminReports, "/api/admin/reports")
api.add_resource(MonthlyReport, "/api/admin/reports/monthly")

api.add_resource(ExaminerDashboard, "/api/examiner/dashboard")
api.add_resource(ExaminerSlots, "/api/examiner/slots")
api.add_resource(ExaminerSlotDetails, "/api/examiner/slots/<int:ident>")
api.add_resource(ExaminerBookings, "/api/examiner/bookings")
api.add_resource(EvaluateStudent, "/api/examiner/bookings/<int:ident>/evaluate")
api.add_resource(CompleteSlot, "/api/examiner/slots/<int:ident>/complete")

api.add_resource(StudentDashboard, "/api/student/dashboard")
api.add_resource(StudentBookings, "/api/student/bookings")
api.add_resource(CancelBooking, "/api/student/bookings/<int:ident>/cancel")
api.add_resource(StudentHistory, "/api/student/history")
api.add_resource(StudentExports, "/api/student/exports")
api.add_resource(DownloadHistory, "/api/student/exports/<string:ident>/download")
api.add_resource(AvailableExaminations, "/api/examinations")
api.add_resource(ExaminationSlots, "/api/examinations/<int:exam_id>/slots")
api.add_resource(ExaminationRubrics, "/api/examinations/<int:exam_id>/rubrics")

if __name__ == "__main__":
    app.run(port=5000)
