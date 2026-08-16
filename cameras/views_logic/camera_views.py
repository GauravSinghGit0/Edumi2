"""
cameras/views_logic/camera_views.py

Camera CRUD + smart feed proxy for all camera types:
  - RTSP       → OpenCV via camera service (port 8003) with in-process fallback
  - IP Webcam  → direct HTTP MJPEG proxy via requests (no OpenCV needed)
  - DroidCam   → direct HTTP MJPEG proxy via requests (no OpenCV needed)
"""

import logging
import os
import time

import cv2
import numpy as np
import requests as req_lib

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from django.contrib.auth import get_user_model

from ..models import Camera, CameraPermission
from .utils import is_admin, can_view_camera, test_rtsp_paths

logger = logging.getLogger("cameras")
User = get_user_model()

# ---------------------------------------------------------------------------
# Known URL paths per HTTP camera app, in priority order
# ---------------------------------------------------------------------------
_HTTP_PATHS = {
    "ip_webcam": ["/video", "/videofeed", "/shot.jpg", "/live"],
    "droidcam":  ["/mjpegfeed", "/video", "/mjpeg", "/cam/1/stream"],
}
_DEFAULT_PORT = {"ip_webcam": 8080, "droidcam": 4747, "rtsp": 554}


# ===========================================================================
# Admin dashboard
# ===========================================================================

@login_required
def admin_dashboard(request):
    if not is_admin(request.user):
        return redirect("login")
    cameras  = Camera.objects.all().order_by("-created_at")
    teachers = User.objects.filter(userprofile__user_type="teacher")
    return render(request, "cameras/control_room/admin_dashboard.html", {"cameras": cameras, "teachers": teachers})


# ===========================================================================
# Add camera
# ===========================================================================

@login_required
def add_camera(request):
    if not is_admin(request.user):
        return JsonResponse({"status": "error", "message": "Permission denied"})

    if request.method == "POST":
        name        = request.POST.get("name", "").strip()
        cam_type    = request.POST.get("camera_type", "rtsp")
        ip_address  = request.POST.get("ip_address", "").strip()
        port_raw    = request.POST.get("port", "").strip()
        username    = request.POST.get("username", "").strip()
        password    = request.POST.get("password", "").strip()
        stream_path = request.POST.get("stream_path", "").strip() or None

        port = int(port_raw) if port_raw.isdigit() else _DEFAULT_PORT.get(cam_type, 554)

        if cam_type == "rtsp" and not stream_path:
            try:
                detected, _ = test_rtsp_paths(ip_address, port, username, password)
                stream_path = detected or "/stream"
            except Exception:
                stream_path = "/stream"
        elif cam_type == "ip_webcam":
            stream_path = stream_path or "/video"
        elif cam_type == "droidcam":
            stream_path = stream_path or "/mjpegfeed"

        camera = Camera.objects.create(
            name=name, camera_type=cam_type,
            ip_address=ip_address, port=port,
            username=username, password=password,
            stream_path=stream_path, is_active=True,
        )
        return JsonResponse({
            "status": "success",
            "message": f'Camera "{name}" added.',
            "camera_id": camera.id,
        })

    return redirect("admin_dashboard")


# ===========================================================================
# Edit camera
# ===========================================================================

