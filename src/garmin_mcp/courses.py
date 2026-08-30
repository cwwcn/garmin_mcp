"""
Course management functions for Garmin Connect MCP Server.

Adds support for uploading GPX files as Garmin Connect Courses. The underlying
Garmin Connect endpoint is undocumented; this module reverse-engineers the
two-step flow used by the web UI:

    1) POST /course-service/course/import   (multipart upload of the GPX)
       -> returns a parsed course skeleton with geoPoints but no distance
          / bounding box / start point

    2) POST /course-service/course          (JSON, the actual save)
       -> server enriches with elevation gain/loss from terrain DB and
          returns the saved course with a courseId.

Both calls require the same OAuth2 bearer the rest of the MCP already uses.
"""

import io
import json
import math
import os
import pathlib
from xml.etree import ElementTree as ET
from typing import Any, Dict, Optional

# The garmin_client will be set by the main file
garmin_client = None


def configure(client):
    """Configure the module with the Garmin client instance"""
    global garmin_client
    garmin_client = client


_EARTH_RADIUS_M = 6371000.0
_GPX_NAMESPACE = "http://www.topografix.com/GPX/1/1"
_GPX_TAG = f"{{{_GPX_NAMESPACE}}}"
_COURSE_DOWNLOAD_DIR_ENV = "GARMIN_COURSE_DOWNLOAD_DIR"

ET.register_namespace("", _GPX_NAMESPACE)


