from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from pymongo import MongoClient, ReturnDocument
from dotenv import load_dotenv
from gridfs import GridFS
from werkzeug.utils import secure_filename

import os
import re
import smtplib
from email.message import EmailMessage
from datetime import datetime


# ============================================================
# LOAD ENVIRONMENT VARIABLES
# ============================================================

load_dotenv()


# ============================================================
# FLASK APPLICATION
# ============================================================

app = Flask(__name__)
CORS(app)


# ============================================================
# EMAIL CONFIGURATION
# ============================================================

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")


def send_confirmation_email(
    to_email,
    registration_id,
    name,
    pass_name,
    pass_amount
):
    try:
        # Check email configuration
        if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
            print(
                "EMAIL_ADDRESS or EMAIL_PASSWORD "
                "is not configured."
            )
            return False

        # Create email
        msg = EmailMessage()

        msg["Subject"] = (
            f"IMUCON 2.0 Registration Confirmation - "
            f"{registration_id}"
        )

        msg["From"] = EMAIL_ADDRESS
        msg["To"] = to_email

        # Email content
        msg.set_content(
            f"""
Dear {name},

Thank you for registering for IMUCON 2.0 –
International Medicine Update Conference.

Your registration has been successfully received.

Registration Details
--------------------------------

Registration ID:
{registration_id}

Pass:
{pass_name}

Amount Paid:
₹{pass_amount}

Conference Dates:
15th–18th December 2026

Venue:
College Council Room, 5th Floor,
SMS&R & Sharda Hospital,
Greater Noida

Your registration is currently under verification.

Please keep your Registration ID for future communication.

Regards,
IMUCON 2.0 Team
Sharda Hospital
"""
        )

        # Connect to Gmail SMTP
        with smtplib.SMTP_SSL(
            "smtp.gmail.com",
            465
        ) as smtp:

            smtp.login(
                EMAIL_ADDRESS,
                EMAIL_PASSWORD
            )

            smtp.send_message(msg)

        print(
            f"Confirmation email sent successfully "
            f"to {to_email}"
        )

        return True

    except Exception as e:
        print(
            "EMAIL SENDING ERROR:",
            str(e)
        )
        return False


# ============================================================
# PATH CONFIGURATION
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

WEBSITE_FOLDER = BASE_DIR

# Vercel writable temporary folder
UPLOAD_FOLDER = os.path.join(
    "/tmp",
    "uploads"
)

os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# Maximum upload size = 10 MB
app.config["MAX_CONTENT_LENGTH"] = (
    10 * 1024 * 1024
)


# ============================================================
# MONGODB CONFIGURATION
# ============================================================

MONGO_URI = os.getenv("MONGO_URI")

if not MONGO_URI:
    raise RuntimeError(
        "MONGO_URI environment variable is not set."
    )

client = MongoClient(
    MONGO_URI
)

db = client["IMUCON_Registration"]

registrations_collection = db["registrations"]

counters_collection = db["counters"]

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
        and filename.rsplit(
            ".",
            1
        )[1].lower() in ALLOWED_EXTENSIONS
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
        {
            "_id": "registration_id"
        },
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

