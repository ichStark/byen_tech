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


# Optional CORS restriction via env var, e.g.:
# ALLOWED_ORIGINS="https://byentech.xyz,https://www.byentech.xyz"
def _get_allowed_origins():
    raw = os.environ.get("ALLOWED_ORIGINS", "").strip()
    if not raw:
        return None
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return parts or None


def ensure_dirs() -> None:
    os.makedirs(UPLOAD_DIR, exist_ok=True)


def allowed_filename(filename: str) -> bool:
    name = filename.lower()
    return any(name.endswith(ext) for ext in ALLOWED_EXTENSIONS)


def px_to_mm(pixels: int, dpi: float) -> float:
    # Convert pixels to millimeters; 25.4 mm per inch
    return pixels * 25.4 / dpi


def mm_to_px(mm: float, dpi: float) -> int:
    # Convert millimeters to pixels
    return int(round(mm * dpi / 25.4))


def read_image_to_temp(file_storage, target_dir: str) -> Tuple[str, Tuple[int, int], float]:
    """
    Persist the uploaded image to a temporary file, normalize (auto-orient via EXIF)
    and convert to RGB JPEG to avoid FPDF format pitfalls on Windows.
    Returns (temp_jpeg_path, (width_px, height_px), dpi)
    """
    raw_name = f"{uuid.uuid4().hex}.upload"
    raw_path = os.path.join(target_dir, raw_name)
    file_storage.save(raw_path)
    try:
        with Image.open(raw_path) as img:
            # Try to preserve correct orientation
            img = ImageOps.exif_transpose(img)
            # Attempt to read DPI, default to 96 if missing
            dpi_info = img.info.get("dpi", (96, 96))
            dpi = float(dpi_info[0]) if isinstance(dpi_info, (tuple, list)) else float(dpi_info)
            if dpi <= 0:
                dpi = 96.0
            rgb = img.convert("RGB")
            width_px, height_px = rgb.size
            temp_name = f"{uuid.uuid4().hex}.jpg"
            temp_path = os.path.join(target_dir, temp_name)
            # Save at high quality to preserve detail for later scaling
            rgb.save(temp_path, format="JPEG", quality=95, subsampling=0, optimize=True, progressive=True)
            return temp_path, (width_px, height_px), dpi
    finally:
        try:
            if os.path.exists(raw_path):
                os.remove(raw_path)
        except Exception:
            pass


def _scale_to_fit(src_w: float, src_h: float, max_w: float, max_h: float) -> Tuple[float, float]:
    """Scale dimensions to fit within max bounds, preserving aspect ratio."""
    if src_w <= 0 or src_h <= 0:
        return 1.0, 1.0
    scale = min(max_w / src_w, max_h / src_h)
    return src_w * scale, src_h * scale


def create_pdf_with_auto_pages(image_entries: List[Tuple[str, Tuple[int, int], float]]) -> bytes:
    """
    Given a list of image entries (path, (w_px,h_px), dpi),
    create a PDF where each page matches the image's dimensions (in mm).
    """
    pdf = FPDF(unit="mm")
    for path, (w_px, h_px), dpi in image_entries:
        w_mm = max(1.0, px_to_mm(w_px, dpi))
        h_mm = max(1.0, px_to_mm(h_px, dpi))
        # Add page with image's size
        pdf.add_page(format=(w_mm, h_mm))
        # Place image covering full page
        # FPDF on Windows prefers forward slashes in paths
        safe_path = os.path.abspath(path).replace("\\", "/")
        pdf.image(safe_path, x=0, y=0, w=w_mm, h=h_mm)
    # Output as bytes
    pdf_bytes = pdf.output(dest="S").encode("latin1")
    return pdf_bytes


def create_pdf_with_pillow(paths: List[str]) -> bytes:
    """
    Fallback: Build the PDF using Pillow only.
    Each image becomes a page at its native size. This is very robust on Windows.
    """
    images: List[Image.Image] = []
    for p in paths:
        img = Image.open(p).convert("RGB")
        images.append(img)
    try:
        buf = io.BytesIO()
        if len(images) == 1:
            images[0].save(buf, format="PDF", resolution=96.0)
        else:
            first, rest = images[0], images[1:]
            first.save(buf, format="PDF", resolution=96.0, save_all=True, append_images=rest)
        buf.seek(0)
        return buf.read()
    finally:
        for im in images:
            try:
                im.close()
            except Exception:
                pass


