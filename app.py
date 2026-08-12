
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import pyodbc
import os
import re
from werkzeug.utils import secure_filename


# ============================================================
# IMUCON REGISTRATION BACKEND
# ============================================================

app = Flask(__name__)
CORS(app)


# ============================================================
# PATH CONFIGURATION
# ============================================================

# Current folder:
# sharda university/IMUCON/

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Parent folder:
# sharda university/

WEBSITE_FOLDER = os.path.dirname(BASE_DIR)


# Payment screenshot folder:
# sharda university/IMUCON/uploads/

UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# Maximum upload size = 10 MB
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024


# ============================================================
# SQL SERVER CONFIGURATION
# ============================================================

SERVER = r"DESKTOP-PUTRNK1\SQLEXPRESS"
DATABASE = "IMUCON_Registration"


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
# DATABASE CONNECTION
# ============================================================

def get_db_connection():

    connection_string = (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        f"SERVER={SERVER};"
        f"DATABASE={DATABASE};"
        "Trusted_Connection=yes;"
    )

    return pyodbc.connect(connection_string)


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

def generate_registration_id(cursor):

    cursor.execute("""
        SELECT ISNULL(
            MAX(
                TRY_CONVERT(
                    INT,
                    REPLACE(
                        registration_id,
                        'IMUCON26-',
                        ''
                    )
                )
            ),
            0
        )
        FROM registrations
    """)

    last_number = cursor.fetchone()[0]

    next_number = last_number + 1

    registration_id = f"IMUCON26-{next_number:05d}"

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
# ASSETS
# ============================================================

@app.route("/assets/<path:filename>")
def assets(filename):

    return send_from_directory(
        os.path.join(
            WEBSITE_FOLDER,
            "assets"
        ),
        filename
    )


# ============================================================
# API STATUS
# ============================================================

@app.route("/api/status")
def api_status():

    return jsonify({
        "status": "running",
        "message": "IMUCON Registration API is running."
    })


# ============================================================
# REGISTRATION API
# ============================================================

@app.route("/api/register", methods=["POST"])
def register():

    connection = None

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
                "message": "Please select a valid pass category."
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
                "message": "Please select a valid registration type."
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
                    "message": "Please select the number of attendees."
                }), 400


            if attendee_count < 2 or attendee_count > 10:

                return jsonify({
                    "success": False,
                    "message": "Group registration must contain 2 to 10 attendees."
                }), 400


        # ====================================================
        # TRANSACTION ID
        # ====================================================

        if not transaction_id:

            return jsonify({
                "success": False,
                "message": "Please enter the Transaction ID / UTR number."
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
                "message": "Please upload your payment screenshot."
            }), 400


        if screenshot.filename == "":

            return jsonify({
                "success": False,
                "message": "Please select a payment screenshot."
            }), 400


        if not allowed_file(
            screenshot.filename
        ):

            return jsonify({
                "success": False,
                "message": (
                    "Invalid image format. "
                    "Please upload PNG, JPG, JPEG or WEBP."
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
        # CONNECT TO SQL SERVER
        # ====================================================

        connection = get_db_connection()

        connection.autocommit = False

        cursor = connection.cursor()


        # ====================================================
        # GENERATE REGISTRATION ID
        # ====================================================

        registration_id = generate_registration_id(
            cursor
        )


        # ====================================================
        # SAVE PAYMENT SCREENSHOT
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


        screenshot_path = os.path.join(
            UPLOAD_FOLDER,
            screenshot_filename
        )


        screenshot.save(
            screenshot_path
        )


        # ====================================================
        # INSERT REGISTRATION
        # ====================================================

        cursor.execute("""

            INSERT INTO registrations (

                registration_id,

                pass_category,

                registration_type,

                attendee_count,

                heard_from,

                transaction_id,

                payment_screenshot,

                status

            )

            VALUES (?, ?, ?, ?, ?, ?, ?, ?)

        """, (

            registration_id,

            pass_category,

            registration_type,

            attendee_count,

            heard_from,

            transaction_id,

            screenshot_filename,

            "Pending"

        ))


        # ====================================================
        # INSERT ATTENDEES
        # ====================================================

        for attendee in attendees:

            cursor.execute("""

                INSERT INTO attendees (

                    registration_id,

                    full_name,

                    date_of_birth,

                    gender,

                    email,

                    mobile,

                    employee_id,

                    id_card_no

                )

                VALUES (?, ?, ?, ?, ?, ?, ?, ?)

            """, (

                registration_id,

                attendee["name"],

                attendee["dob"],

                attendee["gender"],

                attendee["email"],

                attendee["mobile"],

                attendee["employee_id"],

                attendee["id_card_no"]

            ))


        # ====================================================
        # COMMIT DATABASE
        # ====================================================

        connection.commit()


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

        if connection:

            connection.rollback()


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


    # ========================================================
    # CLOSE DATABASE
    # ========================================================

    finally:

        if connection:

            connection.close()


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