@app.route(
    "/api/register",
    methods=["POST"]
)
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

            "BLS - ACLS Course Only (Till 1st November 2026)",

            "BLS - ACLS Course Only (After 1st November 2026)",

            "BLS-ACLS Course with Conference Registration (Till 1st November 2026)",

            "BLS-ACLS Course with Conference Registration (After 1st November 2026)",

            "Early Bird IMUCON Registration (Till 1st November 2026)",

            "IMUCON Registration (After 1st November 2026)",

            "Virtual Conference Registration (12 CME Hrs)"
        }

        if pass_category not in allowed_categories:

            return jsonify({
                "success": False,
                "message": (
                    "Please select a valid pass category."
                )
            }), 400


        # ====================================================
        # VALIDATE PASS ACTIVATION DATE
        # ====================================================

        activation_date = datetime(
            2026,
            11,
            1
        )

        after_november_categories = {

            "BLS - ACLS Course Only (After 1st November 2026)",

            "BLS-ACLS Course with Conference Registration (After 1st November 2026)",

            "IMUCON Registration (After 1st November 2026)"
        }

        before_november_categories = {

            "BLS - ACLS Course Only (Till 1st November 2026)",

            "BLS-ACLS Course with Conference Registration (Till 1st November 2026)",

            "Early Bird IMUCON Registration (Till 1st November 2026)"
        }


        # ====================================================
        # AFTER-NOVEMBER CATEGORIES
        # ====================================================

        if (
            pass_category in after_november_categories
            and datetime.now() < activation_date
        ):

            return jsonify({
                "success": False,
                "message": (
                    "This pass category will be available "
                    "from 1 November 2026."
                )
            }), 400


        # ====================================================
        # BEFORE-NOVEMBER CATEGORIES
        # ====================================================

        if (
            pass_category in before_november_categories
            and datetime.now() >= activation_date
        ):

            return jsonify({
                "success": False,
                "message": (
                    "This pass category was available "
                    "until 31 October 2026."
                )
            }), 400


        # ====================================================
        # BLS-ACLS COMBINED 30 SEAT CAPACITY
        # ====================================================

        bls_categories = {

            "BLS - ACLS Course Only (Till 1st November 2026)",

            "BLS-ACLS Course with Conference Registration (Till 1st November 2026)"
        }

        if pass_category in bls_categories:

            bls_count = registrations_collection.count_documents({
                "pass_category": {
                    "$in": list(bls_categories)
                }
            })

            if bls_count >= 30:

                return jsonify({
                    "success": False,
                    "message": (
                        "The BLS-ACLS course capacity "
                        "of 30 registrations has been reached."
                    )
                }), 400


        # ====================================================
        # SINGLE ATTENDEE ONLY
        # ====================================================

        registration_type = "single"
        attendee_count = 1


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
        # COLLECT SINGLE ATTENDEE INFORMATION
        # ====================================================

        attendees = []

        name = request.form.get(
            "attendee_1_name",
            ""
        ).strip()

        dob = request.form.get(
            "attendee_1_dob",
            ""
        ).strip()

        gender = request.form.get(
            "attendee_1_gender",
            ""
        ).strip()

        email = request.form.get(
            "attendee_1_email",
            ""
        ).strip()

        mobile = request.form.get(
            "attendee_1_mobile",
            ""
        ).strip()


        # ====================================================
        # NAME VALIDATION
        # ====================================================

        if not name:

            return jsonify({
                "success": False,
                "message": (
                    "Please enter the full name."
                )
            }), 400


        # ====================================================
        # DOB VALIDATION
        # ====================================================

        if not dob:

            return jsonify({
                "success": False,
                "message": (
                    "Please enter the date of birth."
                )
            }), 400


        # ====================================================
        # GENDER VALIDATION
        # ====================================================

        if not gender:

            return jsonify({
                "success": False,
                "message": (
                    "Please select gender."
                )
            }), 400


        # ====================================================
        # EMAIL VALIDATION
        # ====================================================

        if not valid_email(email):

            return jsonify({
                "success": False,
                "message": (
                    "Please enter a valid email."
                )
            }), 400


        # ====================================================
        # MOBILE VALIDATION
        # ====================================================

        if not valid_mobile(mobile):

            return jsonify({
                "success": False,
                "message": (
                    "Mobile number must contain "
                    "exactly 10 digits."
                )
            }), 400


        # ====================================================
        # STORE ATTENDEE
        # ====================================================

        attendees.append({

            "name": name,

            "dob": dob,

            "gender": gender,

            "email": email,

            "mobile": mobile

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

        screenshot_data = screenshot.read()

        screenshot_file_id = fs.put(
            screenshot_data,
            filename=screenshot_filename,
            content_type=screenshot.content_type,
            registration_id=registration_id
        )


        # ====================================================
        # PASS AMOUNT
        # ====================================================

        if (
            pass_category ==
            "BLS - ACLS Course Only (Till 1st November 2026)"
        ):

            pass_amount = 11500

            pass_name = (
                "BLS - ACLS Course Only "
                "(Till 1st November 2026)"
            )

        elif (
            pass_category ==
            "BLS - ACLS Course Only (After 1st November 2026)"
        ):

            pass_amount = 12000

            pass_name = (
                "BLS - ACLS Course Only "
                "(After 1st November 2026)"
            )

        elif (
            pass_category ==
            "BLS-ACLS Course with Conference Registration "
            "(Till 1st November 2026)"
        ):

            pass_amount = 13000

            pass_name = (
                "BLS-ACLS Course with Conference "
                "Registration (Till 1st November 2026)"
            )

        elif (
            pass_category ==
            "BLS-ACLS Course with Conference Registration "
            "(After 1st November 2026)"
        ):

            pass_amount = 13500

            pass_name = (
                "BLS-ACLS Course with Conference "
                "Registration (After 1st November 2026)"
            )

        elif (
            pass_category ==
            "Early Bird IMUCON Registration "
            "(Till 1st November 2026)"
        ):

            pass_amount = 2000

            pass_name = (
                "Early Bird IMUCON Registration "
                "(Till 1st November 2026)"
            )

        elif (
            pass_category ==
            "IMUCON Registration "
            "(After 1st November 2026)"
        ):

            pass_amount = 2500

            pass_name = (
                "IMUCON Registration "
                "(After 1st November 2026)"
            )

        else:

            pass_amount = 1200

            pass_name = (
                "Virtual Conference Registration "
                "(12 CME Hrs)"
            )


        # ====================================================
        # CREATE REGISTRATION DOCUMENT
        # ====================================================

        registration_document = {

            "registration_id":
                registration_id,

            "pass_category":
                pass_category,

            "pass_name":
                pass_name,

            "pass_amount":
                pass_amount,

            "registration_type":
                registration_type,

            "attendee_count":
                attendee_count,

            "heard_from":
                heard_from,

            "transaction_id":
                transaction_id,

            "payment_screenshot": {

                "file_id":
                    screenshot_file_id,

                "filename":
                    screenshot_filename

            },

            "status":
                "Pending",

            "attendees":
                attendees,

            "created_at":
                datetime.utcnow()

        }


        # ====================================================
        # SAVE REGISTRATION TO MONGODB
        # ====================================================

        registrations_collection.insert_one(
            registration_document
        )


        # ====================================================
        # SEND REGISTRATION CONFIRMATION EMAIL
        # ====================================================

        email_sent = send_confirmation_email(

            email,

            registration_id,

            name,

            pass_name,

            pass_amount

        )

        # Keep email_sent available for debugging/logging.
        print(
            f"Email notification status for "
            f"{registration_id}: {email_sent}"
        )


        # ====================================================
        # SUCCESS RESPONSE
        # ====================================================

        return jsonify({

            "success": True,

            "message": (
                "Registration submitted successfully!"
            ),

            "registration_id":
                registration_id

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

            "error":
                str(e)

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