def create_pdf_with_pillow_configured(
    image_entries: List[Tuple[str, Tuple[int, int], float]],
    fit_to_image: bool,
    orientation: str,
    margin_key: str,
    dpi: float = 300.0,
) -> bytes:
    """
    Build the PDF using Pillow honoring orientation, margins, and fit behavior.
    We render each page as a Pillow image (RGB) at the given DPI, then save as a multi-page PDF.
    """
    margin_lookup = {"none": 0.0, "small": 10.0, "big": 20.0}  # millimeters
    margin_mm = margin_lookup.get(margin_key, 0.0)
    margin_px = mm_to_px(margin_mm, dpi)

    # Determine uniform page sizing in pixels when multiple images and fit_to_image
    base_page_px: Tuple[int, int] = None
    if fit_to_image and len(image_entries) > 1:
        max_w_px = 1
        max_h_px = 1
        for _, (w_px, h_px), _ in image_entries:
            max_w_px = max(max_w_px, int(w_px))
            max_h_px = max(max_h_px, int(h_px))
        page_w_px, page_h_px = max_w_px, max_h_px
        if orientation == "landscape" and page_h_px > page_w_px:
            page_w_px, page_h_px = page_h_px, page_w_px
        if orientation == "portrait" and page_w_px > page_h_px:
            page_w_px, page_h_px = page_h_px, page_w_px
        base_page_px = (page_w_px, page_h_px)

    pages: List[Image.Image] = []
    for path, (w_px, h_px), src_dpi in image_entries:
        # Load and normalize
        with Image.open(path) as img:
            img = ImageOps.exif_transpose(img).convert("RGB")
            src_w, src_h = img.size

            if base_page_px:
                page_w_px, page_h_px = base_page_px
                max_w = max(1, page_w_px - 2 * margin_px)
                max_h = max(1, page_h_px - 2 * margin_px)
                scale = min(max_w / src_w, max_h / src_h)
                draw_w = int(round(src_w * scale))
                draw_h = int(round(src_h * scale))
                canvas = Image.new("RGB", (page_w_px, page_h_px), (255, 255, 255))
                img_resized = img if scale == 1.0 else img.resize((draw_w, draw_h), Image.LANCZOS)
                x = (page_w_px - draw_w) // 2
                y = (page_h_px - draw_h) // 2
                canvas.paste(img_resized, (x, y))
                pages.append(canvas)
            elif fit_to_image:
                # Page equals image size (rotate page according to orientation),
                # then apply margins by increasing page size and centering the image.
                page_w_px, page_h_px = src_w, src_h
                if orientation == "landscape" and page_h_px > page_w_px:
                    page_w_px, page_h_px = page_h_px, page_w_px
                if orientation == "portrait" and page_w_px > page_h_px:
                    page_w_px, page_h_px = page_h_px, page_w_px

                # Target drawable area
                max_w = max(1, page_w_px - 2 * margin_px)
                max_h = max(1, page_h_px - 2 * margin_px)
                # Scale to fit drawable area
                scale = min(max_w / src_w, max_h / src_h)
                draw_w = int(round(src_w * scale))
                draw_h = int(round(src_h * scale))

                canvas = Image.new("RGB", (page_w_px, page_h_px), (255, 255, 255))
                img_resized = img if scale == 1.0 else img.resize((draw_w, draw_h), Image.LANCZOS)
                x = (page_w_px - draw_w) // 2
                y = (page_h_px - draw_h) // 2
                canvas.paste(img_resized, (x, y))
                pages.append(canvas)
            else:
                # Fixed A4 page in requested orientation at target DPI
                page_mm = MM_A4_LANDSCAPE if orientation == "landscape" else MM_A4_PORTRAIT
                page_w_px = mm_to_px(page_mm[0], dpi)
                page_h_px = mm_to_px(page_mm[1], dpi)
                max_w = max(1, page_w_px - 2 * margin_px)
                max_h = max(1, page_h_px - 2 * margin_px)
                scale = min(max_w / src_w, max_h / src_h)
                draw_w = int(round(src_w * scale))
                draw_h = int(round(src_h * scale))
                canvas = Image.new("RGB", (page_w_px, page_h_px), (255, 255, 255))
                img_resized = img if scale == 1.0 else img.resize((draw_w, draw_h), Image.LANCZOS)
                x = (page_w_px - draw_w) // 2
                y = (page_h_px - draw_h) // 2
                canvas.paste(img_resized, (x, y))
                pages.append(canvas)

    try:
        buf = io.BytesIO()
        if len(pages) == 1:
            pages[0].save(buf, format="PDF", resolution=dpi)
        else:
            first, rest = pages[0], pages[1:]
            first.save(buf, format="PDF", resolution=dpi, save_all=True, append_images=rest)
        buf.seek(0)
        return buf.read()
    finally:
        for p in pages:
            try:
                p.close()
            except Exception:
                pass


