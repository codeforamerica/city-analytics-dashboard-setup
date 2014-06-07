from urllib import urlencode
from uuid import uuid4
import json

from flask import Flask, request, session, redirect, render_template, jsonify
from requests import get, post
import oauth2

google_authorize_url = 'https://accounts.google.com/o/oauth2/auth'
google_access_token_url = 'https://accounts.google.com/o/oauth2/token'

app = Flask(__name__)
app.secret_key = 'fake'

@app.route("/")
def index():
    return render_template('index.html')

@app.route('/authorize-google', methods=['POST'])
def authorize_google():
    redirect_uri = '{0}://{1}/callback'.format(request.scheme, request.host)
    client_id = "656808925171-0db1to95unmk66hkqmnlljhrj8ofj0ce.apps.googleusercontent.com"
    client_secret = "ZqSrok49lcVh5xyUFJI4cGHf"
    state = str(uuid4())

    session['provider'] = 'google'
    session['client_id'] = client_id
    session['client_secret'] = client_secret
    session['state'] = state
    
    query_string = urlencode(dict(client_id=client_id, redirect_uri=redirect_uri,
                                  scope='https://www.googleapis.com/auth/analytics https://www.googleapis.com/auth/analytics.readonly',
                                  state=state, response_type='code',
                                  access_type='offline', approval_prompt='force'))
    
    return redirect(google_authorize_url + '?' + query_string)

@app.route('/callback')
def callback():
    callback = '{0}://{1}/callback'.format(request.scheme, request.host)

    if session['provider'] == 'google':
        args = (session['client_id'], session['client_secret'],
                request.args.get('code'), request.args.get('state'),
                callback)

        return callback_google(*args)
    
    elif session['provider'] == 'heroku':
        args = (session['client_id'], session['client_secret'],
                request.args.get('code'), request.args.get('state'))

        return callback_heroku(*args)
    
    else:
        raise Exception()

def callback_google(client_id, client_secret, code, state, redirect_uri):
    '''
    '''
    if state != session['state']:
        raise Exception()
    
    data = dict(client_id=client_id, client_secret=client_secret,
                code=code, redirect_uri=redirect_uri,
                grant_type='authorization_code')
    
    resp = post(google_access_token_url, data=data)
    access = json.loads(resp.content)
    access_token, token_type = access['access_token'], access['token_type']
    refresh_token = access['refresh_token']
    
    url = 'https://www.googleapis.com/analytics/v3/management/accounts/~all/webproperties'
    
    #
    # '{"error":{"errors":[{"domain":"usageLimits","reason":"accessNotConfigured","message":"Access Not Configured. Please use Google Developers Console to activate the API for your project."}],"code":403,"message":"Access Not Configured. Please use Google Developers Console to activate the API for your project."}}'
    # https://code.google.com/apis/console/ > APIs & Auth > Analytics API "On"
    #
    
    response = get(url, params={'access_token': access_token})
    
    properties = [
        (item['defaultProfileId'], item['name'], item['websiteUrl'])
        for item in json.loads(response.content).get('items')
        if item.get('defaultProfileId', False)
        ]
    
    properties.sort(key=lambda p: p[1].lower())
    
    values = dict(client_id=client_id, client_secret=client_secret,
                  refresh_token=refresh_token, properties=properties)
    
    return render_template('index.html', **values)

if __name__ == '__main__':
    app.run(debug=True)