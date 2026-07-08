import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from models import db, User, Trek, Booking


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
    
    
    # Home Route
    @app.route("/")
    def home():
        featured_treks = Trek.query.filter_by(status="open").order_by(Trek.id.desc()).limit(3).all()
        return render_template("public_home.html", featured_treks=featured_treks)
    
    @app.route("/treks")
    def public_treks():
        q = request.args.get("q", "").strip()
        difficulty = request.args.get("difficulty", "")
        max_price = request.args.get("max_price", "").strip()
        query = Trek.query.filter_by(status="open")
        if q:
            query = query.filter(db.or_(Trek.name.ilike(f"%{q}%"), Trek.location.ilike(f"%{q}%")))
        if difficulty:
            query = query.filter(Trek.difficulty == difficulty)
        if max_price:
            try:
                query = query.filter(Trek.price <= float(max_price))
            except ValueError:
                pass
        treks = query.order_by(Trek.start_date.asc()).all()
        return render_template("public_treks.html", treks=treks, current_q=q, current_difficulty=difficulty, current_max_price=max_price)
    
    @app.route("/trek/<int:id>")
    def public_trek_detail(id):
        trek = Trek.query.get_or_404(id)
        staff_completed_treks = Trek.query.filter_by(assigned_staff_id=trek.assigned_staff_id, status="completed").count()
        has_booked = False
        if current_user.is_authenticated and current_user.role == 0:
            has_booked = Booking.query.filter_by(user_id=current_user.id, trek_id=id, status="booked").first() is not None
        return render_template("public_trek_detail.html", trek=trek, staff_completed_treks=staff_completed_treks, has_booked=has_booked)
    
    @app.route("/about")
    def public_about():
        return render_template("public_about.html")
    
    @app.route("/footer")
    def public_footer():
        return render_template("public_footer.html")
    
    
    # Admin Dashboard
    @app.route("/admin/dashboard")
    @login_required
    def admin_dashboard():
        return render_template("admin_dashboard.html")
    
    @app.route("/admin/treks")
    @login_required
    def admin_treks():
        if current_user.role != 2:
            return redirect(url_for("home"))
        q = request.args.get("q", "").strip()
        difficulty = request.args.get("difficulty", "")
        status = request.args.get("status", "")
        query = Trek.query
        if q:
            query = query.filter(db.or_(Trek.name.ilike(f"%{q}%"), Trek.location.ilike(f"%{q}%")))
        if difficulty:
            query = query.filter(Trek.difficulty == difficulty)
        if status:
            query = query.filter(Trek.status == status)
        treks = query.order_by(Trek.id.desc()).all()
        return render_template("admin_treks.html", treks=treks, current_q=q, current_difficulty=difficulty, current_status=status)
    
    @app.route("/admin/treks/add", methods=["GET", "POST"])
    @login_required
    def admin_treks_add():
        if current_user.role != 2:
            return redirect(url_for("home"))
        if request.method == "POST":
            name = request.form.get("name")
            location = request.form.get("location")
            description = request.form.get("description")
            difficulty = request.form.get("difficulty")
            slots_available = int(request.form.get("slots_available", 0))
            price = float(request.form.get("price", 0.0))
            assigned_staff_id = int(request.form.get("assigned_staff_id"))
            try:
                start_date = datetime.strptime(request.form.get("start_date"), "%Y-%m-%d").date()
                end_date = datetime.strptime(request.form.get("end_date"), "%Y-%m-%d").date()
            except (ValueError, TypeError):
                flash("Invalid date format.", "error")
                return redirect(request.url)
            new_trek = Trek(
                name=name,
                location=location,
                description=description,
                difficulty=difficulty,
                slots_available=slots_available,
                price=price,
                start_date=start_date,
                end_date=end_date,
                assigned_staff_id=assigned_staff_id,
                cover_image=None,
                status="open"
            )
            db.session.add(new_trek)
            db.session.flush()  # Flush to generate the trek ID before committing
            file = request.files.get("cover_image")
            if file and file.filename != "":
                filename = f"{new_trek.id}-{secure_filename(file.filename)}"
                file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
                new_trek.cover_image = filename
            db.session.commit()
            flash("Trek created successfully!", "success")
            return redirect(url_for("admin_treks"))
        staff = User.query.filter_by(role=1, is_approved=True, is_blacklisted=False).all()
        return render_template("admin_trek_form.html", trek=None, staff=staff)
    
    @app.route("/admin/treks/edit/<int:id>", methods=["GET", "POST"])
    @login_required
    def admin_treks_edit(id):
        if current_user.role != 2:
            return redirect(url_for("home"))
        trek = Trek.query.get_or_404(id)
        if request.method == "POST":
            trek.name = request.form.get("name")
            trek.location = request.form.get("location")
            trek.description = request.form.get("description")
            trek.difficulty = request.form.get("difficulty")
            slots_available = int(request.form.get("slots_available", 0))
            trek.price = float(request.form.get("price", 0.0))
            trek.assigned_staff_id = int(request.form.get("assigned_staff_id"))
            # Status & Slots logic
            new_status = request.form.get("status")
            if new_status == "full" or (new_status == "open" and slots_available == 0):
                trek.status = "full"
                trek.slots_available = 0
            else:
                trek.status = new_status
                trek.slots_available = slots_available
            try:
                trek.start_date = datetime.strptime(request.form.get("start_date"), "%Y-%m-%d").date()
                trek.end_date = datetime.strptime(request.form.get("end_date"), "%Y-%m-%d").date()
            except (ValueError, TypeError):
                flash("Invalid date format.", "error")
                return redirect(request.url)
            file = request.files.get("cover_image")
            if file and file.filename != "":
                filename = f"{trek.id}-{secure_filename(file.filename)}"
                file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
                trek.cover_image = filename
            db.session.commit()
            flash("Trek updated successfully!", "success")
            return redirect(url_for("admin_treks"))
        staff = User.query.filter_by(role=1, is_approved=True, is_blacklisted=False).all()
        assigned_staff = User.query.get(trek.assigned_staff_id)
        if assigned_staff not in staff:
            staff.append(assigned_staff)
        return render_template("admin_trek_form.html", trek=trek, staff=staff)
    
    @app.route("/admin/staffs")
    @login_required
    def admin_staffs():
        staffs = User.query.filter_by(role=1).all()
        return render_template("admin_staffs.html", staffs=staffs)
    
    @app.route("/admin/staffs/<int:id>/<action>")
    @login_required
    def admin_staffs_action(id, action):
        if current_user.role != 2:
            return redirect(url_for("home"))
        staff_user = User.query.get_or_404(id)
        if staff_user.role != 1:
            flash("Invalid user role for this action.", "error")
            return redirect(url_for("admin_staffs"))
        if action == "approve":
            staff_user.is_approved = True
            db.session.commit()
            flash(f"Staff {staff_user.name} approved successfully.", "success")
        elif action == "reject":
            db.session.delete(staff_user)
            db.session.commit()
            flash(f"Staff application for {staff_user.name} rejected.", "success")
        elif action == "blacklist":
            staff_user.is_blacklisted = True
            db.session.commit()
            flash(f"Staff {staff_user.name} has been blacklisted.", "error")
        elif action == "unblacklist":
            staff_user.is_blacklisted = False
            db.session.commit()
            flash(f"Staff {staff_user.name} has been restored.", "success")
        return redirect(url_for("admin_staffs"))
    
    @app.route("/admin/trekkers")
    @login_required
    def admin_trekkers():
        trekkers = User.query.filter_by(role=0).all()
        return render_template("admin_trekkers.html", trekkers=trekkers)
    
    @app.route("/admin/trekkers/<int:id>/<action>")
    @login_required
    def admin_trekkers_action(id, action):
        if current_user.role != 2:
            return redirect(url_for("home"))
        trekker = User.query.get_or_404(id)
        if trekker.role != 0:
            flash("Invalid user role for this action.", "error")
            return redirect(url_for("admin_trekkers"))
        if action == "blacklist":
            trekker.is_blacklisted = True
            db.session.commit()
            flash(f"Trekker {trekker.name} has been blacklisted.", "error")
        elif action == "unblacklist":
            trekker.is_blacklisted = False
            db.session.commit()
            flash(f"Trekker {trekker.name} has been restored.", "success")
        return redirect(url_for("admin_trekkers"))
    
    @app.route("/admin/bookings")
    @login_required
    def admin_bookings():
        return render_template("admin_bookings.html")
    
    
    # Staff Dashboard
    @app.route("/staff/dashboard")
    @login_required
    def staff_dashboard():
        if current_user.role != 1 or not current_user.is_approved:
            return redirect(url_for("home"))
        return render_template("staff_dashboard.html")
    
    @app.route("/staff/treks")
    @login_required
    def staff_treks():
        if current_user.role != 1 or not current_user.is_approved:
            return redirect(url_for("home"))
        return render_template("staff_treks.html")
    
    @app.route("/staff/participants")
    @login_required
    def staff_participants():
        if current_user.role != 1 or not current_user.is_approved:
            return redirect(url_for("home"))
        return render_template("staff_participants.html")
    
    @app.route("/staff/profile", methods=["GET", "POST"])
    @login_required
    def staff_profile():
        if current_user.role != 1 or not current_user.is_approved:
            return redirect(url_for("home"))
        return render_template("staff_profile.html")
    
    
    # Trekker Dashboard
    @app.route("/trekker/dashboard")
    @login_required
    def trekker_dashboard():
        if current_user.role != 0:
            return redirect(url_for("home"))
        bookings = Booking.query.filter_by(user_id=current_user.id).all()
        booked_trek_ids = [b.trek_id for b in bookings if b.status == "booked"]
        if booked_trek_ids:
            available_treks = Trek.query.filter(Trek.status == "open", ~Trek.id.in_(booked_trek_ids)).all()
        else:
            available_treks = Trek.query.filter_by(status="open").all()
        return render_template("trekker_dashboard.html", bookings=bookings, available_treks=available_treks)
    
    @app.route("/trekker/bookings")
    @login_required
    def trekker_bookings():
        if current_user.role != 0:
            return redirect(url_for("home"))
        active_bookings = Booking.query.filter_by(user_id=current_user.id, status="booked").all()
        return render_template("trekker_bookings.html", bookings=active_bookings)
    
    @app.route("/trekker/history")
    @login_required
    def trekker_history():
        if current_user.role != 0:
            return redirect(url_for("home"))
        return render_template("trekker_history.html")
    
    @app.route("/trekker/profile", methods=["GET", "POST"])
    @login_required
    def trekker_profile():
        if current_user.role != 0:
            return redirect(url_for("home"))
        if request.method == "POST":
            name = request.form.get("name")
            email = request.form.get("email")
            phone = request.form.get("phone")
            emergency_phone = request.form.get("emergency_phone")
            emergency_relation = request.form.get("emergency_relation")
            if not name or not phone or not email:
                flash("Name, Email, and Phone number are required.", "error")
            else:
                existing_user = User.query.filter(User.email == email, User.id != current_user.id).first()
                if existing_user:
                    flash("Email is already registered by another user.", "error")
                else:
                    current_user.name = name
                    current_user.email = email
                    current_user.phone = phone
                    current_user.emergency_phone = emergency_phone
                    current_user.emergency_relation = emergency_relation
                    db.session.commit()
                    flash("Profile updated successfully.", "success")
                    return redirect(url_for("trekker_profile"))
        return render_template("trekker_profile.html")
    
    @app.route("/book/<int:trek_id>", methods=["POST"])
    @login_required
    def book_trek(trek_id):
        if current_user.role != 0:
            flash("Only trekkers can book treks.", "error")
            return redirect(url_for("public_trek_detail", id=trek_id))
        if current_user.is_blacklisted:
            flash("Your account is suspended. You cannot book new treks.", "error")
            return redirect(url_for("public_trek_detail", id=trek_id))
        trek = Trek.query.get_or_404(trek_id)
        if trek.status != "open":
            flash("This trek is no longer open for booking.", "error")
            return redirect(url_for("public_trek_detail", id=trek_id))
        if trek.slots_available <= 0:
            flash("This trek is sold out.", "error")
            return redirect(url_for("public_trek_detail", id=trek_id))
        existing_booking = Booking.query.filter_by(user_id=current_user.id, trek_id=trek.id, status="booked").first()
        if existing_booking:
            flash("You have already booked this trek.", "error")
            return redirect(url_for("public_trek_detail", id=trek_id))
        new_booking = Booking(user_id=current_user.id, trek_id=trek.id)
        trek.slots_available -= 1
        if trek.slots_available == 0:
            trek.status = "full"
        db.session.add(new_booking)
        db.session.commit()
        flash(f"Successfully booked {trek.name}!", "success")
        return redirect(url_for("trekker_bookings"))
    
    @app.route("/cancel_booking/<int:booking_id>", methods=["POST"])
    @login_required
    def cancel_booking(booking_id):
        if current_user.role != 0:
            return redirect(url_for("home"))
        booking = Booking.query.get_or_404(booking_id)
        if booking.user_id != current_user.id:
            flash("You do not have permission to cancel this booking.", "error")
            return redirect(url_for("trekker_bookings"))
        if booking.status != "booked":
            flash("This booking cannot be cancelled.", "error")
            return redirect(url_for("trekker_bookings"))
        if booking.trek.status in ["completed", "cancelled"]:
            flash("You cannot cancel a booking for a trek that has already concluded.", "error")
            return redirect(url_for("trekker_bookings"))
        booking.status = "cancelled"
        booking.cancelled_date = datetime.utcnow()
        trek = booking.trek
        trek.slots_available += 1
        if trek.status == "full":
            trek.status = "open"
        db.session.commit()
        flash(f"Your booking for '{trek.name}' has been successfully cancelled.", "success")
        return redirect(url_for("trekker_bookings"))
    
    
    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        flash("You have been logged out.", "success")
        return redirect(url_for("home"))
    
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
    
    @app.route("/register", methods=["GET", "POST"])
    def register():
        if current_user.is_authenticated:
            return redirect(url_for("home"))
        if request.method == "POST":
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
                    is_approved=(False if role == 1 else True),  # Staff need admin approval
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

