import os, sys, json

from urllib import urlencode
from tarfile import TarFile
from gzip import GzipFile
from StringIO import StringIO
from uuid import uuid4
from time import sleep
from tempfile import mkdtemp
from os.path import commonprefix, join, isdir, exists, basename
from shutil import make_archive, rmtree

from flask import Flask, request, session, redirect, render_template, jsonify, send_file
from requests import get, post, Session
import oauth2

google_authorize_url = 'https://accounts.google.com/o/oauth2/auth'
google_access_token_url = 'https://accounts.google.com/o/oauth2/token'

heroku_authorize_url = 'https://id.heroku.com/oauth/authorize'
heroku_access_token_url = 'https://id.heroku.com/oauth/token'

app = Flask(__name__)
app.secret_key = 'fake'

@app.route("/")
def index():
    return render_template('index.html')

@app.route('/authorize-google', methods=['POST'])
def authorize_google():
    client_id, client_secret, redirect_uri = google_client_info(request)

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
    client_id, client_secret, redirect_uri = google_client_info(request)
    
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

@app.route('/create-app', methods=['POST'])
@app.route('/prepare-app', methods=['POST'])
def prepare_app():
    '''
    '''
    GA_VIEW_ID, GA_WEBSITE_URL = request.form.get('property').split(' ', 1)
    
    env = dict(LANG='en_US.UTF-8', RACK_ENV='production',
               GA_VIEW_ID=GA_VIEW_ID, GA_WEBSITE_URL=GA_WEBSITE_URL,
               CLIENT_ID=request.form.get('client_id'),
               CLIENT_SECRET=request.form.get('client_secret'),
               REFRESH_TOKEN=request.form.get('refresh_token'))
    
    url = 'http://github.com/codeforamerica/display-screen/tarball/master/'
    app = dict(name='Display Screen', env=env)
    
    session['tarfile'] = prepare_tarball(url, app)
    
    client_id, _, redirect_uri = heroku_client_info(request)
    
    query_string = urlencode(dict(client_id=client_id, redirect_uri=redirect_uri,
                                  response_type='code', scope='global',
                                  state=str(uuid4())))
    
    return redirect(heroku_authorize_url + '?' + query_string)

@app.route('/tarball/<path:filename>')
def get_tarball(filename):
    '''
    '''
    filepath = join(os.environ.get('TMPDIR', '/tmp'), filename)
    
    return send_file(filepath)

@app.route('/callback')
@app.route('/callback-heroku')
def callback_heroku():
    '''
    '''
    code, state = request.args.get('code'), request.args.get('state')
    client_id, client_secret, redirect_uri = heroku_client_info(request)

    data = dict(grant_type='authorization_code', client_secret=client_secret,
                code=code, redirect_uri='')
    
    resp = post(heroku_access_token_url, data=data)
    access = json.loads(resp.content)
    access_token, token_type = access['access_token'], access['token_type']
    refresh_token, session_nonce = access['refresh_token'], access['session_nonce']
    
    try:
        tar = basename(session['tarfile'])
        url = '{0}://{1}/tarball/{2}'.format(get_scheme(request), request.host, tar)
        
        return create_app(access_token, url)
    
    finally:
        os.remove(session['tarfile'])

def get_scheme(request):
    '''
    '''
    if 'x-forwarded-proto' in request.headers:
        return request.headers['x-forwarded-proto']
    
    return request.scheme

def google_client_info(request):
    ''' Return Client ID, secret, and redirect URI for Google OAuth use.
    '''
    scheme, host = get_scheme(request), request.host
    
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

def heroku_client_info(request):
    ''' Return Client ID, secret, and redirect URI for Heroku OAuth use.
    '''
    scheme, host = get_scheme(request), request.host
    
    if (scheme, host) == ('https', '127.0.0.1:5000'):
        id, secret = "7a12d323-b21e-4d40-b9ee-b51c40b5bcc6", "d907bf7e-314c-4f6d-a54c-ed9f85717b23"

    elif (scheme, host) == ('https', 'dfd-dashboard-setup.herokuapp.com'):
        id, secret = "5af3b562-9208-450a-bea6-0f356518c962", "4163a555-c5a7-4355-8db7-73a5e4854ebb"

    else:
        raise Exception()

    return id, secret, '{0}://{1}/callback-heroku'.format(scheme, host)

def prepare_tarball(url, app):
    '''
    '''
    got = get(url, allow_redirects=True)
    raw = GzipFile(fileobj=StringIO(got.content))
    tar = TarFile(fileobj=raw)
    
    try:
        dirpath = mkdtemp(prefix='display-screen-')
        rootdir = join(dirpath, commonprefix(tar.getnames()))
        tar.extractall(dirpath)
        
        if not isdir(rootdir):
            raise Exception('"%s" is not a directory' % rootdir)

        with open(join(rootdir, 'app.json'), 'w') as out:
            json.dump(app, out)
        
        tarpath = make_archive(dirpath, 'gztar', rootdir, '.')
        
    finally:
        rmtree(dirpath)
    
    return tarpath

def create_app(access_token, source_url):
    '''
    '''
    client = Session()
    client.trust_env = False # https://github.com/kennethreitz/requests/issues/2066
    
    data = json.dumps({'source_blob': {'url': source_url}})

    headers = {'Content-Type': 'application/json',
               'Authorization': 'Bearer {0}'.format(access_token),
               'Accept': 'application/vnd.heroku+json; version=3'}

    posted = client.post('https://api.heroku.com/app-setups',
                         headers=headers, data=data)

    setup_id = posted.json()['id']
    app_name = posted.json()['app']['name']

    while True:
        sleep(1)
        gotten = client.get('https://api.heroku.com/app-setups/{0}'.format(setup_id),
                            headers=headers)
    
        if gotten.json()['status'] == 'failed':
            return jsonify(dict(setup=gotten.json(), source=source_url))

        build_id = gotten.json()['build']['id']

        if build_id is not None:
            break

    return redirect('https://dashboard.heroku.com/apps/{0}/activity'.format(app_name))

if __name__ == '__main__':
    if sys.argv[-1] == 'ssl':
        from OpenSSL import SSL
        context = SSL.Context(SSL.SSLv23_METHOD)
        context.use_privatekey_file('ssl/server.key')
        context.use_certificate_file('ssl/server.crt')
    else:
        context = None

    app.run(host='127.0.0.1', port=5000, debug=True, ssl_context=context)
