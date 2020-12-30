from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
import enum

from sqlalchemy import UniqueConstraint

db = SQLAlchemy()


class Project(db.Model):
    """
    The Project model represents any project that is served by the Forge API.
    """
    id = db.Column(db.Integer, primary_key=True, nullable=False)
    name = db.Column(db.String(30), nullable=False)
    slug = db.Column(db.String(30), nullable=False, unique=True, index=True)
    releases = db.relationship('Release', backref='releases', lazy=True)

    def __repr__(self):
        return '<Project %s (%s)>' % (self.name, self.slug)

    def as_json(self):
        return {'name': self.name, 'slug': self.slug, 'releases': [r.as_json() for r in self.releases]}


class ReleaseStatus(enum.Enum):
    """
    An enumeration representing the release status.
    """
    development = 0
    beta = 1
    stable = 2
    maintenance = 3
    unsupported = 4

    def __str__(self):
        return self.name


class Release(db.Model):
    """
    The Release model represents the release of a Project.
    """
    id = db.Column(db.Integer, primary_key=True, nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False, index=True)
    project = db.relationship("Project", back_populates="releases", uselist=False)
    version = db.Column(db.String(30), nullable=False, unique=True, index=True)
    status = db.Column(db.Enum(ReleaseStatus), nullable=False, index=True)
    builds = db.relationship('Build', backref='builds', lazy=True)
    created_at = db.Column(db.DateTime(), default=datetime.now(), nullable=False)
    released_at = db.Column(db.DateTime(), nullable=True)

    def __repr__(self):
        return '<Release %s of %s>' % (self.name, self.project.name)

    def as_json(self):
        base = {'version': self.version, 'status': self.status, 'created_at': self.created_at, 'released_at': \
            self.released_at}

        if len(self.builds) != 0:
            base['builds'] = [b.as_json() for b in self.builds]

        if self.status == ReleaseStatus.stable:
            # Try to find a recommended build
            recommended = Build.query.filter_by(release_id=self.id, recommended=True)\
                .order_by(Build.built_at.desc()).first()
            if recommended is not None:
                base['recommended'] = recommended.as_json()
        return base


class Build(db.Model):
    """
    The Build model represents a specific build of a Release.
    """
    id = db.Column(db.Integer, primary_key=True, nullable=False)
    release = db.relationship("Release", back_populates="builds", uselist=False)
    release_id = db.Column(db.Integer, db.ForeignKey('release.id'), nullable=False, index=True)
    specific_build_id = db.Column(db.Integer(), nullable=False)
    # recommended is only relevant when release's status is "stable"
    recommended = db.Column(db.Boolean(), nullable=False, default=False)
    url = db.Column(db.String(256), nullable=False)
    built_at = db.Column(db.DateTime(), default=datetime.now, nullable=False)

    __table_args__ = (
        UniqueConstraint('release_id', 'specific_build_id', name='release_build_id_uniq'),
    )

    def __repr__(self):
        return '<Build #%d of %s %s>' % (self.specific_build_id, self.release.project.name, self.release.version)

    def as_json(self):
        base = {
            'id': self.specific_build_id,
            'url': self.url,
            'built_at': self.built_at,
        }

        if self.release.status == ReleaseStatus.stable:
            base['recommended'] = self.recommended

        return base