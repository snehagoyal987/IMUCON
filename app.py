from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from pymongo import MongoClient, ReturnDocument
from dotenv import load_dotenv
from gridfs import GridFS
from werkzeug.utils import secure_filename

import os
import re
from datetime import datetime


# ============================================================
# LOAD ENVIRONMENT VARIABLES
# ============================================================

load_dotenv()


# ============================================================
# IMUCON REGISTRATION BACKEND
# ============================================================

app = Flask(__name__)
CORS(app)


# ============================================================
# PATH CONFIGURATION
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Website files are inside the IMUCON folder
WEBSITE_FOLDER = BASE_DIR

# Vercel writable temporary uploads folder
UPLOAD_FOLDER = os.path.join("/tmp", "uploads")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# Maximum upload size = 10 MB
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024


# ============================================================
# MONGODB CONFIGURATION
# ============================================================

MONGO_URI = os.getenv("MONGO_URI")

if not MONGO_URI:
    raise RuntimeError(
        "MONGO_URI environment variable is not set."
    )


# Connect to MongoDB Atlas
client = MongoClient(MONGO_URI)

# Database
db = client["IMUCON_Registration"]

# Collections
registrations_collection = db["registrations"]
counters_collection = db["counters"]

# GridFS for payment screenshots
fs = GridFS(db)


# ============================================================
# ALLOWED PAYMENT SCREENSHOT TYPES
# ============================================================

ALLOWED_EXTENSIONS = {
    "png",
    "jpg",
    "jpeg",
    "webp"
}


# ============================================================
# FILE VALIDATION
# ============================================================

def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower()
        in ALLOWED_EXTENSIONS
    )


# ============================================================
# EMAIL VALIDATION
# ============================================================

def valid_email(email):
    return bool(
        re.fullmatch(
            r"[^@\s]+@[^@\s]+\.[^@\s]+",
            email
        )
    )


# ============================================================
# MOBILE VALIDATION
# ============================================================

def valid_mobile(mobile):
    return bool(
        re.fullmatch(
            r"[0-9]{10}",
            mobile
        )
    )


# ============================================================
# GENERATE REGISTRATION ID
# ============================================================

def generate_registration_id():

    counter = counters_collection.find_one_and_update(
        {"_id": "registration_id"},
        {
            "$inc": {
                "value": 1
            }
        },
        upsert=True,
        return_document=ReturnDocument.AFTER
    )

    next_number = counter["value"]

    registration_id = (
        f"IMUCON26-{next_number:05d}"
    )

    return registration_id


# ============================================================
# HOME PAGE
# ============================================================

@app.route("/")
def home():

    return send_from_directory(
        WEBSITE_FOLDER,
        "index.html"
    )


# ============================================================
# REGISTRATION PAGE
# ============================================================

@app.route("/registration")
def registration():

    return send_from_directory(
        WEBSITE_FOLDER,
        "registration.html"
    )


# ============================================================
# WEBSITE STATIC FILES
# ============================================================

@app.route("/<path:filename>")
def static_files(filename):

    return send_from_directory(
        WEBSITE_FOLDER,
        filename
    )


# ============================================================
# PAYMENT SCREENSHOT
# ============================================================

@app.route("/uploads/<filename>")
def uploaded_file(filename):

    return send_from_directory(
        UPLOAD_FOLDER,
        filename
    )


# ============================================================
# API STATUS
# ============================================================

@app.route("/api/status")
def api_status():

    try:

        # Test MongoDB connection
        client.admin.command("ping")

        return jsonify({
            "status": "running",
            "database": "connected",
            "message": (
                "IMUCON Registration API is running "
                "and MongoDB is connected."
            )
        })

    except Exception as e:

        return jsonify({
            "status": "running",
            "database": "disconnected",
            "message": "MongoDB connection failed.",
            "error": str(e)
        }), 500


# ============================================================
# REGISTRATION API
# ============================================================

