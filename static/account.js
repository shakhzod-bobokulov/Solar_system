(() => {
  "use strict";

  const { t, classLabel } = window.I18N;
  const $ = (id) => document.getElementById(id);
  const VIEWS = ["history", "panels", "map"];

  let panels = [];
  let historyData = null;
  let searchTimer = null;

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function cell(content, className) {
    const td = el("td", className);
    if (content instanceof Node) td.appendChild(content);
    else td.textContent = content;
    return td;
  }

  async function api(url, options) {
    const res = await fetch(url, options);
    if (res.status === 401) {
      window.location.href = "/login";
      throw new Error("unauthorized");
    }
    return res;
  }

  // ------------------------------------------------------------------
  // Ko'rinishlar (tablar)
  // ------------------------------------------------------------------
  function showView(name) {
    const view = VIEWS.includes(name) ? name : "history";
    VIEWS.forEach((v) => ($(`view-${v}`).hidden = v !== view));
    document.querySelectorAll("#accTabs .seg__btn").forEach((b) => {
      b.classList.toggle("is-active", b.dataset.view === view);
    });
    if (view === "map") loadMap();
  }

  document.querySelectorAll("#accTabs .seg__btn").forEach((b) =>
    b.addEventListener("click", () => {
      location.hash = b.dataset.view;
    })
  );
  window.addEventListener("hashchange", () => showView(location.hash.slice(1)));

  // ------------------------------------------------------------------
  // Tekshiruvlar tarixi
  // ------------------------------------------------------------------
  async function loadHistory() {
    const params = new URLSearchParams();
    if ($("hSearch").value.trim()) params.set("q", $("hSearch").value.trim());
    if ($("hClass").value) params.set("cls", $("hClass").value);
    if ($("hPanel").value) params.set("panel_id", $("hPanel").value);
    const res = await api(`/api/me/checks?${params}`);
    historyData = await res.json();
    renderHistory();
  }

  function fillFilters() {
    const classSel = $("hClass");
    const keepClass = classSel.value;
    classSel.innerHTML = "";
    const all = el("option", null, t("admin.filter.all"));
    all.value = "";
    classSel.appendChild(all);
    ((historyData && historyData.classes) || []).forEach((c) => {
      const o = el("option", null, classLabel(c));
      o.value = c;
      classSel.appendChild(o);
    });
    classSel.value = keepClass;

    const panelSel = $("hPanel");
    const keepPanel = panelSel.value;
    panelSel.innerHTML = "";
    const allP = el("option", null, t("account.filter.allpanels"));
    allP.value = "";
    panelSel.appendChild(allP);
    panels.forEach((p) => {
      const o = el("option", null, p.name);
      o.value = String(p.id);
      panelSel.appendChild(o);
    });
    panelSel.value = keepPanel;
  }

  function feedbackCell(row) {
    if (row.fb_ok === null || row.fb_ok === undefined) return cell("–");
    if (row.fb_ok) return cell(el("span", "tag tag--ok", t("fb.correct")));
    const text = row.fb_class ? `${t("fb.wrong")}: ${classLabel(row.fb_class)}` : t("fb.wrong");
    return cell(el("span", "tag tag--bad", text));
  }

  function renderHistory() {
    if (!historyData) return;
    const { checks, summary } = historyData;
    window.Anim.count($("hTotal"), summary.total);
    window.Anim.count($("hClean"), summary.clean);
    window.Anim.count($("hFaulty"), summary.faulty);
    if (summary.avg_loss === null) {
      $("hLoss")._animVal = 0;
      $("hLoss").textContent = "–";
    } else {
      window.Anim.count($("hLoss"), summary.avg_loss, (n) => `${n.toFixed(1)}%`);
    }
    fillFilters();

    const names = Object.fromEntries(panels.map((p) => [p.id, p.name]));
    const body = $("hBody");
    body.innerHTML = "";
    if (!checks.length) {
      const tr = el("tr", "history-empty");
      const td = el("td", null, t("admin.empty"));
      td.colSpan = 9;
      tr.appendChild(td);
      body.appendChild(tr);
    }
    checks.forEach((r) => {
      const tr = el("tr");
      const thumb = el("img");
      thumb.alt = "";
      thumb.loading = "lazy";
      if (r.has_thumb) thumb.src = `/api/checks/${r.id}/thumb`;
      const del = el("button", "btn btn--small btn--danger", t("admin.delete"));
      del.type = "button";
      del.addEventListener("click", async () => {
        if (!window.confirm(t("account.delete.confirm"))) return;
        await api(`/api/me/checks/${r.id}`, { method: "DELETE" });
        await Promise.all([loadHistory(), loadPanels()]);
      });
      const tag = el("span", `tag ${r.is_clean ? "tag--ok" : "tag--bad"}`, classLabel(r.predicted_class));
      tr.append(
        cell(thumb),
        cell(r.created_at),
        cell(r.filename),
        cell(tag),
        cell(`${(r.confidence * 100).toFixed(1)}%`),
        cell(`~${r.power_loss}%`),
        cell(r.panel_id ? names[r.panel_id] || "–" : "–"),
        feedbackCell(r),
        cell(del, "td-actions")
      );
      body.appendChild(tr);
    });
  }

  $("hSearch").addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(loadHistory, 250);
  });
  $("hClass").addEventListener("change", loadHistory);
  $("hPanel").addEventListener("change", loadHistory);

  // ------------------------------------------------------------------
  // Panellar
  // ------------------------------------------------------------------
  async function loadPanels() {
    const res = await api("/api/panels");
    panels = (await res.json()).panels;
    renderPanels();
    fillFilters();
  }

  function sparkline(values) {
    const svgNS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("viewBox", "0 0 120 34");
    svg.setAttribute("class", "spark");
    if (values.length < 2) return svg;
    const max = Math.max(5, ...values);
    const pts = values
      .map((v, i) => `${(i / (values.length - 1)) * 116 + 2},${30 - (v / max) * 26}`)
      .join(" ");
    const line = document.createElementNS(svgNS, "polyline");
    line.setAttribute("points", pts);
    line.setAttribute("fill", "none");
    line.setAttribute("stroke", "currentColor");
    line.setAttribute("stroke-width", "2");
    line.setAttribute("stroke-linejoin", "round");
    line.setAttribute("stroke-linecap", "round");
    svg.appendChild(line);
    return svg;
  }

  function trendBox(p) {
    const box = el("div", "trend");
    const trend = p.trend;
    if (trend.state === "none") {
      box.appendChild(el("span", "tag", t("panel.nochecks")));
      return box;
    }
    if (trend.state === "new") {
      box.appendChild(el("span", "tag tag--blue", t("trend.new")));
      return box;
    }
    const cls = { worse: "tag--bad", better: "tag--ok", same: "" }[trend.state];
    box.appendChild(el("span", `tag ${cls}`, t(`trend.${trend.state}`)));
    const sign = (n) => (n > 0 ? `+${n}` : `${n}`);
    box.appendChild(el("span", "trend__delta", t("trend.delta", { v: sign(trend.delta) })));
    if (trend.delta_30d !== null) {
      box.appendChild(el("span", "trend__delta", t("trend.delta30", { v: sign(trend.delta_30d) })));
    }
    return box;
  }

  function renderPanels() {
    const list = $("panelList");
    list.innerHTML = "";
    if (!panels.length) {
      list.appendChild(el("p", "panel__empty", t("panel.empty")));
      return;
    }
    panels.forEach((p) => {
      const card = el("article", "card panel-card");
      const head = el("div", "panel-card__head");
      const title = el("div");
      title.appendChild(el("h3", null, p.name));
      if (p.lat !== null && p.lon !== null) {
        const a = el("a", "panel-card__loc", `${p.lat.toFixed(5)}, ${p.lon.toFixed(5)}`);
        a.href = `https://www.openstreetmap.org/?mlat=${p.lat}&mlon=${p.lon}#map=17/${p.lat}/${p.lon}`;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        title.appendChild(a);
      }
      head.appendChild(title);
      const spark = el("div", `panel-card__spark ${p.trend.state === "worse" ? "is-bad" : "is-ok"}`);
      spark.appendChild(sparkline(p.spark));
      head.appendChild(spark);
      card.appendChild(head);

      card.appendChild(trendBox(p));
      if (p.last) {
        const last = el("p", "panel-card__last");
        last.append(
          `${t("panel.last")}: `,
          el("b", p.last.is_clean ? "ok" : "bad", classLabel(p.last.predicted_class)),
          ` · ~${p.last.power_loss}% · ${p.last.created_at}`
        );
        card.appendChild(last);
      }

      const actions = el("div", "panel-card__actions");
      const toggle = el("button", "btn btn--small", `${t("panel.history")} (${p.checks})`);
      toggle.type = "button";
      const detail = el("div", "panel-card__detail");
      detail.hidden = true;
      toggle.addEventListener("click", async () => {
        detail.hidden = !detail.hidden;
        if (!detail.hidden) await fillPanelDetail(detail, p.id);
      });
      const del = el("button", "btn btn--small btn--danger", t("admin.delete"));
      del.type = "button";
      del.addEventListener("click", async () => {
        if (!window.confirm(t("panel.delete.confirm", { name: p.name }))) return;
        await api(`/api/panels/${p.id}`, { method: "DELETE" });
        await Promise.all([loadPanels(), loadHistory()]);
      });
      actions.append(toggle, del);
      card.append(actions, detail);
      list.appendChild(card);
    });
  }

  async function fillPanelDetail(box, panelId) {
    box.innerHTML = "";
    const res = await api(`/api/panels/${panelId}/history`);
    const { history } = await res.json();
    if (!history.length) {
      box.appendChild(el("p", "panel__empty", t("panel.nochecks")));
      return;
    }
    const table = el("table", "history-table");
    const thead = el("thead");
    const hr = el("tr");
    [t("col.time"), t("col.result"), t("col.confidence"), t("col.loss")].forEach((h) => hr.appendChild(el("th", null, h)));
    thead.appendChild(hr);
    const tbody = el("tbody");
    history
      .slice()
      .reverse()
      .forEach((h) => {
        const tr = el("tr");
        tr.append(
          cell(h.created_at),
          cell(el("span", `tag ${h.is_clean ? "tag--ok" : "tag--bad"}`, classLabel(h.predicted_class))),
          cell(`${(h.confidence * 100).toFixed(1)}%`),
          cell(`~${h.power_loss}%`)
        );
        tbody.appendChild(tr);
      });
    table.append(thead, tbody);
    const wrap = el("div", "table-wrap table-wrap--bare");
    wrap.appendChild(table);
    box.appendChild(wrap);
  }

  // Yangi panel qo'shish
  $("pGeo").addEventListener("click", () => {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition((pos) => {
      $("pLat").value = pos.coords.latitude.toFixed(6);
      $("pLon").value = pos.coords.longitude.toFixed(6);
    });
  });

  $("pAdd").addEventListener("click", async () => {
    const err = $("pError");
    err.hidden = true;
    const name = $("pName").value.trim();
    if (!name) {
      err.textContent = t("panel.err.name");
      err.hidden = false;
      return;
    }
    const body = { name };
    if ($("pLat").value.trim() || $("pLon").value.trim()) {
      body.lat = $("pLat").value.trim().replace(",", ".");
      body.lon = $("pLon").value.trim().replace(",", ".");
    }
    const res = await api("/api/panels", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const data = await res.json();
      err.textContent = t(data.error === "coord" ? "panel.err.coord" : "panel.err.name");
      err.hidden = false;
      return;
    }
    $("pName").value = $("pLat").value = $("pLon").value = "";
    await loadPanels();
  });

  // ------------------------------------------------------------------
  // Xarita
  // ------------------------------------------------------------------
  async function loadMap() {
    const res = await api("/api/me/map");
    const data = await res.json();
    const empty = !data.checks.length && !data.panels.length;
    $("mapEmpty").hidden = !empty;
    window.SolarMap.render($("map"), data);
    window.SolarMap.refresh($("map"));
  }

  document.addEventListener("langchange", () => {
    renderHistory();
    renderPanels();
    if (!$("view-map").hidden) loadMap();
  });

  (async () => {
    await loadPanels();
    await loadHistory();
    showView(location.hash.slice(1));
  })();
})();
