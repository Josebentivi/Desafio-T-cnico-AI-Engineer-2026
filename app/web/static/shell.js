(() => {
  const toggle = document.getElementById("nav-toggle");
  const navigation = document.getElementById("app-navigation");
  const backdrop = document.querySelector(".nav-backdrop");
  const mobile = window.matchMedia("(max-width: 1100px)");

  function setNavigation(open, restoreFocus = true) {
    document.body.classList.toggle("nav-open", open);
    toggle.setAttribute("aria-expanded", String(open));
    toggle.setAttribute("aria-label", open ? "Close navigation" : "Open navigation");
    backdrop.hidden = !open;
    navigation.inert = mobile.matches && !open;
    document.querySelector(".workspace").inert = open;
    if (open) navigation.querySelector("a").focus();
    else if (restoreFocus) toggle.focus();
  }

  toggle.addEventListener("click", () => setNavigation(!document.body.classList.contains("nav-open")));
  document.querySelectorAll("[data-close-nav]").forEach((button) => {
    button.addEventListener("click", () => setNavigation(false));
  });
  document.addEventListener("keydown", (event) => {
    if (!document.body.classList.contains("nav-open")) return;
    if (event.key === "Escape") setNavigation(false);
    if (event.key === "Tab") {
      const items = [...navigation.querySelectorAll("a, button")].filter((item) => item.getClientRects().length);
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault(); first.focus();
      }
    }
  });
  mobile.addEventListener("change", () => setNavigation(false, false));
  setNavigation(false, false);

  const history = document.querySelector(".history-toggle");
  if (history) {
    history.addEventListener("click", () => {
      const open = document.querySelector(".chat-sidebar").classList.toggle("history-open");
      history.setAttribute("aria-expanded", String(open));
      history.setAttribute("aria-label", open ? "Hide conversation history" : "Show conversation history");
    });
  }
})();
