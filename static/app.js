(() => {
  "use strict";

  // ---------------------------------------------------------------------
  // Theme toggle
  // ---------------------------------------------------------------------
  const root = document.documentElement;
  const themeToggle = document.getElementById("themeToggle");
  const themeIcon = document.getElementById("themeIcon");

  function applyTheme(theme) {
    root.setAttribute("data-theme", theme);
    themeIcon.textContent = theme === "dark" ? "☀️" : "🌙";
  }

  const savedTheme = localStorage.getItem("spd-theme");
  if (savedTheme) {
    applyTheme(savedTheme);
  } else {
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    applyTheme(prefersDark ? "dark" : "light");
  }

  themeToggle.addEventListener("click", () => {
    const current = root.getAttribute("data-theme") === "dark" ? "dark" : "light";
    const next = current === "dark" ? "light" : "dark";
    applyTheme(next);
    localStorage.setItem("spd-theme", next);
  });

  // ---------------------------------------------------------------------
  // Uzbek labels for arbitrary dataset class names (mirrors config.py)
  // ---------------------------------------------------------------------
  const UZ_LABELS = {
    "clean": "Toza",
    "dusty": "Changlangan",
    "dust": "Changlangan",
    "bird-drop": "Qush go'ng'i",
    "bird-droppings": "Qush go'ng'i",
    "physical-damage": "Jismoniy shikast",
    "electrical-damage": "Elektr shikast",
    "snow-covered": "Qor bosgan",
  };

  function normalizeKey(name) {
    return name.trim().toLowerCase().replace(/\s+/g, "-").replace(/_/g, "-");
  }

  function uzLabel(className) {
    return UZ_LABELS[normalizeKey(className)] || className;
  }

  // ---------------------------------------------------------------------
  // Dropzone / file input
  // ---------------------------------------------------------------------
  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("fileInput");
  const resultsGrid = document.getElementById("resultsGrid");
  const clearResultsBtn = document.getElementById("clearResultsBtn");
  const cardTemplate = document.getElementById("resultCardTemplate");
  const historyBody = document.getElementById("historyBody");

  let historyCounter = 0;

  dropzone.addEventListener("click", () => fileInput.click());

  dropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  });

  dropzone.addEventListener("dragleave", () => {
    dropzone.classList.remove("dragover");
  });

  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
    if (e.dataTransfer.files && e.dataTransfer.files.length) {
      handleFiles(e.dataTransfer.files);
    }
  });

  fileInput.addEventListener("change", () => {
    if (fileInput.files && fileInput.files.length) {
      handleFiles(fileInput.files);
      fileInput.value = "";
    }
  });

  clearResultsBtn.addEventListener("click", () => {
    resultsGrid.innerHTML = "";
  });

  function readAsDataURL(file) {
    return new Promise((resolve) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => resolve(null);
      reader.readAsDataURL(file);
    });
  }

  async function handleFiles(fileList) {
    const files = Array.from(fileList);
    if (!files.length) return;

    const cards = [];
    for (const file of files) {
      const card = createLoadingCard(file);
      cards.push(card);
    }

    const formData = new FormData();
    files.forEach((file) => formData.append("files", file));

    let response;
    try {
      response = await fetch("/api/predict", { method: "POST", body: formData });
    } catch (err) {
      cards.forEach((card) => setCardError(card, "Serverga ulanib bo'lmadi. Iltimos qaytadan urinib ko'ring."));
      return;
    }

    let payload;
    try {
      payload = await response.json();
    } catch (err) {
      cards.forEach((card) => setCardError(card, "Server javobini o'qib bo'lmadi."));
      return;
    }

    if (!payload.model_available) {
      cards.forEach((card) =>
        setCardError(card, payload.message || "Model hali o'qitilmagan. README.md ga qarang.")
      );
      return;
    }

    payload.results.forEach((result, idx) => {
      const card = cards[idx];
      if (!card) return;
      if (result.success) {
        populateCard(card, result);
        addHistoryRow(result);
      } else {
        setCardError(card, result.error || "Noma'lum xato yuz berdi.");
      }
    });
  }

  function createLoadingCard(file) {
    const fragment = cardTemplate.content.cloneNode(true);
    const card = fragment.querySelector(".result-card");
    const img = card.querySelector(".result-card__image");
    const filenameEl = card.querySelector(".result-card__filename");
    const statusEl = card.querySelector(".result-card__status");
    const gradcamBtn = card.querySelector(".result-card__gradcam-toggle");

    filenameEl.textContent = file.name;
    statusEl.textContent = "Tahlil qilinmoqda...";
    statusEl.classList.add("loading");
    gradcamBtn.hidden = true;

    readAsDataURL(file).then((dataUrl) => {
      if (dataUrl) img.src = dataUrl;
    });

    resultsGrid.prepend(fragment);
    return resultsGrid.firstElementChild;
  }

  function setCardError(card, message) {
    const statusEl = card.querySelector(".result-card__status");
    statusEl.textContent = message;
    statusEl.classList.remove("loading");
    statusEl.classList.add("error");
  }

  function populateCard(card, result) {
    const img = card.querySelector(".result-card__image");
    const statusEl = card.querySelector(".result-card__status");
    const badgeRow = card.querySelector(".result-card__badge-row");
    const badge = card.querySelector(".badge");
    const soilingPill = card.querySelector(".pill--soiling");
    const lossPill = card.querySelector(".pill--loss");
    const barsWrap = card.querySelector(".result-card__bars");
    const gradcamBtn = card.querySelector(".result-card__gradcam-toggle");

    statusEl.remove();

    const originalSrc = result.preview_base64 || img.src;
    img.src = originalSrc;

    badgeRow.hidden = false;
    badge.textContent = `${result.verdict} — ${uzLabel(result.predicted_class)}`;
    badge.classList.add(result.badge === "clean" ? "badge--clean" : "badge--dirty");
    soilingPill.textContent = `Changlanish: ${result.soiling_level}`;
    lossPill.textContent = `Quvvat yo'qotish: ~${result.power_loss_percent}%`;

    const sorted = Object.entries(result.probabilities).sort((a, b) => b[1] - a[1]);
    sorted.forEach(([className, prob], i) => {
      const row = document.createElement("div");
      row.className = "bar-row";

      const label = document.createElement("div");
      label.className = "bar-row__label";
      label.textContent = uzLabel(className);

      const track = document.createElement("div");
      track.className = "bar-row__track";
      const fill = document.createElement("div");
      fill.className = "bar-row__fill";
      if (i === 0) {
        fill.classList.add("is-top", result.badge === "clean" ? "is-clean" : "is-dirty");
      }
      fill.style.width = `${(prob * 100).toFixed(1)}%`;
      track.appendChild(fill);

      const pct = document.createElement("div");
      pct.className = "bar-row__pct";
      pct.textContent = `${(prob * 100).toFixed(1)}%`;

      row.appendChild(label);
      row.appendChild(track);
      row.appendChild(pct);
      barsWrap.appendChild(row);
    });

    gradcamBtn.hidden = false;
    let showingHeatmap = false;
    gradcamBtn.addEventListener("click", () => {
      showingHeatmap = !showingHeatmap;
      img.src = showingHeatmap ? result.gradcam_base64 : originalSrc;
      gradcamBtn.textContent = showingHeatmap ? "Asl rasm" : "Issiqlik xaritasi";
    });
  }

  function addHistoryRow(result) {
    const emptyRow = historyBody.querySelector(".history-empty");
    if (emptyRow) emptyRow.remove();

    historyCounter += 1;
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${historyCounter}</td>
      <td>${result.timestamp}</td>
      <td><img src="${result.preview_base64}" alt="thumb" /></td>
      <td>${escapeHtml(result.filename)}</td>
      <td>${escapeHtml(result.verdict)} — ${escapeHtml(uzLabel(result.predicted_class))}</td>
      <td>${(result.confidence * 100).toFixed(1)}%</td>
      <td>${escapeHtml(result.soiling_level)}</td>
      <td>~${result.power_loss_percent}%</td>
    `;
    historyBody.prepend(tr);
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }
})();