@app.route("/api/register", methods=["POST"])
def register():

    screenshot_file_id = None

    try:

        # ====================================================
        # REGISTRATION INFORMATION
        # ====================================================

        pass_category = request.form.get(
            "passCategory",
            ""
        ).strip()

        registration_type = request.form.get(
            "registrationType",
            ""
        ).strip()

        attendee_count_value = request.form.get(
            "attendeeCount",
            ""
        ).strip()

        heard_from = request.form.get(
            "heardFrom",
            ""
        ).strip()

        transaction_id = request.form.get(
            "transactionId",
            ""
        ).strip()


        # ====================================================
        # VALIDATE PASS CATEGORY
        # ====================================================

        allowed_categories = {
            "student",
            "staff",
            "general",
            "vip"
        }

        if pass_category not in allowed_categories:

            return jsonify({
                "success": False,
                "message": (
                    "Please select a valid pass category."
                )
            }), 400


        # ====================================================
        # VALIDATE REGISTRATION TYPE
        # ====================================================

        if registration_type not in {
            "single",
            "group"
        }:

            return jsonify({
                "success": False,
                "message": (
                    "Please select a valid registration type."
                )
            }), 400


        # ====================================================
        # ATTENDEE COUNT
        # ====================================================

        if registration_type == "single":

            attendee_count = 1

        else:

            try:

                attendee_count = int(
                    attendee_count_value
                )

            except ValueError:

                return jsonify({
                    "success": False,
                    "message": (
                        "Please select the number "
                        "of attendees."
                    )
                }), 400


            if attendee_count < 2 or attendee_count > 10:

                return jsonify({
                    "success": False,
                    "message": (
                        "Group registration must contain "
                        "2 to 10 attendees."
                    )
                }), 400


        # ====================================================
        # TRANSACTION ID
        # ====================================================

        if not transaction_id:

            return jsonify({
                "success": False,
                "message": (
                    "Please enter the Transaction ID / "
                    "UTR number."
                )
            }), 400


        # ====================================================
        # PAYMENT SCREENSHOT
        # ====================================================

        screenshot = request.files.get(
            "paymentScreenshot"
        )

        if not screenshot:

            return jsonify({
                "success": False,
                "message": (
                    "Please upload your payment screenshot."
                )
            }), 400


        if screenshot.filename == "":

            return jsonify({
                "success": False,
                "message": (
                    "Please select a payment screenshot."
                )
            }), 400


        if not allowed_file(
            screenshot.filename
        ):

            return jsonify({
                "success": False,
                "message": (
                    "Invalid image format. "
                    "Please upload PNG, JPG, JPEG "
                    "or WEBP."
                )
            }), 400


        # ====================================================
        # COLLECT ATTENDEE INFORMATION
        # ====================================================

        attendees = []

        for i in range(
            1,
            attendee_count + 1
        ):

            name = request.form.get(
                f"attendee_{i}_name",
                ""
            ).strip()

            dob = request.form.get(
                f"attendee_{i}_dob",
                ""
            ).strip()

            gender = request.form.get(
                f"attendee_{i}_gender",
                ""
            ).strip()

            email = request.form.get(
                f"attendee_{i}_email",
                ""
            ).strip()

            mobile = request.form.get(
                f"attendee_{i}_mobile",
                ""
            ).strip()

            employee_id = request.form.get(
                f"attendee_{i}_employee_id",
                ""
            ).strip()

            id_card_no = request.form.get(
                f"attendee_{i}_id_card",
                ""
            ).strip()


            # =================================================
            # NAME
            # =================================================

            if not name:

                return jsonify({
                    "success": False,
                    "message": (
                        f"Please enter the full name "
                        f"of attendee {i}."
                    )
                }), 400


            # =================================================
            # DOB
            # =================================================

            if not dob:

                return jsonify({
                    "success": False,
                    "message": (
                        f"Please enter the date of birth "
                        f"of attendee {i}."
                    )
                }), 400


            # =================================================
            # GENDER
            # =================================================

            if not gender:

                return jsonify({
                    "success": False,
                    "message": (
                        f"Please select gender "
                        f"for attendee {i}."
                    )
                }), 400


            # =================================================
            # EMAIL
            # =================================================

            if not valid_email(email):

                return jsonify({
                    "success": False,
                    "message": (
                        f"Please enter a valid email "
                        f"for attendee {i}."
                    )
                }), 400


            # =================================================
            # MOBILE
            # =================================================

            if not valid_mobile(mobile):

                return jsonify({
                    "success": False,
                    "message": (
                        f"Mobile number for attendee {i} "
                        "must contain exactly 10 digits."
                    )
                }), 400


            # =================================================
            # STORE ATTENDEE
            # =================================================

            attendees.append({

                "name": name,

                "dob": dob,

                "gender": gender,

                "email": email,

                "mobile": mobile,

                "employee_id": employee_id,

                "id_card_no": id_card_no

            })


        # ====================================================
        # GENERATE REGISTRATION ID
        # ====================================================

        registration_id = (
            generate_registration_id()
        )


        # ====================================================
        # SAVE PAYMENT SCREENSHOT TO MONGODB
        # ====================================================

        original_filename = secure_filename(
            screenshot.filename
        )

        extension = original_filename.rsplit(
            ".",
            1
        )[1].lower()


        screenshot_filename = (
            f"{registration_id}_payment."
            f"{extension}"
        )


        # Read screenshot
        screenshot_data = screenshot.read()


        # Store screenshot in MongoDB GridFS
        screenshot_file_id = fs.put(
            screenshot_data,
            filename=screenshot_filename,
            content_type=screenshot.content_type,
            registration_id=registration_id
        )


        # ====================================================
        # CREATE REGISTRATION DOCUMENT
        # ====================================================

        registration_document = {

            "registration_id": registration_id,

            "pass_category": pass_category,

            "registration_type": registration_type,

            "attendee_count": attendee_count,

            "heard_from": heard_from,

            "transaction_id": transaction_id,

            "payment_screenshot": {

                "file_id": screenshot_file_id,

                "filename": screenshot_filename

            },

            "status": "Pending",

            "attendees": attendees,

            "created_at": datetime.utcnow()

        }


        # ====================================================
        # SAVE REGISTRATION TO MONGODB
        # ====================================================

        registrations_collection.insert_one(
            registration_document
        )


        # ====================================================
        # SUCCESS RESPONSE
        # ====================================================

        return jsonify({

            "success": True,

            "message": (
                "Registration submitted successfully!"
            ),

            "registration_id": registration_id

        }), 201


    # ========================================================
    # ERROR HANDLING
    # ========================================================

    except Exception as e:

        # If registration fails after screenshot upload,
        # remove the screenshot from GridFS.

        if screenshot_file_id:

            try:

                fs.delete(
                    screenshot_file_id
                )

            except Exception:

                pass


        print(
            "REGISTRATION ERROR:",
            str(e)
        )


        return jsonify({

            "success": False,

            "message": (
                "Registration could not be completed."
            ),

            "error": str(e)

        }), 500


# ============================================================
# RUN FLASK SERVER
# ============================================================

if __name__ == "__main__":

    print()
    print("========================================")
    print("      IMUCON REGISTRATION BACKEND")
    print("========================================")
    print()

    print("Website:")
    print("http://127.0.0.1:5000")

    print()

    print("Registration:")
    print("http://127.0.0.1:5000/registration")

    print()

    print("API:")
    print("http://127.0.0.1:5000/api/status")

    print()

    print("========================================")
    print()


    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
