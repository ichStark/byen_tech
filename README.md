ByenTech JPG → PDF Converter
================================

Futuristic, production-grade JPG/PNG to merged PDF converter with a glassmorphism UI and a Python Flask backend.


Features
--------
- Upload multiple JPG/PNG/JPEG files
- Responsive, Notion-quality glassmorphism UI
- Drag & drop uploads with animated hover
- Live preview grid with hover zoom and delete
- Convert to a single merged PDF (auto page size per image)
- Instant download with success animation
- Flask API using Pillow + FPDF
- CORS enabled
- Production server via gunicorn


Project Structure
-----------------
- `frontend/`
  - `index.html` — UI markup
  - `style.css` — full styling, glassmorphism, animations
  - `script.js` — upload, preview, drag+drop, conversion, download
  - `assets/` — logo and SVG icons
- `backend/`
  - `app.py` — Flask app with `/convert` endpoint
  - `requirements.txt` — Flask/Pillow/FPDF/CORS/Gunicorn
  - `Procfile` — production start command
  - `uploads/` — temporary storage (auto-cleaned per request)


Local Development
-----------------
1) Backend (Python 3.10+ recommended)
```bash
cd backend
python -m venv .venv
.\.venv\Scripts\activate  # Windows
pip install -r requirements.txt
python app.py  # runs on http://localhost:5000
```

2) Frontend (static)

python -m http.server 5500 --bind 127.0.0.1



Frontend Deployment (Vercel)
----------------------------
1) Create a new Vercel project and select the `frontend/` folder.
2) No build step required (static site). Deploy.
3) Set custom domain, e.g., `https://byentech.xyz`.
4) Verify the app loads and the UI is accessible.


Backend Deployment (Render)
--------------------------
1) Create a new Web Service on Render from your repo.
2) Root directory: `backend/`
3) Build Command:
```bash
pip install -r requirements.txt
```
4) Start Command:
```bash
gunicorn app:app
```
5) Add custom domain, e.g., `https://api.byentech.xyz`.

6) CORS
The backend enables CORS for all origins by default. For production, you can restrict CORS to your frontend origin by configuring Flask-CORS:
```python
from flask_cors import CORS
CORS(app, resources={r"/*": {"origins": "https://byentech.xyz"}})
```


Connecting Frontend ↔ Backend
-----------------------------
1) Update the backend URL in `frontend/script.js`:
```javascript
const BACKEND_URL = "https://api.byentech.xyz"; // your Render domain
```
2) Ensure CORS is active on the backend (default in this project).
3) Test: upload images, convert, download.


Security & Limits
-----------------
- Allowed file types: JPG/JPEG/PNG
- Max files: 50 per request (configurable in `app.py`)
- Temporary files are removed after each request
- Images converted to RGB and normalized to JPEG for PDF merging


Notes on PDF Page Size
----------------------
This build uses auto page size per image: each PDF page matches the image dimensions (approx mm using DPI metadata or a sensible default). Images cover the full page, preserving aspect ratio.


Troubleshooting
---------------
- Mixed orientations look odd? That is expected with auto-per-image page sizes. You can change to A4/Letter in `app.py` by using a fixed format in `add_page`.
- If conversion fails, check server logs for Pillow/FPDF errors or invalid files.
- Large images: conversion uses JPEG 92 quality to balance size/quality.


License
-------
Copyright © ByenTech.
```  ```


