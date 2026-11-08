"""Lightweight MJPEG stream and snapshot proxy loading N cameras from config/printers.yaml."""

from pathlib import Path
import httpx
import yaml
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel

app = FastAPI(title="3D Printer Multi-Camera Proxy", version="2.0.0")

CONFIG_PATH = Path("config/printers.yaml")
FALLBACK_CONFIG_PATH = Path("config/printers.yaml.example")


class CameraInfo(BaseModel):
    name: str
    host: str
    stream_url: str
    snapshot_url: str


def load_cameras_from_yaml() -> dict[str, CameraInfo]:
    """Load camera definitions strictly from config/printers.yaml."""
    cameras: dict[str, CameraInfo] = {}

    target_file = CONFIG_PATH if CONFIG_PATH.is_file() else FALLBACK_CONFIG_PATH
    if target_file.is_file():
        try:
            with open(target_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                for item in data.get("printers", []):
                    if isinstance(item, dict) and item.get("host"):
                        name = str(item.get("name") or "printer").strip()
                        host = str(item.get("host")).strip().rstrip("/")
                        if not (host.startswith("http://") or host.startswith("https://")):
                            host = f"http://{host}"

                        stream = item.get("camera_url") or f"{host}/webcam/?action=stream"
                        snap = item.get("camera_snapshot_url") or f"{host}/webcam/?action=snapshot"

                        cameras[name] = CameraInfo(
                            name=name,
                            host=host,
                            stream_url=stream,
                            snapshot_url=snap,
                        )
        except Exception as e:
            print(f"Error loading cameras from {target_file}: {e}")

    return cameras


def resolve_camera(target: str) -> CameraInfo:
    """Resolve camera by name, 1-based numeric index, or fallback for all."""
    cameras = load_cameras_from_yaml()

    if target in cameras:
        return cameras[target]

    # Strip Grafana variable formatting: e.g. {printer-1}
    clean = target.strip("{}\"' ")
    if clean in cameras:
        return cameras[clean]

    # Handle multi-value list from Grafana (e.g. printer-1,printer-2)
    for part in clean.replace("|", ",").split(","):
        part = part.strip()
        if part in cameras:
            return cameras[part]

    # Fallback for $__all or empty
    if target in ("$__all", "all", "All", "*", "") or target.startswith(("{", "$")):
        if cameras:
            return next(iter(cameras.values()))

    if target.isdigit():
        idx = int(target) - 1
        cam_list = list(cameras.values())
        if 0 <= idx < len(cam_list):
            return cam_list[idx]

    raise HTTPException(status_code=404, detail=f"Camera '{target}' not found in config/printers.yaml")


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/camera")


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/camera/list")
async def list_cameras():
    cameras = load_cameras_from_yaml()
    return {"count": len(cameras), "cameras": list(cameras.values())}


@app.get("/camera", response_class=HTMLResponse)
async def camera_dashboard():
    cameras = load_cameras_from_yaml()

    cards_html = []
    for name, cam in cameras.items():
        card = f"""
        <div class="card">
            <div class="card-header">
                <span><b>{name.upper()}</b> ({cam.host})</span>
                <span class="badge">Live Stream</span>
            </div>
            <div class="card-body">
                <img src="/camera/stream/{name}" alt="{name} Live Stream"
                     onerror="this.alt='Camera stream unreachable'; this.style.color='#888';">
            </div>
            <div class="card-footer">
                <span>Feed: <code>{cam.stream_url}</code></span>
                <a href="/camera/snapshot/{name}" target="_blank">Direct Snapshot</a>
            </div>
        </div>
        """
        cards_html.append(card)

    cards_rendered = "\n".join(cards_html)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>3D Printers Fleet - Live Video Streams</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: #111217;
            color: #d8d9da;
            margin: 0;
            padding: 24px;
        }}
        header {{
            margin-bottom: 24px;
        }}
        h1 {{
            font-size: 1.6rem;
            color: #f79420;
            margin: 0 0 6px 0;
        }}
        p.desc {{
            color: #8e8e8e;
            margin: 0;
            font-size: 0.95rem;
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(440px, 1fr));
            gap: 24px;
        }}
        .card {{
            background: #181b1f;
            border: 1px solid #2a2d35;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        }}
        .card-header {{
            padding: 12px 16px;
            background: #202226;
            font-size: 0.95rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid #2a2d35;
        }}
        .card-body {{
            position: relative;
            background: #000;
            min-height: 260px;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .card-body img {{
            width: 100%;
            height: auto;
            display: block;
        }}
        .badge {{
            font-size: 0.75rem;
            padding: 2px 8px;
            border-radius: 4px;
            background: #2ea44f;
            color: #fff;
        }}
        .card-footer {{
            padding: 10px 16px;
            font-size: 0.82rem;
            display: flex;
            justify-content: space-between;
            color: #999;
            background: #141619;
            border-top: 1px solid #2a2d35;
        }}
        .card-footer a {{
            color: #388bfd;
            text-decoration: none;
        }}
        .card-footer a:hover {{
            text-decoration: underline;
        }}
        .nav-links {{
            margin-top: 28px;
            font-size: 0.9rem;
        }}
        .nav-links a {{
            color: #58a6ff;
            text-decoration: none;
            margin-right: 18px;
        }}
    </style>
</head>
<body>
    <header>
        <h1>3D Printer Fleet Live Video Streams</h1>
        <p class="desc">Serving {len(cameras)} camera feeds loaded from config/printers.yaml.</p>
    </header>

    <div class="grid">
        {cards_rendered}
    </div>

    <div class="nav-links">
        <a href="http://localhost:3000" target="_blank">&larr; Open Grafana Dashboards</a>
        <a href="http://localhost:9090" target="_blank">Prometheus</a>
        <a href="http://localhost:9093" target="_blank">Alertmanager</a>
    </div>
</body>
</html>
"""
    return HTMLResponse(content=html_content)


@app.get("/camera/stream/{target}")
async def proxy_mjpeg_stream(target: str):
    """Proxy live MJPEG stream for printer by name or numeric index."""
    cam = resolve_camera(target)
    client = httpx.AsyncClient(timeout=httpx.Timeout(10.0, read=None))

    try:
        req = client.build_request("GET", cam.stream_url)
        res = await client.send(req, stream=True)
        content_type = res.headers.get("content-type", "multipart/x-mixed-replace; boundary=--jpgboundary")

        async def stream_generator():
            try:
                async for chunk in res.aiter_bytes():
                    yield chunk
            finally:
                await res.aclose()
                await client.aclose()

        return StreamingResponse(
            stream_generator(),
            media_type=content_type,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
    except Exception as exc:
        await client.aclose()
        raise HTTPException(
            status_code=502,
            detail=f"Failed to connect to webcam stream at {cam.stream_url}: {exc}",
        )


@app.get("/camera/snapshot/{target}")
async def proxy_snapshot(target: str):
    """Proxy single JPEG snapshot for printer by name or numeric index."""
    cam = resolve_camera(target)
    async with httpx.AsyncClient(timeout=3.0) as client:
        try:
            resp = await client.get(cam.snapshot_url)
            resp.raise_for_status()
            return Response(
                content=resp.content,
                media_type=resp.headers.get("content-type", "image/jpeg"),
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0",
                },
            )
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to fetch snapshot from {cam.snapshot_url}: {exc}",
            )
