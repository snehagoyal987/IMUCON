from flask import (
    Flask,
    request,
    jsonify,
    send_from_directory,
    session,
    send_file
)

from flask_cors import CORS
from pymongo import MongoClient, ReturnDocument
from dotenv import load_dotenv
from gridfs import GridFS
from werkzeug.utils import secure_filename

import os
import re
import smtplib
import io
import hmac

from email.message import EmailMessage
from datetime import datetime


# ============================================================
# LOAD ENVIRONMENT VARIABLES
# ============================================================

load_dotenv()

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")

# Admin dashboard credentials
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

# Flask session secret
SECRET_KEY = os.getenv("SECRET_KEY")


# ============================================================
# IMUCON REGISTRATION BACKEND
# ============================================================

app = Flask(__name__)

# Flask session configuration
app.secret_key = SECRET_KEY

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

CORS(app)


# ============================================================
# PATH CONFIGURATION
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

# Website files are inside the IMUCON folder
WEBSITE_FOLDER = BASE_DIR

# Vercel writable temporary uploads folder
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
        and
        filename.rsplit(
            ".",
            1
        )[1].lower()
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
# ADMIN LOGIN CHECK
# ============================================================

def admin_logged_in():

    return (
        session.get(
            "admin_logged_in"
        ) is True
    )


# ============================================================
# EMAIL - ATTENDEE REGISTRATION CONFIRMATION
# ============================================================

def send_confirmation_email(
    to_email,
    registration_id,
    name,
    pass_name,
    pass_amount
):

    try:

        if (
            not EMAIL_ADDRESS
            or
            not EMAIL_PASSWORD
        ):

            print(
                "EMAIL_ADDRESS or "
                "EMAIL_PASSWORD is not configured."
            )

            return False


        msg = EmailMessage()


        msg["Subject"] = (
            "IMUCON 2.0 Registration "
            f"Confirmation - {registration_id}"
        )


        msg["From"] = EMAIL_ADDRESS

        msg["To"] = to_email


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
            "Confirmation email sent successfully "
            f"to {to_email}"
        )


        return True


    except Exception as e:

        print(
            "CONFIRMATION EMAIL ERROR:",
            str(e)
        )

        return False


# ============================================================
# EMAIL - ADMIN NEW REGISTRATION NOTIFICATION
# ============================================================

def send_admin_notification(
    registration
):

    try:

        if (
            not EMAIL_ADDRESS
            or
            not EMAIL_PASSWORD
        ):

            print(
                "EMAIL_ADDRESS or "
                "EMAIL_PASSWORD is not configured."
            )

            return False


        if not ADMIN_EMAIL:

            print(
                "ADMIN_EMAIL is not configured."
            )

            return False


        # Get first attendee
        attendee = (
            registration["attendees"][0]
        )


        msg = EmailMessage()


        msg["Subject"] = (
            "New IMUCON Registration - "
            f"{registration['registration_id']}"
        )


        msg["From"] = EMAIL_ADDRESS

        msg["To"] = ADMIN_EMAIL


        msg.set_content(
            f"""
NEW IMUCON 2.0 REGISTRATION
========================================

Registration ID:
{registration["registration_id"]}


ATTENDEE DETAILS
========================================

Name:
{attendee["name"]}

Date of Birth:
{attendee["dob"]}

Gender:
{attendee["gender"]}

Email:
{attendee["email"]}

Mobile:
{attendee["mobile"]}


REGISTRATION DETAILS
========================================

Pass:
{registration["pass_name"]}

Amount Paid:
₹{registration["pass_amount"]}

Transaction ID:
{registration["transaction_id"]}

Heard From:
{registration["heard_from"]}

Registration Type:
{registration["registration_type"]}

Attendee Count:
{registration["attendee_count"]}

Status:
{registration["status"]}

Submitted At:
{registration["created_at"]}


========================================
IMUCON 2.0
Sharda Hospital
"""
        )


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
            "Admin notification sent successfully "
            f"to {ADMIN_EMAIL}"
        )


        return True


    except Exception as e:

        print(
            "ADMIN EMAIL ERROR:",
            str(e)
        )

        return False


# ============================================================
# EMAIL - PAYMENT STATUS UPDATE
# ============================================================

