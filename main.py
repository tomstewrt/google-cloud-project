import datetime
from flask import Flask, render_template, request, redirect, flash, Markup
from google.auth.transport import requests
from google.cloud import datastore, storage
from firebase import firebase
import google.oauth2.id_token
import pymongo
import base64
from bson import ObjectId
from bson.json_util import dumps
import os
from google.cloud import secretmanager
from google import auth

app = Flask(__name__)
app.secret_key = "saAdaSdjyauWKkeadvf"
datastore_client = datastore.Client()
firebase_request_adapter = requests.Request()
# set-up mongoDB connection
# use secret manager for a more secure connection.
secrets = secretmanager.SecretManagerServiceClient()
firebase_url = secrets.access_secret_version(
    "projects/324165056060/secrets/GoogleStorage-Connection/versions/1"
).payload.data.decode("utf-8")
firebase_db_url = secrets.access_secret_version(
    "projects/324165056060/secrets/FirebaseDB-Connection/versions/1"
).payload.data.decode("utf-8")
firebase = firebase.FirebaseApplication(firebase_db_url)
storage_client = storage.Client()
bucket = storage_client.get_bucket(firebase_url)
mongo_url = secrets.access_secret_version(
    "projects/324165056060/secrets/MongoDB-Connection/versions/1"
).payload.data.decode("utf-8")
# make sure url exists
if not mongo_url:
    flash("Error: failed to get mongoDB connection string", "danger")
else:
    # set-up client object and connect to cluster using url
    client = pymongo.MongoClient(mongo_url)

# connect to the db
db = client.advancedDev


@app.route("/")
def root():
    # Verify Firebase auth.
    claims = Authenticate()
    time = None

    return render_template("index.html", user_data=claims, time=time)


def update_time(entity, time):
    entity.update({"timestamp": time})
    datastore_client.put(entity)
    return


def store_time(email, dt):
    entity = datastore.Entity(key=datastore_client.key("User", email, "visit"))
    entity.update({"timestamp": dt})

    datastore_client.put(entity)


def fetch_time(email):
    ancestor = datastore_client.key("User", email)
    query = datastore_client.query(kind="visit", ancestor=ancestor)
    result = list(query.fetch(limit=1))
    time = datetime.datetime.now()
    # If first visit store time
    if len(result) == 0:
        store_time(email, time)
    else:
        update_time(result[0], time)
        time = result[0]

    return time


# Prevent invalid format's for security purposes. No html/php files etc..
IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

# [START upload file code]
@app.route("/uploadfile", methods=["GET", "POST"])
def upload_file():
    # Verify Firebase auth.
    claims = Authenticate()
    # new_post is for when an upload has been made, to show the view post link
    new_post_url = None

    if request.method == "POST":
        title = request.form["title"]
        description = request.form["description"]
        if title == None or description == None or "file" not in request.files:
            flash(
                "Error, there was an issue with one of your inputs, all fields must be filled out. Please try again.",
                "danger",
            )
            return redirect(request.url)
        else:
            file = request.files["file"]
            # Check if the file has a name
            if file.filename == "":
                flash("Error, no selected file.", "danger")
                return redirect(request.url)
            # Check if file is an image
            if not allowed_file(file.filename):
                flash(
                    "Error, invalid file uploaded, must be png, jpg or jpeg.", "danger"
                )
                return redirect(request.url)
            # get blob to upload image to google cloud storage gallery folder through firebase
            imageBlob = bucket.blob("/gallery")
            bytes = file.read()
            imageBlob.upload_from_string(bytes)
            # public url has two / at the end when we need / so substring off last char
            image_path = (
                imageBlob.public_url[0 : len(imageBlob.public_url) - 1] + file.filename
            )
            # Create gallery post with path to the firebase storage image
            gallery_post = {
                "name": claims["name"],
                "email": claims["email"],
                "title": title,
                "description": description,
                "imagePath": image_path,
            }
            post_id = db.gallery.insert_one(gallery_post).inserted_id
            print("POST ID - " + str(post_id))
            message = Markup(
                'Successfully uploaded your photo to our gallery. Click <a href="/gallery/'
                + str(post_id)
                + '"><b>here</b></a> to view it.'
            )
            flash(
                message,
                "success",
            )
            new_post = True
            return redirect(request.url)

    return render_template(
        "uploadfile.html",
        user_data=claims,
        new_post_url=new_post_url,
    )


# [END upload form code]

# Check if an allowed file extension
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in IMAGE_EXTENSIONS


# [START gallery view code]
@app.route("/gallery")
def gallery():
    # Get paged gallery data and display to users
    claims = Authenticate()
    results = None
    items_per_page = 9
    page = 1
    # Set the page number to 1, unless its already been
    if request.args.get("page") != None:
        page = request.args.get("page")
    # Check the page number is more than 0
    if page <= 0:
        page = 1

    start_num = 0
    end_num = items_per_page
    # If this isn't the first page set
    if page != 1:
        start_num = (page - 1) * items_per_page + 1
        end_num = page * items_per_page
    # Fetch the gallery results for this page from mongo
    results = db.gallery.find()[start_num:end_num]

    return render_template("gallery.html", user_data=claims, results=results)


# [END gallery view code]

# [START individual gallery post view ]


@app.route("/gallery/<postid>")
def gallery_post(postid):
    claims = Authenticate()
    post = db.gallery.find_one({"_id": ObjectId(postid)})
    if not post:
        flash(
            "Error, couldn't find post with id '" + postid + "', please try again.",
            "danger",
        )
        redirect("/gallery")

    return render_template("gallery_post.html", user_data=claims, post=post)


# [END individual gallery post view ]

# [START Authentication check]


def Authenticate():
    id_token = request.cookies.get("token")
    if id_token:
        try:
            # Verify the token against the Firebase Auth API. This example
            # verifies the token on each page load. For improved performance,
            # some applications may wish to cache results in an encrypted
            # session store (see for instance
            # http://flask.pocoo.org/docs/1.0/quickstart/#sessions)
            return google.oauth2.id_token.verify_firebase_token(
                id_token, firebase_request_adapter
            )
        except ValueError as exc:
            # This will be raised if the token is expired or any other
            # verification checks fail.
            flash(str(exc), "danger")
    else:
        return redirect("/")


# [END Authentication check]


if __name__ == "__main__":
    # Used when running locally only, when deploying to GAE a webserver serves the app
    app.run(host="127.0.0.1", port=8080, debug=True)
