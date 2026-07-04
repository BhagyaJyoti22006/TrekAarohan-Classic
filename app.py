import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User


def create_app():
    app = Flask(__name__)
    
    # Core configuration
    app.config["SECRET_KEY"] = "super-secret-tac-key"
    app.config["ROLE_MAP"] = {0: "trekker", 1: "staff", 2: "admin"}
    
    # Database configuration
    base_dir = os.path.abspath(os.path.dirname(__file__))
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(base_dir, "instance", "tac.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    
    # Uploads and Images configuration
    upload_folder = os.path.join(base_dir, "static", "uploads")
    image_folder = os.path.join(base_dir, "static", "images")
    app.config["UPLOAD_FOLDER"] = upload_folder
    app.config["IMAGE_FOLDER"] = image_folder
    
    # Ensure necessary directories exist
    os.makedirs(os.path.join(base_dir, "instance"), exist_ok=True)
    os.makedirs(upload_folder, exist_ok=True)
    os.makedirs(image_folder, exist_ok=True)
    
    # Initialize Database
    db.init_app(app)
    
    # Initialize Auth
    login_manager = LoginManager()
    login_manager.login_view = "login"
    login_manager.init_app(app)
    
    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))
    
    
    # Dummy home route
    @app.route("/")
    def home():
        return render_template("public_home.html")
    
    
    # Dummy Dashboards
    @app.route("/admin/dashboard")
    @login_required
    def admin_dashboard():
        return render_template("admin_dashboard.html")
    
    @app.route("/staff/dashboard")
    @login_required
    def staff_dashboard():
        return render_template("staff_dashboard.html")
    
    @app.route("/trekker/dashboard")
    @login_required
    def trekker_dashboard():
        return render_template("trekker_dashboard.html")
    
    
    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            role_name = app.config["ROLE_MAP"].get(current_user.role, "trekker")
            return redirect(url_for(f"{role_name}_dashboard"))
        if request.method == "POST":
            username = request.form.get("username")
            password = request.form.get("password")
            user = User.query.filter_by(username=username).first()
            if user and check_password_hash(user.password, password):
                if user.role == 1 and not user.is_approved:
                    flash("Your staff account is pending admin approval.", "error")
                    return redirect(url_for("login"))
                login_user(user)
                role_name = app.config["ROLE_MAP"].get(user.role, "trekker")
                return redirect(url_for(f"{role_name}_dashboard"))
            flash("Invalid username or password", "error")
        return render_template("login.html")
    
    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        flash("You have been logged out.", "success")
        return redirect(url_for("home"))
    
    @app.route("/register", methods=["GET", "POST"])
    def register():
        if current_user.is_authenticated:
            return redirect(url_for("home"))
        if request.method=="POST":
            username = request.form.get("username")
            password = request.form.get("password")
            name = request.form.get("name")
            email = request.form.get("email")
            phone = request.form.get("phone")
            try:
                role = int(request.form.get("role", 0))
            except ValueError:
                role = 0
            if role != 1:
                role = 0
            user_exists = User.query.filter_by(username=username).first()
            email_exists = User.query.filter_by(email=email).first()
            if user_exists:
                flash("Username already exists.", "error")
            elif email_exists:
                flash("Email already registered.", "error")
            else:
                new_user = User(
                    username=username,
                    password=generate_password_hash(password),
                    name=name,
                    email=email,
                    phone=phone,
                    role=role,
                    is_approved=(False if role==1 else True),  # Staff need admin approval
                )
                db.session.add(new_user)
                db.session.commit()
                flash("Registration successful! Please log in.", "success")
                return redirect(url_for("login"))
        return render_template("register.html")
    
    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)