def send_payment_status_email(
    registration,
    new_status
):

    try:

        if (
            not EMAIL_ADDRESS
            or
            not EMAIL_PASSWORD
        ):

            print(
                "EMAIL_ADDRESS or "
                "EMAIL_PASSWORD is not configured."
            )

            return False


        attendee = (
            registration["attendees"][0]
        )


        attendee_email = (
            attendee["email"]
        )

        attendee_name = (
            attendee["name"]
        )

        registration_id = (
            registration["registration_id"]
        )

        pass_name = (
            registration["pass_name"]
        )

        pass_amount = (
            registration["pass_amount"]
        )


        # ====================================================
        # PAYMENT VERIFIED EMAIL
        # ====================================================

        if new_status == "Payment Verified":

            subject = (
                "IMUCON 2.0 Payment Verified - "
                f"{registration_id}"
            )


            message = f"""
Dear {attendee_name},

Your payment for IMUCON 2.0 –
International Medicine Update Conference
has been successfully verified.

Registration Details
--------------------------------

Registration ID:
{registration_id}

Pass:
{pass_name}

Amount:
₹{pass_amount}

Payment Status:
Payment Verified

Conference Dates:
15th–18th December 2026

Venue:
College Council Room, 5th Floor,
SMS&R & Sharda Hospital,
Greater Noida

Your registration is now confirmed.

Please keep your Registration ID for future communication.

Regards,
IMUCON 2.0 Team
Sharda Hospital
"""


        # ====================================================
        # PAYMENT REJECTED EMAIL
        # ====================================================

        else:

            subject = (
                "IMUCON 2.0 Payment Verification Update - "
                f"{registration_id}"
            )


            message = f"""
Dear {attendee_name},

We were unable to verify the payment submitted
for your IMUCON 2.0 registration.

Registration Details
--------------------------------

Registration ID:
{registration_id}

Pass:
{pass_name}

Amount:
₹{pass_amount}

Payment Status:
Payment Rejected

Please contact the IMUCON 2.0 registration team
with your Registration ID for further assistance.

Please do not submit another payment unless
the registration team advises you to do so.

Regards,
IMUCON 2.0 Team
Sharda Hospital
"""


        msg = EmailMessage()

        msg["Subject"] = subject

        msg["From"] = EMAIL_ADDRESS

        msg["To"] = attendee_email

        msg.set_content(message)


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
            "Payment status email sent to "
            f"{attendee_email}"
        )


        return True


    except Exception as e:

        print(
            "PAYMENT STATUS EMAIL ERROR:",
            str(e)
        )

        return False


# ============================================================
# GENERATE REGISTRATION ID
# ============================================================

def generate_registration_id():

    counter = (
        counters_collection.find_one_and_update(

            {
                "_id":
                    "registration_id"
            },

            {
                "$inc": {
                    "value": 1
                }
            },

            upsert=True,

            return_document=
                ReturnDocument.AFTER
        )
    )


    next_number = (
        counter["value"]
    )


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
# ADMIN LOGIN / DASHBOARD PAGE
# ============================================================

@app.route(
    "/admin",
    methods=["GET"]
)
def admin_page():

    if admin_logged_in():

        return send_from_directory(
            WEBSITE_FOLDER,
            "admin.html"
        )


    return send_from_directory(
        WEBSITE_FOLDER,
        "admin_login.html"
    )


# ============================================================
# ADMIN LOGIN API
# ============================================================

@app.route(
    "/admin/login",
    methods=["POST"]
)
def admin_login():

    try:

        data = request.get_json()


        if not data:

            return jsonify({
                "success": False,
                "message":
                    "Invalid request."
            }), 400


        username = (
            data.get(
                "username",
                ""
            ).strip()
        )


        password = (
            data.get(
                "password",
                ""
            )
        )


        if (
            not ADMIN_USERNAME
            or
            not ADMIN_PASSWORD
            or
            not SECRET_KEY
        ):

            print(
                "Admin environment variables "
                "are not configured."
            )


            return jsonify({
                "success": False,
                "message":
                    "Admin login is not configured."
            }), 500


        username_match = (
            hmac.compare_digest(
                username,
                ADMIN_USERNAME
            )
        )


        password_match = (
            hmac.compare_digest(
                password,
                ADMIN_PASSWORD
            )
        )


        if (
            username_match
            and
            password_match
        ):

            session.clear()

            session[
                "admin_logged_in"
            ] = True


            return jsonify({
                "success": True,
                "message":
                    "Login successful."
            })


        return jsonify({
            "success": False,
            "message":
                "Invalid username or password."
        }), 401


    except Exception as e:

        print(
            "ADMIN LOGIN ERROR:",
            str(e)
        )


        return jsonify({
            "success": False,
            "message":
                "Unable to process login."
        }), 500


