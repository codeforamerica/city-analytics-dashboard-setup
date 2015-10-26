import sys, json
from uuid import uuid4

from requests import get, post, Session
import psycopg2.extras

heroku_app_setup_url = 'https://api.heroku.com/app-setups'
heroku_app_setups_template = 'https://api.heroku.com/app-setups/{0}'
heroku_app_activity_template = 'https://dashboard.heroku.com/apps/{0}/activity'
heroku_app_direct_template = 'https://{0}.herokuapp.com'

class SetupError (Exception):
    pass

def get_http_client():
    '''
    '''
    client = Session()
    client.trust_env = False # https://github.com/kennethreitz/requests/issues/2066
    
    return client

def create_app(client, access_token, source_url):
    ''' Create a Heroku application based on a tarball URL, return its setup ID and name.
    '''
    app = {'stack': 'cedar', 'name': 'city-analytics-{}'.format(str(uuid4())[:8])}
    data = json.dumps({'source_blob': {'url': source_url}, 'app': app});

    headers = {'Content-Type': 'application/json',
               'Authorization': 'Bearer {0}'.format(access_token),
               'Accept': 'application/vnd.heroku+json; version=3'}

    posted = client.post(heroku_app_setup_url, headers=headers, data=data)
    print >> sys.stderr, 'create_app()', 'posted:', posted.status_code, posted.json()
    
    if posted.status_code in range(400, 499):
        raise SetupError(posted.json().get('message', posted.text))

    setup_id = posted.json()['id']
    app_name = posted.json()['app']['name']
    
    return setup_id, app_name

def check_app(client, access_token, setup_id):
    '''
    '''
    headers = {'Content-Type': 'application/json',
               'Authorization': 'Bearer {0}'.format(access_token),
               'Accept': 'application/vnd.heroku+json; version=3'}

    gotten = client.get(heroku_app_setups_template.format(setup_id), headers=headers)
    setup = gotten.json()
    
    print >> sys.stderr, 'check_app()', 'gotten:', gotten.status_code, gotten.json()

    if setup['status'] == 'failed':
        raise SetupError('Heroku failed to build {0}, saying "{1}"'.format(setup_id, setup['failure_message']))

    is_finished = bool((setup['build'] or {}).get('id') is not None)

    print >> sys.stderr, 'check_app()', 'is_finished:', is_finished
    
    return is_finished

def get_connection_datum(db, conn_id, key):
    '''
    '''
    db.execute('SELECT data->>%s FROM connections WHERE id = %s', (key, conn_id, ))
    (value, ) = db.fetchone()
    
    return value

def set_connection_datum(db, conn_id, key, value):
    '''
    '''
    db.execute('SELECT data FROM connections WHERE id = %s', (conn_id, ))
    (old_conn_data, ) = db.fetchone()
    
    new_conn_data = dict()
    new_conn_data.update(old_conn_data or dict())
    new_conn_data[key] = value

    db.execute('UPDATE connections SET data = %s WHERE id = %s',
               (psycopg2.extras.Json(new_conn_data), conn_id))
