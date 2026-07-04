from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin


db = SQLAlchemy()


class User(db.Model, UserMixin):
    __tablename__ = "user"
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Integer, default=0, nullable=False)  # 0 = Trekker, 1 = Staff, 2 = Admin
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    
    # Nullable fields (Not shown during registration)
    emergency_phone = db.Column(db.String(20), nullable=True)
    emergency_relation = db.Column(db.String(50), nullable=True)
    experience = db.Column(db.Text, nullable=True)  # Used for Staff
    
    # Flags
    is_approved = db.Column(db.Boolean, default=False)  # Used for Staff
    is_blacklisted = db.Column(db.Boolean, default=False)
    
    # Relationships
    assigned_treks = db.relationship("Trek", backref="staff", lazy=True)
    bookings = db.relationship("Booking", backref="user", lazy=True)


class Trek(db.Model):
    __tablename__ = "trek"
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    difficulty = db.Column(db.String(20), nullable=False)  # "easy", "medium", "hard"
    location = db.Column(db.String(100), nullable=False)
    slots_available = db.Column(db.Integer, nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default="open", nullable=False)  # "open", "full", "ongoing", "completed", "cancelled"
    assigned_staff_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    cover_image = db.Column(db.String(255), nullable=True)
    price = db.Column(db.Float, default=0.0, nullable=False)
    
    # Relationships
    bookings = db.relationship("Booking", backref="trek", lazy=True)


class Booking(db.Model):
    __tablename__ = "booking"
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    trek_id = db.Column(db.Integer, db.ForeignKey("trek.id"), nullable=False)
    booking_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    cancelled_date = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default="booked", nullable=False)  # "booked", "cancelled", "completed"

