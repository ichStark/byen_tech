import io
import os
import uuid

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from PIL import Image, ImageOps

# ---------------- CONFIG ----------------
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}


# ---------------- HELPERS ----------------
def ensure_dirs():
    os.makedirs(UPLOAD_DIR, exist_ok=True)


def allowed_filename(filename: str) -> bool:
    name = filename.lower()
    return any(name.endswith(ext) for ext in ALLOWED_EXTENSIONS)


def _get_allowed_origins():
    raw = os.environ.get("ALLOWED_ORIGINS", "").strip()
    if not raw:
        return None
    return [p.strip() for p in raw.split(",") if p.strip()]


def read_image_to_temp(file_storage, target_dir):
    """
    Save uploaded image, normalize orientation, convert to RGB JPG
    """
    raw_path = os.path.join(target_dir, f"{uuid.uuid4().hex}.upload")
    file_storage.save(raw_path)

    try:
        with Image.open(raw_path) as img:
            img = ImageOps.exif_transpose(img)
            rgb = img.convert("RGB")

            temp_jpg = os.path.join(target_dir, f"{uuid.uuid4().hex}.jpg")
            rgb.save(temp_jpg, "JPEG", quality=95)

            return temp_jpg
    finally:
        if os.path.exists(raw_path):
            os.remove(raw_path)


def cleanup(paths):
    for p in paths:
        if os.path.exists(p):
            os.remove(p)


def create_pdf(image_paths):
    """
    Create a single PDF from images using Pillow (RENDER-SAFE)
    """
    pil_images = [Image.open(p).convert("RGB") for p in image_paths]

    buf = io.BytesIO()
    pil_images[0].save(
        buf,
        format="PDF",
        save_all=True,
        append_images=pil_images[1:]
    )
    buf.seek(0)
    return buf.read()


# ---------------- APP ----------------
def create_app():
    ensure_dirs()
    app = Flask(__name__)

    # ---------- CORS ----------
    allowed = _get_allowed_origins()
    if allowed:
        CORS(app, resources={"/*": {"origins": allowed}}, supports_credentials=True)
    else:
        CORS(app, supports_credentials=True)

    # ---------- ROUTES ----------
    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok"}), 200

    @app.route("/convert", methods=["OPTIONS"])
    def convert_options():
        return jsonify({"ok": True}), 200

    @app.route("/convert", methods=["POST"])
    def convert():
        if "files" not in request.files:
            return jsonify({"error": "No files provided"}), 400

        files = request.files.getlist("files")
        if not files:
            return jsonify({"error": "Empty file list"}), 400

        temp_paths = []

        try:
            for f in files:
                if not allowed_filename(f.filename):
                    return jsonify({"error": f"Unsupported file: {f.filename}"}), 400

                temp_path = read_image_to_temp(f, UPLOAD_DIR)
                temp_paths.append(temp_path)

            pdf_bytes = create_pdf(temp_paths)

            return send_file(
                io.BytesIO(pdf_bytes),
                mimetype="application/pdf",
                as_attachment=True,
                download_name="byentech-merged.pdf"
            )

        except Exception as e:
            return jsonify({"error": f"Failed to convert images: {str(e)}"}), 500

        finally:
            cleanup(temp_paths)

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
