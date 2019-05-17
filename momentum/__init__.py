from flask import Flask
from .models import db
from .releases import bp as releases
from .util import MomentumJSONEncoder


def create_app():
    app = Flask(__name__)
    app.json_encoder = MomentumJSONEncoder
    app.config["SQLALCHEMY_DATABASE_URI"] = "postgres://localhost:5432/forge"
    app.config["SQLALCHEMY_ECHO"] = True
    db.init_app(app)

    @app.route('/')
    def hello_world():
        return 'Hello World!'

    app.register_blueprint(releases)
    return app