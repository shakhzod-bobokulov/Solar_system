/* Barcha sahifalar uchun umumiy: mavzu (dark/light) va chiqish tugmasi. */
(() => {
  "use strict";

  const root = document.documentElement;
  const THEME_KEY = "spd-theme";

  function storedTheme() {
    try {
      return localStorage.getItem(THEME_KEY);
    } catch (e) {
      return null;
    }
  }

  const saved = storedTheme();
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  root.setAttribute("data-theme", saved || (prefersDark ? "dark" : "light"));

  const themeToggle = document.getElementById("themeToggle");
  if (themeToggle) {
    themeToggle.addEventListener("click", () => {
      const next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try {
        localStorage.setItem(THEME_KEY, next);
      } catch (e) {
        /* ixtiyoriy */
      }
    });
  }

  const logoutBtn = document.getElementById("logoutBtn");
  if (logoutBtn) {
    logoutBtn.addEventListener("click", async () => {
      try {
        await fetch("/api/logout", { method: "POST" });
      } finally {
        window.location.href = "/login";
      }
    });
  }

  // PWA: service worker (HTTPS yoki localhost'da ishlaydi; qo'llab-quvvatlanmasa, e'tiborsiz qoldiriladi)
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {});
    });
  }
})();

/* ===================================================================
   Animatsiyalar: raqamlarni sanash va elementlarning ketma-ket paydo bo'lishi.
   "Harakatni kamaytirish" yoqilgan bo'lsa, hammasi darhol ko'rinadi.
   =================================================================== */
(() => {
  "use strict";

  const reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  window.Anim = {
    /** Raqamni joriy qiymatdan `target` gacha silliq sanaydi. format(n) matn qaytaradi. */
    count(el, target, format = (n) => String(Math.round(n)), duration = 800) {
      const from = typeof el._animVal === "number" ? el._animVal : 0;
      el._animVal = target;
      cancelAnimationFrame(el._animRaf);
      clearTimeout(el._animTimer);
      // Yashirin tabda requestAnimationFrame to'xtaydi — yakuniy qiymat baribir qo'yilsin
      el._animTimer = setTimeout(() => {
        if (el._animVal === target) el.textContent = format(target);
      }, duration + 150);
      if (reduceMotion || from === target) {
        el.textContent = format(target);
        return;
      }
      const t0 = performance.now();
      const step = (now) => {
        const p = Math.min(1, (now - t0) / duration);
        const eased = 1 - Math.pow(1 - p, 3); // easeOutCubic
        el.textContent = format(from + (target - from) * eased);
        if (p < 1) el._animRaf = requestAnimationFrame(step);
        else el.textContent = format(target);
      };
      el._animRaf = requestAnimationFrame(step);
    },

    /** Qiymat 0 dan katta bo'lsa sanaydi, aks holda "–" ko'rsatadi. */
    countOrDash(el, target, format, duration) {
      if (target > 0) return this.count(el, target, format, duration);
      el._animVal = 0;
      cancelAnimationFrame(el._animRaf);
      el.textContent = "–";
    },
  };

  if (reduceMotion || !("IntersectionObserver" in window)) return;

  // Ko'rinish maydoniga kirganda sekin paydo bo'ladigan elementlar
  const SELECTOR = ".hero, .detect__card, .steps li, .upload-head, .dropzone, .stats .stat, .kpi, .card, .section__head, .results-grid, .table-wrap, .panel-card";
  document.documentElement.classList.add("js");

  const targets = Array.from(document.querySelectorAll(SELECTOR)).filter(
    (el) => !(el.matches(".table-wrap") && el.closest(".card")) // karta ichidagi jadvalda ikki marta animatsiya bo'lmasin
  );

  let fired = false;
  const io = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        fired = true;
        const el = entry.target;
        io.unobserve(el);
        el.classList.add("is-in");
        // Animatsiyadan keyin sinfni olib tashlaymiz: hover o'tishlariga xalaqit bermasligi uchun
        setTimeout(() => el.classList.remove("reveal", "is-in"), 1100);
      });
    },
    { threshold: 0.06, rootMargin: "0px 0px -4% 0px" }
  );

  // Zaxira: sahifa ko'rinib turibdi, lekin observer ishlamadi — animatsiyasiz hammasini ko'rsatamiz
  setTimeout(() => {
    if (!fired && document.visibilityState === "visible") document.documentElement.classList.remove("js");
  }, 3000);

  targets.forEach((el) => {
    const siblings = Array.from(el.parentElement.children).filter((c) => targets.includes(c));
    el.style.setProperty("--d", `${Math.min(siblings.indexOf(el), 7) * 70}ms`);
    el.classList.add("reveal");
    io.observe(el);
  });
})();