@login_required
def edit_camera(request, camera_id):
    if not is_admin(request.user):
        return JsonResponse({"status": "error", "message": "Permission denied"})

    try:
        camera = get_object_or_404(Camera, id=camera_id)

        if request.method == "POST":
            if "name" in request.POST:
                cam_type    = request.POST.get("camera_type", camera.camera_type)
                port_raw    = request.POST.get("port", "").strip()
                stream_path = request.POST.get("stream_path", "").strip() or None

                camera.name       = request.POST.get("name", camera.name)
                camera.camera_type = cam_type
                camera.ip_address = request.POST.get("ip_address", camera.ip_address).strip()
                camera.username   = request.POST.get("username", "").strip()
                camera.password   = request.POST.get("password", "").strip()
                camera.port       = int(port_raw) if port_raw.isdigit() else _DEFAULT_PORT.get(cam_type, 554)
                camera.is_active  = True

                if cam_type == "rtsp":
                    if stream_path:
                        camera.stream_path = stream_path
                    else:
                        try:
                            detected, _ = test_rtsp_paths(camera.ip_address, camera.port, camera.username, camera.password)
                            if detected:
                                camera.stream_path = detected
                        except Exception as exc:
                            logger.warning(f"RTSP path detection failed: {exc}")
                elif cam_type == "ip_webcam":
                    camera.stream_path = stream_path or "/video"
                else:  # droidcam
                    camera.stream_path = stream_path or "/mjpegfeed"

                camera.save()

            if "teachers" in request.POST or ("name" not in request.POST and "camera_id" in request.POST):
                teacher_ids = request.POST.getlist("teachers")
                CameraPermission.objects.filter(camera=camera).delete()
                for t_id in teacher_ids:
                    try:
                        teacher = User.objects.get(id=int(t_id))
                        CameraPermission.objects.create(camera=camera, teacher=teacher, granted_by=request.user)
                    except Exception as exc:
                        logger.warning(f"Permission grant failed for id={t_id}: {exc}")

            return JsonResponse({"status": "success", "message": "Camera updated"})

        # GET → return data for modal
        assigned = list(camera.get_authorized_teachers().values_list("id", flat=True))
        return JsonResponse({
            "id": camera.id, "name": camera.name,
            "camera_type": camera.camera_type,
            "ip_address": camera.ip_address, "port": camera.port,
            "username": camera.username, "password": camera.password,
            "stream_path": camera.stream_path, "assigned_teachers": assigned,
        })

    except Exception as exc:
        logger.error(f"edit_camera error: {exc}", exc_info=True)
        return JsonResponse({"status": "error", "message": str(exc)}, status=500)


# ===========================================================================
# Delete camera
# ===========================================================================

@login_required
def delete_camera(request, camera_id):
    if not is_admin(request.user):
        return JsonResponse({"status": "error", "message": "Permission denied"})

    if request.method == "POST":
        camera = get_object_or_404(Camera, id=camera_id)
        try:
            camera.delete()
            return JsonResponse({"status": "success"})
        except Exception as exc:
            logger.error(f"delete_camera: {exc}")
            from django.db import connection
            try:
                with connection.cursor() as cur:
                    cur.execute("PRAGMA foreign_keys = OFF;")
                    camera.delete()
                    cur.execute("PRAGMA foreign_keys = ON;")
                return JsonResponse({"status": "success"})
            except Exception as exc2:
                return JsonResponse({"status": "error", "message": str(exc2)}, status=500)
    return redirect("admin_dashboard")


# ===========================================================================
# Main camera feed — routes to correct handler by type
# ===========================================================================

@login_required
def camera_feed(request, camera_id):
    """
    Smart camera feed endpoint.

    IP Webcam / DroidCam  → pure HTTP MJPEG proxy (no OpenCV, no camera service)
    RTSP                  → proxy through camera service (port 8003) with
                            in-process OpenCV streamer as fallback
    """
    camera = get_object_or_404(Camera, id=camera_id)

    if not can_view_camera(request.user, camera):
        return JsonResponse({"error": "Permission denied"}, status=403)

    if camera.camera_type in ("ip_webcam", "droidcam"):
        return _http_mjpeg_feed(camera)

    return _rtsp_feed(request, camera)


# ---------------------------------------------------------------------------
# HTTP MJPEG feed (IP Webcam + DroidCam)
# ---------------------------------------------------------------------------

