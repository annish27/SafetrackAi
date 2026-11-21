import io
import os
import sqlite3
import time
import threading
import smtplib
from datetime import datetime
from math import atan2, cos, radians, sin, sqrt

import cv2
import psutil
import requests
from email.mime.application import MIMEApplication
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from flask import Flask, Response, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from functools import wraps
from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from werkzeug.security import check_password_hash, generate_password_hash
from ultralytics import YOLO

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "sentinel-admin-secret-key")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
DB_DIR = os.path.join(BASE_DIR, "instance")
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "sentinel.db")
REPORT_DIR = os.path.join(BASE_DIR, "reports")
os.makedirs(REPORT_DIR, exist_ok=True)

SCALE_FACTOR = 0.01
SPEED_THRESHOLD = 5.0
PROLONGED_COLLISION_FRAMES = 8
VEHICLE_CLASSES = {1, 2, 3, 5, 7}  # bicycle, car, motorcycle, bus, truck
ACCIDENT_LOCATION = (19.070, 72.877)

SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "pranavreddy772003@gmail.com")
RECEIVER_EMAIL = os.environ.get("RECEIVER_EMAIL", "772003pranav@gmail.com")
PASSWORD = os.environ.get("EMAIL_PASSWORD", "lmip lcuw hmmc soeu")
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY", "7e33ee11182cc2ad20643f007c8b4834")
WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"

model = None
model_lock = threading.Lock()
frame_lock = threading.Lock()
latest_jpeg = None

state_lock = threading.Lock()
job_state = {
    "running": False,
    "completed": False,
    "model_ready": False,
    "accident_detected": False,
    "frame": 0,
    "vehicles": 0,
    "collision_count": 0,
    "max_speed": 0.0,
    "severity": "",
    "weather": "",
    "temperature": 0,
    "vehicle_events": [],
    "police": None,
    "hospital": None,
    "email_sent": False,
    "error": "",
    "source": "",
}


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            email TEXT,
            role TEXT DEFAULT 'admin',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            severity TEXT,
            location TEXT,
            weather TEXT,
            temperature REAL DEFAULT 0,
            status TEXT DEFAULT 'active',
            summary TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    conn.close()


def ensure_default_admin():
    conn = get_db_connection()
    existing = conn.execute(
        "SELECT id FROM users WHERE username = ?",
        (ADMIN_USERNAME,),
    ).fetchone()
    if existing is None:
        conn.execute(
            "INSERT INTO users (username, password_hash, email, role) VALUES (?, ?, ?, ?)",
            (
                ADMIN_USERNAME,
                generate_password_hash(ADMIN_PASSWORD),
                "admin@sentinel.local",
                "admin",
            ),
        )
        conn.commit()
    conn.close()


