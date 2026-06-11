"""
Shikhbo Web Application — Flask backend.

Run locally:
  cd web && pip install -r requirements.txt
  cp .env.example .env  # fill in your credentials
  python app.py

Env vars: see .env.example
"""

import base64
import json
import os
from functools import wraps

from dotenv import load_dotenv
load_dotenv()

from flask import (
    Flask, Response, jsonify, redirect, render_template,
    request, session, stream_with_context, url_for,
)
from flask_cors import CORS
from werkzeug.utils import secure_filename

from scripts.db import (
    authenticate_user, create_otp, create_session, create_user,
    get_messages, get_or_create_google_user, get_sessions, get_user_by_id,
    save_message, update_password, update_user_profile, user_exists, verify_otp,
)
from scripts.auth.otp_email import send_otp
from scripts.auth.google_oauth import register_oauth
from scripts import hf_client
from scripts.ocr_client import is_image

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "shikhbo_dev_secret_2024")
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("FLASK_ENV") == "production"
CORS(app, supports_credentials=True)

oauth = register_oauth(app)

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
ALLOWED_EXT = {"png", "jpg", "jpeg", "webp", "gif", "pdf"}
MAX_FILE = 20 * 1024 * 1024
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

APP_URL = os.getenv("APP_URL", "http://localhost:5000")


# ── helpers ───────────────────────────────────────────────────────────────────

