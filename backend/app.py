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


# ENV — allowed origins for production
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


def px_to_mm(pixels: int, dpi: float) -> float:
    return pixels * 25.4 / dpi


def mm_to_px(mm: float, dpi: float) -> int:
    return int(round(mm * dpi / 25.4))


def read_image_to_temp(file_storage, target_dir) -> Tuple[str, Tuple[int, int], float]:
    """Save uploaded image → normalize → convert → temp jpeg."""
    raw_name = f"{uuid.uuid4().hex}.upload"
    raw_path = os.path.join(target_dir, raw_name)
    file_storage.save(raw_path)

    try:
        with Image.open(raw_path) as img:
            img = ImageOps.exif_transpose(img)
            dpi_info = img.info.get("dpi", (96, 96))
            dpi = float(dpi_info[0]) if isinstance(dpi_info, (tuple, list)) else float(dpi_info)
            if dpi <= 0:
                dpi = 96.0

            rgb = img.convert("RGB")
            width_px, height_px = rgb.size

            temp_path = os.path.join(target_dir, f"{uuid.uuid4().hex}.jpg")
            rgb.save(temp_path, format="JPEG", quality=95, subsampling=0)
            return temp_path, (width_px, height_px), dpi

    finally:
        if os.path.exists(raw_path):
            os.remove(raw_path)


def _scale_to_fit(src_w: float, src_h: float, max_w: float, max_h: float):
    if src_w <= 0 or src_h <= 0:
        return 1.0, 1.0
    scale = min(max_w / src_w, max_h / src_h)
    return src_w * scale, src_h * scale


def create_pdf_configured(image_entries, fit_to_image, orientation, margin_key):
    """Create PDF respecting orientation + margin + fit options."""
    margin_lookup = {"none": 0.0, "small": 10.0, "big": 20.0}
    margin = margin_lookup.get(margin_key, 0.0)

    pdf = FPDF(unit="mm")

    # Multi-image auto-size (fit mode)
    uniform_page = None
    if fit_to_image and len(image_entries) > 1:
        max_w_mm = max(px_to_mm(w, dpi) for _, (w, h), dpi in image_entries)
        max_h_mm = max(px_to_mm(h, dpi) for _, (w, h), dpi in image_entries)

        page_w, page_h = max_w_mm, max_h_mm
        if orientation == "landscape" and page_h > page_w:
            page_w, page_h = page_h, page_w
        if orientation == "portrait" and page_w > page_h:
            page_w, page_h = page_h, page_w

        uniform_page = (page_w, page_h)

    # Begin adding pages
    for path, (w_px, h_px), dpi in image_entries:
        img_w_mm = px_to_mm(w_px, dpi)
        img_h_mm = px_to_mm(h_px, dpi)

        if uniform_page:
            page_w, page_h = uniform_page

        elif fit_to_image:
            page_w, page_h = img_w_mm, img_h_mm
            if orientation == "landscape" and page_h > page_w:
                page_w, page_h = page_h, page_w
            if orientation == "portrait" and page_w > page_h:
                page_w, page_h = page_h, page_w

        else:
            page_w, page_h = (MM_A4_LANDSCAPE if orientation == "landscape" else MM_A4_PORTRAIT)

        max_w = max(1.0, page_w - 2 * margin)
        max_h = max(1.0, page_h - 2 * margin)

        draw_w, draw_h = _scale_to_fit(img_w_mm, img_h_mm, max_w, max_h)
        x = (page_w - draw_w) / 2
        y = (page_h - draw_h) / 2

        pdf.add_page(format=(page_w, page_h))
        safe_path = os.path.abspath(path).replace("\\", "/")
        pdf.image(safe_path, x=x, y=y, w=draw_w, h=draw_h)

    return pdf.output(dest="S").encode("latin1")


def cleanup_files(paths):
    for p in paths:
        if os.path.exists(p):
            os.remove(p)


def create_app():
    ensure_dirs()
    app = Flask(__name__)

    # ---------- FIXED CORS FOR RENDER ----------
    allowed_origins = _get_allowed_origins()
    if allowed_origins:
        CORS(app, resources={r"/*": {
            "origins": allowed_origins,
            "methods": ["GET", "POST", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"],
            "supports_credentials": True
        }})
    else:
        CORS(app, supports_credentials=True)

    # ---------- ROUTES ----------
    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok"}), 200

    # OPTIONS handler (IMPORTANT for CORS)
    @app.route("/convert", methods=["OPTIONS"])
    def convert_options():
        return jsonify({"status": "ok"}), 200

    @app.route("/convert", methods=["POST"])
    def convert():
        if "files" not in request.files:
            return jsonify({"error": "No files provided"}), 400

        files = request.files.getlist("files")
        if not files:
            return jsonify({"error": "Empty file list"}), 400

        if len(files) > 50:
            return jsonify({"error": "Too many files (max 50)"}), 400

        # Read frontend options
        orientation = (request.form.get("orientation") or "portrait").lower()
        if orientation not in ("portrait", "landscape"):
            orientation = "portrait"

        fit_to_image = (request.form.get("fit") or "true").lower() == "true"
        margin_key = (request.form.get("margin") or "none").lower()

        temp_paths = []
        image_entries = []

        try:
            for f in files:
                if not allowed_filename(f.filename):
                    return jsonify({"error": f"Unsupported file: {f.filename}"}), 400

                temp_path, size_px, dpi = read_image_to_temp(f, UPLOAD_DIR)
                temp_paths.append(temp_path)
                image_entries.append((temp_path, size_px, dpi))

            if not image_entries:
                return jsonify({"error": "No valid images"}), 400

            pdf_bytes = create_pdf_configured(
                image_entries=image_entries,
                fit_to_image=fit_to_image,
                orientation=orientation,
                margin_key=margin_key,
            )

            buf = io.BytesIO(pdf_bytes)
            buf.seek(0)
            return send_file(
                buf,
                mimetype="application/pdf",
                as_attachment=True,
                download_name="byentech-merged.pdf"
            )

        except Exception as e:
            return jsonify({"error": f"Failed to convert images: {str(e)}"}), 500

        finally:
            cleanup_files(temp_paths)

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
