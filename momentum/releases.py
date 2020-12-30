from flask import Blueprint, jsonify, redirect, request, Response
from sqlalchemy import false, text
from sqlalchemy.orm import contains_eager, load_only

from momentum.models import Project, Release, Build, ReleaseStatus, db
from momentum.util import emit_json_error, enum_value_by_name_safe

bp = Blueprint('releases', __name__)
bp.url_prefix = '/v1/releases'


@bp.route('/')
def view_releases():
    # Adapted this hack from:
    # https://stackoverflow.com/questions/43727268/limit-child-collections-in-initial-query-sqlalchemy
    #
    # Actually, this seems more efficient, and we're deploying onto PostgreSQL anyway, so...
    builds = Build.query.filter(false()).subquery()
    releases = Release.query.outerjoin(builds)\
        .filter(Project.id == Release.project_id) \
        .order_by(Release.created_at.desc())\
        .limit(10).subquery().lateral()

    projects = Project.query.outerjoin(releases).outerjoin(builds)\
        .options(contains_eager(Project.releases, alias=releases).contains_eager(Release.builds, alias=builds))

    return jsonify({
        'ok': True,
        'projects': [p.as_json() for p in projects]
    })


@bp.route('/<project_slug>')
def view_project(project_slug):
    builds = Build.query.filter(Build.release_id == Release.id).order_by(Build.specific_build_id.desc())\
        .limit(10).subquery().lateral()
    releases = Release.query.outerjoin(builds)\
        .filter(Project.id == Release.id)\
        .order_by(Release.created_at.desc())\
        .limit(10).subquery().lateral()
    project = Project.query.filter_by(slug=project_slug).outerjoin(releases)\
        .options(contains_eager(Project.releases, alias=releases).contains_eager(Release.builds, alias=builds))\
        .all()

    # A little SQLAlchemy gotcha here: the joins we do to include the release and build information in one query combine
    # include all the relevant information in the SQL query. As a result, we _must_ fetch all entries, otherwise it's
    # not going to work.
    if len(project) == 0:
        return emit_json_error(error="No such project found", status_code=404)

    return jsonify({
        'ok': True,
        'project': project[0].as_json()
    })


@bp.route('/<project_slug>/versions/latest')
def latest_releases(project_slug):
    builds = Build.query.filter(Build.release_id == Release.id)\
        .order_by(Build.specific_build_id.desc()).limit(10)\
        .subquery()

    # I don't see any good way out of this
    allowed = [ReleaseStatus.development, ReleaseStatus.beta, ReleaseStatus.stable]
    releases = None
    for status in allowed:
        q = Release.query.filter(Project.id == Release.project_id, Release.status == status)\
            .order_by(text("string_to_array(version, '.')::int[] desc"))\
            .limit(1)
        if releases is None:
            releases = q
        else:
            releases = releases.union(q)
    releases = releases.subquery()

    project = Project.query.filter_by(slug=project_slug)\
        .outerjoin(releases)\
        .outerjoin(builds)\
        .options(contains_eager(Project.releases, alias=releases).contains_eager(Release.builds, alias=builds))\
        .all()

    if len(project) == 0:
        return emit_json_error(error="Not found")

    return jsonify({
        'ok': True,
        'project': project[0].as_json()
    })


@bp.route('/<project_slug>/versions/latest/<stability_level>')
def latest_for_stability_level(project_slug, stability_level):
    stability = ReleaseStatus[stability_level]

    project = Project.query.filter_by(slug=project_slug).options(load_only('id')).one_or_none()
    if project is None:
        return emit_json_error(error="Not found", status_code=404)

    builds = Build.query.filter(Build.release_id == Release.id).order_by(Build.specific_build_id.desc())\
        .limit(100).subquery()
    release = Release.query.outerjoin(builds).filter(Release.project_id == project.id, Release.status == stability)\
        .order_by(Release.created_at.desc())\
        .options(contains_eager(Release.builds, alias=builds))\
        .all()

    if len(release) == 0:
        return emit_json_error(error="No matching release found", status_code=404)

    return jsonify({
        'ok': True,
        'release': release[0].as_json()
    })


@bp.route('/<project_slug>/versions/<version>')
def latest_for_version(project_slug, version):
    project = Project.query.filter_by(slug=project_slug).options(load_only('id')).one_or_none()
    if project is None:
        return emit_json_error(error="No such project found", status_code=404)

    builds = Build.query.filter(Build.release_id == Release.id).order_by(Build.specific_build_id.desc())\
        .limit(100).subquery().lateral()
    release = Release.query.outerjoin(builds).filter(Release.project_id == project.id, Release.version == version)\
        .options(contains_eager(Release.builds, alias=builds)) \
        .limit(1)\
        .one_or_none()

    if release is None:
        return emit_json_error(error="No matching release found", status_code=404)

    return jsonify({
        'ok': True,
        'release': release.as_json()
    })