def get_user_by_username(username):
    conn = get_db_connection()
    user = conn.execute(
        "SELECT * FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    conn.close()
    return user


def record_incident(severity="", location="Unknown", weather="", temperature=0.0, status="active", summary=""):
    conn = get_db_connection()
    cursor = conn.execute(
        "INSERT INTO incidents (severity, location, weather, temperature, status, summary) VALUES (?, ?, ?, ?, ?, ?)",
        (severity, location, weather, float(temperature), status, summary),
    )
    conn.commit()
    incident_id = cursor.lastrowid
    conn.close()
    return incident_id


def get_recent_incidents(limit=8):
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT * FROM incidents ORDER BY created_at DESC LIMIT ?",
        (int(limit),),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def build_route_plan(location, services):
    route_plan = []
    for service in services:
        if not service:
            continue
        lat = service.get("lat")
        lon = service.get("lon")
        if lat is None or lon is None:
            continue
        distance_km = haversine(location[0], location[1], lat, lon)
        route_plan.append(
            {
                "name": service.get("name", "Unnamed service"),
                "type": "police" if service.get("amenity") == "police" else "hospital",
                "lat": lat,
                "lon": lon,
                "distance_km": distance_km,
                "route_color": "#2ecc71" if distance_km < 3 else "#f39c12",
            }
        )
    route_plan.sort(key=lambda item: item["distance_km"])
    return route_plan


def generate_report_pdf(output_path, severity, location, weather, temperature, summary):
    try:
        pdf = canvas.Canvas(output_path, pagesize=letter)
        pdf.setTitle("Sentinel Accident Report")
        pdf.setFont("Helvetica-Bold", 18)
        pdf.drawString(72, 760, "Sentinel Emergency Incident Report")
        pdf.setFont("Helvetica", 12)
        pdf.drawString(72, 730, "Severity: %s" % severity)
        pdf.drawString(72, 710, "Location: %s" % location)
        pdf.drawString(72, 690, "Weather: %s" % weather)
        pdf.drawString(72, 670, "Temperature: %.1f C" % float(temperature or 0))
        pdf.drawString(72, 650, "Summary: ")
        text = pdf.beginText(72, 628)
        text.textLine(summary[:200])
        pdf.drawText(text)
        pdf.save()
        return True
    except Exception:
        return False


def create_incident_report(incident_id):
    incident = None
    conn = get_db_connection()
    incident = conn.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,)).fetchone()
    conn.close()
    if incident is None:
        return None
    report = dict(incident)
    report_path = os.path.join(REPORT_DIR, "incident_%s.pdf" % incident_id)
    ok = generate_report_pdf(
        report_path,
        report.get("severity") or "Unknown",
        report.get("location") or "Unknown",
        report.get("weather") or "Unknown",
        report.get("temperature") or 0,
        report.get("summary") or "No summary available.",
    )
    if not ok:
        return None
    report["pdf_path"] = report_path
    return report


def update_state(**kwargs):
    with state_lock:
        job_state.update(kwargs)


def snapshot_state():
    with state_lock:
        return dict(job_state)


def select_yolo_model():
    total_memory = psutil.virtual_memory().total
    candidates = []
    if total_memory >= 8 * 1024 ** 3:
        candidates = ["yolo11n.pt", "yolov8n.pt"]
    else:
        candidates = ["yolov8n.pt", "yolo11n.pt"]
    last_error = None
    for weights in candidates:
        try:
            loaded = YOLO(weights)
            print("Loaded detection model: %s" % weights)
            return loaded
        except Exception as exc:
            last_error = exc
            print("Could not load %s (%s)" % (weights, exc))
    raise RuntimeError("Unable to load a YOLO model: %s" % last_error)


def load_model_async():
    global model
    try:
        loaded = select_yolo_model()
        with model_lock:
            model = loaded
        update_state(model_ready=True)
    except Exception as exc:
        update_state(error="Model load failed: %s" % exc)


def haversine(lat1, lon1, lat2, lon2):
    earth_km = 6371.0
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    area = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return earth_km * 2 * atan2(sqrt(area), sqrt(1 - area))


def calculate_iou(box1, box2):
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])
    inter_area = max(0, x2 - x1) * max(0, y2 - y1)
    box1_area = max(0, box1[2] - box1[0]) * max(0, box1[3] - box1[1])
    box2_area = max(0, box2[2] - box2[0]) * max(0, box2[3] - box2[1])
    union_area = box1_area + box2_area - inter_area
    return inter_area / union_area if union_area > 0 else 0


def calculate_speed(box1, box2, time_interval):
    if time_interval <= 0:
        return 0.0
    x1, y1 = (box1[0] + box1[2]) / 2, (box1[1] + box1[3]) / 2
    x2, y2 = (box2[0] + box2[2]) / 2, (box2[1] + box2[3]) / 2
    return sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2) / time_interval


def encode_frame(frame):
    ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    if not ok:
        return None
    return buffer.tobytes()


def publish_frame(frame):
    global latest_jpeg
    payload = encode_frame(frame)
    if payload:
        with frame_lock:
            latest_jpeg = payload


