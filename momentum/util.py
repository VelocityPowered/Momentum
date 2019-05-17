from flask.json import JSONEncoder, jsonify
from momentum.models import ReleaseStatus


class MomentumJSONEncoder(JSONEncoder):

    def default(self, o):
        if type(o) == ReleaseStatus:
            return str(o)
        return super().default(o)


def emit_json_error(**kwargs):
    status_code = 400
    if 'status_code' in kwargs:
        status_code = kwargs['status_code']
        del kwargs['status_code']

    kwargs['ok'] = False
    response = jsonify(**kwargs)
    response.status_code = status_code
    return response
