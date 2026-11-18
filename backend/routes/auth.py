import re
from flask import request, session
from flask_restful import Resource
from werkzeug.security import generate_password_hash, check_password_hash
from model import db, User, Student
from redis_client import redis_client


class Login(Resource):

    def post(self):
        data = request.get_json()
        if not isinstance(data, dict):
            return ({"message": "A JSON object is required."}, 400)
        email = data.get("email", "")
        if not isinstance(email, str) or not re.fullmatch(
            "[^@\\s]+@[^@\\s]+\\.[^@\\s]+", email.strip()
        ):
            return ({"message": "Enter a valid email address."}, 400)
        email = email.strip().lower()
        user = User.query.filter_by(email=email).first()
        password = data.get("password", "")
        if not isinstance(password, str) or not password:
            return ({"message": "Password is required."}, 400)
        if not user or not check_password_hash(user.password, password) or user.status != "Active":
            return ({"message": "Invalid email/password, or the account is inactive."}, 401)
        session.clear()
        session["user_id"] = user.id
        session["role"] = user.role
        session.permanent = False
        return {
            "user": {
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
            }
        }


class StudentRegister(Resource):

    def post(self):
        data = request.get_json()
        if not isinstance(data, dict):
            return ({"message": "A JSON object is required."}, 400)
        email = data.get("email", "")
        if not isinstance(email, str) or not re.fullmatch(
            "[^@\\s]+@[^@\\s]+\\.[^@\\s]+", email.strip()
        ):
            return ({"message": "Enter a valid email address."}, 400)
        email = email.strip().lower()
        roll_number = data.get("roll_number", "")
        if (
            not isinstance(roll_number, str)
            or len(roll_number.strip()) > 40
            or (not roll_number.strip())
        ):
            return ({"message": "Invalid roll number."}, 400)
        roll_number = roll_number.strip().upper()
        if (
            User.query.filter_by(email=email).first()
            or Student.query.filter_by(roll_number=roll_number).first()
        ):
            return ({"message": "Email address or roll number is already registered."}, 409)
        password = data.get("password", "")
        if not isinstance(password, str) or not password:
            return ({"message": "Password is required."}, 400)
        user = User(email=email, password=generate_password_hash(password), role="Student")
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
        user.student = Student(
            name=name, department=department, phone=phone, roll_number=roll_number
        )
        db.session.add(user)
        db.session.commit()
        redis_client.delete("admin_dashboard")
        return ({"message": "Registration successful. Please log in."}, 201)


class SessionCheck(Resource):

    def get(self):
        if "user_id" not in session:
            return ({"message": "Please log in."}, 401)
        current_user = User.query.filter_by(id=session["user_id"]).first()
        if current_user is None or current_user.status != "Active":
            session.clear()
            return ({"message": "Please log in with an active account."}, 401)
        if current_user.role == "Student" and current_user.student is None:
            return ({"message": "Student profile not found."}, 401)
        if current_user.role == "Examiner" and current_user.examiner is None:
            return ({"message": "Examiner profile not found."}, 401)
        return {
            "user": {
                "id": current_user.id,
                "email": current_user.email,
                "role": current_user.role,
                "status": current_user.status,
                "name": (
                    (current_user.student or current_user.examiner).name
                    if current_user.student or current_user.examiner
                    else "Administrator"
                ),
                "department": (
                    (current_user.student or current_user.examiner).department
                    if current_user.student or current_user.examiner
                    else ""
                ),
                "phone": (
                    (current_user.student or current_user.examiner).phone
                    if current_user.student or current_user.examiner
                    else ""
                ),
                "student_id": current_user.student.id if current_user.student else None,
                "examiner_id": current_user.examiner.id if current_user.examiner else None,
                "roll_number": current_user.student.roll_number if current_user.student else None,
            }
        }


class Logout(Resource):

    def post(self):
        session.clear()
        return {"message": "Logged out."}


class StudentProfile(Resource):

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
        return {
            "user": {
                "id": current_user.id,
                "email": current_user.email,
                "role": current_user.role,
                "status": current_user.status,
                "name": current_user.student.name,
                "department": current_user.student.department,
                "phone": current_user.student.phone,
                "student_id": current_user.student.id if current_user.student else None,
                "examiner_id": current_user.examiner.id if current_user.examiner else None,
                "roll_number": current_user.student.roll_number if current_user.student else None,
            }
        }

    def put(self):
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
        data = request.get_json()
        if not isinstance(data, dict):
            return ({"message": "A JSON object is required."}, 400)
        name = data.get("name", "")
        if not isinstance(name, str) or len(name.strip()) > 120 or (not name.strip()):
            return ({"message": "Invalid name."}, 400)
        name = name.strip()
        current_user.student.name = name
        department = data.get("department", "")
        if (
            not isinstance(department, str)
            or len(department.strip()) > 100
            or (not department.strip())
        ):
            return ({"message": "Invalid department."}, 400)
        department = department.strip()
        current_user.student.department = department
        phone = data.get("phone", "")
        if not isinstance(phone, str) or len(phone.strip()) > 30 or (not phone.strip()):
            return ({"message": "Invalid phone."}, 400)
        phone = phone.strip()
        current_user.student.phone = phone
        db.session.commit()
        return {
            "user": {
                "id": current_user.id,
                "email": current_user.email,
                "role": current_user.role,
                "status": current_user.status,
                "name": current_user.student.name,
                "department": current_user.student.department,
                "phone": current_user.student.phone,
                "student_id": current_user.student.id if current_user.student else None,
                "examiner_id": current_user.examiner.id if current_user.examiner else None,
                "roll_number": current_user.student.roll_number if current_user.student else None,
            }
        }
