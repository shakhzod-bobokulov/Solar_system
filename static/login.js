(() => {
  "use strict";

  const I18N = window.I18N;
  const { t } = I18N;

  const $ = (id) => document.getElementById(id);
  const form = $("loginForm");
  const els = {
    username: $("username"),
    email: $("email"),
    code: $("code"),
    password: $("password"),
    confirm: $("confirm"),
  };
  const titleEl = $("authTitle");
  const subEl = $("authSub");
  const usernameLabel = $("usernameLabel");
  const passwordLabel = $("passwordLabel");
  const submitBtn = $("loginSubmit");
  const errorEl = $("loginError");
  const infoEl = $("formInfo");
  const regHint = $("regHint");
  const showPassword = $("showPassword");
  const showPasswordWrap = $("showPasswordWrap");
  const tabsEl = $("tabs");
  const forgotLink = $("forgotLink");
  const resendBtn = $("resendBtn");
  const backLink = $("backLink");
  const guestBlock = $("guestBlock");

  const USERNAME_RE = /^[A-Za-z0-9_.-]{3,30}$/;
  const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
  const RESEND_COOLDOWN = 60;

  // Har bir holatda qaysi maydonlar va matnlar ko'rinishi
  const MODES = {
    login: { fields: ["username", "password"], title: "login.title", sub: "login.subtitle", submit: "login.submit", tabs: true },
    register: { fields: ["username", "email", "password", "confirm"], title: "reg.title", sub: "reg.subtitle", submit: "reg.submit", tabs: true },
    verify: { fields: ["code"], title: "verify.title", sub: "verify.subtitle", submit: "verify.submit", back: true, resend: true },
    forgot: { fields: ["email"], title: "forgot.title", sub: "forgot.subtitle", submit: "forgot.submit", back: true },
    reset: { fields: ["code", "password", "confirm"], title: "reset.title", sub: "reset.subtitle", submit: "reset.submit", back: true },
  };

  let mode = "login";
  let pendingEmail = ""; // kod yuborilgan email
  let message = null; // {type: "error"|"info", key, params}
  let busy = false;
  let cooldownUntil = 0;
  let cooldownTimer = null;

  // ------------------------------------------------------------------
  // Ko'rinish
  // ------------------------------------------------------------------
  function setMessage(type, key, params) {
    message = key ? { type, key, params } : null;
    renderMessage();
  }

  function renderMessage() {
    const isError = message && message.type === "error";
    const isInfo = message && message.type === "info";
    errorEl.hidden = !isError;
    infoEl.hidden = !isInfo;
    errorEl.textContent = isError ? t(message.key, message.params) : "";
    infoEl.textContent = isInfo ? t(message.key, message.params) : "";
  }

  function renderResend() {
    const left = Math.max(0, Math.ceil((cooldownUntil - Date.now()) / 1000));
    resendBtn.disabled = left > 0;
    resendBtn.textContent = left > 0 ? t("verify.resend.wait", { s: left }) : t("verify.resend");
  }

  function startCooldown() {
    cooldownUntil = Date.now() + RESEND_COOLDOWN * 1000;
    clearInterval(cooldownTimer);
    cooldownTimer = setInterval(() => {
      renderResend();
      if (Date.now() >= cooldownUntil) clearInterval(cooldownTimer);
    }, 1000);
    renderResend();
  }

  function render() {
    const cfg = MODES[mode];
    titleEl.textContent = t(cfg.title);
    subEl.textContent = t(cfg.sub, { email: pendingEmail });
    submitBtn.textContent = busy ? t("login.busy") : t(cfg.submit);
    usernameLabel.textContent = t(mode === "login" ? "login.id" : "login.username");
    passwordLabel.textContent = t(mode === "reset" ? "reset.newpassword" : "login.password");
    document.body.dataset.titleKey = cfg.title;
    document.title = t(cfg.title);

    form.querySelectorAll("[data-field]").forEach((el) => {
      el.hidden = !cfg.fields.includes(el.dataset.field);
    });
    const hasPassword = cfg.fields.includes("password");
    showPasswordWrap.hidden = !hasPassword;
    regHint.hidden = mode !== "register";
    tabsEl.hidden = !cfg.tabs;
    guestBlock.hidden = !cfg.tabs;
    forgotLink.hidden = mode !== "login";
    backLink.hidden = !cfg.back;
    resendBtn.hidden = !cfg.resend;
    passwordLabel.parentElement.querySelector("input").autocomplete =
      mode === "login" ? "current-password" : "new-password";

    tabsEl.querySelectorAll(".tabs__btn").forEach((b) => {
      const active = b.dataset.mode === mode;
      b.classList.toggle("is-active", active);
      b.setAttribute("aria-selected", active ? "true" : "false");
    });

    renderResend();
    renderMessage();
  }

  function setMode(next, keepMessage) {
    mode = next;
    if (!keepMessage) message = null;
    ["password", "confirm", "code"].forEach((k) => (els[k].value = ""));
    showPassword.checked = false;
    els.password.type = els.confirm.type = "password";
    render();
    const first = form.querySelector("[data-field]:not([hidden]) input");
    if (first) first.focus();
  }

  document.addEventListener("langchange", render);

  tabsEl.querySelectorAll(".tabs__btn").forEach((b) =>
    b.addEventListener("click", () => setMode(b.dataset.mode))
  );
  forgotLink.addEventListener("click", () => setMode("forgot"));
  backLink.addEventListener("click", () => setMode("login"));

  showPassword.addEventListener("change", () => {
    els.password.type = els.confirm.type = showPassword.checked ? "text" : "password";
  });

  // Faqat raqamlar
  els.code.addEventListener("input", () => {
    els.code.value = els.code.value.replace(/\D/g, "").slice(0, 6);
  });

  // ------------------------------------------------------------------
  // So'rovlar
  // ------------------------------------------------------------------
  async function post(url, payload) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...payload, lang: I18N.lang }),
    });
    let data = {};
    try {
      data = await res.json();
    } catch (err) {
      /* JSON emas */
    }
    return { ok: res.ok, status: res.status, data };
  }

  function setBusy(value) {
    busy = value;
    submitBtn.disabled = value;
    submitBtn.textContent = value ? t("login.busy") : t(MODES[mode].submit);
  }

  // Server xato kodlarini tarjima kalitiga aylantirish
  function errorKey(res, scope) {
    const code = res.data && res.data.error;
    if (res.status === 429 && code === "wait") return "verify.err.wait";
    if (res.status === 429) return scope === "login" ? "login.err.too_many" : "reg.err.too_many";
    const map = {
      invalid: "login.err.invalid",
      blocked: "login.err.blocked",
      username: "reg.err.username",
      password: "reg.err.password",
      email: "reg.err.email",
      exists: "reg.err.exists",
      email_exists: "reg.err.email_exists",
      code: "verify.err.code",
      expired: "verify.err.expired",
      mail_failed: "verify.err.mail",
    };
    return map[code] || "login.err.network";
  }

  function validate() {
    const username = els.username.value.trim();
    const email = els.email.value.trim();
    const password = els.password.value;
    if (mode === "login") return username && password ? null : "login.err.invalid";
    if (mode === "register") {
      if (!USERNAME_RE.test(username)) return "reg.err.username";
      if (!EMAIL_RE.test(email)) return "reg.err.email";
      if (password.length < 8) return "reg.err.password";
      if (password !== els.confirm.value) return "reg.err.mismatch";
    }
    if (mode === "forgot" && !EMAIL_RE.test(email)) return "reg.err.email";
    if (mode === "verify" || mode === "reset") {
      if (!/^\d{6}$/.test(els.code.value)) return "verify.err.code";
    }
    if (mode === "reset") {
      if (password.length < 8) return "reg.err.password";
      if (password !== els.confirm.value) return "reg.err.mismatch";
    }
    return null;
  }

  // Kod yuborilgach tasdiqlash oynasiga o'tish
  function goVerify(email, dev) {
    pendingEmail = email;
    setMode("verify", true);
    setMessage("info", dev ? "verify.dev" : "verify.sent");
    startCooldown();
  }

  async function submit() {
    const username = els.username.value.trim();
    const email = els.email.value.trim().toLowerCase();
    const password = els.password.value;

    if (mode === "login") {
      const res = await post("/api/login", { username, password });
      if (res.ok) return (window.location.href = res.data.role === "admin" ? "/admin" : "/");
      if (res.status === 403 && res.data.error === "unverified") {
        // Parol to'g'ri, lekin email tasdiqlanmagan: yangi kod yuboramiz
        pendingEmail = res.data.email;
        const sent = await post("/api/resend", { email: pendingEmail });
        goVerify(pendingEmail, sent.ok && sent.data.dev);
        if (!sent.ok && sent.data.error !== "wait") setMessage("error", errorKey(sent));
        else if (!sent.ok) setMessage("info", "verify.sent");
        return;
      }
      setMessage("error", errorKey(res, "login"));
      els.password.value = "";
      els.password.focus();
      return;
    }

    if (mode === "register") {
      const res = await post("/api/register", { username, email, password });
      if (res.ok) return goVerify(res.data.email, res.data.dev);
      if (res.status === 502) {
        // Hisob yaratildi, lekin xat ketmadi: qayta yuborish mumkin
        goVerify(res.data.email, false);
        setMessage("error", "verify.err.mail");
        return;
      }
      setMessage("error", errorKey(res));
      return;
    }

    if (mode === "verify") {
      const res = await post("/api/verify", { email: pendingEmail, code: els.code.value });
      if (res.ok) return (window.location.href = "/");
      setMessage("error", errorKey(res));
      els.code.value = "";
      els.code.focus();
      return;
    }

    if (mode === "forgot") {
      const res = await post("/api/forgot", { email });
      if (res.ok) {
        pendingEmail = email;
        setMode("reset", true);
        setMessage("info", res.data.dev ? "verify.dev" : "forgot.sent");
        return;
      }
      setMessage("error", errorKey(res));
      return;
    }

    if (mode === "reset") {
      const res = await post("/api/reset", { email: pendingEmail, code: els.code.value, password });
      if (res.ok) {
        setMode("login", true);
        setMessage("info", "reset.done");
        return;
      }
      setMessage("error", errorKey(res));
    }
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (busy) return;
    setMessage(null);
    const problem = validate();
    if (problem) return setMessage("error", problem);

    setBusy(true);
    try {
      await submit();
    } catch (err) {
      setMessage("error", "login.err.network");
    }
    setBusy(false);
  });

  resendBtn.addEventListener("click", async () => {
    if (Date.now() < cooldownUntil || !pendingEmail) return;
    setMessage(null);
    try {
      const res = await post("/api/resend", { email: pendingEmail });
      if (res.ok) {
        setMessage("info", res.data.dev ? "verify.dev" : "verify.sent");
        startCooldown();
      } else {
        setMessage("error", errorKey(res));
        if (res.data.error === "wait") startCooldown();
      }
    } catch (err) {
      setMessage("error", "login.err.network");
    }
  });

  render();
})();
