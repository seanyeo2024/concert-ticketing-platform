from flask import Flask, jsonify, request
from flask_cors import CORS
import mysql.connector
import os
import uuid
from datetime import datetime

app = Flask(__name__)
CORS(app)


def get_db(database: str | None = None):
    return mysql.connector.connect(
        host=os.environ.get("MYSQL_HOST", "localhost"),
        port=int(os.environ.get("MYSQL_PORT", 3306)),
        database=database or os.environ.get("MYSQL_DATABASE", "concert_db"),
        user=os.environ.get("MYSQL_USER", "ctms_user"),
        password=os.environ.get("MYSQL_PASSWORD", "ctms_pass"),
    )


def err(code, message, status=400):
    return (
        jsonify(
            {
                "error": {
                    "code": code,
                    "message": message,
                    "service": "concert",
                    "timestamp": datetime.utcnow().isoformat(),
                }
            }
        ),
        status,
    )


def ensure_schema():
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS concert (
          concertId VARCHAR(36) PRIMARY KEY,
          name VARCHAR(200) NOT NULL,
          artistName VARCHAR(100) NOT NULL,
          venue VARCHAR(200) NOT NULL,
          eventDate DATETIME NOT NULL,
          totalSeats INT NOT NULL DEFAULT 0,
          availableSeats INT NOT NULL DEFAULT 0,
          status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
          cancellationReason VARCHAR(500) NULL,
          currency VARCHAR(3) NOT NULL DEFAULT 'SGD',
          createdAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS seat_category (
          categoryId VARCHAR(36) PRIMARY KEY,
          concertId VARCHAR(36) NOT NULL,
          categoryName VARCHAR(100) NOT NULL,
          basePrice DECIMAL(10,2) NULL,
          totalSeats INT NOT NULL DEFAULT 0,
          availableSeats INT NOT NULL DEFAULT 0,
          createdAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          CONSTRAINT fk_seatcat_concert
            FOREIGN KEY (concertId) REFERENCES concert (concertId)
            ON DELETE CASCADE ON UPDATE CASCADE
        )
        """
    )
    cur.execute("SHOW COLUMNS FROM seat_category LIKE 'basePrice'")
    if not cur.fetchone():
        cur.execute("ALTER TABLE seat_category ADD COLUMN basePrice DECIMAL(10,2) NULL AFTER categoryName")

    cur.execute("SELECT COUNT(*) FROM concert")
    has_rows = cur.fetchone()[0] > 0
    if not has_rows:
        seed_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "../../../database/seeds/concert_db.sql")
        )
        with open(seed_path, "r", encoding="utf-8") as f:
            sql = f.read()
        statements = [stmt.strip() for stmt in sql.split(";") if stmt.strip()]
        for statement in statements:
            cur.execute(statement)
    db.commit()
    cur.close()
    db.close()


def sync_concert_counts(concert_id):
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        UPDATE concert c
        JOIN (
          SELECT concertId, SUM(totalSeats) AS tot, SUM(availableSeats) AS avail
          FROM seat_category
          WHERE concertId = %s
          GROUP BY concertId
        ) s ON c.concertId = s.concertId
        SET c.totalSeats = s.tot,
            c.availableSeats = s.avail
        """,
        (concert_id,),
    )
    db.commit()
    cur.close()
    db.close()


ensure_schema()


@app.route("/concerts", methods=["GET"])
def list_concerts():
    status = request.args.get("status")
    db = get_db()
    cur = db.cursor(dictionary=True)
    if status:
        cur.execute("SELECT * FROM concert WHERE status=%s ORDER BY eventDate", (status,))
    else:
        cur.execute("SELECT * FROM concert ORDER BY eventDate")
    rows = cur.fetchall()
    cur.close()
    db.close()
    return jsonify({"concerts": rows})


