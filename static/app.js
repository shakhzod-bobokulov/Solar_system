(() => {
  "use strict";

  const I18N = window.I18N;
  const { t, classLabel } = I18N;
  const $ = (id) => document.getElementById(id);

  const STATE = JSON.parse($("appState").textContent);
  const ALLOWED = /\.(jpe?g|png|bmp|webp|zip)$/i;
  const CHUNK = 3; // bir so'rovda nechta fayl yuboriladi (progress shu bo'yicha yangilanadi)
  const MAX_TOTAL = 150; // bir amalda ko'pi bilan nechta fayl (brauzer xotirasini himoya qilish uchun)
  const KNOWN_CATEGORIES = ["soiling", "weather", "damage", "hotspot", "electrical", "obstruction"];

  const dropzone = $("dropzone");
  const fileInput = $("fileInput");
  const cameraInput = $("cameraInput");
  const folderInput = $("folderInput");
  const resultsGrid = $("resultsGrid");
  const cardTemplate = $("resultCardTemplate");
  const historyBody = $("historyBody");

  const history = []; // joriy sessiyadagi muvaffaqiyatli natijalar
  let mode = "rgb";

  // ------------------------------------------------------------------
  // Kichik yordamchilar
  // ------------------------------------------------------------------
  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function lsGet(key) {
    try {
      return localStorage.getItem(key);
    } catch (e) {
      return null;
    }
  }

  function lsSet(key, value) {
    try {
      localStorage.setItem(key, value);
    } catch (e) {
      /* ixtiyoriy */
    }
  }

  let toastTimer = null;
  function toast(message) {
    let box = $("toast");
    if (!box) {
      box = el("div", "toast");
      box.id = "toast";
      box.setAttribute("role", "status");
      document.body.appendChild(box);
    }
    box.textContent = message;
    box.classList.add("is-show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => box.classList.remove("is-show"), 4200);
  }

  function esc(value) {
    const div = document.createElement("div");
    div.textContent = value == null ? "" : String(value);
    return div.innerHTML;
  }

  // ------------------------------------------------------------------
  // Rejim: oddiy rasm / termal
  // ------------------------------------------------------------------
  const modeButtons = document.querySelectorAll("#modeSwitch .seg__btn");

  function renderMode() {
    modeButtons.forEach((b) => {
      const active = b.dataset.mode === mode;
      b.classList.toggle("is-active", active);
      b.setAttribute("aria-pressed", active ? "true" : "false");
    });
    const thermalBtn = $("modeThermal");
    thermalBtn.disabled = !STATE.thermal;
    thermalBtn.title = STATE.thermal ? "" : t("mode.thermal.na");
    $("modeHint").textContent = mode === "thermal" ? t("mode.hint.thermal") : t("mode.hint.rgb");
  }

  modeButtons.forEach((b) =>
    b.addEventListener("click", () => {
      if (b.disabled) return;
      mode = b.dataset.mode;
      lsSet("spd-mode", mode);
      renderMode();
    })
  );

  const savedMode = lsGet("spd-mode");
  mode = savedMode === "thermal" && STATE.thermal ? "thermal" : "rgb";

  // ------------------------------------------------------------------
  // Panellar (faqat kirgan foydalanuvchi uchun)
  // ------------------------------------------------------------------
  const panelSelect = $("panelSelect");

  function selectedPanelId() {
    if (!panelSelect) return "";
    return panelSelect.value && panelSelect.value !== "__new__" ? panelSelect.value : "";
  }

  if (panelSelect) {
    const newRow = $("newPanelRow");
    const nameInput = $("newPanelName");
    const latInput = $("newPanelLat");
    const lonInput = $("newPanelLon");
    const errBox = $("newPanelError");
    let previous = "";

    const saved = lsGet("spd-panel");
    if (saved && Array.from(panelSelect.options).some((o) => o.value === saved)) panelSelect.value = saved;
    previous = panelSelect.value;

    const closeNew = () => {
      newRow.hidden = true;
      errBox.hidden = true;
      panelSelect.value = previous;
    };

    panelSelect.addEventListener("change", () => {
      if (panelSelect.value === "__new__") {
        newRow.hidden = false;
        nameInput.focus();
      } else {
        previous = panelSelect.value;
        lsSet("spd-panel", previous);
        newRow.hidden = true;
      }
    });

    $("newPanelCancel").addEventListener("click", closeNew);

    $("newPanelGeo").addEventListener("click", () => {
      if (!navigator.geolocation) return toast(t("panel.geo.na"));
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          latInput.value = pos.coords.latitude.toFixed(6);
          lonInput.value = pos.coords.longitude.toFixed(6);
        },
        () => toast(t("panel.geo.fail")),
        { enableHighAccuracy: true, timeout: 10000 }
      );
    });

    $("newPanelAdd").addEventListener("click", async () => {
      errBox.hidden = true;
      const name = nameInput.value.trim();
      if (!name) {
        errBox.textContent = t("panel.err.name");
        errBox.hidden = false;
        return;
      }
      const body = { name };
      if (latInput.value.trim() || lonInput.value.trim()) {
        body.lat = latInput.value.trim().replace(",", ".");
        body.lon = lonInput.value.trim().replace(",", ".");
      }
      try {
        const res = await fetch("/api/panels", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const data = await res.json();
        if (!res.ok) {
          errBox.textContent = t(data.error === "coord" ? "panel.err.coord" : "panel.err.name");
          errBox.hidden = false;
          return;
        }
        const opt = el("option", null, name);
        opt.value = String(data.id);
        panelSelect.insertBefore(opt, panelSelect.querySelector('option[value="__new__"]'));
        panelSelect.value = opt.value;
        previous = opt.value;
        lsSet("spd-panel", previous);
        nameInput.value = latInput.value = lonInput.value = "";
        newRow.hidden = true;
        toast(t("panel.created"));
      } catch (err) {
        errBox.textContent = t("login.err.network");
        errBox.hidden = false;
      }
    });
  }

  // ------------------------------------------------------------------
  // Yuklash manbalari: tanlash, tashlash (papka ham), kamera, papka, buferdan joylash
  // ------------------------------------------------------------------
  dropzone.addEventListener("click", (e) => {
    if (e.target.closest(".dropzone__actions")) return;
    fileInput.click();
  });
  dropzone.addEventListener("keydown", (e) => {
    if (e.target !== dropzone) return;
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      fileInput.click();
    }
  });
  $("cameraBtn").addEventListener("click", () => cameraInput.click());
  $("folderBtn").addEventListener("click", () => folderInput.click());

  dropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  });
  dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
  dropzone.addEventListener("drop", async (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
    handleFiles(await filesFromDrop(e.dataTransfer));
  });

  // Papka tashlansa, ichidagi fayllar rekursiv o'qiladi
  async function filesFromDrop(dt) {
    const entries = Array.from(dt.items || [])
      .map((item) => (item.webkitGetAsEntry ? item.webkitGetAsEntry() : null))
      .filter(Boolean);
    if (!entries.length) return Array.from(dt.files);

    const out = [];
    async function walk(entry) {
      if (out.length >= MAX_TOTAL * 3) return;
      if (entry.isFile) {
        await new Promise((resolve) => entry.file((f) => (out.push(f), resolve()), resolve));
      } else if (entry.isDirectory) {
        const reader = entry.createReader();
        let batch;
        do {
          batch = await new Promise((resolve) => reader.readEntries(resolve, () => resolve([])));
          for (const child of batch) await walk(child);
        } while (batch.length);
      }
    }
    for (const entry of entries) await walk(entry);
    return out;
  }

  [fileInput, cameraInput, folderInput].forEach((input) =>
    input.addEventListener("change", () => {
      if (input.files && input.files.length) {
        handleFiles(Array.from(input.files));
      }
      input.value = "";
    })
  );

  // Ctrl+V: buferdagi rasm(lar)
  document.addEventListener("paste", (e) => {
    const target = e.target;
    if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return;
    const files = Array.from((e.clipboardData && e.clipboardData.files) || []).filter((f) => f.type.startsWith("image/"));
    if (!files.length) return;
    e.preventDefault();
    handleFiles(files);
    toast(t("upload.pasted", { n: files.length }));
  });

  // ------------------------------------------------------------------
  // Progress va navbat
  // ------------------------------------------------------------------
  const progressBox = $("progress");
  let progressTotal = 0;
  let progressDone = 0;
  let queue = Promise.resolve();

  function renderProgress() {
    progressBox.hidden = progressTotal === 0;
    if (!progressTotal) return;
    $("progressBar").style.width = `${(progressDone / progressTotal) * 100}%`;
    $("progressText").textContent = t("progress.text", { done: progressDone, total: progressTotal });
  }

  function advanceProgress(n) {
    progressDone += n;
    renderProgress();
    if (progressDone >= progressTotal) {
      setTimeout(() => {
        if (progressDone >= progressTotal) {
          progressTotal = progressDone = 0;
          renderProgress();
        }
      }, 1200);
    }
  }

  function handleFiles(fileList) {
    let files = Array.from(fileList).filter((f) => ALLOWED.test(f.name) || f.type.startsWith("image/"));
    if (!files.length) {
      toast(t("upload.none"));
      return;
    }
    if (files.length > MAX_TOTAL) {
      toast(t("upload.truncated", { n: MAX_TOTAL }));
      files = files.slice(0, MAX_TOTAL);
    }
    progressTotal += files.length;
    renderProgress();
    queue = queue.then(() => processFiles(files)).catch(() => {});
  }

  async function processFiles(files) {
    const cards = files.map((file) => createLoadingCard(file));
    for (let i = 0; i < files.length; i += CHUNK) {
      await uploadChunk(files.slice(i, i + CHUNK), cards.slice(i, i + CHUNK));
      advanceProgress(Math.min(CHUNK, files.length - i));
    }
  }

  async function uploadChunk(slice, sliceCards) {
    const form = new FormData();
    slice.forEach((f) => form.append("files", f, f.name));
    form.append("mode", mode);
    const panelId = selectedPanelId();
    if (panelId) form.append("panel_id", panelId);

    let response;
    try {
      response = await fetch("/api/predict", { method: "POST", body: form });
    } catch (err) {
      sliceCards.forEach((c) => setCardError(c, { key: "err.network" }));
      return;
    }

    let payload;
    try {
      payload = await response.json();
    } catch (err) {
      sliceCards.forEach((c) => setCardError(c, { key: "err.parse" }));
      return;
    }
    if (response.status === 413) {
      sliceCards.forEach((c) => setCardError(c, { key: "err.too_many_files" }));
      return;
    }
    if (!payload.model_available) {
      const key = payload.mode === "thermal" ? "err.thermal_model" : "err.model";
      sliceCards.forEach((c) => setCardError(c, { key }));
      return;
    }

    // ZIP bitta fayl, lekin ichida ko'p rasm bo'lishi mumkin: source_index bo'yicha kartalarga bog'laymiz
    const used = new Set();
    payload.results.forEach((result) => {
      const idx = result.source_index;
      let card = sliceCards[idx];
      if (!card || used.has(idx)) card = createShellCard(result.filename);
      used.add(idx);
      if (result.success) {
        card.querySelector(".result-card__filename").textContent = result.filename;
        populateCard(card, result);
        history.unshift(result);
      } else {
        card.querySelector(".result-card__filename").textContent = result.filename;
        setCardError(card, errorSpec(result));
      }
    });
    sliceCards.forEach((c, i) => {
      if (!used.has(i)) setCardError(c, { key: "err.unknown" });
    });
    renderHistory();
  }

  function errorSpec(result) {
    if (result.error_code) return { key: `err.${result.error_code}`, params: result.error_params };
    return { key: "err.unknown" };
  }

  // ------------------------------------------------------------------
  // Natija kartalari
  // ------------------------------------------------------------------
  function createShellCard(name) {
    const fragment = cardTemplate.content.cloneNode(true);
    const card = fragment.querySelector(".result-card");
    card.querySelector(".result-card__image").alt = t("card.alt");
    card.querySelector(".result-card__filename").textContent = name || "";
    const statusEl = card.querySelector(".result-card__status");
    statusEl.textContent = t("card.analyzing");
    statusEl.classList.add("loading");
    card._loading = true;
    card.querySelector(".result-card__image-wrap").classList.add("is-scanning");
    card.querySelector(".result-card__layers").hidden = true;
    I18N.apply(card);
    resultsGrid.prepend(fragment);
    return resultsGrid.firstElementChild;
  }

  function createLoadingCard(file) {
    const card = createShellCard(file.name);
    if (!/\.zip$/i.test(file.name)) {
      const reader = new FileReader();
      reader.onload = () => {
        const img = card.querySelector(".result-card__image");
        if (!img.dataset.final) img.src = reader.result;
      };
      reader.readAsDataURL(file);
    } else {
      card.querySelector(".result-card__image-wrap").classList.add("is-zip");
    }
    return card;
  }

  function setCardError(card, spec) {
    const statusEl = card.querySelector(".result-card__status");
    if (!statusEl) return;
    statusEl.classList.remove("loading");
    statusEl.classList.add("error");
    card.querySelector(".result-card__image-wrap").classList.remove("is-scanning");
    card._loading = false;
    card._error = spec;
    renderCardStatus(card);
  }

  function renderCardStatus(card) {
    const statusEl = card.querySelector(".result-card__status");
    if (!statusEl) return;
    if (card._error) statusEl.textContent = t(card._error.key, card._error.params);
    else if (card._loading) statusEl.textContent = t("card.analyzing");
  }

  function verdictKey(result) {
    if (result.badge === "clean") return "verdict.clean";
    return `verdict.${KNOWN_CATEGORIES.includes(result.category) ? result.category : "damage"}`;
  }

  function populateCard(card, result) {
    const wrap = card.querySelector(".result-card__image-wrap");
    const img = card.querySelector(".result-card__image");
    const heat = card.querySelector(".result-card__heat");
    const mask = card.querySelector(".result-card__mask");
    const statusEl = card.querySelector(".result-card__status");
    const badgeRow = card.querySelector(".result-card__badge-row");
    const barsWrap = card.querySelector(".result-card__bars");
    const heatBtn = card.querySelector(".result-card__gradcam-toggle");
    const maskBtn = card.querySelector(".result-card__mask-toggle");
    const zoomBtn = card.querySelector(".result-card__zoom");
    const slider = card.querySelector(".result-card__slider");
    const range = slider.querySelector("input");

    statusEl.remove();
    card._loading = false;
    card._error = null;
    card._result = result;
    card._showHeat = false;
    card._showMask = false;
    card._opacity = Number(lsGet("spd-heat-opacity") || 65);
    card._fb = "idle";

    img.dataset.final = "1";
    img.src = result.preview_base64;
    heat.src = result.heatmap_base64;
    wrap.style.setProperty("--heat", card._opacity / 100);
    range.value = card._opacity;

    wrap.classList.remove("is-scanning");
    badgeRow.hidden = false;
    card.querySelector(".badge").classList.add("badge--pop");
    card.querySelector(".badge").classList.add(result.badge === "clean" ? "badge--clean" : "badge--dirty");
    const note = el("div", "result-card__note");
    badgeRow.after(note);

    if (result.mode === "thermal") {
      mask.src = result.hot_mask_base64;
      maskBtn.hidden = false;
      card.querySelector(".pill--hot").hidden = false;
    }
    if (result.gps) card.querySelector(".pill--gps").hidden = false;
    card.querySelector(".result-card__layers").hidden = false;
    zoomBtn.hidden = false;

    // Ehtimollik barlari
    Object.entries(result.probabilities)
      .sort((a, b) => b[1] - a[1])
      .forEach(([className, prob], i) => {
        const row = el("div", "bar-row");
        const label = el("div", "bar-row__label");
        label.dataset.class = className;
        const track = el("div", "bar-row__track");
        const fill = el("div", "bar-row__fill");
        if (i === 0) fill.classList.add("is-top", result.badge === "clean" ? "is-clean" : "is-dirty");
        fill.style.width = `${(prob * 100).toFixed(1)}%`;
        track.appendChild(fill);
        row.append(label, track, el("div", "bar-row__pct", `${(prob * 100).toFixed(1)}%`));
        barsWrap.appendChild(row);
      });

    // Issiqlik qatlami va shaffoflik slayderi
    heatBtn.addEventListener("click", () => {
      card._showHeat = !card._showHeat;
      renderLayers(card);
    });
    maskBtn.addEventListener("click", () => {
      card._showMask = !card._showMask;
      renderLayers(card);
    });
    range.addEventListener("input", () => {
      card._opacity = Number(range.value);
      wrap.style.setProperty("--heat", card._opacity / 100);
      lsSet("spd-heat-opacity", String(card._opacity));
    });
    const open = () => openLightbox(card);
    zoomBtn.addEventListener("click", open);
    img.addEventListener("click", open);

    renderLayers(card);
    renderCardText(card);
    renderWarnings(card);
    renderFeedback(card);
  }

  function renderLayers(card) {
    const heat = card.querySelector(".result-card__heat");
    const mask = card.querySelector(".result-card__mask");
    heat.hidden = !card._showHeat;
    mask.hidden = !card._showMask;
    card.querySelector(".result-card__slider").hidden = !card._showHeat;
    card.querySelector(".result-card__gradcam-toggle").textContent = card._showHeat ? t("card.original") : t("card.gradcam");
    card.querySelector(".result-card__mask-toggle").textContent = card._showMask ? t("card.mask.hide") : t("card.mask.show");
  }

  // Tilga bog'liq barcha matnlar
  function renderCardText(card) {
    const result = card._result;
    if (!result) return;
    card.querySelector(".badge").textContent = classLabel(result.predicted_class);
    card.querySelector(".result-card__note").textContent =
      `${t(verdictKey(result))} · ${t("card.confidence", { v: (result.confidence * 100).toFixed(1) })}`;
    card.querySelector(".pill--soiling").textContent = t("card.severity", { v: t(`sev.${result.severity_key}`) });
    card.querySelector(".pill--loss").textContent = t("card.loss", { v: result.power_loss_percent });
    if (result.mode === "thermal") {
      card.querySelector(".pill--hot").textContent = t("card.hot", { v: result.hot_area_percent });
    }
    if (result.gps) {
      const gpsPill = card.querySelector(".pill--gps");
      gpsPill.textContent = `GPS ${result.gps.lat.toFixed(4)}, ${result.gps.lon.toFixed(4)}`;
    }
    card.querySelectorAll(".bar-row__label").forEach((node) => {
      node.textContent = classLabel(node.dataset.class);
    });
    card.querySelector(".result-card__image").alt = t("card.alt");
    card.querySelector(".result-card__zoom").setAttribute("aria-label", t("card.zoom"));
    renderLayers(card);
  }

  // Past ishonch va rasm sifati ogohlantirishlari
  function warningList(result) {
    const out = [];
    if (result.low_confidence) out.push(t("warn.lowconf", { v: (result.confidence * 100).toFixed(0) }));
    (result.quality_warnings || []).forEach((flag) => out.push(t(`warn.${flag}`)));
    return out;
  }

  function renderWarnings(card) {
    const box = card.querySelector(".result-card__warnings");
    const result = card._result;
    if (!result) return;
    const list = warningList(result);
    box.hidden = list.length === 0;
    box.innerHTML = "";
    if (!list.length) return;
    const ul = el("ul");
    list.forEach((text) => ul.appendChild(el("li", null, text)));
    box.append(ul, el("p", "warn__tip", t("warn.tip")));
  }

  // "Natija to'g'rimi?" — foydalanuvchi fikri
  function renderFeedback(card) {
    const box = card.querySelector(".result-card__feedback");
    const result = card._result;
    if (!result || !result.id) {
      box.hidden = true;
      return;
    }
    box.hidden = false;
    box.innerHTML = "";

    if (card._fb === "done") {
      box.appendChild(el("span", "fb__thanks", t("fb.thanks")));
      return;
    }

    if (card._fb === "wrong") {
      const names = result.mode === "thermal" ? STATE.thermalNames : STATE.classNames;
      const select = el("select", "input input--sm");
      const unknown = el("option", null, t("fb.unknown"));
      unknown.value = "";
      select.appendChild(unknown);
      names
        .filter((n) => n !== result.predicted_class)
        .forEach((n) => {
          const o = el("option", null, classLabel(n));
          o.value = n;
          select.appendChild(o);
        });
      const send = el("button", "btn btn--small btn--primary", t("fb.send"));
      send.type = "button";
      send.addEventListener("click", () => sendFeedback(card, false, select.value));
      const cancel = el("button", "btn btn--small btn--ghost", t("panel.cancel"));
      cancel.type = "button";
      cancel.addEventListener("click", () => {
        card._fb = "idle";
        renderFeedback(card);
      });
      box.append(el("span", "fb__q", t("fb.which")), select, send, cancel);
      return;
    }

    const yes = el("button", "btn btn--small", t("fb.yes"));
    yes.type = "button";
    yes.addEventListener("click", () => sendFeedback(card, true, ""));
    const no = el("button", "btn btn--small", t("fb.no"));
    no.type = "button";
    no.addEventListener("click", () => {
      card._fb = "wrong";
      renderFeedback(card);
    });
    box.append(el("span", "fb__q", t("fb.question")), yes, no);
  }

  async function sendFeedback(card, ok, correctClass) {
    const result = card._result;
    try {
      const res = await fetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ check_id: result.id, ok, correct_class: correctClass || null }),
      });
      if (!res.ok) throw new Error("feedback");
      card._fb = "done";
      renderFeedback(card);
    } catch (err) {
      toast(t("fb.error"));
    }
  }

  // ------------------------------------------------------------------
  // Kattalashtirish oynasi (lightbox): zoom, siljitish, shaffoflik
  // ------------------------------------------------------------------
  const lb = {
    root: $("lightbox"),
    stage: $("lbStage"),
    layer: $("lbLayer"),
    base: $("lbBase"),
    heat: $("lbHeat"),
    mask: $("lbMask"),
    opacity: $("lbOpacity"),
    heatToggle: $("lbHeatToggle"),
    maskToggle: $("lbMaskToggle"),
    maskWrap: $("lbMaskWrap"),
    card: null,
    z: 1,
    px: 0,
    py: 0,
    fw: 0,
    fh: 0,
  };
  const pointers = new Map();
  let pinchStart = null;
  const MAX_ZOOM = 10;

  function applyTransform() {
    lb.layer.style.transform = `translate(${lb.px}px, ${lb.py}px) scale(${lb.z})`;
  }

  function fitView() {
    const sw = lb.stage.clientWidth;
    const sh = lb.stage.clientHeight;
    const nw = lb.base.naturalWidth || 4;
    const nh = lb.base.naturalHeight || 3;
    const k = Math.min(sw / nw, sh / nh) * 0.96;
    lb.fw = Math.max(1, nw * k);
    lb.fh = Math.max(1, nh * k);
    lb.layer.style.width = `${lb.fw}px`;
    lb.layer.style.height = `${lb.fh}px`;
    lb.z = 1;
    lb.px = (sw - lb.fw) / 2;
    lb.py = (sh - lb.fh) / 2;
    applyTransform();
  }

  function zoomAt(cx, cy, factor) {
    const z2 = Math.min(MAX_ZOOM, Math.max(1, lb.z * factor));
    if (z2 === lb.z) return;
    if (z2 === 1) return fitView();
    lb.px = cx - (cx - lb.px) * (z2 / lb.z);
    lb.py = cy - (cy - lb.py) * (z2 / lb.z);
    lb.z = z2;
    applyTransform();
  }

  function stagePoint(e) {
    const r = lb.stage.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  }

  function openLightbox(card) {
    const result = card._result;
    if (!result) return;
    lb.card = card;
    lb.base.onload = fitView;
    lb.base.src = result.preview_base64;
    lb.heat.src = result.heatmap_base64;
    lb.heat.style.opacity = card._opacity / 100;
    lb.opacity.value = card._opacity;
    lb.heatToggle.checked = true;
    lb.heat.hidden = false;
    const thermal = result.mode === "thermal";
    lb.maskWrap.hidden = !thermal;
    lb.mask.hidden = !thermal;
    lb.maskToggle.checked = true;
    if (thermal) lb.mask.src = result.hot_mask_base64;
    $("lbTitle").textContent = `${result.filename} — ${classLabel(result.predicted_class)} (${(result.confidence * 100).toFixed(1)}%)`;
    lb.root.hidden = false;
    document.body.classList.add("no-scroll");
    requestAnimationFrame(fitView);
  }

  function closeLightbox() {
    lb.root.hidden = true;
    document.body.classList.remove("no-scroll");
    lb.card = null;
  }

  $("lbClose").addEventListener("click", closeLightbox);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !lb.root.hidden) closeLightbox();
  });
  window.addEventListener("resize", () => !lb.root.hidden && fitView());
  $("lbReset").addEventListener("click", fitView);
  $("lbZoomIn").addEventListener("click", () => zoomAt(lb.stage.clientWidth / 2, lb.stage.clientHeight / 2, 1.5));
  $("lbZoomOut").addEventListener("click", () => zoomAt(lb.stage.clientWidth / 2, lb.stage.clientHeight / 2, 1 / 1.5));
  lb.heatToggle.addEventListener("change", () => (lb.heat.hidden = !lb.heatToggle.checked));
  lb.maskToggle.addEventListener("change", () => (lb.mask.hidden = !lb.maskToggle.checked));
  lb.opacity.addEventListener("input", () => {
    const v = Number(lb.opacity.value);
    lb.heat.style.opacity = v / 100;
    if (lb.card) {
      lb.card._opacity = v;
      lb.card.querySelector(".result-card__image-wrap").style.setProperty("--heat", v / 100);
      lb.card.querySelector(".result-card__slider input").value = v;
      lsSet("spd-heat-opacity", String(v));
    }
  });

  lb.stage.addEventListener(
    "wheel",
    (e) => {
      e.preventDefault();
      const p = stagePoint(e);
      zoomAt(p.x, p.y, e.deltaY < 0 ? 1.15 : 1 / 1.15);
    },
    { passive: false }
  );
  lb.stage.addEventListener("dblclick", (e) => {
    const p = stagePoint(e);
    if (lb.z > 1) fitView();
    else zoomAt(p.x, p.y, 3);
  });
  lb.stage.addEventListener("pointerdown", (e) => {
    lb.stage.setPointerCapture(e.pointerId);
    pointers.set(e.pointerId, stagePoint(e));
    if (pointers.size === 2) {
      const [a, b] = Array.from(pointers.values());
      pinchStart = { dist: Math.hypot(a.x - b.x, a.y - b.y), z: lb.z };
    }
  });
  lb.stage.addEventListener("pointermove", (e) => {
    if (!pointers.has(e.pointerId)) return;
    const prev = pointers.get(e.pointerId);
    const cur = stagePoint(e);
    pointers.set(e.pointerId, cur);
    if (pointers.size === 1 && lb.z > 1) {
      lb.px += cur.x - prev.x;
      lb.py += cur.y - prev.y;
      applyTransform();
    } else if (pointers.size === 2 && pinchStart) {
      const [a, b] = Array.from(pointers.values());
      const dist = Math.hypot(a.x - b.x, a.y - b.y);
      const target = Math.min(MAX_ZOOM, Math.max(1, pinchStart.z * (dist / pinchStart.dist)));
      zoomAt((a.x + b.x) / 2, (a.y + b.y) / 2, target / lb.z);
    }
  });
  const endPointer = (e) => {
    pointers.delete(e.pointerId);
    if (pointers.size < 2) pinchStart = null;
  };
  lb.stage.addEventListener("pointerup", endPointer);
  lb.stage.addEventListener("pointercancel", endPointer);

  // ------------------------------------------------------------------
  // Tarix jadvali va statistika
  // ------------------------------------------------------------------
  function cell(text) {
    return el("td", null, text);
  }

  function renderHistory() {
    historyBody.innerHTML = "";
    if (!history.length) {
      const tr = el("tr", "history-empty");
      const td = el("td", null, t("history.empty"));
      td.colSpan = 8;
      tr.appendChild(td);
      historyBody.appendChild(tr);
    }
    history.forEach((result, i) => {
      const tr = el("tr");
      const thumbTd = el("td");
      const thumb = el("img");
      thumb.src = result.preview_base64;
      thumb.alt = "";
      thumbTd.appendChild(thumb);
      tr.append(
        cell(history.length - i),
        cell(result.timestamp),
        thumbTd,
        cell(result.filename),
        cell(classLabel(result.predicted_class)),
        cell(`${(result.confidence * 100).toFixed(1)}%`),
        cell(t(`sev.${result.severity_key}`)),
        cell(`~${result.power_loss_percent}%`)
      );
      historyBody.appendChild(tr);
    });
    renderStats();
    renderCalc();
  }

  function renderStats() {
    const total = history.length;
    const clean = history.filter((r) => r.badge === "clean").length;
    window.Anim.count($("statTotal"), total);
    window.Anim.count($("statClean"), clean);
    window.Anim.count($("statDirty"), total - clean);
    if (total) window.Anim.count($("statLoss"), averageLoss(), (n) => `${n.toFixed(1)}%`);
    else {
      $("statLoss")._animVal = 0;
      $("statLoss").textContent = "–";
    }
  }

  function averageLoss() {
    if (!history.length) return 0;
    return history.reduce((s, r) => s + (Number(r.power_loss_percent) || 0), 0) / history.length;
  }

  // ------------------------------------------------------------------
  // Yo'qotish kalkulyatori
  // ------------------------------------------------------------------
  const calcEls = {
    watts: $("calcWatts"),
    count: $("calcCount"),
    hours: $("calcHours"),
    tariff: $("calcTariff"),
    loss: $("calcLoss"),
    auto: $("calcAuto"),
  };
  const CALC_KEY = "spd-calc";

  function loadCalc() {
    try {
      const saved = JSON.parse(lsGet(CALC_KEY) || "{}");
      ["watts", "count", "hours", "tariff"].forEach((k) => {
        if (saved[k] > 0) calcEls[k].value = saved[k];
      });
      if (typeof saved.auto === "boolean") calcEls.auto.checked = saved.auto;
      if (!calcEls.auto.checked && saved.loss >= 0) calcEls.loss.value = saved.loss;
    } catch (e) {
      /* buzuq saqlangan qiymat — standart qiymatlar qoladi */
    }
  }

  function calcResult() {
    const num = (input, fallback = 0) => {
      const v = parseFloat(String(input.value).replace(",", "."));
      return Number.isFinite(v) && v >= 0 ? v : fallback;
    };
    const watts = num(calcEls.watts);
    const count = num(calcEls.count);
    const hours = num(calcEls.hours);
    const tariff = num(calcEls.tariff);
    const loss = Math.min(100, num(calcEls.loss));
    const idealKwh = (watts / 1000) * count * hours * 30; // oyiga
    const lostKwh = idealKwh * (loss / 100);
    return { watts, count, hours, tariff, loss, lostKwh, month: lostKwh * tariff, year: lostKwh * tariff * 12 };
  }

  const LOCALES = { uz: "uz-UZ", ru: "ru-RU", en: "en-US" };
  function fmt(n, digits = 0) {
    return new Intl.NumberFormat(LOCALES[I18N.lang] || "en-US", { maximumFractionDigits: digits }).format(n);
  }

  function renderCalc() {
    if (calcEls.auto.checked) {
      calcEls.loss.value = history.length ? averageLoss().toFixed(1) : "0";
    }
    calcEls.loss.disabled = calcEls.auto.checked;
    const r = calcResult();
    const cur = t("calc.currency");
    window.Anim.countOrDash($("calcKwh"), r.lostKwh, (n) => `${fmt(n, 1)} kWh`);
    window.Anim.countOrDash($("calcMonth"), r.month, (n) => `${fmt(n)} ${cur}`);
    window.Anim.countOrDash($("calcYear"), r.year, (n) => `${fmt(n)} ${cur}`);
    lsSet(
      CALC_KEY,
      JSON.stringify({ watts: r.watts, count: r.count, hours: r.hours, tariff: r.tariff, loss: r.loss, auto: calcEls.auto.checked })
    );
  }

  Object.values(calcEls).forEach((input) => input.addEventListener("input", renderCalc));
  calcEls.auto.addEventListener("change", renderCalc);
  loadCalc();

  // ------------------------------------------------------------------
  // PDF hisobot (brauzerning "PDF sifatida saqlash" oynasi orqali)
  // ------------------------------------------------------------------
  function buildReportHtml() {
    const calc = calcResult();
    const cur = t("calc.currency");
    const total = history.length;
    const clean = history.filter((r) => r.badge === "clean").length;
    const now = new Date().toLocaleString(LOCALES[I18N.lang] || "en-US");

    const blocks = history
      .slice()
      .reverse()
      .map((r, i) => {
        const warns = warningList(r);
        const images = [
          `<figure><img src="${r.preview_base64}" alt=""/><figcaption>${esc(t("report.original"))}</figcaption></figure>`,
          `<figure><img src="${r.gradcam_base64}" alt=""/><figcaption>${esc(t("card.gradcam"))}</figcaption></figure>`,
        ];
        if (r.mode === "thermal" && r.hot_mask_overlay_base64) {
          images.push(`<figure><img src="${r.hot_mask_overlay_base64}" alt=""/><figcaption>${esc(t("card.mask.show"))}</figcaption></figure>`);
        }
        const rows = [
          [t("col.result"), `<b class="${r.badge === "clean" ? "ok" : "bad"}">${esc(classLabel(r.predicted_class))}</b>`],
          [t("col.confidence"), `${(r.confidence * 100).toFixed(1)}%`],
          [t("col.severity"), esc(t(`sev.${r.severity_key}`))],
          [t("col.loss"), `~${r.power_loss_percent}%`],
        ];
        if (r.mode === "thermal") rows.push([t("report.hotarea"), `${r.hot_area_percent}%`]);
        if (r.gps) rows.push(["GPS", `${r.gps.lat.toFixed(5)}, ${r.gps.lon.toFixed(5)}`]);
        rows.push([t("report.advice"), esc(t(verdictKey(r)))]);
        return `
          <section class="item">
            <h3>${i + 1}. ${esc(r.filename)} <small>${esc(r.timestamp)}</small></h3>
            <div class="imgs">${images.join("")}</div>
            <table>${rows.map(([k, v]) => `<tr><th>${esc(k)}</th><td>${v}</td></tr>`).join("")}</table>
            ${warns.length ? `<ul class="warn">${warns.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>` : ""}
          </section>`;
      })
      .join("");

    const calcBlock =
      calc.lostKwh > 0
        ? `<h2>${esc(t("calc.title"))}</h2>
           <table>
             <tr><th>${esc(t("calc.watts"))} × ${esc(t("calc.count"))}</th><td>${fmt(calc.watts)} W × ${fmt(calc.count)}</td></tr>
             <tr><th>${esc(t("calc.hours"))}</th><td>${fmt(calc.hours, 1)}</td></tr>
             <tr><th>${esc(t("calc.loss"))}</th><td>${fmt(calc.loss, 1)}%</td></tr>
             <tr><th>${esc(t("calc.out.kwh"))}</th><td>${fmt(calc.lostKwh, 1)} kWh</td></tr>
             <tr><th>${esc(t("calc.out.month"))}</th><td>${fmt(calc.month)} ${esc(cur)}</td></tr>
             <tr><th>${esc(t("calc.out.year"))}</th><td>${fmt(calc.year)} ${esc(cur)}</td></tr>
           </table>`
        : "";

    return `<!doctype html><html lang="${I18N.lang}"><head><meta charset="utf-8"/>
      <title>${esc(t("report.title"))}</title>
      <style>
        *{box-sizing:border-box} body{font:13px/1.5 "Segoe UI",Roboto,Arial,sans-serif;color:#111827;margin:24px}
        h1{font-size:20px;margin:0 0 4px} h2{font-size:15px;margin:22px 0 8px} h3{font-size:14px;margin:0 0 8px}
        h3 small{font-weight:400;color:#6b7280;margin-left:8px} .meta{color:#6b7280;margin-bottom:14px}
        table{border-collapse:collapse;width:100%;margin:6px 0} th,td{border:1px solid #e5e7eb;padding:5px 9px;text-align:left}
        th{background:#f9fafb;width:34%;font-weight:600} .ok{color:#15803d} .bad{color:#b91c1c}
        .item{break-inside:avoid;border:1px solid #e5e7eb;border-radius:8px;padding:12px;margin:12px 0}
        .imgs{display:flex;gap:10px;margin-bottom:8px} figure{margin:0;flex:1;min-width:0}
        figure img{width:100%;max-height:230px;object-fit:contain;background:#0b0f17;border-radius:6px}
        figcaption{font-size:11px;color:#6b7280;text-align:center;margin-top:2px}
        .warn{margin:8px 0 0;padding:8px 8px 8px 24px;background:#fffbeb;border:1px solid #f59e0b;border-radius:6px;color:#92400e}
        .note{color:#6b7280;font-size:11px;margin-top:16px}
        @media print{body{margin:10mm}.item{page-break-inside:avoid}}
      </style></head><body>
      <h1>${esc(t("report.title"))}</h1>
      <div class="meta">${esc(now)}${STATE.user ? " · " + esc(STATE.user) : ""}</div>
      <table>
        <tr><th>${esc(t("stat.total"))}</th><td>${total}</td></tr>
        <tr><th>${esc(t("stat.clean"))}</th><td>${clean}</td></tr>
        <tr><th>${esc(t("stat.faulty"))}</th><td>${total - clean}</td></tr>
        <tr><th>${esc(t("stat.loss"))}</th><td>${averageLoss().toFixed(1)}%</td></tr>
      </table>
      ${calcBlock}
      <h2>${esc(t("results.title"))}</h2>
      ${blocks}
      <p class="note">${esc(t("how.note"))}</p>
      </body></html>`;
  }

  $("reportBtn").addEventListener("click", () => {
    if (!history.length) return toast(t("report.empty"));
    const win = window.open("", "_blank");
    if (!win) return toast(t("report.popup"));
    win.document.open();
    win.document.write(buildReportHtml());
    win.document.close();
    // rasmlar (data URL) yuklanib bo'lishi uchun qisqa kutish, so'ng chop etish oynasi
    setTimeout(() => {
      win.focus();
      win.print();
    }, 700);
  });

  $("clearResultsBtn").addEventListener("click", () => {
    resultsGrid.innerHTML = "";
  });

  // ------------------------------------------------------------------
  // Til o'zgarganda dinamik kontentni qayta chizish
  // ------------------------------------------------------------------
  function setEmptyLabel() {
    resultsGrid.dataset.empty = t("results.empty");
  }

  document.addEventListener("langchange", () => {
    setEmptyLabel();
    renderMode();
    renderProgress();
    resultsGrid.querySelectorAll(".result-card").forEach((card) => {
      card.querySelector(".result-card__image").alt = t("card.alt");
      renderCardText(card);
      renderCardStatus(card);
      renderWarnings(card);
      renderFeedback(card);
    });
    renderHistory();
    if (lb.card) $("lbTitle").textContent = `${lb.card._result.filename} — ${classLabel(lb.card._result.predicted_class)}`;
  });

  setEmptyLabel();
  renderMode();
  renderHistory();
})();
