"""Fixed Bishop workflow dispatch; no caller-selected repository, ref or URL."""
import json
from urllib.request import Request, urlopen

WORKFLOW = 'bishop-live-bias.yml'
REF = 'claude-bishop-aggressive'
URL = 'https://api.github.com/repos/awujo/practicing/actions/workflows/' + WORKFLOW + '/dispatches'


def dispatch_bias(token, *, open_url=None):
    if not token:
        raise ValueError('Bishop GitHub dispatch token is required')
    request = Request(URL, data=json.dumps({'ref': REF}).encode(), method='POST',
                      headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
                               'Content-Type': 'application/json', 'X-GitHub-Api-Version': '2022-11-28'})
    with (open_url or urlopen)(request, timeout=15) as response:
        if response.status != 204:
            raise RuntimeError('Workflow dispatch was not accepted')
    return dict(queued=True, workflow=WORKFLOW, branch=REF)
