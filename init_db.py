from app import create_app
from models import db, User
from werkzeug.security import generate_password_hash

app = create_app()

with app.app_context():
    # Create all database tables
    db.create_all()
    # Create a default admin user if one doesn't exist
    admin = User.query.filter_by(username="admin").first()
    if not admin:
        admin_user = User(
            username="admin",
            password=generate_password_hash("admin123"),
            role=2,  # 2 = Admin
            name="System Administrator",
            email="admin@tac.com",
            phone="0000000000",
            is_approved=True,
            is_blacklisted=False,
        )
        db.session.add(admin_user)
        db.session.commit()
        print("Database 'tac.db' created successfully.")
        print("Default Admin user generated (Username: admin | Password: admin123).")
    else:
        print("Database already initialized.")

