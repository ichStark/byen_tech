import io
import os
import uuid
from typing import List, Tuple

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from PIL import Image, ImageOps
from fpdf import FPDF

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}

MM_A4_PORTRAIT = (210.0, 297.0)
MM_A4_LANDSCAPE = (297.0, 210.0)


def _get_allowed_origins():
    raw = os.environ.get("ALLOWED_ORIGINS", "").strip()
    if not raw:
        return None
    return [p.strip() for p in raw.split(",") if p.strip()]


def ensure_dirs():
    os.makedirs(UPLOAD_DIR, exist_ok=True)


def allowed_filename(filename: str) -> bool:
    name = filename.lower()
    return any(name.endswith(ext) for ext in ALLOWED_EXTENSIONS)


def px_to_mm(px, dpi):
    return px * 25.4 / dpi


def read_image_to_temp(file_storage, target_dir):
    tmp_raw = os.path.join(target_dir, f"{uuid.uuid4().hex}.upload")
    file_storage.save(tmp_raw)

    try:
        with Image.open(tmp_raw) as img:
            img = ImageOps.exif_transpose(img)
            dpi_data = img.info.get("dpi", (96, 96))
            dpi = float(dpi_data[0]) if isinstance(dpi_data, (tuple, list)) else 96.0

            rgb = img.convert("RGB")
            temp_jpg = os.path.join(target_dir, f"{uuid.uuid4().hex}.jpg")
            rgb.save(temp_jpg, "JPEG", quality=95)

            return temp_jpg, rgb.size, dpi

    finally:
        if os.path.exists(tmp_raw):
            os.remove(tmp_raw)


def scale_to_fit(w, h, max_w, max_h):
    scale = min(max_w / w, max_h / h)
    return w * scale, h * scale


def create_pdf(images, fit, orientation, margin_key):
    margins = {"none": 0, "small": 10, "big": 20}
    margin = margins.get(margin_key, 0)

    pdf = FPDF(unit="mm")

    for path, (w_px, h_px), dpi in images:
        w_mm = px_to_mm(w_px, dpi)
        h_mm = px_to_mm(h_px, dpi)

        if fit:
            page_w, page_h = w_mm, h_mm
        else:
            page_w, page_h = (MM_A4_LANDSCAPE if orientation == "landscape" else MM_A4_PORTRAIT)

        max_w = page_w - 2 * margin
        max_h = page_h - 2 * margin
        draw_w, draw_h = scale_to_fit(w_mm, h_mm, max_w, max_h)

        x = (page_w - draw_w) / 2
        y = (page_h - draw_h) / 2

        # IMPORTANT → CORRECT FORMAT
        pdf.add_page(format=(page_w, page_h))

        pdf.image(path, x=x, y=y, w=draw_w, h=draw_h)

    return pdf.output(dest="S").encode("latin1")


def cleanup(paths):
    for p in paths:
        if os.path.exists(p):
            os.remove(p)


def create_app():
    ensure_dirs()
    app = Flask(__name__)

    allowed = _get_allowed_origins()
    if allowed:
        CORS(app, resources={"/*": {"origins": allowed}}, supports_credentials=True)
    else:
        CORS(app, supports_credentials=True)

    @app.route("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.route("/convert", methods=["OPTIONS"])
    def opt():
        return jsonify({"ok": True})

    @app.route("/convert", methods=["POST"])
    def convert():
        if "files" not in request.files:
            return jsonify({"error": "No files"}), 400

        files = request.files.getlist("files")
        if not files:
            return jsonify({"error": "No files"}), 400

        orientation = request.form.get("orientation", "portrait")
        fit = request.form.get("fit", "false").lower() == "true"
        margin = request.form.get("margin", "none")

        temp = []
        imgs = []

        try:
            for f in files:
                p, size, dpi = read_image_to_temp(f, UPLOAD_DIR)
                temp.append(p)
                imgs.append((p, size, dpi))

            pdf_bytes = create_pdf(imgs, fit, orientation, margin)
            buf = io.BytesIO(pdf_bytes)
            buf.seek(0)

            return send_file(buf, mimetype="application/pdf", as_attachment=True,
                             download_name="byentech-merged.pdf")

        except Exception as e:
            return jsonify({"error": str(e)}), 500

        finally:
            cleanup(temp)

    return app


app = create_app()
