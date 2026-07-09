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
        booking_status = None
        if current_user.is_authenticated and current_user.role == 0:
            booking = Booking.query.filter(Booking.user_id == current_user.id, Booking.trek_id == id, Booking.status != "cancelled").first()
            if booking:
                booking_status = booking.status
        return render_template("public_trek_detail.html", trek=trek, staff_completed_treks=staff_completed_treks, booking_status=booking_status)
    
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
        if current_user.role != 2:
            return redirect(url_for("home"))
        treks = Trek.query.count()
        bookings = Booking.query.filter_by(status="booked").count()
        users = User.query.filter(User.role.in_([0, 1])).count()
        pendings = User.query.filter_by(role=1, is_approved=False).count()
        q = request.args.get("q", "").strip()
        role = request.args.get("role", "")
        status = request.args.get("status", "")
        query = User.query
        if q:
            if q.isdigit():
                query = query.filter(db.or_(User.id == int(q), User.name.ilike(f"%{q}%"), User.username.ilike(f"%{q}%")))
            else:
                query = query.filter(db.or_(User.name.ilike(f"%{q}%"), User.username.ilike(f"%{q}%")))
        if role and role.isdigit():
            query = query.filter(User.role == int(role))
        if status:
            if status == "blacklisted":
                query = query.filter(User.is_blacklisted == True)
            elif status == "pending":
                query = query.filter(User.is_blacklisted == False, User.role == 1, User.is_approved == False)
            elif status == "active":
                query = query.filter(User.is_blacklisted == False, db.or_(User.role != 1, User.is_approved == True))
        all_users = query.order_by(User.id.desc()).all()
        return render_template("admin_dashboard.html", total_treks=treks, total_bookings=bookings, total_users=users, pending_staffs=pendings, all_users=all_users, current_q=q, current_role=role, current_status=status)
    
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
            if difficulty not in ["easy", "medium", "hard"]:
                flash("Invalid difficulty level.", "error")
                return redirect(request.url)
            slots_available = int(request.form.get("slots_available", 0))
            price = float(request.form.get("price", 0.0))
            assigned_staff_id = int(request.form.get("assigned_staff_id"))
            try:
                start_date = datetime.strptime(request.form.get("start_date"), "%Y-%m-%d").date()
                end_date = datetime.strptime(request.form.get("end_date"), "%Y-%m-%d").date()
                if end_date < start_date:
                    flash("End date cannot be before start date.", "error")
                    return redirect(request.url)
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
            if trek.status in ["completed", "cancelled"]:
                flash("This trek has concluded and cannot be edited.", "error")
                return redirect(url_for("admin_treks_edit", id=trek.id))
            trek.name = request.form.get("name")
            trek.location = request.form.get("location")
            trek.description = request.form.get("description")
            difficulty = request.form.get("difficulty")
            if difficulty not in ["easy", "medium", "hard"]:
                flash("Invalid difficulty level.", "error")
                return redirect(request.url)
            trek.difficulty = difficulty
            slots_available = int(request.form.get("slots_available", 0))
            trek.price = float(request.form.get("price", 0.0))
            trek.assigned_staff_id = int(request.form.get("assigned_staff_id"))
            # Status & Slots logic
            new_status = request.form.get("status")
            valid_statuses = ["open", "full", "ongoing", "completed", "cancelled"]
            if new_status in valid_statuses:
                if new_status == "full" or (new_status == "open" and slots_available <= 0):
                    trek.status = "full"
                    trek.slots_available = 0
                else:
                    trek.status = new_status
                    trek.slots_available = slots_available
                if new_status == "cancelled":
                    active_bookings = Booking.query.filter_by(trek_id=trek.id, status="booked").all()
                    for b in active_bookings:
                        b.status = "cancelled"
                        b.cancelled_date = datetime.utcnow()
                elif new_status == "completed":
                    active_bookings = Booking.query.filter_by(trek_id=trek.id, status="booked").all()
                    for b in active_bookings:
                        b.status = "completed"
            else:
                flash("Invalid status.", "error")
                return redirect(request.url)
            try:
                trek.start_date = datetime.strptime(request.form.get("start_date"), "%Y-%m-%d").date()
                trek.end_date = datetime.strptime(request.form.get("end_date"), "%Y-%m-%d").date()
                if trek.end_date < trek.start_date:
                    flash("End date cannot be before start date.", "error")
                    return redirect(request.url)
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
        bookings = Booking.query.filter_by(trek_id=trek.id).order_by(Booking.booking_date.desc()).all()
        return render_template("admin_trek_form.html", trek=trek, staff=staff, bookings=bookings)
    
    @app.route("/admin/staffs")
    @login_required
    def admin_staffs():
        if current_user.role != 2:
            return redirect(url_for("home"))
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
        if current_user.role != 2:
            return redirect(url_for("home"))
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
        if current_user.role != 2:
            return redirect(url_for("home"))
        bookings = Booking.query.order_by(Booking.booking_date.desc()).all()
        return render_template("admin_bookings.html", bookings=bookings)
    
    @app.route("/admin/cancel_booking/<int:booking_id>", methods=["POST"])
    @login_required
    def admin_cancel_participant(booking_id):
        if current_user.role != 2:
            return redirect(url_for("home"))
        booking = Booking.query.get_or_404(booking_id)
        trek = booking.trek
        if booking.status != "booked":
            flash("This booking cannot be cancelled.", "error")
            return redirect(url_for("admin_bookings"))
        if trek.status in ["completed", "cancelled"]:
            flash("You cannot cancel a booking for a trek that has already concluded.", "error")
            return redirect(url_for("admin_bookings"))
        booking.status = "cancelled"
        booking.cancelled_date = datetime.utcnow()
        trek.slots_available += 1
        if trek.status == "full":
            trek.status = "open"
        db.session.commit()
        flash("Booking cancelled successfully. Slot reopened.", "success")
        return redirect(request.referrer or url_for("admin_bookings"))
    
    
    # Staff Dashboard
    @app.route("/staff/dashboard")
    @login_required
    def staff_dashboard():
        if current_user.role != 1 or not current_user.is_approved:
            return redirect(url_for("home"))
        assigned_treks = Trek.query.filter_by(assigned_staff_id=current_user.id).all()
        total_treks = len(assigned_treks)
        active_trek_ids = [t.id for t in assigned_treks if t.status not in ["completed", "cancelled"]]
        active_participants = 0
        if active_trek_ids:
            active_participants = Booking.query.filter(Booking.trek_id.in_(active_trek_ids), Booking.status == "booked").count()
        all_trek_ids = [t.id for t in assigned_treks]
        unique_trekkers = 0
        if all_trek_ids:
            unique_trekkers = db.session.query(Booking.user_id).filter(Booking.trek_id.in_(all_trek_ids), Booking.status == "booked").distinct().count()
        ongoing_treks_list = [t for t in assigned_treks if t.status == "ongoing"]
        return render_template("staff_dashboard.html", total_treks=total_treks, active_participants=active_participants, unique_trekkers=unique_trekkers, ongoing_treks=ongoing_treks_list)
    
    @app.route("/staff/treks")
    @login_required
    def staff_treks():
        if current_user.role != 1 or not current_user.is_approved:
            return redirect(url_for("home"))
        treks = Trek.query.filter_by(assigned_staff_id=current_user.id).all()
        return render_template("staff_treks.html", treks=treks)
    
    @app.route("/staff/participants")
    @login_required
    def staff_participants():
        if current_user.role != 1 or not current_user.is_approved:
            return redirect(url_for("home"))
        assigned_treks = Trek.query.filter_by(assigned_staff_id=current_user.id).all()
        trek_ids = [t.id for t in assigned_treks]
        if trek_ids:
            bookings = Booking.query.filter(Booking.trek_id.in_(trek_ids)).order_by(Booking.booking_date.desc()).all()
        else:
            bookings = []
        return render_template("staff_participants.html", bookings=bookings)
    
    @app.route("/staff/profile", methods=["GET", "POST"])
    @login_required
    def staff_profile():
        if current_user.role != 1 or not current_user.is_approved:
            return redirect(url_for("home"))
        if request.method == "POST":
            name = request.form.get("name")
            email = request.form.get("email")
            phone = request.form.get("phone")
            emergency_phone = request.form.get("emergency_phone")
            emergency_relation = request.form.get("emergency_relation")
            experience = request.form.get("experience")
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
                    current_user.experience = experience
                    db.session.commit()
                    flash("Profile updated successfully.", "success")
                    return redirect(url_for("staff_profile"))
        return render_template("staff_profile.html")
    
    @app.route("/staff/trek/<int:trek_id>", methods=["GET", "POST"])
    @login_required
    def staff_trek_manage(trek_id):
        if current_user.role != 1 or not current_user.is_approved:
            return redirect(url_for("home"))
        trek = Trek.query.get_or_404(trek_id)
        if trek.assigned_staff_id != current_user.id:
            flash("You do not have permission to manage this trek.", "error")
            return redirect(url_for("staff_treks"))
        if request.method == "POST":
            if trek.status in ["completed", "cancelled"]:
                flash("This trek has concluded and cannot be managed.", "error")
                return redirect(url_for("staff_trek_manage", trek_id=trek.id))
            new_status = request.form.get("status")
            new_slots = request.form.get("slots_available")
            valid_statuses = ["open", "full", "ongoing", "completed", "cancelled"]
            if new_status in valid_statuses:
                trek.status = new_status
                if new_status == "cancelled":
                    active_bookings = Booking.query.filter_by(trek_id=trek.id, status="booked").all()
                    for b in active_bookings:
                        b.status = "cancelled"
                        b.cancelled_date = datetime.utcnow()
                elif new_status == "completed":
                    active_bookings = Booking.query.filter_by(trek_id=trek.id, status="booked").all()
                    for b in active_bookings:
                        b.status = "completed"
            if new_slots is not None:
                try:
                    trek.slots_available = int(new_slots)
                except ValueError:
                    pass
            db.session.commit()
            flash("Trek updated successfully.", "success")
            return redirect(url_for("staff_trek_manage", trek_id=trek.id))
        bookings = Booking.query.filter_by(trek_id=trek.id).order_by(Booking.booking_date.desc()).all()
        return render_template("staff_trek_manage.html", trek=trek, bookings=bookings)
    
    @app.route("/staff/cancel_booking/<int:booking_id>", methods=["POST"])
    @login_required
    def staff_cancel_participant(booking_id):
        if current_user.role != 1 or not current_user.is_approved:
            return redirect(url_for("home"))
        booking = Booking.query.get_or_404(booking_id)
        trek = booking.trek
        if trek.assigned_staff_id != current_user.id:
            flash("You do not have permission to manage this booking.", "error")
            return redirect(url_for("staff_participants"))
        if booking.status != "booked":
            flash("This booking cannot be cancelled.", "error")
            return redirect(url_for("staff_participants"))
        if trek.status in ["completed", "cancelled"]:
            flash("You cannot cancel a booking for a trek that has already concluded.", "error")
            return redirect(url_for("staff_participants"))
        booking.status = "cancelled"
        booking.cancelled_date = datetime.utcnow()
        trek.slots_available += 1
        if trek.status == "full":
            trek.status = "open"
        db.session.commit()
        flash("Booking cancelled successfully. Slot reopened.", "success")
        return redirect(request.referrer or url_for("staff_participants"))
    
    
    # Trekker Dashboard
    @app.route("/trekker/dashboard")
    @login_required
    def trekker_dashboard():
        if current_user.role != 0:
            return redirect(url_for("home"))
        bookings = Booking.query.filter_by(user_id=current_user.id).order_by(Booking.booking_date.desc()).all()
        booked_trek_ids = [b.trek_id for b in bookings if b.status == "booked"]
        q = request.args.get("q", "").strip()
        difficulty = request.args.get("difficulty", "")
        max_price = request.args.get("max_price", "").strip()
        query = Trek.query.filter(Trek.status == "open")
        if booked_trek_ids:
            query = query.filter(~Trek.id.in_(booked_trek_ids))
        if q:
            query = query.filter(db.or_(Trek.name.ilike(f"%{q}%"), Trek.location.ilike(f"%{q}%")))
        if difficulty:
            query = query.filter(Trek.difficulty == difficulty)
        if max_price:
            try:
                query = query.filter(Trek.price <= float(max_price))
            except ValueError:
                pass
        available_treks = query.order_by(Trek.start_date.asc()).all()
        return render_template("trekker_dashboard.html", bookings=bookings, available_treks=available_treks, current_q=q, current_difficulty=difficulty, current_max_price=max_price)
    
    @app.route("/trekker/bookings")
    @login_required
    def trekker_bookings():
        if current_user.role != 0:
            return redirect(url_for("home"))
        active_bookings = Booking.query.filter_by(user_id=current_user.id, status="booked").order_by(Booking.booking_date.desc()).all()
        return render_template("trekker_bookings.html", bookings=active_bookings)
    
    @app.route("/trekker/history")
    @login_required
    def trekker_history():
        if current_user.role != 0:
            return redirect(url_for("home"))
        historical_bookings = Booking.query.filter(
            Booking.user_id == current_user.id,
            Booking.status.in_(["completed", "cancelled"])
        ).order_by(Booking.booking_date.desc()).all()
        return render_template("trekker_history.html", bookings=historical_bookings)
    
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
        trek = booking.trek
        if booking.user_id != current_user.id:
            flash("You do not have permission to cancel this booking.", "error")
            return redirect(url_for("trekker_bookings"))
        if booking.status != "booked":
            flash("This booking cannot be cancelled.", "error")
            return redirect(url_for("trekker_bookings"))
        if trek.status in ["completed", "cancelled"]:
            flash("You cannot cancel a booking for a trek that has already concluded.", "error")
            return redirect(url_for("trekker_bookings"))
        booking.status = "cancelled"
        booking.cancelled_date = datetime.utcnow()
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