def _validate_course_id(course_id: int) -> int:
    """Return a positive integer course id or raise a user-facing error."""
    if isinstance(course_id, bool):
        raise ValueError("course_id must be a positive integer")
    try:
        normalized = int(course_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("course_id must be a positive integer") from exc
    if normalized <= 0 or normalized != course_id:
        raise ValueError("course_id must be a positive integer")
    return normalized


def _finite_float(value: Any, field: str) -> Optional[float]:
    """Convert a value to a finite float, rejecting invalid numeric data."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    return number


def _normalise_geo_point(point: Any, index: int) -> Dict[str, Any]:
    """Validate and copy one Garmin route point using canonical GPX fields."""
    if not isinstance(point, dict):
        raise ValueError(f"geo point {index} is not an object")

    latitude = _finite_float(_first_present(point, "latitude", "lat"), f"geo point {index} latitude")
    longitude = _finite_float(_first_present(point, "longitude", "lon"), f"geo point {index} longitude")
    if latitude is None or not -90 <= latitude <= 90:
        raise ValueError(f"geo point {index} latitude is outside -90..90")
    if longitude is None or not -180 <= longitude <= 180:
        raise ValueError(f"geo point {index} longitude is outside -180..180")

    normalized = dict(point)
    normalized["latitude"] = latitude
    normalized["longitude"] = longitude
    elevation = _finite_float(
        _first_present(point, "elevation", "elevationInMeters", "altitude"),
        f"geo point {index} elevation",
    )
    normalized["elevation"] = 0.0 if elevation is None else elevation
    return normalized


def _extract_geo_points(course: Dict[str, Any]) -> list[Dict[str, Any]]:
    """Extract route points from Garmin's top-level or course-line response."""
    raw_points = course.get("geoPoints")
    if raw_points is None or raw_points == []:
        raw_points = []
        for line in course.get("courseLines") or []:
            if isinstance(line, dict):
                raw_points.extend(line.get("points") or [])
    if not isinstance(raw_points, list):
        raise ValueError("course geoPoints must be a list")
    return [_normalise_geo_point(point, index) for index, point in enumerate(raw_points) if point is not None]


def _normalise_course_points(course: Dict[str, Any]) -> tuple[list[Dict[str, Any]], int]:
    """Curate course waypoints and count malformed entries without crashing."""
    raw_points = course.get("coursePoints") or []
    if not isinstance(raw_points, list):
        raise ValueError("coursePoints must be a list")

    waypoints: list[Dict[str, Any]] = []
    invalid_count = 0
    for point in raw_points:
        if not isinstance(point, dict):
            invalid_count += 1
            continue
        try:
            lat = _finite_float(_first_present(point, "lat", "latitude"), "waypoint latitude")
            lon = _finite_float(_first_present(point, "lon", "longitude"), "waypoint longitude")
            if lat is None or lon is None or not -90 <= lat <= 90 or not -180 <= lon <= 180:
                invalid_count += 1
                continue
        except ValueError:
            invalid_count += 1
            continue
        try:
            distance = _finite_float(point.get("distance"), "waypoint distance")
        except ValueError:
            invalid_count += 1
            continue
        waypoints.append(
            {
                "name": (
                    point.get("name")
                    or point.get("label")
                    or point.get("pointType")
                    or point.get("coursePointType")
                    or "Waypoint"
                ),
                "type": (
                    point.get("pointType")
                    or point.get("coursePointType")
                    or point.get("type")
                    or point.get("typeKey")
                ),
                "lat": lat,
                "lon": lon,
                "distance_m": distance,
            }
        )
    return waypoints, invalid_count


def _first_present(data: Dict[str, Any], *keys: str) -> Any:
    """Return the first value that is present and not None (preserving zero)."""
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None


def _course_url(course_id: int) -> Optional[str]:
    """Build a Garmin Connect course URL when the client exposes its domain."""
    client = getattr(garmin_client, "client", None)
    domain = getattr(client, "domain", None)
    if not domain or not isinstance(domain, str):
        return None
    return f"https://connect.{domain}/modern/course/{course_id}"


def _resolve_gpx_output_path(course_id: int, output_path: Optional[str] = None) -> Optional[str]:
    """Resolve a GPX destination without silently writing to the app directory.

    An explicit path may be a file or a directory.  When omitted, the course
    directory environment variable is preferred, with the activity download
    directory retained as a backwards-compatible fallback.  ``None`` means
    the caller must ask the user where to save the file.
    """
    course_id = _validate_course_id(course_id)
    if output_path is not None:
        if not isinstance(output_path, str) or not output_path.strip():
            raise ValueError("output_path must be a non-empty file or directory path")
        expanded = os.path.abspath(os.path.expanduser(output_path.strip()))
        path = pathlib.Path(expanded)
        # Existing directories, trailing separators, and extensionless paths
        # are treated as directories. This makes /data/routes convenient.
        if (path.exists() and path.is_dir()) or output_path.endswith(("/", "\\")):
            return str(path / f"{course_id}.gpx")
        if path.exists() and not path.is_file():
            raise ValueError("output_path must be a regular file or directory")
        if path.suffix == "":
            return str(path / f"{course_id}.gpx")
        if path.suffix.lower() != ".gpx":
            raise ValueError("output_path file must use the .gpx extension")
        return str(path)

    configured_dir = os.getenv(_COURSE_DOWNLOAD_DIR_ENV) or os.getenv("GARMIN_FIT_DOWNLOAD_DIR")
    if not configured_dir:
        return None
    base = pathlib.Path(os.path.abspath(os.path.expanduser(configured_dir)))
    return str(base / f"{course_id}.gpx")


def _xml_text(value: Any) -> Optional[str]:
    """Return a safe non-empty XML text value."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _append_text(parent: ET.Element, tag: str, value: Any) -> None:
    text = _xml_text(value)
    if text is not None:
        ET.SubElement(parent, _GPX_TAG + tag).text = text


def _build_course_gpx(course: Dict[str, Any]) -> tuple[bytes, Dict[str, int]]:
    """Build a standards-compliant GPX 1.1 document from a Garmin course."""
    geo_points = _extract_geo_points(course)
    if len(geo_points) < 2:
        raise ValueError("Course contains fewer than 2 valid geo points")
    waypoints, invalid_waypoints = _normalise_course_points(course)

    name = _xml_text(course.get("courseName")) or "Garmin Course"
    root = ET.Element(
        _GPX_TAG + "gpx",
        {"version": "1.1", "creator": "GarminConnectMCP"},
    )
    metadata = ET.SubElement(root, _GPX_TAG + "metadata")
    _append_text(metadata, "name", name)

    for waypoint in waypoints:
        wpt = ET.SubElement(
            root,
            _GPX_TAG + "wpt",
            {"lat": str(waypoint["lat"]), "lon": str(waypoint["lon"])},
        )
        _append_text(wpt, "name", waypoint["name"])
        _append_text(wpt, "type", waypoint["type"])

    track = ET.SubElement(root, _GPX_TAG + "trk")
    _append_text(track, "name", name)
    segment = ET.SubElement(track, _GPX_TAG + "trkseg")
    for point in geo_points:
        track_point = ET.SubElement(
            segment,
            _GPX_TAG + "trkpt",
            {"lat": str(point["latitude"]), "lon": str(point["longitude"])},
        )
        _append_text(track_point, "ele", point.get("elevation"))
        timestamp = point.get("timestamp") or point.get("time")
        if isinstance(timestamp, str) and timestamp.strip():
            _append_text(track_point, "time", timestamp)

    ET.indent(root, space="  ")
    payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    # Parse our own output once before touching disk. This guards against
    # accidental malformed XML if the response shape changes later.
    ET.fromstring(payload)
    return payload, {
        "waypoints_count": len(waypoints),
        "invalid_waypoints_count": invalid_waypoints,
        "track_points_count": len(geo_points),
    }


def _atomic_write(path: str, payload: bytes, overwrite: bool) -> None:
    """Write bytes atomically, refusing accidental overwrite by default."""
    target = pathlib.Path(path)
    if target.is_symlink():
        raise ValueError("Refusing to write through a symbolic link")
    if target.exists() and not overwrite:
        raise FileExistsError(f"File already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp-{os.getpid()}")
    try:
        with open(temporary, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _haversine(p1: Dict[str, float], p2: Dict[str, float]) -> float:
    lat1, lon1 = math.radians(p1["latitude"]), math.radians(p1["longitude"])
    lat2, lon2 = math.radians(p2["latitude"]), math.radians(p2["longitude"])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


def _initial_bearing(p1: Dict[str, float], p2: Dict[str, float]) -> float:
    lat1, lat2 = math.radians(p1["latitude"]), math.radians(p2["latitude"])
    dlon = math.radians(p2["longitude"] - p1["longitude"])
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


# Map common activity keys to the Garmin activity type id Garmin's course
# service understands. The id list is small and stable.
_ACTIVITY_TYPE_IDS = {
    "running": 1,
    "cycling": 2,
    "hiking": 3,
    "walking": 9,
    "trail_running": 6,
    "mountain_biking": 5,
    "road_biking": 10,
    "gravel_cycling": 4,
}


def _build_course_payload(
    parsed: Dict[str, Any],
    course_name: str,
    activity_type_id: int,
    description: Optional[str],
) -> Dict[str, Any]:
    """Construct the create-course JSON body from the /import response."""

    if not isinstance(parsed, dict):
        raise ValueError("Parsed course response must be an object")
    geo_points = _extract_geo_points(parsed)
    if len(geo_points) < 2:
        raise ValueError("Parsed course has fewer than 2 geo points; GPX is empty or invalid")

    # Compute cumulative distance per point + total
    total_distance = 0.0
    for i, p in enumerate(geo_points):
        if i == 0:
            p["distance"] = 0.0
        else:
            total_distance += _haversine(geo_points[i - 1], p)
            p["distance"] = total_distance

    lats = [p["latitude"] for p in geo_points]
    lons = [p["longitude"] for p in geo_points]

    bbox = {
        "center": {
            "latitude": (min(lats) + max(lats)) / 2,
            "longitude": (min(lons) + max(lons)) / 2,
        },
        "lowerLeft": {"latitude": min(lats), "longitude": min(lons)},
        "upperRight": {"latitude": max(lats), "longitude": max(lons)},
        "lowerLeftLatIsSet": True,
        "lowerLeftLongIsSet": True,
        "upperRightLatIsSet": True,
        "upperRightLongIsSet": True,
    }

    start_point = {
        "latitude": geo_points[0]["latitude"],
        "longitude": geo_points[0]["longitude"],
        "elevation": geo_points[0].get("elevation") or 0.0,
        "distance": None,
        "timestamp": None,
    }

    bearing = _initial_bearing(geo_points[0], geo_points[-1])

    return {
        "courseName": course_name,
        "description": description,
        "openStreetMap": False,
        "matchedToSegments": False,
        "userProfilePk": None,
        "userGroupPk": None,
        "rulePK": 2,  # private
        "geoRoutePk": None,
        "sourceTypeId": 3,  # GPX
        "sourcePk": None,
        "distanceMeter": total_distance,
        "elevationGainMeter": 0.0,
        "elevationLossMeter": 0.0,
        "startPoint": start_point,
        "coursePoints": [],
        "boundingBox": bbox,
        "hasShareableEvent": False,
        "hasTurnDetectionDisabled": False,
        "activityTypePk": activity_type_id,
        "virtualPartnerId": None,
        "includeLaps": False,
        "elapsedSeconds": None,
        "speedMeterPerSecond": None,
        "courseLines": [
            {
                "courseId": None,
                "sortOrder": 1,
                "numberOfPoints": len(geo_points),
                "distanceInMeters": total_distance,
                "bearing": bearing,
                "points": geo_points,
                "coordinateSystem": "WGS84",
                "originalCoordinateSystem": "WGS84",
            }
        ],
        "coordinateSystem": "WGS84",
        "targetCoordinateSystem": "WGS84",
        "originalCoordinateSystem": "WGS84",
        "consumer": None,
        "elevationSource": 3,
        "hasPaceBand": False,
        "hasPowerGuide": False,
        "favorite": False,
        "startNote": None,
        "finishNote": None,
        "cutoffDuration": None,
        "geoPoints": geo_points,
    }


def register_tools(app):
    """Register course management tools"""

    @app.tool()
    async def get_courses() -> str:
        """List all courses saved on Garmin Connect.

        Returns a curated list of courses with id, name, distance, activity type
        and creation date.
        """
        try:
            data = garmin_client.client.connectapi("/course-service/course")

            if not isinstance(data, list):
                return json.dumps(data, indent=2)

            curated = []
            for course in data:
                if not isinstance(course, dict):
                    continue
                curated.append(
                    {
                        "course_id": course.get("courseId"),
                        "name": course.get("courseName"),
                        "distance_m": _first_present(course, "distanceInMeters", "distanceMeter"),
                        "elevation_gain_m": _first_present(
                            course, "elevationGainInMeters", "elevationGainMeter"
                        ),
                        "elevation_loss_m": _first_present(
                            course, "elevationLossInMeters", "elevationLossMeter"
                        ),
                        "activity": (
                            course.get("activityType", {}).get("typeKey")
                            if isinstance(course.get("activityType"), dict)
                            else None
                        ),
                        "has_pace_band": course.get("hasPaceBand"),
                        "created": course.get("createdDateFormatted"),
                    }
                )
            return json.dumps({"count": len(curated), "courses": curated}, indent=2)
        except Exception as e:
            return f"Error listing courses: {str(e)}"

    @app.tool()
    async def get_course_details(course_id: int) -> str:
        """Get detailed metadata and navigation points for a Garmin course.

        This is a read-only operation.  ``course_id`` should come from
        ``get_courses``.  Route geometry is summarized by point count; use
        ``download_course_gpx`` when the actual track file is needed.
        """
        try:
            course_id = _validate_course_id(course_id)
            data = garmin_client.client.connectapi(f"/course-service/course/{course_id}")
            if not isinstance(data, dict) or not data:
                return f"Error: course {course_id} not found or returned no data."

            waypoints, invalid_waypoints = _normalise_course_points(data)
            geo_points = _extract_geo_points(data)
            result = {
                "course_id": _first_present(data, "courseId") or course_id,
                "name": data.get("courseName"),
                "distance_m": _first_present(data, "distanceInMeters", "distanceMeter"),
                "elevation_gain_m": _first_present(
                    data, "elevationGainInMeters", "elevationGainMeter"
                ),
                "elevation_loss_m": _first_present(
                    data, "elevationLossInMeters", "elevationLossMeter"
                ),
                "activity": (
                    data.get("activityType", {}).get("typeKey")
                    if isinstance(data.get("activityType"), dict)
                    else None
                ),
                "waypoints_count": len(waypoints),
                "waypoints": waypoints,
                "geo_points_count": len(geo_points),
            }
            if invalid_waypoints:
                result["invalid_waypoints_count"] = invalid_waypoints
            url = _course_url(course_id)
            if url:
                result["url"] = url
            return json.dumps(result, indent=2)
        except Exception as e:
            return f"Error fetching course details: {str(e)}"

    @app.tool()
    async def download_course_gpx(
        course_id: int,
        output_path: Optional[str] = None,
        overwrite: bool = False,
    ) -> str:
        """Export a Garmin Connect course as a standards-compliant GPX file.

        The file is written inside the MCP container/NAS filesystem, not sent
        directly to Telegram.  ``output_path`` may be a .gpx file or a
        directory.  When omitted, ``GARMIN_COURSE_DOWNLOAD_DIR`` is preferred,
        followed by ``GARMIN_FIT_DOWNLOAD_DIR``.  Existing files are protected
        unless ``overwrite=True`` is explicitly requested.
        """
        temporary_path: Optional[str] = None
        try:
            course_id = _validate_course_id(course_id)
            target_path = _resolve_gpx_output_path(course_id, output_path)
            if target_path is None:
                return json.dumps(
                    {
                        "status": "needs_setup",
                        "course_id": course_id,
                        "message": (
                            "Provide output_path or set GARMIN_COURSE_DOWNLOAD_DIR "
                            "(GARMIN_FIT_DOWNLOAD_DIR is also supported)."
                        ),
                    },
                    indent=2,
                )

            target = pathlib.Path(target_path)
            if target.exists() and target.is_symlink():
                return f"Error downloading course GPX: refusing to write through symbolic link: {target}"
            if target.exists() and not overwrite:
                return json.dumps(
                    {
                        "status": "exists",
                        "course_id": course_id,
                        "gpx_path": str(target),
                        "message": "File already exists; set overwrite=true only after confirming.",
                    },
                    indent=2,
                )

            data = garmin_client.client.connectapi(f"/course-service/course/{course_id}")
            if not isinstance(data, dict) or not data:
                return f"Error: course {course_id} not found or returned no data."

            payload, counts = _build_course_gpx(data)
            _atomic_write(str(target), payload, overwrite=overwrite)
            result = {
                "status": "success",
                "course_id": course_id,
                "name": _xml_text(data.get("courseName")) or f"Garmin Course {course_id}",
                "gpx_path": str(target),
                **counts,
            }
            url = _course_url(course_id)
            if url:
                result["url"] = url
            return json.dumps(result, indent=2)
        except (ValueError, FileExistsError) as e:
            return f"Error downloading course GPX: {str(e)}"
        except Exception as e:
            return f"Error downloading course GPX: {str(e)}"

    @app.tool()
    async def upload_course(
        gpx_path: str,
        course_name: Optional[str] = None,
        activity_type: str = "running",
        description: Optional[str] = None,
    ) -> str:
        """Upload a GPX file as a Garmin Connect Course.

        The course can then be loaded onto the watch (sync or "Send to Device")
        and used as a navigation course or to build a PacePro strategy.

        Args:
            gpx_path: Absolute path to the .gpx file on disk.
            course_name: Override the course name. Defaults to the name parsed
                from the GPX file.
            activity_type: One of running, cycling, hiking, walking, trail_running,
                mountain_biking, road_biking, gravel_cycling. Defaults to running.
            description: Optional description shown on the course detail page.
        """
        try:
            _p = pathlib.Path(gpx_path)
            if _p.suffix.lower() != ".gpx":
                return f"Error: only .gpx files are allowed, got: {_p.suffix or '(no extension)'}"
            gpx_path = str(_p.resolve())
            if not os.path.isfile(gpx_path):
                return f"Error: GPX file not found: {gpx_path}"

            activity_type_id = _ACTIVITY_TYPE_IDS.get(activity_type.lower())
            if activity_type_id is None:
                return (
                    f"Error: unknown activity_type '{activity_type}'. "
                    f"Supported: {', '.join(sorted(_ACTIVITY_TYPE_IDS))}."
                )

            with open(gpx_path, "rb") as f:
                gpx_bytes = f.read()

            # Step 1: parse the GPX server-side
            parsed = garmin_client.client.post(
                "connectapi",
                "/course-service/course/import",
                files={
                    "file": (
                        os.path.basename(gpx_path),
                        gpx_bytes,
                        "application/gpx+xml",
                    )
                },
                api=True,
            )

            effective_name = (
                course_name
                or parsed.get("courseName")
                or os.path.splitext(os.path.basename(gpx_path))[0]
            )

            # Step 2: build the create payload and save
            payload = _build_course_payload(
                parsed,
                course_name=effective_name,
                activity_type_id=activity_type_id,
                description=description,
            )

            saved = garmin_client.client.post(
                "connectapi", "/course-service/course", json=payload, api=True,
            )
            return json.dumps(
                {
                    "status": "success",
                    "course_id": saved.get("courseId"),
                    "name": saved.get("courseName"),
                    "distance_m": saved.get("distanceMeter"),
                    "elevation_gain_m": saved.get("elevationGainMeter"),
                    "elevation_loss_m": saved.get("elevationLossMeter"),
                    "activity_type_id": saved.get("activityTypePk"),
                    "url": f"https://connect.{garmin_client.client.domain}/modern/course/{saved.get('courseId')}",
                },
                indent=2,
            )

        except Exception as e:
            return f"Error uploading course: {str(e)}"

    @app.tool()
    async def delete_course(course_id: int) -> str:
        """Delete a course from Garmin Connect.

        Args:
            course_id: ID of the course to delete (get IDs from get_courses).
        """
        try:
            garmin_client.client.delete(
                "connectapi", f"/course-service/course/{course_id}"
            )
            return json.dumps(
                {
                    "status": "success",
                    "course_id": course_id,
                    "message": f"Course {course_id} deleted",
                },
                indent=2,
            )
        except Exception as e:
            return f"Error deleting course: {str(e)}"

    return app
