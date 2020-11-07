import datetime
from flask import Flask, render_template, request, redirect
from google.auth.transport import requests
from google.cloud import datastore
import google.oauth2.id_token


app = Flask(__name__)
datastore_client = datastore.Client()

@app.route('/')
def root():
    # Store the currrent access time in Datastore.
    store_time(datetime.datetime.now())
    # Fetch the most recent 10 access times from Datastore.
    times = fetch_times(10)

    return render_template('index.html', times=times)

def store_time(dt):
    entity = datastore.Entity(key=datastore_client.key('visit'))
    entity.update({
        'timestamp': dt
    })

    datastore_client.put(entity)

def fetch_times(limit):
    query = datastore_client.query(kind='visit')
    query.order = ['-timestamp']

    times = query.fetch(limit=limit)

    return times

if __name__ == '__main__':
    # Used when running locally only, when deploying to GAE a webserver serves the app
    app.run(host='127.0.0.1', port=8080, debug=True)