import sys, json
from uuid import uuid4

from requests import get, post, Session

heroku_app_setup_url = 'https://api.heroku.com/app-setups'
heroku_app_setups_template = 'https://api.heroku.com/app-setups/{0}'
heroku_app_activity_template = 'https://dashboard.heroku.com/apps/{0}/activity'
heroku_app_direct_template = 'https://{0}.herokuapp.com'

class SetupError (Exception):
    pass

def create_app(access_token, source_url):
    ''' Create a Heroku application based on a tarball URL, return its name.
    '''
    client = Session()
    client.trust_env = False # https://github.com/kennethreitz/requests/issues/2066
    
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
    
    return setup_id
