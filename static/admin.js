(() => {
  "use strict";

  const { t, classLabel } = window.I18N;
  const $ = (id) => document.getElementById(id);

  const VIEWS = ["dashboard", "checks", "users", "map", "settings"];

  let data = null;
  let loadFailed = false;
  let range = "daily";

  // ------------------------------------------------------------------
  // Ma'lumot yuklash
  // ------------------------------------------------------------------
  async function load() {
    try {
      const res = await fetch("/api/admin/overview");
      if (res.status === 401) {
        window.location.href = "/login";
        return;
      }
      data = await res.json();
      loadFailed = false;
    } catch (err) {
      loadFailed = true;
    }
    render();
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
  // Yordamchilar
  // ------------------------------------------------------------------
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

  function messageRow(key, span) {
    const tr = el("tr", "history-empty");
    const td = el("td", null, t(key));
    td.colSpan = span;
    tr.appendChild(td);
    return tr;
  }

  function resultTag(row) {
    return el("span", `tag ${row.is_clean ? "tag--ok" : "tag--bad"}`, classLabel(row.predicted_class));
  }

  function thumbCell(row) {
    const td = el("td", "thumb-cell");
    if (row.has_thumb) {
      const img = el("img");
      img.src = `/api/checks/${row.id}/thumb`;
      img.alt = "";
      img.loading = "lazy";
      td.appendChild(img);
    } else {
      td.textContent = "–";
    }
    return td;
  }

  const pct = (n, total) => (total ? `${Math.round((n / total) * 100)}%` : "–");

  // ------------------------------------------------------------------
  // Ko'rinishlar (sidebar navigatsiyasi)
  // ------------------------------------------------------------------
  function showView(name) {
    const view = VIEWS.includes(name) ? name : "dashboard";
    VIEWS.forEach((v) => ($(`view-${v}`).hidden = v !== view));
    document.querySelectorAll(".nav__item[data-view]").forEach((a) => {
      a.classList.toggle("is-active", a.dataset.view === view);
    });
    if (view === "map") loadMap();
  }

  function syncFromHash() {
    showView(location.hash.replace("#", ""));
  }
  window.addEventListener("hashchange", syncFromHash);

  // ------------------------------------------------------------------
  // Boshqaruv paneli
  // ------------------------------------------------------------------
  function renderDashboard() {
    const { stats, users, daily, checks } = data;
    window.Anim.count($("kTotal"), stats.total);
    window.Anim.count($("kClean"), stats.clean);
    window.Anim.count($("kFaulty"), stats.faulty);
    if (stats.avg_loss === null) {
      $("kLoss")._animVal = 0;
      $("kLoss").textContent = "–";
    } else {
      window.Anim.count($("kLoss"), stats.avg_loss, (n) => `${n.toFixed(1)}%`);
    }
    window.Anim.count($("kUsers"), users.length);
    const today = daily.length ? daily[daily.length - 1] : { clean: 0, faulty: 0 };
    window.Anim.count($("kToday"), today.clean + today.faulty);
    $("kCleanPct").textContent = pct(stats.clean, stats.total);
    $("kFaultyPct").textContent = pct(stats.faulty, stats.total);
    $("defaultPwBanner").hidden = !data.default_password;

    renderChart();
    renderClassBars(stats);
    renderFaults(stats);

    const body = $("recentBody");
    body.innerHTML = "";
    if (!checks.length) body.appendChild(messageRow("admin.empty", 6));
    checks.slice(0, 8).forEach((r) => {
      const tr = el("tr");
      tr.append(thumbCell(r), cell(r.created_at), cell(r.username), cell(r.filename), cell(resultTag(r)), cell(`~${r.power_loss}%`));
      body.appendChild(tr);
    });
  }

  function renderChart() {
    $("chartTitle").textContent = t(range === "daily" ? "admin.chart.title" : "admin.chart.monthly");
    document.querySelectorAll("#chartSwitch .seg__btn").forEach((b) => b.classList.toggle("is-active", b.dataset.range === range));

    const series = range === "daily" ? data.daily : data.monthly;
    const chart = $("chart");
    chart.innerHTML = "";
    const max = Math.max(1, ...series.map((d) => d.clean + d.faulty));
    series.forEach((d, idx) => {
      const total = d.clean + d.faulty;
      const col = el("div", "chart__col");
      col.style.setProperty("--i", idx); // ustunlar ketma-ket o'sishi uchun
      col.title = `${d.date}: ${total}`;
      const area = el("div", "chart__area");
      const heightPct = (total / max) * 88; // yuqorida yozuv uchun joy qoldiramiz
      const val = el("span", "chart__val", total || "");
      val.style.bottom = `calc(${heightPct}% + 3px)`;
      area.appendChild(val);
      const bar = el("div", "chart__bar");
      bar.style.height = `${heightPct}%`;
      if (d.faulty) {
        const f = el("div", "chart__seg chart__seg--bad");
        f.style.flex = d.faulty;
        bar.appendChild(f);
      }
      if (d.clean) {
        const c = el("div", "chart__seg chart__seg--ok");
        c.style.flex = d.clean;
        bar.appendChild(c);
      }
      area.appendChild(bar);
      col.appendChild(area);
      // kunlik: DD.MM, oylik: MM.YY
      const label = range === "daily" ? `${d.date.slice(8)}.${d.date.slice(5, 7)}` : `${d.date.slice(5, 7)}.${d.date.slice(2, 4)}`;
      col.appendChild(el("span", "chart__lab", label));
      chart.appendChild(col);
    });
  }

  function renderClassBars(stats) {
    const wrap = $("classBars");
    wrap.innerHTML = "";
    if (!stats.by_class.length) {
      wrap.appendChild(el("div", "panel__empty", t("admin.noclasses")));
      return;
    }
    const max = Math.max(1, ...stats.by_class.map((c) => c.count));
    stats.by_class.forEach((c) => {
      const row = el("div", "bar-row bar-row--wide");
      const track = el("div", "bar-row__track");
      const fill = el("div", "bar-row__fill is-top");
      fill.style.background = "var(--primary)";
      fill.style.width = `${(c.count / max) * 100}%`;
      track.appendChild(fill);
      row.append(el("div", "bar-row__label", classLabel(c.class)), track, el("div", "bar-row__pct", c.count));
      wrap.appendChild(row);
    });
  }

  // Eng ko'p uchraydigan nosozliklar reytingi (toza panellarsiz)
  function renderFaults(stats) {
    const box = $("faultRank");
    box.innerHTML = "";
    const totalFaulty = stats.faults.reduce((s, f) => s + f.count, 0);
    if (!stats.faults.length) {
      box.appendChild(el("div", "panel__empty", t("admin.noclasses")));
    }
    stats.faults.forEach((f, i) => {
      const row = el("div", "rank__row");
      row.appendChild(el("span", null, `${i + 1}. ${classLabel(f.class)}`));
      row.appendChild(el("span", "rank__meta", `${f.count} · ${pct(f.count, totalFaulty)} · ~${f.avg_loss}%`));
      const bar = el("div", "rank__bar");
      const fill = el("i");
      fill.style.width = `${(f.count / stats.faults[0].count) * 100}%`;
      bar.appendChild(fill);
      row.appendChild(bar);
      box.appendChild(row);
    });

    const fb = stats.feedback;
    const note = $("fbStat");
    note.innerHTML = "";
    if (fb.total) {
      note.append(`${t("admin.fb.stat")}: `, el("b", null, `${fb.wrong} / ${fb.total}`), ` (${pct(fb.wrong, fb.total)})`);
    }
  }

  document.querySelectorAll("#chartSwitch .seg__btn").forEach((b) =>
    b.addEventListener("click", () => {
      range = b.dataset.range;
      if (data) renderChart();
    })
  );

  // ------------------------------------------------------------------
  // Tekshiruvlar
  // ------------------------------------------------------------------
  function fillClassFilter() {
    const select = $("checksClass");
    const current = select.value;
    select.innerHTML = "";
    const all = el("option", null, t("admin.filter.all"));
    all.value = "";
    select.appendChild(all);
    data.stats.by_class.forEach((c) => {
      const o = el("option", null, classLabel(c.class));
      o.value = c.class;
      select.appendChild(o);
    });
    select.value = current;
  }

  function feedbackTag(r) {
    if (r.fb_ok === null || r.fb_ok === undefined) return "–";
    if (r.fb_ok) return el("span", "tag tag--ok", t("fb.correct"));
    return el("span", "tag tag--bad", r.fb_class ? `${t("fb.wrong")}: ${classLabel(r.fb_class)}` : t("fb.wrong"));
  }

  function renderChecks() {
    const q = $("checksSearch").value.trim().toLowerCase();
    const cls = $("checksClass").value;
    const fb = $("checksFb").value;
    const rows = data.checks.filter((r) => {
      if (cls && r.predicted_class !== cls) return false;
      if (q && !(r.filename.toLowerCase().includes(q) || r.username.toLowerCase().includes(q))) return false;
      if (fb === "wrong" && r.fb_ok !== 0) return false;
      if (fb === "correct" && r.fb_ok !== 1) return false;
      if (fb === "none" && r.fb_ok !== null) return false;
      return true;
    });
    $("checksCount").textContent = rows.length;

    const body = $("checksBody");
    body.innerHTML = "";
    if (!rows.length) body.appendChild(messageRow("admin.empty", 10));
    rows.forEach((r) => {
      const tr = el("tr");
      const gps = r.lat !== null && r.lon !== null ? `${r.lat.toFixed(4)}, ${r.lon.toFixed(4)}` : "–";
      tr.append(
        thumbCell(r),
        cell(r.created_at),
        cell(r.username),
        cell(r.filename),
        cell(t(r.mode === "thermal" ? "mode.thermal.short" : "mode.rgb.short")),
        cell(resultTag(r)),
        cell(`${(r.confidence * 100).toFixed(1)}%`),
        cell(`~${r.power_loss}%`),
        cell(feedbackTag(r)),
        cell(gps)
      );
      body.appendChild(tr);
    });
  }

  // ------------------------------------------------------------------
  // Foydalanuvchilar
  // ------------------------------------------------------------------
  function userStatusTag(u) {
    if (u.blocked) return el("span", "tag tag--bad", t("admin.status.blocked"));
    return el("span", `tag ${u.verified ? "tag--ok" : "tag--warn"}`, t(u.verified ? "admin.status.verified" : "admin.status.pending"));
  }

  function renderUsers() {
    const q = $("usersSearch").value.trim().toLowerCase();
    const rows = data.users.filter((u) => !q || u.username.toLowerCase().includes(q) || (u.email || "").toLowerCase().includes(q));
    $("usersCount").textContent = rows.length;

    const body = $("usersBody");
    body.innerHTML = "";
    if (!rows.length) body.appendChild(messageRow("admin.users.empty", 7));
    rows.forEach((u) => {
      const tr = el("tr");
      const actions = el("td", "td-actions");

      const block = el("button", "btn btn--small", t(u.blocked ? "admin.unblock" : "admin.block"));
      block.type = "button";
      block.addEventListener("click", async () => {
        if (!u.blocked && !window.confirm(t("admin.block.confirm", { name: u.username }))) return;
        await api(`/api/admin/users/${u.id}/block`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ blocked: !u.blocked }),
        });
        load();
      });

      const del = el("button", "btn btn--small btn--danger", t("admin.delete"));
      del.type = "button";
      del.addEventListener("click", async () => {
        if (!window.confirm(t("admin.delete.confirm", { name: u.username }))) return;
        await api(`/api/admin/users/${u.id}`, { method: "DELETE" });
        load();
      });
      actions.append(block, " ", del);

      tr.append(cell(u.id), cell(u.username), cell(u.email || "–"), cell(userStatusTag(u)), cell(u.created_at), cell(u.checks), actions);
      body.appendChild(tr);
    });
  }

  // ------------------------------------------------------------------
  // Xarita
  // ------------------------------------------------------------------
  async function loadMap() {
    const res = await api("/api/admin/map");
    const points = await res.json();
    $("mapEmpty").hidden = points.checks.length + points.panels.length > 0;
    window.SolarMap.render($("map"), points);
    window.SolarMap.refresh($("map"));
  }

  // ------------------------------------------------------------------
  // Parol o'zgartirish
  // ------------------------------------------------------------------
  $("pwForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const ok = $("pwOk");
    const err = $("pwError");
    ok.hidden = err.hidden = true;
    const current = $("pwCurrent").value;
    const next = $("pwNew").value;
    if (next.length < 8) {
      err.textContent = t("reg.err.password");
      err.hidden = false;
      return;
    }
    if (next !== $("pwConfirm").value) {
      err.textContent = t("reg.err.mismatch");
      err.hidden = false;
      return;
    }
    const res = await api("/api/admin/password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ current, new: next }),
    });
    if (res.ok) {
      $("pwForm").reset();
      ok.textContent = t("admin.pw.done");
      ok.hidden = false;
      load();
      return;
    }
    const body = await res.json();
    err.textContent = t(body.error === "wrong_current" ? "admin.pw.wrong" : body.error === "too_many" ? "login.err.too_many" : "reg.err.password");
    err.hidden = false;
  });

  // ------------------------------------------------------------------
  // Umumiy chizish va hodisalar
  // ------------------------------------------------------------------
  function render() {
    if (!data) {
      const msg = loadFailed ? "admin.loaderr" : "admin.empty";
      ["recentBody", "checksBody"].forEach((id) => {
        $(id).innerHTML = "";
        $(id).appendChild(messageRow(msg, 10));
      });
      return;
    }
    fillClassFilter();
    renderDashboard();
    renderChecks();
    renderUsers();
  }

  document.querySelectorAll('[data-action="refresh"]').forEach((b) => b.addEventListener("click", load));
  $("checksSearch").addEventListener("input", () => data && renderChecks());
  $("checksClass").addEventListener("change", () => data && renderChecks());
  $("checksFb").addEventListener("change", () => data && renderChecks());
  $("usersSearch").addEventListener("input", () => data && renderUsers());

  $("clearBtn").addEventListener("click", async () => {
    if (!window.confirm(t("admin.confirm"))) return;
    await api("/api/admin/checks", { method: "DELETE" });
    load();
  });

  document.addEventListener("langchange", () => {
    render();
    if (!$("view-map").hidden) loadMap();
  });

  syncFromHash();
  load();
})();