def _allowed(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return wrapper


# ── pages ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    if "user" in session:
        return redirect(url_for("chat_page"))
    return render_template("index.html")


@app.route("/chat")
@login_required
def chat_page():
    return render_template("chat.html", user=session["user"])


@app.route("/reset-password")
def reset_page():
    return render_template("reset.html")


# ── auth: email/password ──────────────────────────────────────────────────────

@app.route("/api/signup", methods=["POST"])
def signup():
    d = request.get_json(force=True)
    name, email, password = d.get("name","").strip(), d.get("email","").strip(), d.get("password","").strip()
    class_, curriculum = d.get("class","SSC").strip(), d.get("curriculum","NCTB").strip()

    if not all([name, email, password]):
        return jsonify({"error": "Name, email and password are required."}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters."}), 400

    user = create_user(name, email, password, class_, curriculum)
    if user is None:
        return jsonify({"error": "An account with this email already exists."}), 409

    session["user"] = user
    return jsonify({"message": "Account created.", "user": user}), 201


@app.route("/api/login", methods=["POST"])
def login():
    d = request.get_json(force=True)
    email, password = d.get("email","").strip(), d.get("password","").strip()

    if not email or not password:
        return jsonify({"error": "Email and password required."}), 400

    user = authenticate_user(email, password)
    if not user:
        return jsonify({"error": "Invalid email or password."}), 401

    session["user"] = user
    return jsonify({"message": "Login successful.", "user": user}), 200


@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Logged out."}), 200


# ── auth: Google OAuth ────────────────────────────────────────────────────────

@app.route("/api/auth/google")
def google_login():
    redirect_uri = f"{APP_URL}/api/auth/google/callback"
    return oauth.google.authorize_redirect(redirect_uri)


@app.route("/api/auth/google/callback")
def google_callback():
    try:
        token = oauth.google.authorize_access_token()
        info = token.get("userinfo") or oauth.google.userinfo()
        user = get_or_create_google_user(
            google_id=info["sub"],
            email=info["email"],
            name=info.get("name", info["email"].split("@")[0]),
            avatar_url=info.get("picture", ""),
        )
        session["user"] = user
        return redirect(url_for("chat_page"))
    except Exception as e:
        return redirect(f"/?error={str(e)}")


# ── auth: forgot password / OTP ───────────────────────────────────────────────

@app.route("/api/forgot-password", methods=["POST"])
def forgot_password():
    d = request.get_json(force=True)
    email = d.get("email", "").strip().lower()
    if not email:
        return jsonify({"error": "Email required."}), 400
    if not user_exists(email):
        # Don't reveal whether email exists
        return jsonify({"message": "If that email is registered, a code has been sent."}), 200

    code = create_otp(email, purpose="reset")
    sent = send_otp(email, code, purpose="reset")
    if not sent:
        return jsonify({"error": "Could not send email. Try again later."}), 500
    return jsonify({"message": "OTP sent. Check your inbox."}), 200


@app.route("/api/verify-otp", methods=["POST"])
def verify_otp_route():
    d = request.get_json(force=True)
    email = d.get("email", "").strip().lower()
    code = d.get("code", "").strip()
    new_password = d.get("new_password", "").strip()

    if not all([email, code, new_password]):
        return jsonify({"error": "Email, code and new password are required."}), 400
    if len(new_password) < 6:
        return jsonify({"error": "Password must be at least 6 characters."}), 400
    if not verify_otp(email, code, purpose="reset"):
        return jsonify({"error": "Invalid or expired code."}), 400

    update_password(email, new_password)
    return jsonify({"message": "Password updated. You can now log in."}), 200


# ── user ──────────────────────────────────────────────────────────────────────

@app.route("/api/me")
@login_required
def me():
    return jsonify({"user": session["user"]})


@app.route("/api/update-profile", methods=["POST"])
@login_required
def update_profile():
    d = request.get_json(force=True)
    user = session["user"]
    name = d.get("name", "").strip() or user["name"]
    class_ = d.get("class", "").strip() or user["class"]
    curriculum = d.get("curriculum", "").strip() or user["curriculum"]

    updated = update_user_profile(user["uid"], name, class_, curriculum)
    if not updated:
        return jsonify({"error": "Update failed."}), 500

    session["user"] = updated
    session.modified = True
    return jsonify({"message": "Profile updated.", "user": updated}), 200


# ── chat history ──────────────────────────────────────────────────────────────

@app.route("/api/sessions")
@login_required
def list_sessions():
    sessions_list = get_sessions(session["user"]["uid"])
    return jsonify({"sessions": sessions_list})


@app.route("/api/sessions/<int:sid>/messages")
@login_required
def session_messages(sid: int):
    messages = get_messages(sid)
    return jsonify({"messages": messages})


# ── AI query (proxies to HF Space) ────────────────────────────────────────────

@app.route("/api/query", methods=["POST"])
@login_required
def query():
    user = session["user"]
    file_path = None

    if request.content_type and "multipart/form-data" in request.content_type:
        query_text = request.form.get("query", "").strip()
        subject = request.form.get("subject", "ICT")
        mode = request.form.get("mode", "normal")
        session_id = request.form.get("session_id")

        uploaded_file = request.files.get("file")
        if uploaded_file and uploaded_file.filename:
            if not _allowed(uploaded_file.filename):
                return jsonify({"error": "File type not allowed."}), 400
            fname = secure_filename(uploaded_file.filename)
            file_path = os.path.join(UPLOAD_FOLDER, fname)
            uploaded_file.save(file_path)
    else:
        d = request.get_json(force=True)
        query_text = d.get("query", "").strip()
        subject = d.get("subject", "ICT")
        mode = d.get("mode", "normal")
        session_id = d.get("session_id")

    if not query_text:
        return jsonify({"error": "Query is required."}), 400

    curriculum = user.get("curriculum", "NCTB")
    class_ = user.get("class", "SSC")

    # Persist to DB
    if not session_id:
        session_id = create_session(user["uid"], subject, curriculum)
    try:
        save_message(session_id, "user", query_text)
    except Exception:
        pass

    # Image uploaded → HF Space /vision (OCR+RAG) → stream answer
    if file_path and is_image(file_path):
        def image_generate():
            try:
                yield json.dumps({"status": "reading_image"}) + "\n"

                with open(file_path, "rb") as fh:
                    image_b64 = base64.b64encode(fh.read()).decode()

                result = hf_client.vision_query(image_b64, query_text, subject, curriculum, class_)

                if "error" in result:
                    yield json.dumps({"chunk": f"[Image error: {result['error']}]"}) + "\n"
                    return

                extracted = result.get("extracted_text", "")
                answer = result.get("answer", "")
                sources = result.get("sources", [])
                grounded = result.get("grounded", False)

                if grounded and sources:
                    yield json.dumps({"status": "grounded", "sources": sources}) + "\n"

                if extracted:
                    yield json.dumps({"status": "image_read", "extracted_text": extracted[:200]}) + "\n"

                # Stream answer in word chunks
                assistant_reply: list[str] = []
                words = answer.split(" ")
                buf: list[str] = []
                for word in words:
                    buf.append(word)
                    if len(buf) >= 8:
                        chunk = " ".join(buf) + " "
                        assistant_reply.append(chunk)
                        yield json.dumps({"chunk": chunk}) + "\n"
                        buf = []
                if buf:
                    chunk = " ".join(buf)
                    assistant_reply.append(chunk)
                    yield json.dumps({"chunk": chunk}) + "\n"

                try:
                    save_message(session_id, "assistant", "".join(assistant_reply))
                except Exception:
                    pass
            finally:
                if file_path and os.path.isfile(file_path):
                    try:
                        os.remove(file_path)
                    except OSError:
                        pass

        return Response(stream_with_context(image_generate()), mimetype="application/x-ndjson")

    # Text query → stream from HF Space
    assistant_reply = []

    def generate():
        for payload in hf_client.chat_stream(query_text, curriculum, class_, subject, mode):
            if "chunk" in payload:
                assistant_reply.append(payload["chunk"])
            yield json.dumps(payload) + "\n"
        full_reply = "".join(assistant_reply)
        if full_reply:
            try:
                save_message(session_id, "assistant", full_reply)
            except Exception:
                pass

    return Response(stream_with_context(generate()), mimetype="application/x-ndjson")


# ── health ────────────────────────────────────────────────────────────────────

@app.route("/api/health")
def health_check():
    hf_status = hf_client.health()
    return jsonify({"web": "ok", "hf_space": hf_status})


if __name__ == "__main__":
    app.run(debug=True, port=5000, host="0.0.0.0")
