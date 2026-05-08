from flask import Flask, render_template, request, redirect, session, send_from_directory
import os
import sqlite3
from pdfminer.high_level import extract_text
import docx
from werkzeug.utils import secure_filename

# 🔥 PDF
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

app = Flask(__name__)
app.secret_key = "secret123"

# -------- FOLDERS -------- #

UPLOAD_FOLDER = "resumes"
REPORT_FOLDER = "reports"

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["REPORT_FOLDER"] = REPORT_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(REPORT_FOLDER, exist_ok=True)

# -------- DATABASE -------- #

def init_db():
    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute("""CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE,
        password TEXT
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS uploads(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT,
        filename TEXT,
        score REAL,
        matched TEXT,
        missing TEXT
    )""")

    conn.commit()
    conn.close()

init_db()

# -------- REGISTER -------- #

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = sqlite3.connect("users.db")
        cur = conn.cursor()

        cur.execute("SELECT * FROM users WHERE email=?", (email,))
        user = cur.fetchone()

        if user:
            conn.close()
            return render_template("register.html", error="⚠️ User already exists!")

        cur.execute("INSERT INTO users(email,password) VALUES(?,?)",
                    (email, password))

        conn.commit()
        conn.close()

        return redirect("/")

    return render_template("register.html", error=None)

# -------- LOGIN -------- #

@app.route("/", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        # ADMIN LOGIN
        if email == "admin@gmail.com" and password == "admin@123":
            session.clear()
            session["admin"] = True
            return redirect("/admin")

        conn = sqlite3.connect("users.db")
        cur = conn.cursor()

        cur.execute("SELECT * FROM users WHERE email=? AND password=?",
                    (email, password))

        user = cur.fetchone()
        conn.close()

        if user:
            session.clear()
            session["user"] = email
            return redirect("/dashboard")
        else:
            return render_template("login.html", error="❌ Invalid Email or Password")

    return render_template("login.html", error=None)

# -------- FORGOT PASSWORD -------- #

@app.route("/forgot", methods=["GET", "POST"])
def forgot():
    if request.method == "POST":
        email = request.form["email"]
        new_pass = request.form["password"]

        conn = sqlite3.connect("users.db")
        cur = conn.cursor()

        cur.execute("SELECT * FROM users WHERE email=?", (email,))
        user = cur.fetchone()

        if user:
            cur.execute("UPDATE users SET password=? WHERE email=?",
                        (new_pass, email))
            conn.commit()
            conn.close()
            return render_template("forgot.html", msg="✅ Password Updated!", error=None)
        else:
            conn.close()
            return render_template("forgot.html", error="❌ Email not found!", msg=None)

    return render_template("forgot.html", msg=None, error=None)

# -------- DASHBOARD -------- #

@app.route("/dashboard", methods=["GET","POST"])
def dashboard():
    if "user" not in session:
        return redirect("/")

    score = 0
    matched = []
    missing = []

    if request.method == "POST":
        resume = request.files["resume"]
        job = request.form["job"]

        if resume:
            filename = secure_filename(resume.filename)

            # 🔥 UNIQUE NAME
            filename = session["user"] + "_" + filename

            path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            resume.save(path)

            text = read_resume(path)
            score, matched, missing = calculate_match(text, job)

            conn = sqlite3.connect("users.db")
            cur = conn.cursor()

            cur.execute("INSERT INTO uploads(email,filename,score,matched,missing) VALUES(?,?,?,?,?)",
                        (session["user"], filename, score, ", ".join(matched), ", ".join(missing)))

            conn.commit()
            conn.close()

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute("SELECT filename, score, matched, missing FROM uploads WHERE email=?",
                (session["user"],))
    history = cur.fetchall()

    conn.close()

    return render_template("dashboard.html",
                           score=score,
                           matched=matched,
                           missing=missing,
                           history=history)

# -------- DOWNLOAD REPORT -------- #

@app.route("/download/<filename>")
def download_file(filename):
    if "user" not in session:
        return redirect("/")

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute("SELECT score, matched, missing FROM uploads WHERE filename=? AND email=?",
                (filename, session["user"]))
    data = cur.fetchone()
    conn.close()

    if not data:
        return "No report found"

    score, matched, missing = data

    matched_list = matched.split(", ")
    missing_list = missing.split(", ")

    # 🔥 SMART SUGGESTIONS
    suggestions = []
    for skill in missing_list:
        if skill == "python":
            suggestions.append("Python → AI, ML, Backend")
        elif skill == "sql":
            suggestions.append("SQL → Database & Data roles")
        elif skill == "react":
            suggestions.append("React → Frontend jobs")
        else:
            suggestions.append(f"Improve {skill}")

    # ✅ SAVE IN REPORTS FOLDER
    report_name = filename.replace(".pdf", "") + "_report.pdf"
    file_path = os.path.join(app.config["REPORT_FOLDER"], report_name)

    doc = SimpleDocTemplate(file_path)
    styles = getSampleStyleSheet()

    content = []

    content.append(Paragraph("AI Resume Analysis Report", styles["Title"]))
    content.append(Spacer(1, 15))

    content.append(Paragraph(f"<b>User:</b> {session['user']}", styles["Normal"]))
    content.append(Paragraph(f"<b>Resume:</b> {filename}", styles["Normal"]))
    content.append(Paragraph(f"<b>Score:</b> {score}%", styles["Normal"]))

    content.append(Spacer(1, 10))

    content.append(Paragraph("<b>Matched Skills:</b>", styles["Heading2"]))
    for m in matched_list:
        content.append(Paragraph("✔ " + m, styles["Normal"]))

    content.append(Spacer(1, 10))

    content.append(Paragraph("<b>Missing Skills:</b>", styles["Heading2"]))
    for m in missing_list:
        content.append(Paragraph("✘ " + m, styles["Normal"]))

    content.append(Spacer(1, 10))

    content.append(Paragraph("<b>Suggestions:</b>", styles["Heading2"]))
    for s in suggestions:
        content.append(Paragraph("💡 " + s, styles["Normal"]))

    doc.build(content)

    return send_from_directory(app.config["REPORT_FOLDER"], report_name, as_attachment=True)

# -------- ADMIN -------- #

@app.route("/admin")
def admin():
    if "admin" not in session:
        return redirect("/")

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute("SELECT email, filename, score, matched, missing FROM uploads")
    data = cur.fetchall()

    conn.close()

    return render_template("admin.html", data=data)

# -------- FILE VIEW -------- #

@app.route("/user_view/<filename>")
def user_view_file(filename):
    if "user" not in session:
        return redirect("/")
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

# -------- LOGOUT -------- #

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# -------- FUNCTIONS -------- #

def read_resume(file):
    text = ""
    try:
        if file.endswith(".pdf"):
            text = extract_text(file)
        elif file.endswith(".docx"):
            doc = docx.Document(file)
            for p in doc.paragraphs:
                text += p.text
    except:
        print("Error reading file")
    return text.lower()

def calculate_match(resume, job):
    r = set(resume.split())
    j = set(job.lower().split())

    if not j:
        return 0, [], []

    matched = list(r & j)
    missing = list(j - r)
    score = (len(matched)/len(j))*100

    return round(score,2), matched[:10], missing[:10]

# -------- RUN -------- #

if __name__ == "__main__":
    app.run(debug=True)