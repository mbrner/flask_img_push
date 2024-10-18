# coding: utf-8

from __future__ import print_function
import os
import sys
import threading
from flask import (
    Flask,
    render_template,
    jsonify,
    request,
    send_from_directory,
    redirect,
    url_for,
    flash,
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
app.secret_key = "DONTTELLANYONETHESECRETKEY"
app.config["DATABASE"] = os.getenv("SLIDESHOW_DB", "slideshow.sqlite")
app.config["IMG_DIR"] = os.getenv(
    "SLIDESHOW_IMG_DIR", os.path.join(os.getenv("HOME"), "Pictures", "wedding")
)

# Load password from environment variable or use a default (in production, ensure it's securely managed)
USERNAME = os.getenv("SLIDESHOW_USER", "admin")
PASSWORD = os.getenv("SLIDESHOW_PASSWORD", "horst")

# Use the auth object to handle password authentication
@auth.verify_password
def verify_password(username, password):
    if username == USERNAME and password == PASSWORD:
        return True
    return False

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
        filenames, _ = get_rnd_db_entries(N=4)
        URL = f"http://{HOSTNAME}:{PORT}/images/"
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

# Protect routes using the @auth.login_required decorator
@app.route('/')
@auth.login_required
def client():
    """Client site, for sending pictures and comments"""
    return render_template("client.html", error=request.args.get("error"))

@app.route("/gallery")
@auth.login_required
def gallery():
    """Gallery site, for displaying sent pictures and comments"""
    # Fetch 5 images from database
    filenames, comments = get_rnd_db_entries(N=5)
    URL = f"http://{HOSTNAME}:{PORT}/images/"
    filenames = {i: URL + s for i, s in enumerate(filenames)}
    return render_template("gallery.html", filenames=filenames, comment=comments[2])

@app.route("/posts", methods=["POST"])
@auth.login_required
def add_post():
    # Fill post db entry
    URL = f"http://{HOSTNAME}:{PORT}/images/"
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
@auth.login_required
def get_posts():
    posts = list(Post.select().dicts())
    return jsonify(posts=posts)

@app.route("/images/<name>")
@auth.login_required
def img_host(name):
    return send_from_directory(app.config["IMG_DIR"], name)

@app.route("/database_clear")
@auth.login_required
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
@auth.login_required
def db_show():
    query = Post.select()
    s = "<h1> Database dump: </h1>"
    for item in query:
        s += "{}: {}".format(item.id, item.name) + "<br>"

    return s

@socket.on('connect')
@auth.login_required
def handle_connect():
    print('Client connected!')

@socket.on('disconnect')
def handle_disconnect():
    print('Client disconnected!')

# Start the server wrapper
def start_server():
    socket.run(app, host="0.0.0.0", port=8000, debug=True)