def _http_mjpeg_feed(camera):
    """
    Directly proxy the phone's HTTP MJPEG or JPEG stream.
    Tries every known URL path in order; saves the working one for next time.
    """
    ip   = camera.ip_address.strip()
    port = camera.port or _DEFAULT_PORT.get(camera.camera_type, 8080)

    # Build candidate list — stored path gets tried first
    candidates = list(_HTTP_PATHS.get(camera.camera_type, []))
    if camera.stream_path and camera.stream_path not in candidates:
        candidates.insert(0, camera.stream_path)

    base = f"http://{ip}:{port}"

    for path in candidates:
        url = f"{base}{path}"
        resp = _try_http_stream(camera, url, base, path)
        if resp is not None:
            return resp

    logger.warning(f"HTTP camera {camera.id} unreachable at {base}")
    return _offline_frame(camera)


def _try_http_stream(camera, url, base, path):
    """
    Attempt to open url as MJPEG or JPEG stream.
    Returns a StreamingHttpResponse on success, None on failure.
    """
    try:
        upstream = req_lib.get(url, stream=True, timeout=5)
        ct = upstream.headers.get("Content-Type", "")

        ok = (
            upstream.status_code == 200
            and ("multipart" in ct or "jpeg" in ct or "image" in ct or "octet-stream" in ct)
        )
        if not ok:
            upstream.close()
            return None

        logger.info(f"HTTP camera {camera.id} connected: {url}  ({ct})")

        # Persist the working path so next request skips probing
        if camera.stream_path != path:
            try:
                Camera.objects.filter(pk=camera.pk).update(stream_path=path)
            except Exception:
                pass

        # Single JPEG endpoint → wrap in a looping MJPEG boundary stream
        if "multipart" not in ct:
            upstream.close()

            def _jpeg_loop():
                hdr = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                while True:
                    try:
                        r = req_lib.get(url, timeout=5)
                        if r.status_code == 200:
                            yield hdr + r.content + b"\r\n"
                    except Exception:
                        break
                    time.sleep(0.08)          # ~12 fps

            response = StreamingHttpResponse(
                _jpeg_loop(),
                content_type="multipart/x-mixed-replace; boundary=frame",
            )
        else:
            # True MJPEG stream — pass chunks straight through
            def _mjpeg_pass():
                try:
                    for chunk in upstream.iter_content(chunk_size=4096):
                        if chunk:
                            yield chunk
                except Exception:
                    pass
                finally:
                    upstream.close()

            response = StreamingHttpResponse(_mjpeg_pass(), content_type=ct)

        response["Cache-Control"]    = "no-cache, no-store, must-revalidate"
        response["Pragma"]           = "no-cache"
        response["Expires"]          = "0"
        response["X-Accel-Buffering"] = "no"
        return response

    except (req_lib.exceptions.ConnectionError, req_lib.exceptions.Timeout):
        return None
    except Exception as exc:
        logger.debug(f"_try_http_stream({url}): {exc}")
        return None


# ---------------------------------------------------------------------------
# RTSP feed (via camera service with in-process fallback)
# ---------------------------------------------------------------------------

def _rtsp_feed(request, camera):
    from django.conf import settings

    quality     = request.GET.get("q", "med")
    camera_svc  = getattr(settings, "CAMERA_SERVICE_URL", "http://localhost:8003")
    feed_url    = f"{camera_svc}/cameras/{camera.id}/feed/?q={quality}"

    try:
        upstream = req_lib.get(feed_url, stream=True, timeout=10, verify=False)
        ct = upstream.headers.get("Content-Type", "multipart/x-mixed-replace; boundary=frame")

        def _stream():
            try:
                for chunk in upstream.iter_content(chunk_size=8192):
                    if chunk:
                        yield chunk
            except Exception:
                pass
            finally:
                upstream.close()

        resp = StreamingHttpResponse(_stream(), content_type=ct)
        resp["Cache-Control"]     = "no-cache, no-store, must-revalidate"
        resp["Pragma"]            = "no-cache"
        resp["Expires"]           = "0"
        resp["X-Accel-Buffering"] = "no"
        return resp

    except req_lib.exceptions.ConnectionError:
        logger.warning(f"Camera service offline — using in-process streamer for camera {camera.id}")
        from .streaming_views import camera_manager, _generate_frames
        qmap = {"4k": "4k", "high": "high", "1080p": "high", "720p": "med", "480p": "med", "360p": "low"}
        q    = qmap.get(quality, "med")
        url  = camera.get_full_rtsp_url()
        streamer = camera_manager.get_streamer(camera.id, url)
        resp = StreamingHttpResponse(
            _generate_frames(streamer, camera, url, q, camera.id),
            content_type="multipart/x-mixed-replace; boundary=frame",
        )
        resp["Cache-Control"]     = "no-cache, no-store, must-revalidate"
        resp["X-Accel-Buffering"] = "no"
        return resp

    except Exception as exc:
        logger.error(f"_rtsp_feed error for camera {camera.id}: {exc}")
        return JsonResponse({"error": str(exc)}, status=500)