def alert_nearest_services(location):
    lat, lon = location
    overpass_query = """
    [out:json];
    (
      node["amenity"="police"](around:5000,%s,%s);
      node["amenity"="hospital"](around:5000,%s,%s);
    );
    out body;
    """ % (lat, lon, lat, lon)
    try:
        response = requests.get(
            "https://overpass-api.de/api/interpreter",
            params={"data": overpass_query},
            timeout=12,
        )
        data = response.json()
    except Exception as exc:
        print("Overpass lookup failed: %s" % exc)
        return None, None

    police_stations = []
    hospitals = []
    for element in data.get("elements", []):
        tags = element.get("tags") or {}
        item = {
            "name": tags.get("name", "Unnamed"),
            "lat": element.get("lat"),
            "lon": element.get("lon"),
        }
        if tags.get("amenity") == "police":
            police_stations.append(item)
        elif tags.get("amenity") == "hospital":
            hospitals.append(item)

    nearest_police = min(
        police_stations,
        key=lambda p: haversine(lat, lon, p["lat"], p["lon"]),
        default=None,
    )
    nearest_hospital = min(
        hospitals,
        key=lambda h: haversine(lat, lon, h["lat"], h["lon"]),
        default=None,
    )
    if nearest_police:
        nearest_police["distance_km"] = haversine(lat, lon, nearest_police["lat"], nearest_police["lon"])
    if nearest_hospital:
        nearest_hospital["distance_km"] = haversine(lat, lon, nearest_hospital["lat"], nearest_hospital["lon"])
    return nearest_police, nearest_hospital


def get_weather(lat, lon):
    try:
        response = requests.get(
            WEATHER_URL,
            params={"lat": lat, "lon": lon, "appid": WEATHER_API_KEY, "units": "metric"},
            timeout=8,
        )
        weather_data = response.json()
        if response.status_code == 200:
            return weather_data["weather"][0]["description"], weather_data["main"]["temp"]
    except Exception as exc:
        print("Weather lookup failed: %s" % exc)
    return "unavailable", 0


def estimate_severity(collision_count, max_speed, weather_condition):
    weather = (weather_condition or "").lower()
    if collision_count > 5 or max_speed > SPEED_THRESHOLD * 1.5 or "rain" in weather or "fog" in weather:
        return "HIGH SEVERITY: Immediate emergency response required"
    if collision_count > 3 or max_speed > SPEED_THRESHOLD:
        return "MEDIUM SEVERITY: Urgent medical attention recommended"
    return "LOW SEVERITY: Standard medical check recommended"


def resize_image(image_path, max_size=(800, 600)):
    with Image.open(image_path) as img:
        img.thumbnail(max_size)
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format="JPEG")
        return img_byte_arr.getvalue()


def generate_accident_report(collision_count, max_speed, weather_condition, temperature, vehicle_events,
                             nearest_police_station, nearest_hospital):
    police_name = nearest_police_station["name"] if nearest_police_station else "Not available"
    hospital_name = nearest_hospital["name"] if nearest_hospital else "Not available"
    police_dist = (
        "%.2f" % nearest_police_station["distance_km"] if nearest_police_station and "distance_km" in nearest_police_station else "N/A"
    )
    hospital_dist = (
        "%.2f" % nearest_hospital["distance_km"] if nearest_hospital and "distance_km" in nearest_hospital else "N/A"
    )
    return """Accident Detection System - Detailed Report
============================================

Incident Details:
-----------------
Date and Time: %s
Location: Latitude %s, Longitude %s

Collision Metrics:
-----------------
Total Collision Count: %s
Maximum Detected Speed: %.2f px/s

Weather Conditions:
------------------
Description: %s
Temperature: %.1f C

Vehicle Events:
--------------
Detected Events: %s

Nearest Emergency Services:
--------------------------
Police Station: %s
Police Station Distance: %s km
Hospital: %s
Hospital Distance: %s km

Severity Assessment:
-------------------
%s
""" % (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ACCIDENT_LOCATION[0],
        ACCIDENT_LOCATION[1],
        collision_count,
        max_speed,
        weather_condition,
        temperature,
        ", ".join(vehicle_events) if vehicle_events else "No significant events",
        police_name,
        police_dist,
        hospital_name,
        hospital_dist,
        estimate_severity(collision_count, max_speed, weather_condition),
    )


