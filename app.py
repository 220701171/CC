from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_pymongo import PyMongo
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import timedelta
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev_secret_for_local_testing')

app.config['MONGO_URI'] = os.environ.get('MONGO_URI', '')
mongo = PyMongo(app)

app.permanent_session_lifetime = timedelta(minutes=30)

COLLEGE_KEY = "Rec#1234"

students = mongo.db.students
admins = mongo.db.admins
registrations = mongo.db.registrations
events = mongo.db.events


# Login Protection Decorator
def login_required(role=None):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if 'user' not in session:
                flash("Login required")
                return redirect(url_for("index"))
            if role and session.get('role') != role:
                flash("Unauthorized Access")
                return redirect(url_for("index"))
            return func(*args, **kwargs)
        return wrapper
    return decorator


@app.route('/')
def index():
    return render_template("index.html")


# ================================================================
#                           STUDENT
# ================================================================
@app.route("/student/event/register/<eid>", methods=["GET", "POST"])
@login_required("student")
def register_event(eid):

    event = events.find_one({"_id": ObjectId(eid)})
    student = students.find_one({"_id": ObjectId(session['user'])})

    if not event:
        flash("Event not found")
        return redirect(url_for("student_dashboard"))

    # ❗ Block if full
    if int(event["capacity"]) <= 0:
        flash("Registration closed! No seats available.")
        return redirect(url_for("student_dashboard"))

    # ❗ Prevent duplicate registrations
    existing = registrations.find_one({
        "event_id": eid,
        "student_id": session['user']
    })
    if existing:
        flash("You have already registered for this event!")
        return redirect(url_for("student_dashboard"))

    if request.method == "POST":
        # Insert registration
        registrations.insert_one({
            "event_id": eid,
            "student_id": session['user'],
            "student_name": student["name"],
            "student_email": student["email"]
        })

        # ❗ Reduce capacity by 1
        events.update_one(
            {"_id": ObjectId(eid)},
            {"$inc": {"capacity": -1}}
        )

        flash("Registration Successful!")
        return redirect(url_for("student_dashboard"))

    return render_template("event_register.html", event=event, student=student)


@app.route('/student/register', methods=['GET', 'POST'])
def student_register():
    if request.method == 'POST':
        name = request.form['name'].strip()
        email = request.form['email'].strip().lower()
        password = request.form['password']

        if students.find_one({'email': email}):
            flash("Email already registered")
            return redirect(url_for('student_register'))

        students.insert_one({
            "name": name,
            "email": email,
            "password": generate_password_hash(password),
            "approved": False,
            "room_id": None
        })

        flash("Registration successful, wait for approval")
        return redirect(url_for('index'))

    return render_template("student_register.html")


@app.route('/student/login', methods=['GET', 'POST'])
def student_login():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']

        user = students.find_one({'email': email})

        if not user or not check_password_hash(user['password'], password):
            flash("Invalid Credentials")
            return redirect(url_for('student_login'))

        if not user.get('approved'):
            return render_template("pending_approval.html", email=user['email'])

        session['user'] = str(user['_id'])
        session['role'] = 'student'
        session.permanent = True

        return redirect(url_for('student_dashboard'))

    return render_template("student_login.html")


@app.route('/student/dashboard')
@login_required("student")
def student_dashboard():
    all_events = list(events.find())
    return render_template("student_dashboard.html", events=all_events)


# ================================================================
#                           ADMIN / WARDEN
# ================================================================
@app.route('/admin/register', methods=['GET', 'POST'])
def admin_register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email'].strip().lower()
        password = request.form['password']
        key = request.form['college_key']

        if key != COLLEGE_KEY:
            flash("Invalid College Key")
            return redirect(url_for('admin_register'))

        admins.insert_one({
            "name": name,
            "email": email,
            "password": generate_password_hash(password)
        })

        flash("Admin registered successfully")
        return redirect(url_for('index'))

    return render_template("admin_register.html")


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']
        user = admins.find_one({"email": email})

        if not user or not check_password_hash(user['password'], password):
            flash("Invalid credentials")
            return redirect(url_for('admin_login'))

        session['user'] = str(user['_id'])
        session['role'] = 'admin'
        session.permanent = True

        return redirect(url_for('admin_dashboard'))

    return render_template("admin_login.html")


@app.route('/admin/dashboard')
@login_required("admin")
def admin_dashboard():
    pending = list(students.find({"approved": False}))
    all_events = list(events.find())

    # Fetch registrations event-wise
    event_regs = {}
    for e in all_events:
        event_regs[str(e["_id"])] = list(registrations.find({"event_id": str(e["_id"])}))

    return render_template("admin_dashboard.html",
                           pending=pending,
                           events=all_events,
                           event_regs=event_regs)


@app.route('/admin/approve/<sid>')
@login_required("admin")
def approve_student(sid):
    students.update_one({"_id": ObjectId(sid)}, {"$set": {"approved": True}})
    flash("Student approved")
    return redirect(url_for("admin_dashboard"))


# ================================================================
#                       EVENT MANAGEMENT (ADMIN ONLY)
# ================================================================
@app.route('/admin/event/add', methods=["POST"])
@login_required("admin")
def add_event():
    data = {
        "club_name": request.form['club'],
        "event_name": request.form['event'],
        "capacity": int(request.form['capacity']),
        "description": request.form['desc']
    }
    events.insert_one(data)

    flash("Event added successfully")
    return redirect(url_for("admin_dashboard"))


@app.route('/admin/event/delete/<eid>')
@login_required("admin")
def delete_event(eid):
    events.delete_one({"_id": ObjectId(eid)})
    registrations.delete_many({"event_id": eid})
    flash("Event deleted")
    return redirect(url_for("admin_dashboard"))


@app.route('/admin/event/update/<eid>', methods=["POST"])
@login_required("admin")
def update_event(eid):
    events.update_one(
        {"_id": ObjectId(eid)},
        {"$set": {
            "club_name": request.form['club'],
            "event_name": request.form['event'],
            "capacity": int(request.form['capacity']),
            "description": request.form['desc']
        }}
    )
    flash("Event updated successfully")
    return redirect(url_for("admin_dashboard"))


@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out")
    return redirect(url_for('index'))


if __name__ == "__main__":
    app.run(debug=True)

