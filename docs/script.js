/* claude-code-teams landing page — minimal interactive bits */

(function () {
  // ── Theme toggle (persists in localStorage; respects system pref on first load) ──
  const root = document.documentElement;
  const KEY = "cct-theme";

  function applyTheme(theme) {
    root.setAttribute("data-theme", theme);
    try { localStorage.setItem(KEY, theme); } catch (_) {}
  }

  // First-paint priority: stored > system > dark default
  try {
    const stored = localStorage.getItem(KEY);
    if (stored === "light" || stored === "dark") {
      root.setAttribute("data-theme", stored);
    } else if (window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches) {
      root.setAttribute("data-theme", "light");
    }
  } catch (_) {}

  const toggle = document.getElementById("themeToggle");
  if (toggle) {
    toggle.addEventListener("click", () => {
      const cur = root.getAttribute("data-theme") || "dark";
      applyTheme(cur === "dark" ? "light" : "dark");
    });
  }

  // ── Add copy-to-clipboard buttons to <pre> blocks ──
  document.querySelectorAll("pre").forEach((pre) => {
    if (pre.closest(".terminal")) return; // skip the hero terminal — it's decorative

    const btn = document.createElement("button");
    btn.className = "copy-btn";
    btn.type = "button";
    btn.setAttribute("aria-label", "Copy code");
    btn.textContent = "Copy";

    pre.style.position = "relative";
    btn.style.cssText = `
      position: absolute;
      top: 0.6rem;
      right: 0.6rem;
      padding: 0.3rem 0.7rem;
      font-size: 0.75rem;
      font-weight: 500;
      color: var(--text-muted);
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 6px;
      cursor: pointer;
      opacity: 0;
      transition: opacity 180ms, color 180ms, border-color 180ms;
    `;

    pre.addEventListener("mouseenter", () => (btn.style.opacity = "1"));
    pre.addEventListener("mouseleave", () => (btn.style.opacity = "0"));
    btn.addEventListener("focus", () => (btn.style.opacity = "1"));

    btn.addEventListener("click", async () => {
      const text = pre.querySelector("code")?.textContent ?? pre.textContent ?? "";
      try {
        await navigator.clipboard.writeText(text);
        btn.textContent = "Copied";
        btn.style.color = "var(--green)";
        setTimeout(() => {
          btn.textContent = "Copy";
          btn.style.color = "var(--text-muted)";
        }, 1400);
      } catch (_) {
        btn.textContent = "Failed";
        setTimeout(() => (btn.textContent = "Copy"), 1400);
      }
    });

    pre.appendChild(btn);
  });

  // ── Subtle: highlight the topbar nav link for the section in view ──
  const sections = document.querySelectorAll("section[id]");
  const navLinks = document.querySelectorAll(".nav a[href^='#']");

  if ("IntersectionObserver" in window && sections.length) {
    const map = new Map();
    navLinks.forEach((a) => {
      const id = a.getAttribute("href")?.slice(1);
      if (id) map.set(id, a);
    });

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          const link = map.get(entry.target.id);
          if (!link) return;
          if (entry.isIntersecting) {
            navLinks.forEach((a) => a.style.color = "");
            link.style.color = "var(--text)";
          }
        });
      },
      { rootMargin: "-30% 0px -65% 0px" }
    );

    sections.forEach((s) => observer.observe(s));
  }
})();