def create_pdf_configured(
    image_entries: List[Tuple[str, Tuple[int, int], float]],
    fit_to_image: bool,
    orientation: str,
    margin_key: str,
) -> bytes:
    """
    Create a PDF honoring:
    - fit_to_image: if True, page size matches the image (rotated to orientation)
    - orientation: 'portrait' or 'landscape'
    - margin_key: 'none' | 'small' | 'big'
    """
    margin_lookup = {"none": 0.0, "small": 10.0, "big": 20.0}
    margin = margin_lookup.get(margin_key, 0.0)
    pdf = FPDF(unit="mm")

    # Uniform page sizing when multiple images are uploaded and fit_to_image is requested.
    # We pick a common page size large enough to contain all images, then scale each image to fit.
    uniform_page: Tuple[float, float] = None
    if fit_to_image and len(image_entries) > 1:
        max_w_mm = 1.0
        max_h_mm = 1.0
        for _, (w_px, h_px), dpi in image_entries:
            max_w_mm = max(max_w_mm, px_to_mm(w_px, dpi))
            max_h_mm = max(max_h_mm, px_to_mm(h_px, dpi))
        page_w, page_h = max_w_mm, max_h_mm
        if orientation == "landscape" and page_h > page_w:
            page_w, page_h = page_h, page_w
        if orientation == "portrait" and page_w > page_h:
            page_w, page_h = page_h, page_w
        uniform_page = (page_w, page_h)

    for path, (w_px, h_px), dpi in image_entries:
        img_w_mm = max(1.0, px_to_mm(w_px, dpi))
        img_h_mm = max(1.0, px_to_mm(h_px, dpi))

        if uniform_page:
            page_w, page_h = uniform_page
        elif fit_to_image:
            # Base page on image size, but honor requested orientation by swapping
            page_w, page_h = img_w_mm, img_h_mm
            if orientation == "landscape" and page_h > page_w:
                page_w, page_h = page_h, page_w
            if orientation == "portrait" and page_w > page_h:
                page_w, page_h = page_h, page_w
        else:
            page_w, page_h = (MM_A4_PORTRAIT if orientation != "landscape" else MM_A4_LANDSCAPE)

        # Compute drawable area and scaled image size
        max_w = max(1.0, page_w - 2 * margin)
        max_h = max(1.0, page_h - 2 * margin)
        draw_w, draw_h = _scale_to_fit(img_w_mm, img_h_mm, max_w, max_h)
        x = (page_w - draw_w) / 2.0
        y = (page_h - draw_h) / 2.0

        pdf.add_page(format=(page_w, page_h))
        safe_path = os.path.abspath(path).replace("\\", "/")
        pdf.image(safe_path, x=x, y=y, w=draw_w, h=draw_h)

    return pdf.output(dest="S").encode("latin1")


def cleanup_files(paths: List[str]) -> None:
    for p in paths:
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            # Best-effort cleanup
            pass


def create_app() -> Flask:
    ensure_dirs()
    app = Flask(__name__)
    allowed_origins = _get_allowed_origins()
    if allowed_origins:
        CORS(app, resources={r"/*": {"origins": allowed_origins}})
    else:
        CORS(app)  # default: allow all (good for local dev)

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok"}), 200

    @app.route("/convert", methods=["POST"])
    def convert():
        """
        Accepts multipart/form-data with repeated 'files' fields containing images.
        Returns a merged PDF where each page matches the image size (auto per image).
        """
        if "files" not in request.files:
            return jsonify({"error": "No files provided. Use field name 'files'."}), 400

        files = request.files.getlist("files")
        if not files:
            return jsonify({"error": "Empty file list."}), 400

        if len(files) > 50:
            return jsonify({"error": "Too many files. Max 50."}), 400

        # Read options
        orientation = (request.form.get("orientation") or "portrait").lower()
        if orientation not in ("portrait", "landscape"):
            orientation = "portrait"
        fit_to_image = (request.form.get("fit") or "true").lower() == "true"
        margin_key = (request.form.get("margin") or "none").lower()

        temp_paths: List[str] = []
        image_entries: List[Tuple[str, Tuple[int, int], float]] = []
        try:
            for f in files:
                if not f or not f.filename:
                    continue
                if not allowed_filename(f.filename):
                    return jsonify({"error": f"Unsupported file type: {f.filename}"}), 400
                temp_path, size_px, dpi = read_image_to_temp(f, UPLOAD_DIR)
                temp_paths.append(temp_path)
                image_entries.append((temp_path, size_px, dpi))

            if not image_entries:
                return jsonify({"error": "No valid images provided."}), 400

            # Try FPDF first; if it fails (e.g., environment-specific issue), fallback to Pillow-only PDF
            try:
                pdf_bytes = create_pdf_configured(
                    image_entries=image_entries,
                    fit_to_image=fit_to_image,
                    orientation=orientation,
                    margin_key=margin_key,
                )
            except Exception:
                # Fallback path using Pillow (also honors options)
                pdf_bytes = create_pdf_with_pillow_configured(
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
                download_name="byentech-merged.pdf",
            )
        except Exception as e:
            # Return error detail to help diagnose locally; keep generic in production
            return jsonify({"error": f"Failed to convert images: {str(e)}"}), 500
        finally:
            cleanup_files(temp_paths)

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)