@bp.route('/<project_slug>/versions/latest/<stability_level>/download')
def download_latest_for_stability_level(project_slug, stability_level):
    stability = ReleaseStatus[stability_level]

    project = Project.query.filter_by(slug=project_slug).options(load_only('id')).one_or_none()
    if project is None:
        return emit_json_error(error="No such project found", status_code=404)

    builds = Build.query.filter(Build.release_id == Release.id).order_by(Build.specific_build_id.desc())\
        .limit(1).subquery()
    release = Release.query.outerjoin(builds).filter(Release.project_id == project.id, Release.status == stability)\
        .order_by(Release.created_at.desc())\
        .options(contains_eager(Release.builds, alias=builds))\
        .one_or_none()

    if release is None:
        return emit_json_error(error="No matching release found", status_code=404)

    if len(release.builds) == 1:
        return redirect(release.builds[0].url)
    else:
        return emit_json_error(error="No matching builds found", status_code=404)


@bp.route('/<project_slug>/versions/<version>/builds/<build_id>/download')
def download_build(project_slug, version, build_id):
    project = Project.query.filter_by(slug=project_slug).options(load_only('id')).one_or_none()
    if project is None:
        return emit_json_error(error="No such project found", status_code=404)

    release = Release.query.filter(Release.project_id == project.id, Release.version == version)\
        .options(load_only('id')).one_or_none()
    if release is None:
        return emit_json_error(error="No such release found", status_code=404)

    build = Build.query.filter(Build.release_id == release.id, Build.specific_build_id == build_id)\
        .options(load_only('url'))\
        .one_or_none()
    if build is None:
        return emit_json_error(error="No matching build found", status_code=404)

    return redirect(release.builds[0].url)


@bp.route('/<project_slug>/versions', methods=['PUT'])
def add_version(project_slug):
    if request.method != 'PUT':
        return emit_json_error(error="Invalid method")
    
    if 'status' not in request.form:
        return emit_json_error(error="Status of release not provided")
    
    normalized_status = enum_value_by_name_safe(ReleaseStatus, request.form['status'])
    if normalized_status is None:
        return emit_json_error(error="Status is invalid")
    
    if 'version' not in request.form:
        return emit_json_error(error="Version for release not provided")

    project = Project.query.filter_by(slug=project_slug).options(load_only('id')).one_or_none()
    if project is None:
        return emit_json_error(error="No such project found", status_code=404)

    release = Release.query.filter(Release.project_id == project.id, Release.version == request.form['version'])\
        .options(load_only('id')).one_or_none()
    if release is not None:
        return emit_json_error(error="Release already exists", status_code=404)

    release = Release()
    release.project_id = project.id
    release.version = request.form["version"]
    release.status = normalized_status
    db.session.add(release)
    db.session.commit()

    response = jsonify(ok=True)
    response.status_code = 201
    return response


@bp.route('/<project_slug>/versions/<version>', methods=['PUT'])
def edit_version(project_slug, version):
    if request.method != 'PUT':
        return emit_json_error(error="Invalid method")

    status_if_changed = request.form.get('status')
    if status_if_changed is not None and enum_value_by_name_safe(ReleaseStatus, status_if_changed) is None:
        return emit_json_error(error="Status of release not valid")
    
    project = Project.query.filter_by(slug=project_slug).options(load_only('id')).one_or_none()
    if project is None:
        return emit_json_error(error="No such project found", status_code=404)

    release = Release.query.filter(Release.project_id == project.id, Release.version == version)\
        .options(load_only('id')).one_or_none()
    if release is None:
        return emit_json_error(error="Release does not exists", status_code=404)

    if status_if_changed is not None:
        release.status = ReleaseStatus[status_if_changed]
    db.session.add(release)
    db.session.commit()

    response = jsonify(ok=True)
    response.status_code = 201
    return response


@bp.route('/<project_slug>/versions/<version>/builds/<build_id>', methods=['PUT'])
def add_build(project_slug, version, build_id):
    if request.method != 'PUT':
        return emit_json_error(error="Invalid method")

    project = Project.query.filter_by(slug=project_slug).options(load_only('id')).one_or_none()
    if project is None:
        return emit_json_error(error="No such project found", status_code=404)

    release = Release.query.filter(Release.project_id == project.id, Release.version == version)\
        .options(load_only('id')).one_or_none()
    if release is None:
        return emit_json_error(error="No such release found", status_code=404)

    build_exists = db.session.query(
        Build.query.filter(Build.release_id == release.id, Build.specific_build_id == build_id).exists()
    ).scalar()
    if build_exists:
        return emit_json_error(error="Build already exists")

    build = Build()
    build.release_id = release.id
    build.specific_build_id = build_id
    # TODO: Upload to Amazon S3 or the like?
    build.url = 'https://example.com'
    db.session.add(build)
    db.session.commit()

    return jsonify(ok=True)