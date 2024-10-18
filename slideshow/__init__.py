# coding: utf-8

from __future__ import print_function
import os
import sys
import threading
from flask import (
    Flask,
    render_template,
    render_template_string,
    jsonify,
    request,
    send_from_directory,
    redirect,
    url_for,
    flash,
    session
)
from flask_httpauth import HTTPBasicAuth
from flask_socketio import SocketIO
from datetime import datetime
import numpy as np
import time

from .database import database, Post, get_rnd_db_entries, get_max_id
from .image import fix_orientation

auth = HTTPBasicAuth()

app = Flask(__name__)


# Ensure session lasts for the duration of the browser session
app.config['SESSION_PERMANENT'] = True  # Session will not persist when the browser is closed
app.config['SESSION_TYPE'] = 'filesystem'  # Optional: Store session on the server-side if needed

app.secret_key = "DONTTELLANYONETHESECRETKEY"
app.config["DATABASE"] = os.getenv("SLIDESHOW_DB", "slideshow.sqlite")
app.config["IMG_DIR"] = os.getenv(
    "SLIDESHOW_IMG_DIR", os.path.join(os.getenv("HOME"), "Pictures", "wedding")
)
app.config["HOSTNAME"] = os.getenv("HOSTNAME", "localhost")
app.config["PORT"] = os.getenv("PORT", "8000")

USERNAME = os.getenv("SLIDESHOW_USER", "admin")
PASSWORD = os.getenv("SLIDESHOW_PASSWORD", "horst")

# Use the auth object to handle password authentication
@auth.verify_password
def verify_password(username, password):
    if username == USERNAME and password == PASSWORD:
        return True
    return False

# Use session-based authentication
def login_required(f):
    """Decorator to protect routes."""
    def decorated_function(*args, **kwargs):
        if not session.get('authenticated'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['password'] == PASSWORD:
            session['authenticated'] = True  # Cache password in session
            return redirect(url_for('client'))  # Redirect to the client after login
        else:
            return "Incorrect password", 401
    return render_template_string('''
        <form method="post">
            <input type="password" name="password" placeholder="Enter Password">
            <input type="submit" value="Submit">
        </form>
    ''')

@app.route('/logout')
def logout():
    session.pop('authenticated', None)  # Clear authentication from session
    return redirect(url_for('login'))

# Init app before launch
@app.before_first_request
def init_app():
    # Setup database
    database.init(app.config["DATABASE"])
    database.create_tables([Post], safe=True)
    # Set the timer to push new random content to gallery
    socket.start_background_task(start_gallery_updater)

def start_gallery_updater():
    while True:
        socket.sleep(15)
        print("Updated gallery", file=sys.stderr)

        # Access HOSTNAME and PORT from the Flask configuration
        hostname = app.config.get("HOSTNAME", "localhost")
        port = app.config.get("PORT", "8000")

        filenames, _ = get_rnd_db_entries(N=4)
        URL = f"http://{hostname}:{port}/images/"
        filenames = {i: URL + s for i, s in enumerate(filenames)}
        socket.emit(
            "galupdate",
            {
                "img_tl": filenames[0],
                "img_bl": filenames[1],
                "img_tr": filenames[2],
                "img_br": filenames[3],
            }
        )

# Init flask SocketIO
socket = SocketIO()
socket.init_app(app)

@app.route('/')
@login_required  # Use session-based login
def client():
    """Client site, for sending pictures and comments"""
    return render_template("client.html", error=request.args.get("error"))

@app.route("/gallery")
@login_required  # Protect gallery with login
def gallery():
    """Gallery site, for displaying sent pictures and comments"""
    # Fetch 5 images from database
    filenames, comments = get_rnd_db_entries(N=5)
    print(filenames)
    URL = f"http://{app.config['HOSTNAME']}:{app.config['PORT']}/images/"
    filenames = {i: URL + s for i, s in enumerate(filenames)}
    return render_template("gallery.html", filenames=filenames, comment=comments[2])

@app.route("/posts", methods=["POST"])
@login_required  # Ensure only authenticated users can post
def add_post():
    # Fill post db entry
    URL = f"http://{app.config['HOSTNAME']}:{app.config['PORT']}/images/"
    try:
        post = Post()
        post.timestamp = datetime.utcnow()
        comment = request.form["comment"]
        post.comment = comment

        # Get image from form, resize and save
        img_file = request.files["image"]
        img_resized = fix_orientation(img_file)

        ext = os.path.splitext(request.files["image"].filename)[1]
        filename = post.timestamp.isoformat().replace(":", "_") + ext
        img_path = os.path.join(app.config["IMG_DIR"], filename)
        img_resized.save(img_path)

        # Save image filename in post db and finalize
        post.name = filename
        post.save()
        msg = "Bild erfolgreich hochgeladen :)"

        print('Emitting new image')
        socket.emit("new_image", {"filename": URL + filename, "comment": comment})
    except Exception as e:
        msg = e

    flash(msg)
    return redirect(url_for("client"))

@app.route("/posts", methods=["GET"])
@login_required
def get_posts():
    posts = list(Post.select().dicts())
    return jsonify(posts=posts)

# Hosted images from database, access by full filename
@app.route("/images/<name>")
# @login_required  # Protect images with login
def img_host(name):
    return send_from_directory(app.config["IMG_DIR"], name)

@app.route("/database_clear")
@login_required
def db_clear():
    max_id = get_max_id()
    if max_id is not None:
        del_query = (
            Post.delete()
            .where(Post.id << np.arange(1, max_id + 1).tolist())
        )
        try:
            rows_del = del_query.execute()
            msg = "Deleted {} rows. DB is now empty.".format(rows_del)
            success = True
        except Exception as e:
            msg = e
            success = False
    else:
        msg = "DB was already empty, did nothing."
        success = True

    return render_template("clear_db.html", success=success, msg=msg)

@app.route("/database_show")
@login_required
def db_show():
    query = Post.select()
    s = "<h1> Database dump: </h1>"
    for item in query:
        s += "{}: {}".format(item.id, item.name) + "<br>"

    return s

@socket.on('connect')
@login_required  # Protect socket connection with login
def handle_connect():
    print('Client connected!')

@socket.on('disconnect')
def handle_disconnect():
    print('Client disconnected!')

# Start the server wrapper
def start_server():
    socket.run(app, host="0.0.0.0", port=8000, debug=True)
