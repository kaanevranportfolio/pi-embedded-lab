#!/usr/bin/env python3
"""Browser control panel for the belt_counter program running on the Pi.

  PI_HOST=<pi address> python3 belt_ui.py [--key KEYFILE] [--port 8080] [--disp 2]
  open http://localhost:8080/  ->  Start / Stop / Reset, move the green counting line.

The Pi does the vision work (belt_counter). This server only starts it over SSH, relays
its output to the browser and forwards the few control commands. Python standard library only.

Browser stream (/stream), repeated per message:
  4 bytes big-endian JSON length | JSON | 4 bytes payload length | payload (YUYV 320x240 or empty)
"""
import argparse
import collections
import io
import json
import os
import shlex
import struct
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs, urlparse

BIN = "/home/root/belt_counter"
cfg = {}
S = {"proc": None, "running": False, "seq": 0, "msg": None, "err": collections.deque(maxlen=5),
     "cv": threading.Condition(), "line": 25, "t_start": 0.0, "frames": 0, "bytes": 0,
     "fps": 0.0, "kbps": 0.0, "rec_seq": 0, "rec_cmd": ""}
lock = threading.Lock()
REC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rec-out")

PAGE = r"""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Belt counter</title>
<style>
body{font-family:system-ui,sans-serif;margin:16px;background:#111;color:#eee}
h1{font-size:18px;margin:0 0 10px}
#wrap{display:flex;gap:16px;flex-wrap:wrap}
canvas{background:#000;border:1px solid #444;max-width:100%}
button{font-size:16px;padding:8px 18px;margin-right:6px;border-radius:6px;border:1px solid #666;background:#2a2a2a;color:#eee;cursor:pointer}
button.go{background:#1f6f3a} button.stop{background:#7a2a2a}
.big{font-size:56px;font-weight:700;line-height:1;color:#4cff7a}
.small{color:#aaa;font-size:13px}
label{display:block;margin:10px 0 2px}
#stat{font-family:ui-monospace,monospace;font-size:13px;white-space:pre;color:#bbb;margin-top:10px}
#err{color:#ff8a8a}
</style>
<h1>Belt counter: Raspberry Pi 3 + C270</h1>
<div id=wrap>
 <div><canvas id=cv width=640 height=480></canvas></div>
 <div style="min-width:260px">
  <div><button class=go id=bstart>Start</button><button class=stop id=bstop>Stop</button><button id=breset>Reset</button></div>
  <div style="margin-top:14px" class=small>Objects moved LEFT across the green line</div>
  <div class=big id=cleft>0</div>
  <div class=small style="margin-top:8px">moved right: <span id=cright>0</span> &nbsp; in view: <span id=nobj>0</span></div>
  <label>Line position: <span id=lpv>25</span>%</label>
  <input type=range id=line min=5 max=95 value=25 style="width:100%">
  <details style="margin-top:12px"><summary class=small>Sensitivity</summary>
   <label>Brightness difference: <span id=thyv>35</span></label><input type=range id=thy min=10 max=120 value=35 style="width:100%">
   <label>Colour difference: <span id=thcv>30</span></label><input type=range id=thc min=10 max=120 value=30 style="width:100%">
  </details>
  <div id=stat></div><div id=err></div>
 </div>
</div>
<script>
const cv=document.getElementById('cv'),ctx=cv.getContext('2d');
const off=document.createElement('canvas');off.width=320;off.height=240;const octx=off.getContext('2d');
const img=octx.createImageData(320,240);
const $=id=>document.getElementById(id);
const post=(p)=>fetch(p,{method:'POST'}).catch(()=>{});
$('bstart').onclick=()=>post('/api/start'); $('bstop').onclick=()=>post('/api/stop'); $('breset').onclick=()=>post('/api/reset');
let t1=null;
$('line').oninput=e=>{$('lpv').textContent=e.target.value;clearTimeout(t1);t1=setTimeout(()=>post('/api/cmd?name=line&value='+e.target.value),80)};
$('thy').oninput=e=>{$('thyv').textContent=e.target.value;post('/api/cmd?name=thy&value='+e.target.value)};
$('thc').oninput=e=>{$('thcv').textContent=e.target.value;post('/api/cmd?name=thc&value='+e.target.value)};
let last=null,lineNow=25;
function draw(j){
  ctx.drawImage(off,0,0,640,480);
  const lx=lineNow/100*640; ctx.strokeStyle='#00ff40';ctx.lineWidth=3;ctx.beginPath();ctx.moveTo(lx,0);ctx.lineTo(lx,480);ctx.stroke();
  ctx.lineWidth=2;ctx.font='14px sans-serif';
  for(const o of (j.objs||[])){
    ctx.strokeStyle=o.flag==1?'#00ff40':(o.flag==2?'#ffa000':'#ffee00');
    ctx.strokeRect(o.x0*2,o.y0*2,(o.x1-o.x0)*2,(o.y1-o.y0)*2);
    ctx.fillStyle=ctx.strokeStyle;ctx.fillText('#'+o.id,o.x0*2+2,o.y0*2-4);
  }
  ctx.fillStyle='rgba(0,0,0,.6)';ctx.fillRect(8,8,236,58);   /* counter drawn into the video too */
  ctx.fillStyle='#4cff7a';ctx.font='bold 42px sans-serif';ctx.fillText(j.cl,18,54);
  ctx.fillStyle='#ddd';ctx.font='14px sans-serif';ctx.fillText('moved left over the line',72,34);ctx.fillText('moved right: '+j.cr,72,54);
}
/* optional canvas recording, only in the page opened with ?rec=1; started and stopped by the server */
const isRec=location.search.includes('rec=1');let rec=null,chunks=[];
function recStart(){
  if(rec)return;const types=['video/mp4;codecs=avc1','video/webm;codecs=vp9','video/webm;codecs=vp8'];
  const mt=types.find(t=>MediaRecorder.isTypeSupported(t));chunks=[];
  rec=new MediaRecorder(cv.captureStream(30),{mimeType:mt,videoBitsPerSecond:3000000});
  rec.ondataavailable=e=>{if(e.data.size)chunks.push(e.data)};
  rec.onstop=async()=>{const ext=mt.startsWith('video/mp4')?'mp4':'webm';
    await fetch('/api/rec/upload?ext='+ext,{method:'POST',body:new Blob(chunks,{type:mt.split(';')[0]})});rec=null;};
  rec.start(500);
}
function recStop(){if(rec&&rec.state!=='inactive')rec.stop();}
function yuyv(p){
  const d=img.data;let o=0;
  for(let i=0;i<p.length;i+=4){
    const y0=p[i]-16,u=p[i+1]-128,y1=p[i+2]-16,v=p[i+3]-128;
    const rr=409*v+128,gg=-100*u-208*v+128,bb=516*u+128;
    let c=298*y0;d[o++]=clamp((c+rr)>>8);d[o++]=clamp((c+gg)>>8);d[o++]=clamp((c+bb)>>8);d[o++]=255;
    c=298*y1;d[o++]=clamp((c+rr)>>8);d[o++]=clamp((c+gg)>>8);d[o++]=clamp((c+bb)>>8);d[o++]=255;
  }
  octx.putImageData(img,0,0);
}
const clamp=x=>x<0?0:(x>255?255:x);
function onMsg(j,p){
  if(j.type==='rec'){if(isRec){j.cmd==='start'?recStart():recStop();}return;}
  if(j.type==='frame'){
    if(p.length===320*240*2) yuyv(p);
    lineNow=j.line; last=j; draw(j);
    $('cleft').textContent=j.cl; $('cright').textContent=j.cr; $('nobj').textContent=j.nobj;
  }
  $('stat').textContent=(j.running?'RUNNING':'stopped')+'   link '+j.fps.toFixed(0)+' msg/s  '+j.kbps.toFixed(0)+' kB/s'+
    (last&&j.running?'\nPi: '+(last.proc/1000).toFixed(1)+' ms/frame, '+(last.cpu/10).toFixed(0)+'% of one core, paper Y='+last.yref:'');
  $('err').textContent=j.err||'';
}
async function run(){
  for(;;){
    try{
      const r=await fetch('/stream');const rd=r.body.getReader();
      let buf=new Uint8Array(1<<20),a=0,b=0;
      for(;;){
        const {value,done}=await rd.read(); if(done)break;
        if(b+value.length>buf.length){ // compact or grow
          const n=b-a; let nb=buf; if(n+value.length>buf.length) nb=new Uint8Array(Math.max(buf.length*2,n+value.length));
          nb.set(buf.subarray(a,b),0); buf=nb;a=0;b=n;
        }
        buf.set(value,b);b+=value.length;
        for(;;){
          if(b-a<4)break; const jl=new DataView(buf.buffer,a,4).getUint32(0);
          if(b-a<4+jl+4)break; const pl=new DataView(buf.buffer,a+4+jl,4).getUint32(0);
          if(b-a<4+jl+4+pl)break;
          const j=JSON.parse(new TextDecoder().decode(buf.subarray(a+4,a+4+jl)));
          const p=buf.subarray(a+8+jl,a+8+jl+pl); onMsg(j,p); a+=8+jl+pl;
        }
      }
    }catch(e){} await new Promise(r=>setTimeout(r,1000));
  }
}
ctx.fillStyle='#000';ctx.fillRect(0,0,640,480);ctx.fillStyle='#888';ctx.font='20px sans-serif';ctx.fillText('Press Start',270,240);
run();
</script>
"""


