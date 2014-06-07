from urllib import urlencode
from uuid import uuid4
import sys, json

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
    client_id, client_secret, redirect_uri = google_client_info(request.scheme, request.host)

    query_string = urlencode(dict(client_id=client_id, redirect_uri=redirect_uri,
                                  scope='https://www.googleapis.com/auth/analytics https://www.googleapis.com/auth/analytics.readonly',
                                  state=str(uuid4()), response_type='code',
                                  access_type='offline', approval_prompt='force'))
    
    return redirect(google_authorize_url + '?' + query_string)

@app.route('/callback-google')
def callback_google():
    '''
    '''
    code, state = request.args.get('code'), request.args.get('state')
    client_id, client_secret, redirect_uri = google_client_info(request.scheme, request.host)
    
    data = dict(client_id=client_id, client_secret=client_secret,
                code=code, redirect_uri=redirect_uri,
                grant_type='authorization_code')
    
    resp = post(google_access_token_url, data=data)
    access = json.loads(resp.content)
    access_token, token_type = access['access_token'], access['token_type']
    refresh_token = access['refresh_token']
    
    #
    # '{"error":{"errors":[{"domain":"usageLimits","reason":"accessNotConfigured","message":"Access Not Configured. Please use Google Developers Console to activate the API for your project."}],"code":403,"message":"Access Not Configured. Please use Google Developers Console to activate the API for your project."}}'
    # https://code.google.com/apis/console/ > APIs & Auth > Analytics API "On"
    #
    url = 'https://www.googleapis.com/analytics/v3/management/accounts/~all/webproperties'
    response = json.loads(get(url, params={'access_token': access_token}).content)
    
    if 'items' not in response:
        return jsonify(response)
    
    properties = [
        (item['defaultProfileId'], item['name'], item['websiteUrl'])
        for item in response.get('items')
        if item.get('defaultProfileId', False)
        ]
    
    properties.sort(key=lambda p: p[1].lower())
    
    values = dict(client_id=client_id, client_secret=client_secret,
                  refresh_token=refresh_token, properties=properties)
    
    return render_template('index.html', **values)

def google_client_info(scheme, host):
    ''' Return Client ID, secret, and redirect URI for Google OAuth use.
    '''
    if (scheme, host) == ('http', '127.0.0.1:5000'):
        id, secret = "422651909980-a35en10nc91si1aad64laoav4besih1m.apps.googleusercontent.com", "g9nDZDifVWflKbydh12sbFH7"

    elif (scheme, host) == ('https', '127.0.0.1:5000'):
        id, secret = "422651909980-9covddi3im2441kaf57g4k0ev7hqupfi.apps.googleusercontent.com", "HyQpjg-Oak9eBKLVkBvEVbLd"

    elif (scheme, host) == ('http', 'dfd-dashboard-setup.herokuapp.com'):
        id, secret = "422651909980-kb46m28v262ml8gu30fb9294agi3v845.apps.googleusercontent.com", "P8HR9uZ15RUFBDSg0wq_bE6w"

    elif (scheme, host) == ('https', 'dfd-dashboard-setup.herokuapp.com'):
        id, secret = "422651909980-cm38qtgra61jub0c9uiis3qoc2lhasse.apps.googleusercontent.com", "qk2SIzRSn-_6MZpNdhUGQnJL"

    else:
        raise Exception()

    return id, secret, '{0}://{1}/callback-google'.format(scheme, host)

if __name__ == '__main__':
    if sys.argv[-1] == 'ssl':
        from OpenSSL import SSL
        context = SSL.Context(SSL.SSLv23_METHOD)
        context.use_privatekey_file('ssl/server.key')
        context.use_certificate_file('ssl/server.crt')
    else:
        context = None

    app.run(host='127.0.0.1', port=5000, debug=True, ssl_context=context)
