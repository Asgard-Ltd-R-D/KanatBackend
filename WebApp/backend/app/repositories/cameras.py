import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from app.models import Camera


class AliasTaken(Exception):
    """Another camera already has this alias (uq_cameras_alias)."""


def get(db: DBSession, camera_id: uuid.UUID) -> Camera | None:
    return db.get(Camera, camera_id)


def list_all(db: DBSession) -> list[Camera]:
    """Every camera, in the order they were added."""
    return db.query(Camera).order_by(Camera.created_at).all()


def save(db: DBSession, camera: Camera) -> Camera:
    """Adds or updates the camera. Raises AliasTaken if its alias is in use."""
    db.add(camera)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise AliasTaken(camera.alias) from e
    db.refresh(camera)
    return camera


def delete(db: DBSession, camera: Camera) -> None:
    db.delete(camera)
    db.commit()