# ============================================================
# ADMIN LOGOUT
# ============================================================

@app.route(
    "/admin/logout",
    methods=["POST"]
)
def admin_logout():

    session.clear()


    return jsonify({
        "success": True,
        "message":
            "Logged out successfully."
    })


# ============================================================
# ADMIN REGISTRATIONS API
# ============================================================

@app.route(
    "/api/admin/registrations",
    methods=["GET"]
)
def admin_registrations():

    if not admin_logged_in():

        return jsonify({
            "success": False,
            "message":
                "Unauthorized."
        }), 401


    try:

        registrations = list(
            registrations_collection.find(
                {},
                {
                    "_id": 0
                }
            ).sort(
                "created_at",
                -1
            )
        )


        cleaned_registrations = []


        for registration in registrations:

            created_at = (
                registration.get(
                    "created_at"
                )
            )


            if created_at:

                try:

                    registration[
                        "created_at"
                    ] = created_at.isoformat()

                except Exception:

                    registration[
                        "created_at"
                    ] = str(
                        created_at
                    )


            payment_screenshot = (
                registration.get(
                    "payment_screenshot"
                )
            )


            if payment_screenshot:

                registration[
                    "payment_screenshot"
                ] = {

                    "filename":
                        payment_screenshot.get(
                            "filename",
                            ""
                        )

                }


            cleaned_registrations.append(
                registration
            )


        return jsonify({

            "success": True,

            "registrations":
                cleaned_registrations

        })


    except Exception as e:

        print(
            "ADMIN REGISTRATIONS ERROR:",
            str(e)
        )


        return jsonify({

            "success": False,

            "message":
                "Unable to load registrations."

        }), 500


# ============================================================
# ADMIN PAYMENT SCREENSHOT
# ============================================================

@app.route(
    "/admin/payment-screenshot/<registration_id>",
    methods=["GET"]
)
def admin_payment_screenshot(
    registration_id
):

    if not admin_logged_in():

        return jsonify({
            "success": False,
            "message":
                "Unauthorized."
        }), 401


    try:

        registration = (
            registrations_collection.find_one(
                {
                    "registration_id":
                        registration_id
                }
            )
        )


        if not registration:

            return jsonify({
                "success": False,
                "message":
                    "Registration not found."
            }), 404


        payment_screenshot = (
            registration.get(
                "payment_screenshot"
            )
        )


        if not payment_screenshot:

            return jsonify({
                "success": False,
                "message":
                    "Payment screenshot not found."
            }), 404


        file_id = (
            payment_screenshot.get(
                "file_id"
            )
        )


        if not file_id:

            return jsonify({
                "success": False,
                "message":
                    "Payment screenshot file not found."
            }), 404


        grid_file = fs.get(
            file_id
        )


        content_type = (
            getattr(
                grid_file,
                "content_type",
                None
            )
        )


        if not content_type:

            content_type = (
                "image/jpeg"
            )


        filename = (
            payment_screenshot.get(
                "filename",
                "payment-screenshot"
            )
        )


        return send_file(

            io.BytesIO(
                grid_file.read()
            ),

            mimetype=content_type,

            download_name=filename

        )


    except Exception as e:

        print(
            "PAYMENT SCREENSHOT ERROR:",
            str(e)
        )


        return jsonify({

            "success": False,

            "message":
                "Unable to load payment screenshot."

        }), 500


# ============================================================
# ADMIN VERIFY PAYMENT
# ============================================================

@app.route(
    "/api/admin/verify/<registration_id>",
    methods=["POST"]
)
def admin_verify_payment(
    registration_id
):

    if not admin_logged_in():

        return jsonify({
            "success": False,
            "message":
                "Unauthorized."
        }), 401


    try:

        registration = (
            registrations_collection.find_one(
                {
                    "registration_id":
                        registration_id
                }
            )
        )


        if not registration:

            return jsonify({
                "success": False,
                "message":
                    "Registration not found."
            }), 404


        old_status = (
            registration.get(
                "status",
                ""
            )
        )


        if old_status == "Payment Verified":

            return jsonify({

                "success": True,

                "message":
                    "Payment is already verified."

            })


        result = (
            registrations_collection.update_one(

                {
                    "registration_id":
                        registration_id
                },

                {
                    "$set": {

                        "status":
                            "Payment Verified",

                        "verified_at":
                            datetime.utcnow()

                    }
                }
            )
        )


        if result.modified_count == 0:

            return jsonify({

                "success": False,

                "message":
                    "Registration status "
                    "was not updated."

            }), 500


        registration[
            "status"
        ] = "Payment Verified"


        email_sent = (
            send_payment_status_email(
                registration,
                "Payment Verified"
            )
        )


        if email_sent:

            message = (
                "Payment verified successfully. "
                "Attendee confirmation email sent."
            )

        else:

            message = (
                "Payment verified successfully, "
                "but the attendee email could not "
                "be sent."
            )


        return jsonify({

            "success": True,

            "message": message

        })


    except Exception as e:

        print(
            "VERIFY PAYMENT ERROR:",
            str(e)
        )


        return jsonify({

            "success": False,

            "message":
                "Unable to verify payment."

        }), 500


