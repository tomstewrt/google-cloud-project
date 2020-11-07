import datetime
from flask import Flask, render_template, request, redirect
from google.auth.transport import requests
from google.cloud import datastore
import google.oauth2.id_token


app = Flask(__name__)
datastore_client = datastore.Client()
firebase_request_adapter = requests.Request()

@app.route('/')
def root():
    # Verify Firebase auth.
    id_token = request.cookies.get('token')
    error_message = None
    claims = None
    times = None

    if id_token:
        try:
            # Verify the token against the Firebase Auth API. This example
            # verifies the token on each page load. For improved performance,
            # some applications may wish to cache results in an encrypted
            # session store (see for instance
            # http://flask.pocoo.org/docs/1.0/quickstart/#sessions).
            claims = google.oauth2.id_token.verify_firebase_token(
                id_token, firebase_request_adapter)

            store_time(claims['email'], datetime.datetime.now())
            times = fetch_times(claims['email'], 10)
        except ValueError as exc:
            # This will be raised if the token is expired or any other 
            # verification checks fail
            error_message = str(exc)     
    
    return render_template('index.html', user_data=claims, 
    times=times, error_message=error_message)

def store_time(email, dt):
    entity = datastore.Entity(key=datastore_client.key('User', email, 'visit'))
    entity.update({
        'timestamp': dt
    })

    datastore_client.put(entity)

def fetch_times(email, limit):
    ancestor = datastore_client.key('User', email)
    query = datastore_client.query(kind='visit', ancestor=ancestor) 
    query.order = ['-timestamp']

    times = query.fetch(limit=limit)

    return times

if __name__ == '__main__':
    # Used when running locally only, when deploying to GAE a webserver serves the app
    app.run(host='127.0.0.1', port=8080, debug=True)