@app.route("/concerts/<concert_id>", methods=["GET"])
def get_concert(concert_id):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM concert WHERE concertId=%s", (concert_id,))
    row = cur.fetchone()
    cur.close()
    db.close()
    if not row:
        return err("CONCERT_NOT_FOUND", "Concert not found", 404)
    return jsonify(row)


@app.route("/concerts", methods=["POST"])
def create_concert():
    data = request.get_json() or {}
    required = ["name", "artistName", "venue", "eventDate", "currency"]
    if not all(data.get(k) for k in required):
        return err("MISSING_FIELDS", f"Required: {required}")

    concert_id = data.get("concertId") or f"CONC-{uuid.uuid4().hex[:6].upper()}"
    categories = data.get("categories", [])
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute(
            """
            INSERT INTO concert
              (concertId, name, artistName, venue, eventDate, totalSeats, availableSeats, status, currency, cancellationReason)
            VALUES (%s,%s,%s,%s,%s,0,0,%s,%s,%s)
            """,
            (
                concert_id,
                data["name"],
                data["artistName"],
                data["venue"],
                data["eventDate"],
                data.get("status", "ACTIVE"),
                data["currency"],
                data.get("cancellationReason"),
            ),
        )
        for category in categories:
            cur.execute(
                """
                INSERT INTO seat_category
                  (categoryId, concertId, categoryName, basePrice, totalSeats, availableSeats)
                VALUES (%s,%s,%s,%s,%s,%s)
                """,
                (
                    category.get("categoryId") or f"CAT-{uuid.uuid4().hex[:8].upper()}",
                    concert_id,
                    category["categoryName"],
                    category.get("basePrice"),
                    category["totalSeats"],
                    category.get("availableSeats", category["totalSeats"]),
                ),
            )
        db.commit()
    except mysql.connector.IntegrityError:
        db.rollback()
        return err("CONCERT_EXISTS", "Concert or category already exists", 409)
    finally:
        cur.close()
        db.close()

    sync_concert_counts(concert_id)
    return jsonify({"concertId": concert_id}), 201


@app.route("/concerts/<concert_id>", methods=["PUT"])
def update_concert(concert_id):
    data = request.get_json() or {}
    allowed = [
        "name",
        "artistName",
        "venue",
        "eventDate",
        "status",
        "currency",
        "cancellationReason",
        "availableSeats",
        "totalSeats",
    ]
    updates = {k: data[k] for k in allowed if k in data}
    if not updates:
        return err("NO_FIELDS", "No updatable fields provided")

    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM concert WHERE concertId=%s", (concert_id,))
    existing = cur.fetchone()
    if not existing:
        cur.close()
        db.close()
        return err("CONCERT_NOT_FOUND", "Concert not found", 404)
    if existing["status"] == "CANCELLED" and updates.get("status") == "CANCELLED":
        cur.close()
        db.close()
        return err("ALREADY_CANCELLED", "Concert already cancelled", 409)

    set_clause = ", ".join(f"{k}=%s" for k in updates)
    values = list(updates.values()) + [concert_id]
    cur = db.cursor()
    cur.execute(f"UPDATE concert SET {set_clause} WHERE concertId=%s", values)
    db.commit()
    cur.close()
    db.close()
    return jsonify({"updated": True, "concertId": concert_id})


@app.route("/concerts/<concert_id>/seats", methods=["GET"])
def get_seats(concert_id):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute(
        "SELECT categoryId, concertId, categoryName, basePrice, totalSeats, availableSeats FROM seat_category WHERE concertId=%s ORDER BY categoryId",
        (concert_id,),
    )
    rows = cur.fetchall()
    cur.close()
    if not rows:
        cur = db.cursor(dictionary=True)
        cur.execute("SELECT concertId FROM concert WHERE concertId=%s", (concert_id,))
        concert = cur.fetchone()
        cur.close()
        db.close()
        if not concert:
            return err("CONCERT_NOT_FOUND", "Concert not found", 404)
        return jsonify({"concertId": concert_id, "categories": []})
    db.close()
    return jsonify({"concertId": concert_id, "categories": rows})