def send_email(subject, report, images, pdf_path=None):
    msg = MIMEMultipart()
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(report, "plain"))
    for image in images[:3]:
        if not os.path.exists(image):
            continue
        img = MIMEImage(resize_image(image), name=os.path.basename(image))
        msg.attach(img)
    if pdf_path and os.path.exists(pdf_path):
        with open(pdf_path, "rb") as pdf_file:
            attachment = MIMEApplication(pdf_file.read(), _subtype="pdf")
            attachment.add_header("Content-Disposition", "attachment", filename=os.path.basename(pdf_path))
            msg.attach(attachment)
    server = smtplib.SMTP("smtp.gmail.com", 587, timeout=20)
    server.starttls()
    server.login(SENDER_EMAIL, PASSWORD)
    server.send_message(msg)
    server.quit()


def detect_accident(video_path, send_alert=False):
    global model
    with model_lock:
        detector = model
    if detector is None:
        update_state(running=False, completed=True, error="YOLO model is not ready yet.")
        return

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        update_state(running=False, completed=True, error="Could not open the selected video.")
        return

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frame_interval = 1.0 / fps
    accident_detected = False
    frame_counter = 0
    collision_count = 0
    max_speed = 0.0
    last_boxes = []
    prolonged_collision_count = 0
    images_to_attach = []
    context_fetched = False
    weather_condition = ""
    temperature = 0
    nearest_police_station = None
    nearest_hospital = None
    vehicle_events = []
    post_accident_frames = 0

    update_state(
        running=True,
        completed=False,
        accident_detected=False,
        frame=0,
        vehicles=0,
        collision_count=0,
        max_speed=0.0,
        severity="",
        weather="",
        temperature=0,
        vehicle_events=[],
        police=None,
        hospital=None,
        email_sent=False,
        error="",
        source=os.path.basename(video_path),
    )

    try:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            results = detector(frame, verbose=False, conf=0.35)
            result = results[0]
            xyxy = result.boxes.xyxy.cpu().numpy() if result.boxes is not None else []
            classes = result.boxes.cls.cpu().numpy() if result.boxes is not None else []
            confs = result.boxes.conf.cpu().numpy() if result.boxes is not None else []

            boxes = []
            labels = []
            for i, box in enumerate(xyxy):
                cls_id = int(classes[i]) if i < len(classes) else -1
                if cls_id not in VEHICLE_CLASSES:
                    continue
                boxes.append(box[:4])
                name = result.names.get(cls_id, "vehicle") if hasattr(result, "names") else "vehicle"
                conf = confs[i] if i < len(confs) else 0
                labels.append("%s %.2f" % (name, conf))

            for i, box in enumerate(boxes):
                x1, y1, x2, y2 = [int(v) for v in box]
                color = (0, 0, 255) if accident_detected else (62, 224, 160)
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(frame, labels[i], (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (76, 201, 240), 1)
                if i < len(last_boxes):
                    speed = calculate_speed(last_boxes[i], box, frame_interval)
                    max_speed = max(max_speed, speed)
                    cv2.putText(
                        frame,
                        "%.1f px/s" % speed,
                        (x1, y2 + 16),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.45,
                        (255, 176, 32),
                        1,
                    )

            collision_detected = False
            for i in range(len(boxes)):
                for j in range(i + 1, len(boxes)):
                    if calculate_iou(boxes[i], boxes[j]) > 0.2:
                        collision_detected = True
                        collision_count += 1

            if collision_detected:
                prolonged_collision_count += 1
                vehicle_events.append("Bounding-box overlap")
            else:
                prolonged_collision_count = 0

            if prolonged_collision_count >= PROLONGED_COLLISION_FRAMES or collision_count >= 12:
                accident_detected = True

            if accident_detected:
                cv2.putText(frame, "ACCIDENT DETECTED", (36, 48), cv2.FONT_HERSHEY_SIMPLEX, 1.05, (0, 0, 255), 3)
                if not context_fetched:
                    weather_condition, temperature = get_weather(ACCIDENT_LOCATION[0], ACCIDENT_LOCATION[1])
                    nearest_police_station, nearest_hospital = alert_nearest_services(ACCIDENT_LOCATION)
                    context_fetched = True
                if len(images_to_attach) < 4:
                    frame_filename = os.path.join(UPLOAD_DIR, "frame_%s.jpg" % frame_counter)
                    cv2.imwrite(frame_filename, frame)
                    images_to_attach.append(frame_filename)
                post_accident_frames += 1
                if post_accident_frames > int(fps * 2):
                    publish_frame(frame)
                    break

            severity = estimate_severity(collision_count, max_speed, weather_condition) if accident_detected else ""
            unique_events = sorted(set(vehicle_events))[-4:]
            update_state(
                accident_detected=accident_detected,
                frame=frame_counter,
                vehicles=len(boxes),
                collision_count=collision_count,
                max_speed=max_speed,
                severity=severity,
                weather=weather_condition,
                temperature=temperature,
                vehicle_events=unique_events,
                police=nearest_police_station,
                hospital=nearest_hospital,
            )
            publish_frame(frame)
            last_boxes = boxes
            frame_counter += 1
            time.sleep(max(0.01, min(0.04, frame_interval)))

        if accident_detected:
            summary = (
                "Accident detected with %s collision events, max speed %.1f px/s, "
                "weather=%s, nearest hospital=%s."
                % (
                    collision_count,
                    max_speed,
                    weather_condition or "unavailable",
                    nearest_hospital["name"] if nearest_hospital else "not available",
                )
            )
            record_incident(
                severity=estimate_severity(collision_count, max_speed, weather_condition),
                location=", ".join(map(str, ACCIDENT_LOCATION)),
                weather=weather_condition or "unavailable",
                temperature=float(temperature or 0),
                status="active",
                summary=summary,
            )

        if accident_detected and send_alert and images_to_attach:
            try:
                report = generate_accident_report(
                    collision_count,
                    max_speed,
                    weather_condition,
                    temperature,
                    sorted(set(vehicle_events)),
                    nearest_police_station,
                    nearest_hospital,
                )
                report_path = os.path.join(REPORT_DIR, "accident_report_%s.pdf" % int(time.time()))
                pdf_ok = generate_report_pdf(
                    report_path,
                    estimate_severity(collision_count, max_speed, weather_condition),
                    ", ".join(map(str, ACCIDENT_LOCATION)),
                    weather_condition,
                    temperature,
                    report,
                )
                if pdf_ok:
                    send_email("Accident Detection System - Critical Report", report, images_to_attach, pdf_path=report_path)
                else:
                    send_email("Accident Detection System - Critical Report", report, images_to_attach)
                update_state(email_sent=True)
            except Exception as exc:
                update_state(error="Email dispatch failed: %s" % exc)
    except Exception as exc:
        update_state(error=str(exc))
    finally:
        cap.release()
        update_state(running=False, completed=True)


def start_detection_thread(video_path, send_alert=False):
    if snapshot_state()["running"]:
        return False
    worker = threading.Thread(target=detect_accident, args=(video_path, send_alert), daemon=True)
    worker.start()
    return True


def admin_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login"))
        return view_func(*args, **kwargs)

    return wrapped_view


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/admin")
def admin_root():
    return redirect(url_for("admin_login"))


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        user = get_user_by_username(username)
        if user and check_password_hash(user["password_hash"], password):
            session["is_admin"] = True
            session["admin_user"] = user["username"]
            return redirect(url_for("admin_dashboard"))
        error = "Invalid admin username or password."
    return render_template("admin_login.html", error=error)


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    status = snapshot_state()
    dashboard = {
        "model_ready": bool(status.get("model_ready")),
        "running": bool(status.get("running")),
        "accident_detected": bool(status.get("accident_detected")),
        "frame": status.get("frame", 0),
        "vehicles": status.get("vehicles", 0),
        "collision_count": status.get("collision_count", 0),
        "max_speed": float(status.get("max_speed", 0.0) or 0.0),
        "severity": status.get("severity") or "No active incident",
        "weather": status.get("weather") or "Awaiting detection",
        "temperature": status.get("temperature", 0),
        "vehicle_events": status.get("vehicle_events") or ["Waiting for detection"],
        "police": status.get("police"),
        "hospital": status.get("hospital"),
        "email_sent": bool(status.get("email_sent")),
        "error": status.get("error") or "",
    }
    incidents = get_recent_incidents(8)
    return render_template(
        "admin_dashboard.html",
        dashboard=dashboard,
        incidents=incidents,
        admin_user=session.get("admin_user", "Admin"),
    )


@app.route("/admin/incidents")
@admin_required
def admin_incidents():
    incidents = get_recent_incidents(20)
    return render_template("admin_incidents.html", incidents=incidents, admin_user=session.get("admin_user", "Admin"))


@app.route("/admin/route-map")
@admin_required
def admin_route_map():
    status = snapshot_state()
    fallback_services = [
        {"name": "City Police Station", "lat": ACCIDENT_LOCATION[0] + 0.005, "lon": ACCIDENT_LOCATION[1] - 0.004, "amenity": "police"},
        {"name": "Metro General Hospital", "lat": ACCIDENT_LOCATION[0] - 0.004, "lon": ACCIDENT_LOCATION[1] + 0.006, "amenity": "hospital"},
        {"name": "Emergency Care Center", "lat": ACCIDENT_LOCATION[0] + 0.008, "lon": ACCIDENT_LOCATION[1] + 0.005, "amenity": "hospital"},
    ]
    nearest_services = status.get("police") and status.get("hospital")
    route_services = fallback_services
    if nearest_services:
        route_services = []
        if status.get("police"):
            route_services.append({**status.get("police"), "amenity": "police"})
        if status.get("hospital"):
            route_services.append({**status.get("hospital"), "amenity": "hospital"})
    route_plan = build_route_plan(ACCIDENT_LOCATION, route_services)
    return render_template(
        "admin_route_map.html",
        accident_location=ACCIDENT_LOCATION,
        route_plan=route_plan,
        route_services=route_services,
        admin_user=session.get("admin_user", "Admin"),
    )


@app.route("/admin/report/<int:incident_id>")
@admin_required
def admin_report(incident_id):
    report = create_incident_report(incident_id)
    if report is None:
        return redirect(url_for("admin_incidents"))
    return render_template("admin_report.html", report=report, admin_user=session.get("admin_user", "Admin"))


@app.route("/admin/report/<int:incident_id>/download")
@admin_required
def admin_download_report(incident_id):
    report = create_incident_report(incident_id)
    if report is None:
        return redirect(url_for("admin_incidents"))
    return send_from_directory(REPORT_DIR, os.path.basename(report["pdf_path"]), as_attachment=True)


@app.route("/api/status")
def api_status():
    return jsonify(snapshot_state())


@app.route("/api/detect", methods=["POST"])
def api_detect():
    if not snapshot_state()["model_ready"]:
        return jsonify({"error": "YOLO model is still loading. Try again in a few seconds."}), 409
    if snapshot_state()["running"]:
        return jsonify({"error": "A detection job is already running."}), 409

    send_alert = False
    video_path = None
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        send_alert = bool(payload.get("send_email"))
        sample = payload.get("sample")
        if sample:
            safe_name = os.path.basename(sample)
            candidate = os.path.join(BASE_DIR, safe_name)
            if not os.path.isfile(candidate):
                return jsonify({"error": "Sample video not found."}), 404
            video_path = candidate
    else:
        send_alert = request.form.get("send_email") in ("1", "true", "on")
        video_file = request.files.get("video")
        if video_file and video_file.filename:
            filename = os.path.basename(video_file.filename)
            video_path = os.path.join(UPLOAD_DIR, filename)
            video_file.save(video_path)

    if not video_path:
        return jsonify({"error": "Please choose a video file or a demo clip."}), 400

    start_detection_thread(video_path, send_alert=send_alert)
    return jsonify({"ok": True})


@app.route("/detect", methods=["POST"])
def detect_route():
    video_file = request.files.get("video")
    if not video_file:
        return "No video uploaded.", 400
    video_path = os.path.join(UPLOAD_DIR, os.path.basename(video_file.filename))
    video_file.save(video_path)
    detect_accident(video_path, send_alert=True)
    return "Detection completed."


@app.route("/stream")
def stream():
    def generate():
        while True:
            with frame_lock:
                payload = latest_jpeg
            if payload:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + payload + b"\r\n"
            time.sleep(0.04)

    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)


init_db()
ensure_default_admin()

if __name__ == "__main__":
    threading.Thread(target=load_model_async, daemon=True).start()
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False, threaded=True, use_reloader=False)