# ---------------------------------------------------------------------------
# Offline placeholder frame (shown when camera is unreachable)
# ---------------------------------------------------------------------------

def _offline_frame(camera):
    """Loop a single JPEG error frame so the <img> tag always shows something."""
    h, w = 480, 640
    img  = np.zeros((h, w, 3), dtype=np.uint8)
    img[:] = (20, 20, 40)

    font = cv2.FONT_HERSHEY_SIMPLEX
    lines = [
        (f"Camera offline: {camera.name}", 0.7, 180),
        (f"{camera.ip_address}:{camera.port}", 0.65, 230),
        ("Open the app on your device and", 0.55, 275),
        ("make sure it is streaming.", 0.55, 310),
    ]
    for text, scale, y in lines:
        (tw, _), _ = cv2.getTextSize(text, font, scale, 1)
        cv2.putText(img, text, ((w - tw) // 2, y), font, scale, (80, 160, 255), 1, cv2.LINE_AA)

    _, jpeg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 75])
    data = jpeg.tobytes()

    def _loop():
        hdr = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
        while True:
            yield hdr + data + b"\r\n"
            time.sleep(2)

    resp = StreamingHttpResponse(_loop(), content_type="multipart/x-mixed-replace; boundary=frame")
    resp["Cache-Control"] = "no-cache"
    return resp


# ===========================================================================
# Test / probe endpoints
# ===========================================================================

@login_required
def test_camera(request, camera_id):
    """Live connectivity test for a saved camera."""
    if not is_admin(request.user):
        return JsonResponse({"status": "error", "message": "Permission denied"})

    camera = get_object_or_404(Camera, id=camera_id)

    if camera.camera_type in ("ip_webcam", "droidcam"):
        return _probe_http(
            cam_type=camera.camera_type,
            ip=camera.ip_address,
            port=camera.port,
            camera_obj=camera,
        )

    # RTSP — try camera service, then local OpenCV
    try:
        from django.conf import settings
        svc = getattr(settings, "CAMERA_SERVICE_URL", "http://localhost:8003")
        r   = req_lib.get(f"{svc}/cameras/{camera_id}/test/", timeout=20, verify=False)
        if r.status_code == 200:
            return JsonResponse(r.json())
    except req_lib.exceptions.ConnectionError:
        pass
    except Exception as exc:
        logger.warning(f"Camera service test failed: {exc}")

    full_url = camera.get_full_rtsp_url()
    results  = []
    for transport in ("tcp", "udp"):
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = f"rtsp_transport;{transport}"
        cap = cv2.VideoCapture(full_url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 6000)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret and frame is not None:
                results.append({"method": f"RTSP/{transport.upper()}", "status": "success",
                                 "frame_size": f"{frame.shape[1]}x{frame.shape[0]}"})
            else:
                results.append({"method": f"RTSP/{transport.upper()}", "status": "opened_no_frame"})
        else:
            results.append({"method": f"RTSP/{transport.upper()}", "status": "failed"})
        cap.release()

    ok = any(r["status"] == "success" for r in results)
    return JsonResponse({
        "camera_id": camera_id, "camera_name": camera.name,
        "url_tested": full_url, "results": results,
        "overall_status": "success" if ok else "failed",
    })