@app.route("/concerts/<concert_id>/seats", methods=["POST"])
def create_seat_categories(concert_id):
    data = request.get_json() or {}
    categories = data.get("categories", [])
    if not categories:
        return err("EMPTY_PAYLOAD", "categories array is required")

    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT concertId FROM concert WHERE concertId=%s", (concert_id,))
    existing_concert = cur.fetchone()
    cur.close()
    db.close()
    if not existing_concert:
        return err("CONCERT_NOT_FOUND", "Concert not found", 404)

    db = get_db()
    cur = db.cursor()
    created = []
    try:
        for category in categories:
            if not category.get("categoryName") or category.get("totalSeats") is None:
                db.rollback()
                return err("MISSING_FIELDS", "Each category needs categoryName and totalSeats")

            total_seats = int(category["totalSeats"])
            available_seats = int(category.get("availableSeats", total_seats))
            if total_seats < 0 or available_seats < 0 or available_seats > total_seats:
                db.rollback()
                return err("INVALID_SEAT_COUNTS", "Seat counts would become invalid", 400)

            category_id = category.get("categoryId") or f"CAT-{uuid.uuid4().hex[:8].upper()}"
            cur.execute(
                """
                INSERT INTO seat_category
                  (categoryId, concertId, categoryName, basePrice, totalSeats, availableSeats)
                VALUES (%s,%s,%s,%s,%s,%s)
                """,
                (
                    category_id,
                    concert_id,
                    category["categoryName"],
                    category.get("basePrice"),
                    total_seats,
                    available_seats,
                ),
            )
            created.append(
                {
                    "categoryId": category_id,
                    "categoryName": category["categoryName"],
                    "totalSeats": total_seats,
                    "availableSeats": available_seats,
                    "basePrice": category.get("basePrice"),
                }
            )
        db.commit()
    except mysql.connector.IntegrityError:
        db.rollback()
        return err("CATEGORY_EXISTS", "One or more categories already exist for this concert", 409)
    finally:
        cur.close()
        db.close()

    sync_concert_counts(concert_id)
    return jsonify({"concertId": concert_id, "categories": created}), 201


@app.route("/concerts/<concert_id>/seats/<category_id>", methods=["PUT"])
def update_seat_category(concert_id, category_id):
    data = request.get_json() or {}
    if not any(key in data for key in ("availableSeats", "totalSeats", "deltaAvailable")):
        return err("MISSING_FIELDS", "Provide availableSeats, totalSeats, or deltaAvailable")

    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute(
        "SELECT * FROM seat_category WHERE concertId=%s AND categoryId=%s",
        (concert_id, category_id),
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        db.close()
        return err("CATEGORY_NOT_FOUND", "Seat category not found", 404)

    new_total = data.get("totalSeats", row["totalSeats"])
    new_available = row["availableSeats"]
    if "availableSeats" in data:
        new_available = data["availableSeats"]
    if "deltaAvailable" in data:
        new_available = row["availableSeats"] + int(data["deltaAvailable"])
    if new_available < 0 or new_total < 0 or new_available > new_total:
        cur.close()
        db.close()
        return err("INVALID_SEAT_COUNTS", "Seat counts would become invalid", 400)

    cur = db.cursor()
    cur.execute(
        """
        UPDATE seat_category
        SET totalSeats=%s, availableSeats=%s
        WHERE concertId=%s AND categoryId=%s
        """,
        (new_total, new_available, concert_id, category_id),
    )
    db.commit()
    cur.close()
    db.close()
    sync_concert_counts(concert_id)
    return jsonify(
        {
            "updated": True,
            "concertId": concert_id,
            "categoryId": category_id,
            "totalSeats": new_total,
            "availableSeats": new_available,
        }
    )


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "concert"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
