import os
from flask import Flask, render_template


def create_app():
    app = Flask(__name__)
    
    # Core configuration
    app.config["SECRET_KEY"] = "super-secret-tac-key"
    
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
    
    # Dummy home route
    @app.route("/")
    def home():
        return render_template("public_home.html")
    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)