@login_required
def probe_camera(request):
    """
    Probe an unsaved camera before it is added.
    GET params: type, ip, port
    """
    if not is_admin(request.user):
        return JsonResponse({"overall_status": "failed", "hint": "Permission denied."})

    cam_type = request.GET.get("type", "ip_webcam")
    ip       = request.GET.get("ip", "").strip()
    port_raw = request.GET.get("port", "").strip()

    if not ip:
        return JsonResponse({"overall_status": "failed", "hint": "No IP address provided."})

    port = int(port_raw) if port_raw.isdigit() else _DEFAULT_PORT.get(cam_type, 8080)

    if cam_type == "rtsp":
        return _probe_rtsp(ip, port)

    return _probe_http(cam_type=cam_type, ip=ip, port=port)


def _probe_rtsp(ip, port):
    """Quick OpenCV probe for RTSP (no DB changes)."""
    results = []
    for transport in ("tcp", "udp"):
        url = f"rtsp://{ip}:{port}/stream"
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = f"rtsp_transport;{transport}"
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)
        opened = cap.isOpened()
        ret, frame = cap.read() if opened else (False, None)
        cap.release()
        status = "success" if (ret and frame is not None) else ("failed_to_open" if not opened else "opened_no_frame")
        results.append({"method": f"RTSP/{transport.upper()}", "status": status})

    ok = any(r["status"] == "success" for r in results)
    return JsonResponse({
        "overall_status": "success" if ok else "failed",
        "results": results,
        "hint": (
            f"RTSP reachable at rtsp://{ip}:{port}"
            if ok else
            f"Cannot reach {ip}:{port}. Check IP, port, firewall, and that the camera is powered on."
        ),
    })


def _probe_http(cam_type, ip, port, camera_obj=None):
    """
    Probe HTTP camera paths. Optionally updates DB (camera_obj) with working path.
    Returns JsonResponse with probe results.
    """
    port = port or _DEFAULT_PORT.get(cam_type, 8080)
    base = f"http://{ip}:{port}"

    candidates = list(_HTTP_PATHS.get(cam_type, []))
    if camera_obj and camera_obj.stream_path and camera_obj.stream_path not in candidates:
        candidates.insert(0, camera_obj.stream_path)

    results      = []
    working_path = None

    for path in candidates:
        url = f"{base}{path}"
        try:
            r  = req_lib.get(url, stream=True, timeout=4)
            ct = r.headers.get("Content-Type", "")
            r.close()
            if r.status_code == 200 and ("multipart" in ct or "jpeg" in ct or "image" in ct):
                results.append({"url": url, "status": "success", "content_type": ct})
                if working_path is None:
                    working_path = path
                    if camera_obj:
                        Camera.objects.filter(pk=camera_obj.pk).update(stream_path=path)
            else:
                results.append({"url": url, "status": f"http_{r.status_code}", "content_type": ct})
        except req_lib.exceptions.ConnectionError:
            results.append({"url": url, "status": "connection_refused"})
        except req_lib.exceptions.Timeout:
            results.append({"url": url, "status": "timeout"})
        except Exception as exc:
            results.append({"url": url, "status": f"error: {exc}"})

    return JsonResponse({
        "overall_status": "success" if working_path else "failed",
        "results": results,
        "working_path": working_path,
        "hint": (
            f"Connected at {base}{working_path}"
            if working_path else
            f"Could not reach {base}. "
            "Make sure the app is open and streaming, "
            "and both devices are on the same WiFi network."
        ),
    })


# ===========================================================================
# Misc
# ===========================================================================

@login_required
def test_feed_page(request):
    return render(request, "test_feed.html")