def ssh_base():
    """ssh with normal host-key checking. Extra options (e.g. for a Pi that is reflashed often)
    can be passed in PI_SSH_OPTS."""
    extra = shlex.split(os.environ.get("PI_SSH_OPTS", ""))
    return ["ssh", "-T", "-i", cfg["key"], "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=6", "-o", "LogLevel=ERROR"] + extra + [f"root@{cfg['host']}"]


def remote_cleanup():
    subprocess.run(ssh_base() + ["killall belt_counter v4l2-ctl 2>/dev/null; true"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)


def publish(j, payload=b""):
    with S["cv"]:
        S["msg"] = (json.dumps(j).encode(), payload)
        S["seq"] += 1
        S["cv"].notify_all()


def read_exact(f, n):
    data = b""
    while len(data) < n:
        chunk = f.read(n - len(data))
        if not chunk:
            return None
        data += chunk
    return data


def stderr_reader(p):
    for line in p.stderr:
        S["err"].append(line.decode(errors="replace").strip())


def reader(out):
    S["frames"], S["bytes"], S["fps"], S["kbps"] = 0, 0, 0.0, 0.0
    last_t, last_f, last_b = time.time(), 0, 0
    try:
        while True:
            line = out.readline()
            if not line:
                break
            f = line.split()
            if len(f) < 13 or f[0] != b"F":
                continue
            nobj, plen = int(f[7]), int(f[11])
            objs = []
            for _ in range(nobj):
                o = out.readline().split()
                objs.append({"id": int(o[1]), "x0": int(o[2]), "y0": int(o[3]), "x1": int(o[4]),
                             "y1": int(o[5]), "flag": int(o[6])})
            payload = read_exact(out, plen) if plen else b""
            if plen and payload is None:
                break
            S["frames"] += 1
            S["bytes"] += len(line) + plen
            now = time.time()
            if now - last_t >= 1.0:
                S["fps"] = (S["frames"] - last_f) / (now - last_t)
                S["kbps"] = (S["bytes"] - last_b) / (now - last_t) / 1000.0
                last_t, last_f, last_b = now, S["frames"], S["bytes"]
            publish({"type": "frame", "running": True, "seq": int(f[1]), "cl": int(f[5]), "cr": int(f[6]),
                     "nobj": nobj, "proc": int(f[8]), "cpu": int(f[9]), "line": int(f[10]), "yref": int(f[12]),
                     "objs": objs, "fps": S["fps"], "kbps": S["kbps"], "err": ""}, payload or b"")
    finally:
        S["running"] = False
        publish(status_json())


def status_json():
    run = S["running"]
    return {"type": "status", "running": run, "fps": S["fps"] if run else 0.0,
            "kbps": S["kbps"] if run else 0.0, "err": " | ".join(S["err"]) if not run else ""}


def send_cmd(text):
    p = S["proc"]
    if p and S["running"] and p.stdin:
        try:
            p.stdin.write((text + "\n").encode())
            p.stdin.flush()
        except (BrokenPipeError, OSError):
            pass


def start():
    with lock:
        if S["running"]:
            return
        S["err"].clear()
        remote = f"killall belt_counter v4l2-ctl 2>/dev/null; exec {BIN} --line {S['line']} --disp {cfg['disp']}"
        p = subprocess.Popen(ssh_base() + [remote], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, bufsize=0)
        S["proc"], S["running"] = p, True
        out = io.BufferedReader(p.stdout, buffer_size=1 << 20)
        threading.Thread(target=reader, args=(out,), daemon=True).start()
        threading.Thread(target=stderr_reader, args=(p,), daemon=True).start()


def stop():
    with lock:
        p = S["proc"]
        if not p:
            return
        try:
            p.stdin.close()
        except OSError:
            pass
        try:
            p.wait(timeout=4)
        except subprocess.TimeoutExpired:
            p.terminate()
        S["running"] = False
    remote_cleanup()
    publish(status_json())


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _ok(self, body=b"", ctype="application/json"):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            self._ok(PAGE.encode(), "text/html; charset=utf-8")
        elif u.path == "/api/status":
            self._ok(json.dumps(status_json()).encode())
        elif u.path == "/stream":
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            seen, seen_rec = 0, S["rec_seq"]
            try:
                while True:
                    with S["cv"]:
                        S["cv"].wait_for(lambda: S["seq"] != seen or S["rec_seq"] != seen_rec, timeout=1.0)
                        msg, seen = S["msg"], S["seq"]
                        rec_new, seen_rec, rec_cmd = S["rec_seq"] != seen_rec, S["rec_seq"], S["rec_cmd"]
                    if msg is None:
                        msg = (json.dumps(status_json()).encode(), b"")
                    j, payload = msg
                    self.wfile.write(struct.pack(">I", len(j)) + j + struct.pack(">I", len(payload)) + payload)
                    if rec_new:
                        r = json.dumps({"type": "rec", "cmd": rec_cmd}).encode()
                        self.wfile.write(struct.pack(">I", len(r)) + r + struct.pack(">I", 0))
            except (BrokenPipeError, ConnectionResetError):
                pass
        else:
            self.send_error(404)

    def do_POST(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/api/start":
            start()
        elif u.path == "/api/stop":
            stop()
        elif u.path == "/api/reset":
            send_cmd("RESET")
        elif u.path == "/api/rec":
            cmd = q.get("cmd", [""])[0]
            if cmd in ("start", "stop"):
                with S["cv"]:
                    S["rec_cmd"] = cmd
                    S["rec_seq"] += 1
                    S["cv"].notify_all()
        elif u.path == "/api/rec/upload":
            ext = q.get("ext", ["webm"])[0]
            ext = ext if ext in ("mp4", "webm") else "webm"
            n = int(self.headers.get("Content-Length", "0"))
            data = self.rfile.read(n) if 0 < n <= 200 * 1024 * 1024 else b""
            os.makedirs(REC_DIR, exist_ok=True)
            path = os.path.join(REC_DIR, time.strftime("belt-%Y%m%d-%H%M%S.") + ext)
            with open(path, "wb") as fh:
                fh.write(data)
            print(f"recording saved: {path} ({len(data)} bytes)", flush=True)
        elif u.path == "/api/cmd":
            name, val = q.get("name", [""])[0], q.get("value", ["0"])[0]
            if name in ("line", "thy", "thc") and val.isdigit():
                if name == "line":
                    S["line"] = int(val)
                send_cmd(f"{name.upper()} {int(val)}")
        else:
            self.send_error(404)
            return
        self._ok(b"{}")


class Server(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=os.environ.get("PI_HOST"), help="Pi address (or set PI_HOST)")
    ap.add_argument("--key", default=os.environ.get("PI_KEY", os.path.expanduser("~/.ssh/id_ed25519")),
                    help="SSH private key (or set PI_KEY)")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--disp", type=int, default=2, help="send every Nth frame to the browser (detection runs on all)")
    a = ap.parse_args()
    if not a.host:
        ap.error("give the Pi address with --host or PI_HOST")
    cfg.update(host=a.host, key=a.key, disp=a.disp)
    srv = Server(("127.0.0.1", a.port), Handler)
    print(f"open http://localhost:{a.port}/   (Ctrl+C to quit)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop()


if __name__ == "__main__":
    main()
