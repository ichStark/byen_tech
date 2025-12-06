// ByenTech JPG → PDF Converter - Frontend Logic
// Futuristic Simplicity: modular, readable, production-ready vanilla JS

(() => {
  "use strict";

  // Backend URL: set to your Render URL in production, e.g., https://api.byentech.xyz
  const BACKEND_URL = (typeof window !== "undefined" && window.BYENTECH_BACKEND_URL) || "http://localhost:5000";

  // State
  const imageItems = []; // { id, file, url, key }
  let pdfBlobUrl = null;

  // DOM
  const fileInput = document.getElementById("file-input");
  const dropzone = document.getElementById("dropzone");
  const selectBtn = document.getElementById("select-files-btn");
  const previewGrid = document.getElementById("preview-grid");
  const fileCountEl = document.getElementById("file-count");
  const optionsCard = document.getElementById("options-card");
  const btnPortrait = document.getElementById("opt-portrait");
  const btnLandscape = document.getElementById("opt-landscape");
  const chkFit = document.getElementById("opt-fit");
  const btnMarginNone = document.getElementById("margin-none");
  const btnMarginSmall = document.getElementById("margin-small");
  const btnMarginBig = document.getElementById("margin-big");
  const convertBtn = document.getElementById("convert-btn");
  const loader = document.getElementById("loader");
  const success = document.getElementById("success");
  const downloadBtn = document.getElementById("download-btn");
  const progress = document.getElementById("progress");
  const notif = document.getElementById("notif");
  const yearEl = document.getElementById("year");
  const themeToggle = document.getElementById("theme-toggle");

  if (yearEl) {
    yearEl.textContent = new Date().getFullYear().toString();
  }

  // Utilities
  const uid = () => (crypto && crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}_${Math.random().toString(16).slice(2)}`);
  const fileKey = (f) => `${f.name}_${f.size}`;
  const isImage = (f) => /^image\/(png|jpg|jpeg)$/i.test(f.type) || /\.(png|jpg|jpeg)$/i.test(f.name);

  // Option state
  const options = {
    orientation: "landscape", // default matches UI button state
    fitToImage: false,        // switch is unchecked by default
    margin: "none",           // default matches UI button state
  };

  // Ensure JS options mirror the actual initial UI state on load
  (function syncOptionsFromUI() {
    if (btnLandscape && btnLandscape.classList.contains("is-active")) {
      options.orientation = "landscape";
    } else if (btnPortrait && btnPortrait.classList.contains("is-active")) {
      options.orientation = "portrait";
    }

    if (typeof chkFit?.checked === "boolean") {
      options.fitToImage = !!chkFit.checked;
    }

    if (btnMarginNone && btnMarginNone.classList.contains("is-active")) {
      options.margin = "none";
    } else if (btnMarginSmall && btnMarginSmall.classList.contains("is-active")) {
      options.margin = "small";
    } else if (btnMarginBig && btnMarginBig.classList.contains("is-active")) {
      options.margin = "big";
    }
  })();

  function setSegmentedActive(groupButtons, activeButton) {
    groupButtons.forEach((b) => b.classList.remove("is-active"));
    activeButton.classList.add("is-active");
  }

  function showNotif(message, type = "info") {
    if (!notif) return;
    notif.textContent = message || "";
    notif.style.color = type === "error" ? "#b91c1c" : "#475569";
  }

  function setLoading(isLoading) {
    if (isLoading) {
      convertBtn.classList.add("loading");
      loader.style.display = "inline-block";
      success.style.display = "none";
      convertBtn.disabled = true;
      if (progress) progress.classList.add("loading");
    } else {
      convertBtn.classList.remove("loading");
      loader.style.display = "none";
      if (progress) progress.classList.remove("loading");
    }
  }

  function setSuccessReady(blobUrl) {
    pdfBlobUrl = blobUrl;
    success.style.display = "block";
    downloadBtn.hidden = false;
  }

  function updateCTAState() {
    convertBtn.disabled = imageItems.length === 0;
  }

  function addFiles(files) {
    const added = [];
    for (const file of files) {
      if (!isImage(file)) {
        showNotif("Only JPG, JPEG, or PNG files are supported.", "error");
        continue;
      }
      const key = fileKey(file);
      if (imageItems.some((x) => x.key === key)) {
        continue; // dedupe by name+size
      }
      const url = URL.createObjectURL(file);
      imageItems.push({ id: uid(), file, url, key });
      added.push(file.name);
    }
    if (added.length) {
      showNotif(`${added.length} image(s) added.`);
    }
    renderPreviews();
    updateCTAState();
  }

  function removeItem(id) {
    const idx = imageItems.findIndex((x) => x.id === id);
    if (idx >= 0) {
      try { URL.revokeObjectURL(imageItems[idx].url); } catch {}
      imageItems.splice(idx, 1);
      renderPreviews();
      updateCTAState();
    }
  }

  function clearPdfUrl() {
    if (pdfBlobUrl) {
      try { URL.revokeObjectURL(pdfBlobUrl); } catch {}
      pdfBlobUrl = null;
    }
    downloadBtn.hidden = true;
    success.style.display = "none";
  }

  function renderPreviews() {
    clearPdfUrl();
    previewGrid.innerHTML = "";
    if (imageItems.length === 0) {
      if (optionsCard) optionsCard.hidden = true;
      if (fileCountEl) fileCountEl.textContent = "0";
      return;
    }
    if (optionsCard) optionsCard.hidden = false;
    if (fileCountEl) fileCountEl.textContent = String(imageItems.length);
    const fragment = document.createDocumentFragment();
    for (const item of imageItems) {
      const card = document.createElement("div");
      card.className = "preview-item enter";

      const img = document.createElement("img");
      img.src = item.url;
      img.alt = item.file.name;
      img.className = "preview-img";

      const removeBtn = document.createElement("button");
      removeBtn.className = "preview-remove";
      removeBtn.type = "button";
      removeBtn.title = "Remove image";
      removeBtn.addEventListener("click", () => removeItem(item.id));
      const icon = document.createElement("img");
      icon.src = "./assets/icons/delete.svg";
      icon.alt = "";
      removeBtn.appendChild(icon);

      card.appendChild(img);
      card.appendChild(removeBtn);
      fragment.appendChild(card);
    }
    previewGrid.appendChild(fragment);
  }

  // Drag & drop
  function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
  }
  ["dragenter", "dragover", "dragleave", "drop"].forEach((ev) => {
    dropzone.addEventListener(ev, preventDefaults, false);
  });
  ["dragenter", "dragover"].forEach((ev) => {
    dropzone.addEventListener(ev, () => dropzone.classList.add("is-drag"), false);
  });
  ["dragleave", "drop"].forEach((ev) => {
    dropzone.addEventListener(ev, () => dropzone.classList.remove("is-drag"), false);
  });
  dropzone.addEventListener("drop", (e) => {
    const dt = e.dataTransfer;
    if (!dt) return;
    const files = dt.files ? Array.from(dt.files) : [];
    addFiles(files);
  });

  // File input
  selectBtn.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", (e) => {
    const files = e.target.files ? Array.from(e.target.files) : [];
    addFiles(files);
    fileInput.value = "";
  });

  // Option handlers
  if (btnPortrait && btnLandscape) {
    btnPortrait.addEventListener("click", () => {
      options.orientation = "portrait";
      setSegmentedActive([btnPortrait, btnLandscape], btnPortrait);
    });
    btnLandscape.addEventListener("click", () => {
      options.orientation = "landscape";
      setSegmentedActive([btnPortrait, btnLandscape], btnLandscape);
    });
  }
  if (chkFit) {
    chkFit.addEventListener("change", () => {
      options.fitToImage = !!chkFit.checked;
    });
  }
  if (btnMarginNone && btnMarginSmall && btnMarginBig) {
    btnMarginNone.addEventListener("click", () => {
      options.margin = "none";
      setSegmentedActive([btnMarginNone, btnMarginSmall, btnMarginBig], btnMarginNone);
    });
    btnMarginSmall.addEventListener("click", () => {
      options.margin = "small";
      setSegmentedActive([btnMarginNone, btnMarginSmall, btnMarginBig], btnMarginSmall);
    });
    btnMarginBig.addEventListener("click", () => {
      options.margin = "big";
      setSegmentedActive([btnMarginNone, btnMarginSmall, btnMarginBig], btnMarginBig);
    });
  }

  // Convert
  convertBtn.addEventListener("click", async () => {
    if (imageItems.length === 0) return;
    setLoading(true);
    showNotif("Converting images to PDF...");
    try {
      const formData = new FormData();
      for (const item of imageItems) {
        formData.append("files", item.file, item.file.name);
      }
      formData.append("orientation", options.orientation);
      formData.append("fit", String(options.fitToImage));
      formData.append("margin", options.margin);
      const resp = await fetch(`${BACKEND_URL}/convert`, {
        method: "POST",
        body: formData,
      });
      if (!resp.ok) {
        const text = await resp.text().catch(() => "");
        throw new Error(text || "Conversion failed");
      }
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      // Do not auto-download; show Download button
      setSuccessReady(url);
      showNotif("Success! Your PDF has been generated.");
    } catch (err) {
      console.error(err);
      showNotif("Error: Unable to convert images. Please try again.", "error");
    } finally {
      setLoading(false);
      updateCTAState();
    }
  });

  downloadBtn.addEventListener("click", () => {
    if (!pdfBlobUrl) return;
    const a = document.createElement("a");
    a.href = pdfBlobUrl;
    a.download = "byentech-merged.pdf";
    document.body.appendChild(a);
    a.click();
    a.remove();
  });

  // Theme toggle
  const root = document.documentElement;
  const savedTheme = localStorage.getItem("byentech_theme");
  if (savedTheme === "dark" || (!savedTheme && window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches)) {
    root.setAttribute("data-theme", "dark");
  }
  if (themeToggle) {
    themeToggle.addEventListener("click", () => {
      const isDark = root.getAttribute("data-theme") === "dark";
      if (isDark) {
        root.removeAttribute("data-theme");
        localStorage.setItem("byentech_theme", "light");
      } else {
        root.setAttribute("data-theme", "dark");
        localStorage.setItem("byentech_theme", "dark");
      }
    });
  }
})();