# ============================================================
# ADMIN REJECT PAYMENT
# ============================================================

@app.route(
    "/api/admin/reject/<registration_id>",
    methods=["POST"]
)
def admin_reject_payment(
    registration_id
):

    if not admin_logged_in():

        return jsonify({

            "success": False,

            "message":
                "Unauthorized."

        }), 401


    try:

        registration = (
            registrations_collection.find_one(
                {
                    "registration_id":
                        registration_id
                }
            )
        )


        if not registration:

            return jsonify({

                "success": False,

                "message":
                    "Registration not found."

            }), 404


        old_status = (
            registration.get(
                "status",
                ""
            )
        )


        if old_status == "Payment Rejected":

            return jsonify({

                "success": True,

                "message":
                    "Payment is already rejected."

            })


        result = (
            registrations_collection.update_one(

                {
                    "registration_id":
                        registration_id
                },

                {
                    "$set": {

                        "status":
                            "Payment Rejected",

                        "rejected_at":
                            datetime.utcnow()

                    }
                }
            )
        )


        if result.modified_count == 0:

            return jsonify({

                "success": False,

                "message":
                    "Registration status "
                    "was not updated."

            }), 500


        registration[
            "status"
        ] = "Payment Rejected"


        email_sent = (
            send_payment_status_email(
                registration,
                "Payment Rejected"
            )
        )


        if email_sent:

            message = (
                "Payment rejected successfully. "
                "Attendee notification email sent."
            )

        else:

            message = (
                "Payment rejected successfully, "
                "but the attendee email could not "
                "be sent."
            )


        return jsonify({

            "success": True,

            "message": message

        })


    except Exception as e:

        print(
            "REJECT PAYMENT ERROR:",
            str(e)
        )


        return jsonify({

            "success": False,

            "message":
                "Unable to reject payment."

        }), 500


# ============================================================
# API STATUS
# ============================================================

