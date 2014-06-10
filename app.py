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

from flask import Flask, request, redirect, render_template, jsonify, send_file, make_response
from requests import get, post, Session
import oauth2

display_screen_tarball_url = 'http://github.com/codeforamerica/display-screen/tarball/master/'

google_authorize_url = 'https://accounts.google.com/o/oauth2/auth'
google_access_token_url = 'https://accounts.google.com/o/oauth2/token'

google_analytics_properties_url = 'https://www.googleapis.com/analytics/v3/management/accounts/~all/webproperties'
google_plus_whoami_url = 'https://www.googleapis.com/plus/v1/people/me'
google_auth_scopes = 'email', 'https://www.googleapis.com/auth/analytics', 'https://www.googleapis.com/auth/analytics.readonly'

heroku_authorize_url = 'https://id.heroku.com/oauth/authorize'
heroku_access_token_url = 'https://id.heroku.com/oauth/token'

heroku_app_setup_url = 'https://api.heroku.com/app-setups'
heroku_app_setups_template = 'https://api.heroku.com/app-setups/{0}'
heroku_app_activity_template = 'https://dashboard.heroku.com/apps/{0}/activity'

class SetupError (Exception):
    pass

app = Flask(__name__)

@app.route("/")
def index():
    ''' Render front page with all the info.
    
        If not running locally, force SSL.
    '''
    scheme, host = get_scheme(request), request.host
    
    if scheme == 'http' and host[:9] not in ('localhost', '127.0.0.1'):
        return redirect('https://dfd-dashboard-setup.herokuapp.com')

    return render_template('index.html', style_base=get_style_base(request))

@app.route('/authorize-google', methods=['POST'])
def authorize_google():
    ''' Ask Google to authenticate. On success, return to /callback-google.
    '''
    client_id, client_secret, redirect_uri = google_client_info(request)

    query_string = urlencode(dict(client_id=client_id, redirect_uri=redirect_uri,
                                  scope=' '.join(google_auth_scopes),
                                  state=str(uuid4()), response_type='code',
                                  access_type='offline', approval_prompt='force'))
    
    return redirect(google_authorize_url + '?' + query_string)

@app.route('/callback-google')
def callback_google():
    ''' Complete Google authentication, get web properties, and show the form.
    '''
    code, state = request.args.get('code'), request.args.get('state')
    client_id, client_secret, redirect_uri = google_client_info(request)
    
    data = dict(client_id=client_id, client_secret=client_secret,
                code=code, redirect_uri=redirect_uri,
                grant_type='authorization_code')
    
    try:
        response = post(google_access_token_url, data=data)
        access = json.loads(response.content)
    
        if response.status_code != 200:
            if 'error_description' in access:
                raise SetupError('Google says "{0}"'.format(access['error_description']))
            else:
                raise SetupError('Google Error')
    
        access_token, refresh_token = access['access_token'], access['refresh_token']
    
        name, email = get_google_personal_info(access_token)
        properties = get_google_analytics_properties(access_token)
    
        if not properties:
            raise SetupError("Your Google Account isn't associated with any Google Analytics properties. Log in to Google with a different account?")
    
    except SetupError, e:
        values = dict(style_base=get_style_base(request), message=e.message)
        return make_response(render_template('error.html', **values), 400)
    
    values = dict(client_id=client_id, client_secret=client_secret,
                  refresh_token=refresh_token, properties=properties,
                  style_base=get_style_base(request), name=name, email=email)
    
    return render_template('index.html', **values)

@app.route('/create-app', methods=['POST'])
@app.route('/prepare-app', methods=['POST'])
def prepare_app():
    ''' Prepare app, ask Heroku to authenticate, return to /callback-heroku.
    '''
    GA_VIEW_ID, GA_WEBSITE_URL = request.form.get('property').split(' ', 1)
    
    env = dict(LANG='en_US.UTF-8', RACK_ENV='production',
               GA_VIEW_ID=GA_VIEW_ID, GA_WEBSITE_URL=GA_WEBSITE_URL,
               CLIENT_ID=request.form.get('client_id'),
               CLIENT_SECRET=request.form.get('client_secret'),
               REFRESH_TOKEN=request.form.get('refresh_token'))
    
    tarpath = prepare_tarball(display_screen_tarball_url,
                              dict(name='Display Screen', env=env))
    
    client_id, _, redirect_uri = heroku_client_info(request)
    
    query_string = urlencode(dict(client_id=client_id, redirect_uri=redirect_uri,
                                  response_type='code', scope='global',
                                  state=tarpath))
    
    return redirect(heroku_authorize_url + '?' + query_string)

@app.route('/tarball/<path:filename>')
def get_tarball(filename):
    ''' Return the named application tarball from the temp directory.
    '''
    filepath = join(os.environ.get('TMPDIR', '/tmp'), filename)
    
    return send_file(filepath)

@app.route('/callback-heroku')
def callback_heroku():
    ''' Complete Heroku authentication, start app-setup, redirect to app page.
    '''
    code, tarpath = request.args.get('code'), request.args.get('state')
    client_id, client_secret, redirect_uri = heroku_client_info(request)

    data = dict(grant_type='authorization_code', client_secret=client_secret,
                code=code, redirect_uri='')
    
    resp = post(heroku_access_token_url, data=data)
    access = json.loads(resp.content)
    access_token, token_type = access['access_token'], access['token_type']
    refresh_token, session_nonce = access['refresh_token'], access['session_nonce']
    
    try:
        tar = basename(tarpath)
        url = '{0}://{1}/tarball/{2}'.format(get_scheme(request), request.host, tar)
        app_name = create_app(access_token, url)
        
        return redirect(heroku_app_activity_template.format(app_name))
    
    finally:
        os.remove(tarpath)

