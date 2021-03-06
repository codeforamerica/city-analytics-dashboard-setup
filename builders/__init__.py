import sys, json, logging
from smtplib import SMTP
from uuid import uuid4

from requests import get, post, Session
import psycopg2.extras

heroku_app_setup_url = 'https://api.heroku.com/app-setups'
heroku_app_setups_template = 'https://api.heroku.com/app-setups/{0}'
heroku_app_activity_template = 'https://dashboard.heroku.com/apps/{0}/activity'
heroku_app_direct_template = 'https://{0}.herokuapp.com'

logger = logging.getLogger('noteworthy')

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
    logger.debug('create_app() posted: {} {}'.format(posted.status_code, posted.json()))
    
    if posted.status_code in range(400, 499):
        message = 'Heroku says: {}'.format(posted.json().get('message', posted.text))
        raise SetupError(message)

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
    
    logger.debug('check_app() gotten: {} {}'.format(gotten.status_code, gotten.json()))

    if setup['status'] == 'failed':
        raise SetupError('Heroku failed to build {0}, saying "{1}"'.format(setup_id, setup['failure_message']))

    is_finished = bool((setup['build'] or {}).get('id') is not None)

    logger.debug('check_app() is_finished: {}'.format(is_finished))
    
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

def add_connection(db, email, name, website_url, tarball_path):
    '''
    '''
    db.execute('''INSERT INTO connections
                  (email_address, profile_name, website_url) 
                  VALUES (%s, %s, %s)''',
               (email, name, website_url))

    db.execute("SELECT CURRVAL('connections_id_seq')")
    (tarball_id, ) = db.fetchone()

    db.execute('INSERT INTO tarballs (id, contents) VALUES (%s, %s)',
               (tarball_id, buffer(open(tarball_path).read())))
    
    return tarball_id

def send_email(fromaddr, toaddr, msg, smtp_dict):
    '''
    '''
    conn = SMTP(smtp_dict['SMTP_HOSTNAME'])
    conn.login(smtp_dict['SMTP_USERNAME'], smtp_dict['SMTP_PASSWORD'])
    conn.sendmail(fromaddr, (fromaddr, toaddr), msg)
    conn.quit()