@app.route("/api/status")
def api_status():

    try:

        # Test MongoDB connection
        client.admin.command(
            "ping"
        )


        return jsonify({

            "status":
                "running",

            "database":
                "connected",

            "message":
                "IMUCON Registration API "
                "is running and MongoDB "
                "is connected."

        })


    except Exception as e:

        return jsonify({

            "status":
                "running",

            "database":
                "disconnected",

            "message":
                "MongoDB connection failed.",

            "error":
                str(e)

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

        pass_category = (
            request.form.get(
                "passCategory",
                ""
            ).strip()
        )


        heard_from = (
            request.form.get(
                "heardFrom",
                ""
            ).strip()
        )


        transaction_id = (
            request.form.get(
                "transactionId",
                ""
            ).strip()
        )


        # ====================================================
        # VALIDATE PASS CATEGORY
        # ====================================================

        allowed_categories = {

            "BLS - ACLS Course Only "
            "(Till 1st November 2026)",

            "BLS - ACLS Course Only "
            "(After 1st November 2026)",

            "BLS-ACLS Course with Conference "
            "Registration (Till 1st November 2026)",

            "BLS-ACLS Course with Conference "
            "Registration (After 1st November 2026)",

            "Early Bird IMUCON Registration "
            "(Till 1st November 2026)",

            "IMUCON Registration "
            "(After 1st November 2026)",

            "Virtual Conference Registration "
            "(12 CME Hrs)"
        }


        if pass_category not in allowed_categories:

            return jsonify({

                "success": False,

                "message":
                    "Please select a valid "
                    "pass category."

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

            "BLS - ACLS Course Only "
            "(After 1st November 2026)",

            "BLS-ACLS Course with Conference "
            "Registration (After 1st November 2026)",

            "IMUCON Registration "
            "(After 1st November 2026)"
        }


        before_november_categories = {

            "BLS - ACLS Course Only "
            "(Till 1st November 2026)",

            "BLS-ACLS Course with Conference "
            "Registration (Till 1st November 2026)",

            "Early Bird IMUCON Registration "
            "(Till 1st November 2026)"
        }


        # ====================================================
        # AFTER-NOVEMBER CATEGORIES
        # ====================================================

        if (
            pass_category
            in after_november_categories
            and
            datetime.now()
            < activation_date
        ):

            return jsonify({

                "success": False,

                "message":
                    "This pass category will be "
                    "available from 1 November 2026."

            }), 400


        # ====================================================
        # BEFORE-NOVEMBER CATEGORIES
        # ====================================================

        if (
            pass_category
            in before_november_categories
            and
            datetime.now()
            >= activation_date
        ):

            return jsonify({

                "success": False,

                "message":
                    "This pass category was "
                    "available until 31 October 2026."

            }), 400


        # ====================================================
        # BLS-ACLS COMBINED 30 SEAT CAPACITY
        # ====================================================

        bls_categories = {

            "BLS - ACLS Course Only "
            "(Till 1st November 2026)",

            "BLS-ACLS Course with Conference "
            "Registration (Till 1st November 2026)"
        }


        if pass_category in bls_categories:

            bls_count = (
                registrations_collection
                .count_documents({

                    "pass_category": {

                        "$in":
                            list(
                                bls_categories
                            )

                    }

                })
            )


            if bls_count >= 30:

                return jsonify({

                    "success": False,

                    "message":
                        "The BLS-ACLS course "
                        "capacity of 30 "
                        "registrations has "
                        "been reached."

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

                "message":
                    "Please enter the Transaction "
                    "ID / UTR number."

            }), 400


        # ====================================================
        # PAYMENT SCREENSHOT
        # ====================================================

        screenshot = (
            request.files.get(
                "paymentScreenshot"
            )
        )


        if not screenshot:

            return jsonify({

                "success": False,

                "message":
                    "Please upload your "
                    "payment screenshot."

            }), 400


        if screenshot.filename == "":

            return jsonify({

                "success": False,

                "message":
                    "Please select a "
                    "payment screenshot."

            }), 400


        if not allowed_file(
            screenshot.filename
        ):

            return jsonify({

                "success": False,

                "message":
                    "Invalid image format. "
                    "Please upload PNG, JPG, "
                    "JPEG or WEBP."

            }), 400


        # ====================================================
        # COLLECT ATTENDEE INFORMATION
        # ====================================================

        attendees = []


        name = (
            request.form.get(
                "attendee_1_name",
                ""
            ).strip()
        )


        dob = (
            request.form.get(
                "attendee_1_dob",
                ""
            ).strip()
        )


        gender = (
            request.form.get(
                "attendee_1_gender",
                ""
            ).strip()
        )


        email = (
            request.form.get(
                "attendee_1_email",
                ""
            ).strip()
        )


        mobile = (
            request.form.get(
                "attendee_1_mobile",
                ""
            ).strip()
        )


        # ====================================================
        # NAME VALIDATION
        # ====================================================

        if not name:

            return jsonify({

                "success": False,

                "message":
                    "Please enter the full name."

            }), 400


        # ====================================================
        # DOB VALIDATION
        # ====================================================

        if not dob:

            return jsonify({

                "success": False,

                "message":
                    "Please enter the date of birth."

            }), 400


        # ====================================================
        # GENDER VALIDATION
        # ====================================================

        if not gender:

            return jsonify({

                "success": False,

                "message":
                    "Please select gender."

            }), 400


        # ====================================================
        # EMAIL VALIDATION
        # ====================================================

        if not valid_email(email):

            return jsonify({

                "success": False,

                "message":
                    "Please enter a valid email."

            }), 400


        # ====================================================
        # MOBILE VALIDATION
        # ====================================================

        if not valid_mobile(mobile):

            return jsonify({

                "success": False,

                "message":
                    "Mobile number must contain "
                    "exactly 10 digits."

            }), 400


        # ====================================================
        # STORE ATTENDEE
        # ====================================================

        attendees.append({

            "name":
                name,

            "dob":
                dob,

            "gender":
                gender,

            "email":
                email,

            "mobile":
                mobile

        })


        # ====================================================
        # GENERATE REGISTRATION ID
        # ====================================================

        registration_id = (
            generate_registration_id()
        )


        # ====================================================
        # SAVE PAYMENT SCREENSHOT TO GRIDFS
        # ====================================================

        original_filename = (
            secure_filename(
                screenshot.filename
            )
        )


        extension = (
            original_filename
            .rsplit(
                ".",
                1
            )[1]
            .lower()
        )


        screenshot_filename = (
            f"{registration_id}"
            f"_payment."
            f"{extension}"
        )


        screenshot_data = (
            screenshot.read()
        )


        screenshot_file_id = fs.put(

            screenshot_data,

            filename=
                screenshot_filename,

            content_type=
                screenshot.content_type,

            registration_id=
                registration_id
        )


        # ====================================================
        # PASS AMOUNT
        # ====================================================

        if (
            pass_category
            ==
            "BLS - ACLS Course Only "
            "(Till 1st November 2026)"
        ):

            pass_amount = 11500

            pass_name = (
                "BLS - ACLS Course Only "
                "(Till 1st November 2026)"
            )


        elif (
            pass_category
            ==
            "BLS - ACLS Course Only "
            "(After 1st November 2026)"
        ):

            pass_amount = 12000

            pass_name = (
                "BLS - ACLS Course Only "
                "(After 1st November 2026)"
            )


        elif (
            pass_category
            ==
            "BLS-ACLS Course with Conference "
            "Registration (Till 1st November 2026)"
        ):

            pass_amount = 13000

            pass_name = (
                "BLS-ACLS Course with Conference "
                "Registration "
                "(Till 1st November 2026)"
            )


        elif (
            pass_category
            ==
            "BLS-ACLS Course with Conference "
            "Registration (After 1st November 2026)"
        ):

            pass_amount = 13500

            pass_name = (
                "BLS-ACLS Course with Conference "
                "Registration "
                "(After 1st November 2026)"
            )


        elif (
            pass_category
            ==
            "Early Bird IMUCON Registration "
            "(Till 1st November 2026)"
        ):

            pass_amount = 2000

            pass_name = (
                "Early Bird IMUCON Registration "
                "(Till 1st November 2026)"
            )


        elif (
            pass_category
            ==
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
                "Payment Under Verification",

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
        # SEND EMAIL TO ATTENDEE
        # ====================================================

        attendee_email_sent = (
            send_confirmation_email(

                email,

                registration_id,

                name,

                pass_name,

                pass_amount

            )
        )


        print(
            "Attendee email status for "
            f"{registration_id}: "
            f"{attendee_email_sent}"
        )


        # ====================================================
        # SEND EMAIL TO ADMIN
        # ====================================================

        admin_email_sent = (
            send_admin_notification(
                registration_document
            )
        )


        print(
            "Admin notification status for "
            f"{registration_id}: "
            f"{admin_email_sent}"
        )


        # ====================================================
        # SUCCESS RESPONSE
        # ====================================================

        return jsonify({

            "success":
                True,

            "message":
                "Registration submitted successfully!",

            "registration_id":
                registration_id

        }), 201


    # ========================================================
    # ERROR HANDLING
    # ========================================================

    except Exception as e:

        # If registration fails after
        # screenshot upload, delete
        # screenshot from GridFS.

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

            "success":
                False,

            "message":
                "Registration could not "
                "be completed.",

            "error":
                str(e)

        }), 500


# ============================================================
# WEBSITE STATIC FILES
# ============================================================

@app.route(
    "/<path:filename>"
)
def static_files(filename):

    return send_from_directory(
        WEBSITE_FOLDER,
        filename
    )


# ============================================================
# PAYMENT UPLOADS
# ============================================================

@app.route(
    "/uploads/<filename>"
)
def uploaded_file(filename):

    return send_from_directory(
        UPLOAD_FOLDER,
        filename
    )


# ============================================================
# RUN FLASK SERVER
# ============================================================

if __name__ == "__main__":

    print()

    print(
        "========================================"
    )

    print(
        "      IMUCON REGISTRATION BACKEND"
    )

    print(
        "========================================"
    )

    print()

    print(
        "Website:"
    )

    print(
        "http://127.0.0.1:5000"
    )

    print()

    print(
        "Registration:"
    )

    print(
        "http://127.0.0.1:5000/registration"
    )

    print()

    print(
        "Admin:"
    )

    print(
        "http://127.0.0.1:5000/admin"
    )

    print()

    print(
        "API:"
    )

    print(
        "http://127.0.0.1:5000/api/status"
    )

    print()

    print(
        "========================================"
    )

    print()

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