def get_scheme(request):
    ''' Get the current URL scheme, e.g. 'http' or 'https'.
    '''
    if 'x-forwarded-proto' in request.headers:
        return request.headers['x-forwarded-proto']
    
    return request.scheme

def get_style_base(request):
    ''' Get the correct style base URL for the current scheme.
    '''
    if get_scheme(request) == 'https':
        return 'https://style.s.codeforamerica.org'
    
    return 'http://style.codeforamerica.org'

def get_google_personal_info(access_token):
    ''' Get account name and email from Google Plus.
    '''
    response = get(google_plus_whoami_url, params={'access_token': access_token})
    
    if response.status_code != 200:
        if 'error_description' in access:
            raise SetupError('Google says "{0}"'.format(access['error_description']))
        else:
            raise SetupError('Google Error')
    
    whoami = json.loads(response.content)
    emails = dict([(e['type'], e['value']) for e in whoami['emails']])
    email = emails.get('account', whoami['emails'][0]['value'])
    name = whoami['displayName']
    
    return name, email

def get_google_analytics_properties(access_token):
    ''' Get sorted list of web properties from Google Analytics.
    '''
    response = get(google_analytics_properties_url, params={'access_token': access_token})
    
    if response.status_code != 200:
        if 'error_description' in access:
            raise SetupError('Google says "{0}"'.format(access['error_description']))
        else:
            raise SetupError('Google Error')
    
    properties = [
        (item['defaultProfileId'], item['name'], item['websiteUrl'])
        for item in json.loads(response.content).get('items')
        if item.get('defaultProfileId', False)
        ]
    
    properties.sort(key=lambda p: p[1].lower())
    
    return properties
    
def google_client_info(request):
    ''' Return Client ID, secret, and redirect URI for Google OAuth use.
    '''
    scheme, host = get_scheme(request), request.host
    
    if (scheme, host) == ('http', 'localhost:5000'):
        id, secret = "422651909980-7stoc5hn9nfrv9l9otrnf8tjei0lm68q.apps.googleusercontent.com", "qZ511l73AqF0K8sX6g2wSTMG"

    elif (scheme, host) == ('https', 'dfd-dashboard-setup.herokuapp.com'):
        id, secret = "422651909980-cm38qtgra61jub0c9uiis3qoc2lhasse.apps.googleusercontent.com", "qk2SIzRSn-_6MZpNdhUGQnJL"

    else:
        raise Exception('You know nothing of {0}://{1}, Google'.format(scheme, host))

    return id, secret, '{0}://{1}/callback-google'.format(scheme, host)

def heroku_client_info(request):
    ''' Return Client ID, secret, and redirect URI for Heroku OAuth use.
    '''
    scheme, host = get_scheme(request), request.host
    
    if (scheme, host) == ('http', 'localhost:5000'):
        id, secret = "e46e254a-d99e-47c1-83bd-f9bc9854d467", "8cfd15f1-89b6-4516-9650-ce6650c78b4c"

    elif (scheme, host) == ('https', 'dfd-dashboard-setup.herokuapp.com'):
        id, secret = "e422c58c-aa9d-4fec-8bc2-66c859e2f5df", "9fffa26f-5202-4bce-b139-e4b227690b53"

    else:
        raise Exception('You know nothing of {0}://{1}, Heroku'.format(scheme, host))

    return id, secret, '{0}://{1}/callback-heroku'.format(scheme, host)

def prepare_tarball(url, app):
    ''' Prepare a tarball with app.json from the source URL.
    '''
    got = get(url, allow_redirects=True)
    raw = GzipFile(fileobj=StringIO(got.content))
    tar = TarFile(fileobj=raw)
    
    try:
        dirpath = mkdtemp(prefix='display-screen-')
        rootdir = join(dirpath, commonprefix(tar.getnames()))
        tar.extractall(dirpath)
        
        if not isdir(rootdir):
            raise Exception('"{0}" is not a directory'.format(rootdir))

        with open(join(rootdir, 'app.json'), 'w') as out:
            json.dump(app, out)
        
        tarpath = make_archive(dirpath, 'gztar', rootdir, '.')
        
    finally:
        rmtree(dirpath)
    
    return tarpath

def create_app(access_token, source_url):
    ''' Create a Heroku application based on a tarball URL, return its name.
    '''
    client = Session()
    client.trust_env = False # https://github.com/kennethreitz/requests/issues/2066
    
    data = json.dumps({'source_blob': {'url': source_url}})

    headers = {'Content-Type': 'application/json',
               'Authorization': 'Bearer {0}'.format(access_token),
               'Accept': 'application/vnd.heroku+json; version=3'}

    posted = client.post(heroku_app_setup_url, headers=headers, data=data)
    setup_id = posted.json()['id']
    app_name = posted.json()['app']['name']

    while True:
        sleep(1)
        gotten = client.get(heroku_app_setups_template.format(setup_id), headers=headers)
        setup = gotten.json()
    
        if setup['status'] == 'failed':
            raise Exception('Heroku failed to build from {0}, saying "{1}"'.format(source_url, setup['failure_message']))

        if setup['build']['id'] is not None:
            break

    return app_name

if __name__ == '__main__':
    if sys.argv[-1] == 'ssl':
        from OpenSSL import SSL
        context = SSL.Context(SSL.SSLv23_METHOD)
        context.use_privatekey_file('ssl/server.key')
        context.use_certificate_file('ssl/server.crt')
    else:
        context = None

    app.run(host='localhost', port=5000, debug=True, ssl_context=context)
