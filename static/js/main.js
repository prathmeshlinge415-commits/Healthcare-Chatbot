// Site-wide behaviour: theme toggle, mobile menu, alerts, loading buttons, confirm dialogs, password toggle.
(function () {
  var root = document.documentElement;
  var themeBtn = document.getElementById("themeToggle");
  function paint() {
    var dark = root.getAttribute("data-theme") === "dark";
    if (themeBtn) { themeBtn.textContent = dark ? "☀️" : "🌙"; themeBtn.setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode"); }
  }
  if (themeBtn) themeBtn.addEventListener("click", function () {
    var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    try { localStorage.setItem("theme", next); } catch (e) {}
    paint();
  });
  paint();

  var toggle = document.getElementById("navToggle"), nav = document.getElementById("mainNav");
  if (toggle && nav) toggle.addEventListener("click", function () {
    var open = nav.classList.toggle("open");
    toggle.setAttribute("aria-expanded", open); toggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
  });

  document.addEventListener("click", function (e) {
    if (e.target.classList.contains("alert-close")) e.target.parentElement.remove();
    var pw = e.target.closest("[data-toggle-pw]");
    if (pw) {
      var input = document.getElementById(pw.dataset.togglePw), show = input.type === "password";
      input.type = show ? "text" : "password"; pw.setAttribute("aria-label", show ? "Hide password" : "Show password");
    }
  });

  document.querySelectorAll("form[data-confirm]").forEach(function (f) {
    f.addEventListener("submit", function (e) { if (!window.confirm(f.dataset.confirm)) e.preventDefault(); });
  });
  document.querySelectorAll("form[data-loading]").forEach(function (f) {
    f.addEventListener("submit", function () {
      var b = f.querySelector('button[type="submit"]');
      if (b) { b.dataset.label = b.textContent; b.disabled = true; b.textContent = "Please wait…"; }
    });
  });
  window.addEventListener("pageshow", function () {  // restore buttons when coming back with the Back button
    document.querySelectorAll("form[data-loading] button[type=submit]").forEach(function (b) {
      if (b.dataset.label) { b.disabled = false; b.textContent = b.dataset.label; }
    });
  });
})();
