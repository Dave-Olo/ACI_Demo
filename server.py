import hashlib
import logging
import os
import sqlite3
import ssl
import tempfile
from datetime import datetime

from flask import Flask, jsonify, request
from dotenv import load_dotenv

DATABASE = os.path.join(os.path.dirname(__file__), "pins.db")
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)


def get_tls_context():
    certificate = os.environ.get("TLS_CERT_PEM", "").replace("\\n", "\n")
    private_key = os.environ.get("TLS_KEY_PEM", "").replace("\\n", "\n")

    missing_variables = []
    if not certificate.strip():
        missing_variables.append("TLS_CERT_PEM")
    if not private_key.strip():
        missing_variables.append("TLS_KEY_PEM")
    if missing_variables:
        raise RuntimeError(
            f"Missing required HTTPS environment variable(s): {', '.join(missing_variables)}"
        )

    certificate_file = tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False)
    private_key_file = tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False)
    try:
        certificate_file.write(certificate)
        private_key_file.write(private_key)
    finally:
        certificate_file.close()
        private_key_file.close()

    try:
        tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls_context.load_cert_chain(certificate_file.name, private_key_file.name)
        return tls_context
    finally:
        os.remove(certificate_file.name)
        os.remove(private_key_file.name)


def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()

    # Migrate pins table if facility_id or facility_name columns are missing
    cursor = conn.execute("PRAGMA table_info(pins)")
    existing_columns = {row["name"] for row in cursor.fetchall()}
    target_columns = {"pin_hash", "facility_id", "facility_name"}
    needs_migration = existing_columns and not target_columns.issubset(existing_columns)

    if needs_migration:
        logger.info("Migrating pins table to add facility_id/facility_name columns...")
        has_facility_id = "facility_id" in existing_columns
        conn.execute("ALTER TABLE pins RENAME TO pins_old")
        conn.execute(
            """
            CREATE TABLE pins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pin_hash TEXT NOT NULL,
                facility_id TEXT NOT NULL DEFAULT '',
                facility_name TEXT NOT NULL DEFAULT '',
                used INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                UNIQUE(pin_hash, facility_id)
            )
            """
        )
        if has_facility_id:
            conn.execute(
                "INSERT INTO pins (id, pin_hash, facility_id, facility_name, used, created_at) "
                "SELECT id, pin_hash, facility_id, '', used, created_at FROM pins_old"
            )
        else:
            conn.execute(
                "INSERT INTO pins (id, pin_hash, facility_id, facility_name, used, created_at) "
                "SELECT id, pin_hash, '', '', used, created_at FROM pins_old"
            )
        conn.execute("DROP TABLE pins_old")
        logger.info("Migration complete.")
    else:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pin_hash TEXT NOT NULL,
                facility_id TEXT NOT NULL DEFAULT '',
                facility_name TEXT NOT NULL DEFAULT '',
                used INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                UNIQUE(pin_hash, facility_id)
            )
            """
        )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS facility_registrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            access_code TEXT NOT NULL UNIQUE,
            facility_name TEXT NOT NULL,
            facility_id TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()
    logger.info("Database initialized.")


def hash_access_code(access_code: str) -> str:
    return hashlib.sha256(access_code.encode("utf-8")).hexdigest()


def _register_facility(payload: dict):
    access_code = str(payload.get("accessCode", "")).strip()
    facility_name = str(payload.get("facilityName", "")).strip()
    facility_id = str(payload.get("facilityId", "")).strip()

    missing_fields = []
    if not access_code:
        missing_fields.append("accessCode")
    if not facility_name:
        missing_fields.append("facilityName")
    if not facility_id:
        missing_fields.append("facilityId")

    if missing_fields:
        logger.warning("Facility registration missing fields: %s", missing_fields)
        return (
            jsonify(
                {
                    "success": False,
                    "error": f"Missing required field(s): {', '.join(missing_fields)}",
                }
            ),
            400,
        )

    created_at = datetime.utcnow().isoformat() + "Z"
    try:
        conn = get_db_connection()
        conn.execute(
            "INSERT INTO facility_registrations (access_code, facility_name, facility_id, created_at) VALUES (?, ?, ?, ?)",
            (access_code, facility_name, facility_id, created_at),
        )
        conn.commit()
        conn.close()
        logger.info("Facility registered: facilityId=%s", facility_id)
    except sqlite3.IntegrityError:
        logger.warning(
            "Facility registration conflict: facilityId=%s or accessCode already exists", facility_id
        )
        return jsonify({"success": False, "error": "Facility registration already exists."}), 409

    return (
        jsonify(
            {
                "success": True,
                "message": "Facility registration received successfully.",
                "facilityId": facility_id,
            }
        ),
        201,
    )


@app.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True)
    if not data:
        logger.warning("POST /register - invalid JSON body from %s", request.remote_addr)
        return jsonify({"success": False, "error": "Request body must be valid JSON."}), 400

    logger.debug("POST /register payload keys: %s from %s", list(data.keys()), request.remote_addr)

    # Access code registration: requires accessCode, facilityId, facilityName
    access_code = str(data.get("accessCode", "")).strip()
    facility_id = str(data.get("facilityId", "")).strip()
    facility_name = str(data.get("facilityName", "")).strip()

    missing_fields = []
    if not access_code:
        missing_fields.append("accessCode")
    if not facility_id:
        missing_fields.append("facilityId")
    if not facility_name:
        missing_fields.append("facilityName")
    if missing_fields:
        logger.warning("POST /register - missing fields: %s from %s", missing_fields, request.remote_addr)
        return jsonify({"success": False, "error": f"Missing required field(s): {', '.join(missing_fields)}"}), 400

    if not access_code.isdigit() or len(access_code) < 4 or len(access_code) > 16:
        logger.warning("POST /register - invalid accessCode format from %s", request.remote_addr)
        return jsonify({"success": False, "error": "accessCode must be 4-16 digits."}), 400

    pin_hash = hash_access_code(access_code)
    created_at = datetime.utcnow().isoformat() + "Z"

    try:
        conn = get_db_connection()
        conn.execute(
            "INSERT INTO pins (pin_hash, facility_id, facility_name, used, created_at) VALUES (?, ?, ?, 0, ?)",
            (pin_hash, facility_id, facility_name, created_at),
        )
        conn.commit()
        conn.close()
        logger.info(
            "POST /register - access code registered for facilityId=%s facilityName=%s",
            facility_id, facility_name,
        )
    except sqlite3.IntegrityError:
        logger.warning("POST /register - access code already exists for facilityId=%s", facility_id)
        return jsonify({"success": False, "error": "Access code already exists for this facility."}), 409

    return jsonify({"success": True, "message": "Access code registered successfully.", "facilityId": facility_id, "facilityName": facility_name}), 201


@app.route("/facility/register", methods=["POST"])
def register_facility():
    data = request.get_json(silent=True)
    if not data:
        logger.warning("POST /facility/register - invalid JSON body from %s", request.remote_addr)
        return jsonify({"success": False, "error": "Request body must be valid JSON."}), 400

    logger.info("POST /facility/register attempt from %s", request.remote_addr)
    return _register_facility(data)


@app.route("/authenticate", methods=["POST"])
def authenticate():
    data = request.get_json(silent=True)
    if not data:
        logger.warning("POST /authenticate - invalid JSON body from %s", request.remote_addr)
        return jsonify({"success": False, "error": "Request body must be valid JSON."}), 400

    access_code = str(data.get("accessCode", "")).strip()
    facility_id = str(data.get("facilityId", "")).strip()
    facility_name = str(data.get("facilityName", "")).strip()

    missing_fields = []
    if not access_code:
        missing_fields.append("accessCode")
    if not facility_id:
        missing_fields.append("facilityId")
    if not facility_name:
        missing_fields.append("facilityName")
    if missing_fields:
        logger.warning("POST /authenticate - missing fields: %s from %s", missing_fields, request.remote_addr)
        return jsonify({"success": False, "error": f"Missing required field(s): {', '.join(missing_fields)}"}), 400

    if not access_code.isdigit():
        logger.warning("POST /authenticate - invalid accessCode format from %s", request.remote_addr)
        return jsonify({"success": False, "error": "Invalid accessCode format."}), 400

    pin_hash = hash_access_code(access_code)
    conn = get_db_connection()
    cursor = conn.execute(
        "SELECT id, used, facility_name FROM pins WHERE pin_hash = ? AND facility_id = ?",
        (pin_hash, facility_id),
    )
    row = cursor.fetchone()

    if row is None:
        conn.close()
        logger.warning(
            "POST /authenticate - access code not found for facilityId=%s facilityName=%s from %s",
            facility_id, facility_name, request.remote_addr,
        )
        return jsonify({"success": False, "authenticated": False, "error": "Access code not found."}), 404

    if row["facility_name"] and row["facility_name"] != facility_name:
        conn.close()
        logger.warning(
            "POST /authenticate - facilityName mismatch for facilityId=%s from %s",
            facility_id, request.remote_addr,
        )
        return jsonify({"success": False, "authenticated": False, "error": "Facility name does not match."}), 403

    if row["used"]:
        conn.close()
        logger.warning(
            "POST /authenticate - access code already used for facilityId=%s facilityName=%s from %s",
            facility_id, facility_name, request.remote_addr,
        )
        return jsonify({"success": False, "authenticated": False, "error": "Access code has already been used."}), 403

    conn.execute("UPDATE pins SET used = 1 WHERE id = ?", (row["id"],))
    conn.commit()
    conn.close()
    logger.info(
        "POST /authenticate - authenticated and invalidated for facilityId=%s facilityName=%s",
        facility_id, facility_name,
    )

    return jsonify({"success": True, "authenticated": True, "message": "Access code is valid and has been invalidated.", "facilityName": facility_name}), 200


@app.route("/invalidate", methods=["POST"])
def invalidate():
    data = request.get_json(silent=True)
    if not data:
        logger.warning("POST /invalidate - invalid JSON body from %s", request.remote_addr)
        return jsonify({"success": False, "error": "Request body must be valid JSON."}), 400

    access_code = str(data.get("accessCode", "")).strip()
    facility_id = str(data.get("facilityId", "")).strip()
    facility_name = str(data.get("facilityName", "")).strip()

    missing_fields = []
    if not access_code:
        missing_fields.append("accessCode")
    if not facility_id:
        missing_fields.append("facilityId")
    if not facility_name:
        missing_fields.append("facilityName")
    if missing_fields:
        logger.warning("POST /invalidate - missing fields: %s from %s", missing_fields, request.remote_addr)
        return jsonify({"success": False, "error": f"Missing required field(s): {', '.join(missing_fields)}"}), 400

    if not access_code.isdigit():
        logger.warning("POST /invalidate - invalid accessCode format from %s", request.remote_addr)
        return jsonify({"success": False, "error": "Invalid accessCode format."}), 400

    pin_hash = hash_access_code(access_code)
    conn = get_db_connection()
    cursor = conn.execute(
        "SELECT id, used, facility_name FROM pins WHERE pin_hash = ? AND facility_id = ?",
        (pin_hash, facility_id),
    )
    row = cursor.fetchone()

    if row is None:
        conn.close()
        logger.warning(
            "POST /invalidate - access code not found for facilityId=%s facilityName=%s from %s",
            facility_id, facility_name, request.remote_addr,
        )
        return jsonify({"success": False, "error": "Access code not found."}), 404

    if row["facility_name"] and row["facility_name"] != facility_name:
        conn.close()
        logger.warning(
            "POST /invalidate - facilityName mismatch for facilityId=%s from %s",
            facility_id, request.remote_addr,
        )
        return jsonify({"success": False, "error": "Facility name does not match."}), 403

    if row["used"]:
        conn.close()
        logger.info(
            "POST /invalidate - access code already invalidated for facilityId=%s facilityName=%s",
            facility_id, facility_name,
        )
        return jsonify({"success": False, "message": "Access code is already invalidated."}), 200

    conn.execute("UPDATE pins SET used = 1 WHERE id = ?", (row["id"],))
    conn.commit()
    conn.close()
    logger.info(
        "POST /invalidate - access code invalidated for facilityId=%s facilityName=%s",
        facility_id, facility_name,
    )

    return jsonify({"success": True, "message": "Access code invalidated successfully.", "facilityName": facility_name}), 200


@app.route("/status", methods=["GET"])
def status():
    logger.debug("GET /status from %s", request.remote_addr)
    return jsonify({"success": True, "message": "HTTPS PIN auth server is running."}), 200


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="PIN authentication server")
    parser.add_argument(
        "--mode",
        choices=["http", "https"],
        default="https",
        help="Run server in HTTP or HTTPS mode (default: https)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8443,
        help="Port to listen on (default: 8443)",
    )
    args = parser.parse_args()

    init_db()

    if args.mode == "https":
        tls_context = get_tls_context()

        logger.info("Starting HTTPS server on https://0.0.0.0:%d ...", args.port)
        app.run(host="0.0.0.0", port=args.port, ssl_context=tls_context)
    else:
        logger.info("Starting HTTP server on http://0.0.0.0:%d ...", args.port)
        app.run(host="0.0.0.0", port=args.port)
