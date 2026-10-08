import os, re, uuid, subprocess
from pathlib import Path
from threading import Thread
import requests
from flask import Flask, render_template, request, jsonify, send_file
import imageio_ffmpeg

app = Flask(__name__)
BASE_DIR = Path(__file__).resolve().parent
TEMP_DIR = BASE_DIR / "temp_downloads"
TEMP_DIR.mkdir(exist_ok=True)
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
COBALT_API_URL = os.environ.get("COBALT_API_URL", "").rstrip("/")
jobs = {}

def clean_filename(text):
    text = re.sub(r'[<>:"/\\|?*]', "_", str(text).strip())
    text = re.sub(r"\s+", "_", text)
    return text[:100] or "Student"

def clean_url(url):
    url = url.strip()
    m = re.match(r"https?://(?:www\.)?youtu\.be/([^?&#/]+)", url, re.I)
    if m: return f"https://www.youtube.com/watch?v={m.group(1)}"
    m = re.search(r"(?:youtube\.com/watch\?[^#]*?v=)([^&#]+)", url, re.I)
    if m: return f"https://www.youtube.com/watch?v={m.group(1)}"
    return url

def update(j, **v):
    if j in jobs: jobs[j].update(v)

def convert(src, dst):
    r = subprocess.run([FFMPEG,"-y","-i",str(src),"-vn","-codec:a","libmp3lame","-b:a","192k",str(dst)],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if r.returncode: raise RuntimeError(r.stderr[-2000:] or "FFmpeg conversion failed.")

def local_job(j, upload, form, name):
    src = TEMP_DIR / f"{j}{Path(upload.filename or 'audio').suffix or '.tmp'}"
    try:
        update(j,status="processing",message="Processing selected file...")
        upload.save(src)
        fn = f"{clean_filename(form)}_{clean_filename(name)}.mp3"
        out = TEMP_DIR / f"{j}_{fn}"
        update(j,message="Converting selected file to MP3...")
        convert(src,out)
        update(j,status="ready",message="Ready",file=str(out),filename=fn)
    except Exception as e: update(j,status="error",message=str(e))
    finally: src.unlink(missing_ok=True)

def url_job(j, url, form, name):
    try:
        if not COBALT_API_URL:
            raise RuntimeError("Cobalt API is not configured on the server.")
        update(j,status="processing",message="Connecting to media service...")
        payload={"url":clean_url(url),"audioFormat":"mp3","audioBitrate":"192",
                 "downloadMode":"audio","filenameStyle":"basic","disableMetadata":False}
        r=requests.post(COBALT_API_URL+"/",json=payload,
                        headers={"Accept":"application/json","Content-Type":"application/json"},timeout=60)
        try: data=r.json()
        except: raise RuntimeError(f"Media service returned HTTP {r.status_code}.")
        if r.status_code >= 400 or data.get("status")=="error":
            raise RuntimeError(data.get("code") or data.get("text") or "Media service rejected the URL.")
        if data.get("status") not in ("tunnel","redirect") or not data.get("url"):
            raise RuntimeError(f"Media service returned: {data.get('status','unknown')}")
        update(j,message="Downloading converted MP3...")
        fn=f"{clean_filename(form)}_{clean_filename(name)}.mp3"
        out=TEMP_DIR/f"{j}_{fn}"
        with requests.get(data["url"],stream=True,timeout=300) as r2:
            r2.raise_for_status()
            with open(out,"wb") as f:
                for chunk in r2.iter_content(1024*1024):
                    if chunk: f.write(chunk)
        if out.stat().st_size==0: raise RuntimeError("Downloaded MP3 was empty.")
        update(j,status="ready",message="Ready",file=str(out),filename=fn)
    except Exception as e: update(j,status="error",message=str(e)[-1800:])

@app.route("/")
def index(): return render_template("index.html")

@app.route("/download",methods=["POST"])
def download():
    form=request.form.get("form_no","").strip()
    name=request.form.get("student_name","").strip()
    url=request.form.get("url","").strip()
    upload=request.files.get("local_file")
    if not form: return jsonify(error="Please enter Form No."),400
    if not name: return jsonify(error="Please enter Student Name."),400
    if not url and not (upload and upload.filename):
        return jsonify(error="Paste a media URL or choose a local file."),400
    j=uuid.uuid4().hex
    jobs[j]={"status":"queued","message":"Starting...","file":None,"filename":None}
    if upload and upload.filename:
        Thread(target=local_job,args=(j,upload,form,name),daemon=True).start()
    else:
        Thread(target=url_job,args=(j,url,form,name),daemon=True).start()
    return jsonify(job_id=j)

@app.route("/status/<j>")
def status(j):
    if j not in jobs: return jsonify(status="error",message="Job not found."),404
    x=jobs[j]; return jsonify(status=x["status"],message=x["message"],filename=x.get("filename"))

@app.route("/get/<j>")
def get(j):
    x=jobs.get(j)
    if not x or x["status"]!="ready": return jsonify(error="File is not ready."),404
    p=Path(x["file"])
    if not p.exists(): return jsonify(error="Generated file no longer exists."),404
    return send_file(p,as_attachment=True,download_name=x["filename"],mimetype="audio/mpeg")

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)))
