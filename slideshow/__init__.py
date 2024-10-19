from flask import (
    Flask, render_template, render_template_string, redirect, url_for, request, session, flash, jsonify
)
from flask_httpauth import HTTPBasicAuth
from flask_socketio import SocketIO
from functools import wraps
from datetime import datetime
import os
import base64
from .database import database, Post, get_rnd_db_entries, get_max_id
from .image import fix_orientation

auth = HTTPBasicAuth()
app = Flask(__name__)

# App configuration
app.secret_key = "DONTTELLANYONETHESECRETKEY"  # Change this for production
app.config["SESSION_TYPE"] = "filesystem"  # Store session on the server-side
app.config["SESSION_PERMANENT"] = False  # Session lasts until the browser is closed
app.config["DATABASE"] = os.getenv("SLIDESHOW_DB", "slideshow.sqlite")
app.config["IMG_DIR"] = os.getenv("SLIDESHOW_IMG_DIR", "path/to/image/folder")
app.config["HOSTNAME"] = os.getenv("HOSTNAME", "localhost")
app.config["PORT"] = os.getenv("PORT", "8000")

# Login credentials from environment variables
USERNAME = os.getenv("SLIDESHOW_USER", "admin")
PASSWORD = os.getenv("SLIDESHOW_PASSWORD", "password123")

# Verify password for authentication
@auth.verify_password
def verify_password(username, password):
    return username == USERNAME and password == PASSWORD

# Decorator to require login for routes
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('authenticated'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Login route for password-based authentication
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['password'] == PASSWORD:
            session['authenticated'] = True  # Authenticate user in the session
            flash('Login successful!', 'success')
            return redirect(url_for('gallery'))  # Redirect to the gallery
        else:
            flash('Incorrect password, please try again.', 'danger')
    return render_template_string('''
        <form method="post">
            <input type="password" name="password" placeholder="Enter Password">
            <input type="submit" value="Submit">
        </form>
        <p style="color:red;">{{ get_flashed_messages() }}</p>
    ''')

# Logout route to clear session
@app.route('/logout')
def logout():
    session.pop('authenticated', None)  # Clear authentication
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

# Client page for uploading images (requires login)
@app.route('/')
@login_required
def client():
    return render_template('client.html')

# Gallery page that displays images from the database (requires login)
@app.route('/gallery')
@login_required
def gallery():
    filenames, comments = get_rnd_db_entries(N=5)
    img_data = {}

    # Read each image, convert to base64, and include in the template
    for i, filename in enumerate(filenames):
        img_path = os.path.join(app.config['IMG_DIR'], filename)
        with open(img_path, "rb") as img_file:
            img_data[i] = base64.b64encode(img_file.read()).decode('utf-8')

    return render_template('gallery.html', img_data=img_data, comment=comments[2])

# Add post route for uploading new images (requires login)
@app.route('/posts', methods=['POST'])
@login_required
def add_post():
    try:
        post = Post()
        post.timestamp = datetime.utcnow()
        comment = request.form['comment']
        post.comment = comment

        # Handle image upload
        img_file = request.files['image']
        img_resized = fix_orientation(img_file)
        ext = os.path.splitext(img_file.filename)[1]
        filename = post.timestamp.isoformat().replace(':', '_') + ext
        img_path = os.path.join(app.config['IMG_DIR'], filename)
        img_resized.save(img_path)

        # Save post data to the database
        post.name = filename
        post.save()

        # Emit new image to update the gallery
        with open(img_path, "rb") as img_file:
            img_base64 = base64.b64encode(img_file.read()).decode('utf-8')
        socket.emit("new_image", {"filename": img_base64, "comment": comment})
        flash("Image uploaded successfully!", 'success')
    except Exception as e:
        flash(f"Error: {str(e)}", 'danger')

    return redirect(url_for('client'))

# Init app before launch (sets up database and starts gallery updater)
@app.before_first_request
def init_app():
    # Setup database
    database.init(app.config["DATABASE"])
    database.create_tables([Post], safe=True)
    
    # Start the gallery updater task in the background
    socket.start_background_task(start_gallery_updater)

# Background task to periodically update the gallery with random images

def start_gallery_updater():
    while True:
        socket.sleep(15)  # Sleep for 15 seconds between updates
        print("Updating gallery...")

        filenames, _ = get_rnd_db_entries(N=4)  # Fetch 4 random images from the database
        img_data = {}

        # Read each image as binary data
        for i, filename in enumerate(filenames):
            img_path = os.path.join(app.config['IMG_DIR'], filename)
            with open(img_path, "rb") as img_file:
                img_data[f"img_{i}"] = img_file.read()  # Read the binary image data

        # Emit the binary image data to all connected clients
        socket.emit("galupdate", {
            "img_tl": img_data["img_0"],
            "img_bl": img_data["img_1"],
            "img_tr": img_data["img_2"],
            "img_br": img_data["img_3"]
        })


# Endpoint to clear the database (for debugging or resetting during development)
@app.route("/database_clear")
@login_required
def db_clear():
    max_id = get_max_id()
    if max_id is not None:
        try:
            rows_deleted = Post.delete().where(Post.id <= max_id).execute()
            flash(f"Deleted {rows_deleted} rows from the database.", 'success')
        except Exception as e:
            flash(f"Error: {str(e)}", 'danger')
    else:
        flash("The database was already empty.", 'info')
    return redirect(url_for('client'))

# Endpoint to show all posts in the database (for debugging)
@app.route("/database_show")
@login_required
def db_show():
    query = Post.select()
    db_dump = "<h1> Database dump: </h1>"
    for item in query:
        db_dump += f"{item.id}: {item.name}<br>"
    return db_dump


# SocketIO setup
from flask_socketio import SocketIO

# Allow specific origins or set it to "*" to allow all origins
socket = SocketIO(app, cors_allowed_origins="https://wedding.mathisboerner.de")

# Start the server
def start_server():
    import eventlet
    eventlet.monkey_patch()
    socket.run(app, host="0.0.0.0", port=8000, debug=True)

