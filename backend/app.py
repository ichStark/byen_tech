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
    return any(filename.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS)


def px_to_mm(pixels: int, dpi: float) -> float:
    return pixels * 25.4 / dpi


def read_image_to_temp(file_storage, target_dir):
    raw_name = f"{uuid.uuid4().hex}.upload"
    raw_path = os.path.join(target_dir, raw_name)
    file_storage.save(raw_path)

    try:
        with Image.open(raw_path) as img:
            img = ImageOps.exif_transpose(img)
            dpi_info = img.info.get("dpi", (96, 96))
            dpi = float(dpi_info[0])
            if dpi <= 0:
                dpi = 96

            rgb = img.convert("RGB")
            width_px, height_px = rgb.size

            temp_path = os.path.join(target_dir, f"{uuid.uuid4().hex}.jpg")
            rgb.save(temp_path, "JPEG", quality=95)
            return temp_path, (width_px, height_px), dpi

    finally:
        if os.path.exists(raw_path):
            os.remove(raw_path)


def _scale_to_fit(src_w, src_h, max_w, max_h):
    scale = min(max_w / src_w, max_h / src_h)
    return src_w * scale, src_h * scale


def create_pdf_configured(image_entries, fit_to_image, orientation, margin_key):
    margin_lookup = {"none": 0, "small": 10, "big": 20}
    margin = margin_lookup.get(margin_key, 0)

    pdf = FPDF(unit="mm")
    pdf.set_auto_page_break(0)

    for path, (w_px, h_px), dpi in image_entries:
        img_w_mm = px_to_mm(w_px, dpi)
        img_h_mm = px_to_mm(h_px, dpi)

        if not fit_to_image:
            page_w, page_h = (MM_A4_LANDSCAPE if orientation == "landscape" else MM_A4_PORTRAIT)
        else:
            page_w, page_h = img_w_mm, img_h_mm

        max_w = max(1, page_w - 2 * margin)
        max_h = max(1, page_h - 2 * margin)

        draw_w, draw_h = _scale_to_fit(img_w_mm, img_h_mm, max_w, max_h)
        x = (page_w - draw_w) / 2
        y = (page_h - draw_h) / 2

        # FIXED: page format must be set during construction
        pdf_w = page_w
        pdf_h = page_h
        page_pdf = FPDF(unit="mm", format=(pdf_w, pdf_h))
        page_pdf.add_page()

        safe = os.path.abspath(path).replace("\\", "/")
        page_pdf.image(safe, x=x, y=y, w=draw_w, h=draw_h)

        # Append this page into main PDF
        pdf.pages.append(page_pdf.pages[1])

    return pdf.output(dest="S").encode("latin1")


def cleanup_files(paths):
    for p in paths:
        if os.path.exists(p):
            os.remove(p)


def create_app():
    ensure_dirs()
    app = Flask(__name__)

    allowed = _get_allowed_origins()
    if allowed:
        CORS(app, resources={r"/*": {"origins": allowed}}, supports_credentials=True)
    else:
        CORS(app, supports_credentials=True)

    @app.route("/health")
    def health():
        return jsonify({"status": "ok"}), 200

    @app.route("/convert", methods=["OPTIONS"])
    def opt():
        return jsonify({"status": "ok"}), 200

    @app.route("/convert", methods=["POST"])
    def convert():
        if "files" not in request.files:
            return jsonify({"error": "No files"}), 400

        files = request.files.getlist("files")
        orientation = request.form.get("orientation", "portrait").lower()
        fit_to_image = request.form.get("fit", "true").lower() == "true"
        margin_key = request.form.get("margin", "none").lower()

        temp_paths = []
        img_entries = []

        try:
            for f in files:
                if not allowed_filename(f.filename):
                    return jsonify({"error": "Invalid file"}), 400

                temp, size, dpi = read_image_to_temp(f, UPLOAD_DIR)
                temp_paths.append(temp)
                img_entries.append((temp, size, dpi))

            pdf_bytes = create_pdf_configured(img_entries, fit_to_image, orientation, margin_key)

            buf = io.BytesIO(pdf_bytes)
            buf.seek(0)
            return send_file(buf, mimetype="application/pdf", download_name="byentech.pdf", as_attachment=True)

        except Exception as e:
            return jsonify({"error": f"{str(e)}"}), 500

        finally:
            cleanup_files(temp_paths)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
