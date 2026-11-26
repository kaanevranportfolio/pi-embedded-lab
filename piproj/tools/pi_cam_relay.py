#!/usr/bin/env python3
"""Relay a UVC camera MJPG stream from the Pi to a browser on this PC.

Pi side : v4l2-ctl writes MJPG frames to stdout, carried over SSH.
PC side : frames are split at the JPEG start marker and served as
          multipart/x-mixed-replace on http://localhost:PORT/
Stats   : once per second on stdout (CSV) and as JSON at /stats.

Self-test without a Pi: --file some.mjpg (frames are replayed in a loop).
"""
import argparse
import json
import os
import shlex
import socketserver
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

SOI = b"\xff\xd8"
state = {"frame": None, "seq": 0, "frames": 0, "bytes": 0, "fps": 0.0,
         "kbps": 0.0, "last_size": 0, "lock": threading.Condition(), "done": False}

PAGE = b"""<!doctype html><meta charset=utf-8><title>Pi camera</title>
<body style="font-family:sans-serif;margin:16px">
<img src="/stream" style="max-width:100%;border:1px solid #888">
<pre id=s>waiting...</pre>
<script>setInterval(async()=>{try{const r=await fetch('/stats');
const j=await r.json();document.getElementById('s').textContent=
'fps '+j.fps.toFixed(1)+'   '+j.kbps.toFixed(0)+' kB/s   last frame '+j.last_size+' B   total frames '+j.frames}catch(e){}},1000)</script>
"""


def frames_from(stream):
    """Yield JPEG frames from a byte stream (split at start markers)."""
    buf = b""
    while True:
        chunk = stream.read(65536)
        if not chunk:
            return
        buf += chunk
        while True:
            first = buf.find(SOI)
            if first < 0:
                buf = b""
                break
            nxt = buf.find(SOI, first + 2)
            if nxt < 0:
                buf = buf[first:]
                break
            yield buf[first:nxt]
            buf = buf[nxt:]


def publish(frame):
    with state["lock"]:
        state["frame"] = frame
        state["seq"] += 1
        state["frames"] += 1
        state["bytes"] += len(frame)
        state["last_size"] = len(frame)
        state["lock"].notify_all()


def reader(args):
    if args.file:
        data = open(args.file, "rb").read()
        frames = [f for f in frames_from(__import__("io").BytesIO(data + SOI))]
        while not state["done"]:
            for f in frames:
                publish(f)
                time.sleep(1.0 / args.fps)
        return
    cmd = ssh_cmd(args) + [
           f"v4l2-ctl -d /dev/video0 --set-fmt-video=width={args.width},height={args.height},"
           f"pixelformat=MJPG --set-parm={args.fps} --stream-mmap --stream-skip={args.skip} --stream-to=-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        for f in frames_from(p.stdout):
            publish(f)
    finally:
        p.terminate()
        state["done"] = True


def stats_loop():
    last_f, last_b, t0 = 0, 0, time.time()
    print("t_s,fps,kBps,frames", flush=True)
    while not state["done"]:
        time.sleep(1)
        with state["lock"]:
            f, b = state["frames"], state["bytes"]
            state["fps"] = float(f - last_f)
            state["kbps"] = (b - last_b) / 1000.0
            print(f"{time.time() - t0:.0f},{state['fps']:.0f},{state['kbps']:.0f},{f}", flush=True)
        last_f, last_b = f, b


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(PAGE)
        elif self.path == "/stats":
            with state["lock"]:
                body = json.dumps({k: state[k] for k in ("fps", "kbps", "frames", "last_size")}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/stream":
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()
            seen = 0
            try:
                while not state["done"]:
                    with state["lock"]:
                        state["lock"].wait_for(lambda: state["seq"] != seen or state["done"], timeout=5)
                        frame, seen = state["frame"], state["seq"]
                    if frame is None:
                        continue
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                     + str(len(frame)).encode() + b"\r\n\r\n" + frame + b"\r\n")
            except (BrokenPipeError, ConnectionResetError):
                pass
        else:
            self.send_error(404)


class Server(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=os.environ.get("PI_HOST"), help="Pi address (or set PI_HOST)")
    ap.add_argument("--key", default=os.environ.get("PI_KEY", os.path.expanduser("~/.ssh/id_ed25519")),
                    help="SSH private key (or set PI_KEY)")
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--skip", type=int, default=5, help="frames dropped at start (exposure settling)")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--duration", type=int, default=0, help="stop after N seconds (0 = until Ctrl+C)")
    ap.add_argument("--file", help="replay frames from this MJPG file instead of the Pi")
    args = ap.parse_args()
    if not args.host and not args.file:
        ap.error("give the Pi address with --host or PI_HOST (or use --file for a self-test)")
    threading.Thread(target=reader, args=(args,), daemon=True).start()
    threading.Thread(target=stats_loop, daemon=True).start()
    srv = Server(("127.0.0.1", args.port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"open http://localhost:{args.port}/", file=sys.stderr)
    t0 = time.time()
    try:
        while not state["done"] and (not args.duration or time.time() - t0 < args.duration):
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    state["done"] = True
    srv.shutdown()
    cleanup(args)


def cleanup(args):
    """The remote v4l2-ctl can outlive the SSH session (no tty): stop it so the camera is free."""
    if args.file:
        return
    subprocess.run(ssh_cmd(args) + ["killall v4l2-ctl 2>/dev/null; true"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)


def ssh_cmd(args):
    """ssh with normal host-key checking; extra options (e.g. a throwaway known_hosts file for a
    Pi that is reflashed often) can be passed in PI_SSH_OPTS."""
    extra = shlex.split(os.environ.get("PI_SSH_OPTS", ""))
    return ["ssh", "-i", args.key, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=6", "-o", "LogLevel=ERROR"] + extra + [f"root@{args.host}"]


if __name__ == "__main__":
    main()
