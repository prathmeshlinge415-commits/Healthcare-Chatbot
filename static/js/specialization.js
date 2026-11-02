(function () {
  var search = document.getElementById("specSearch"), cards = Array.prototype.slice.call(document.querySelectorAll(".spec"));
  var count = document.getElementById("specCount"), empty = document.getElementById("specEmpty");
  if (search) search.addEventListener("input", function () {
    var q = search.value.trim().toLowerCase(), n = 0;
    cards.forEach(function (c) { var ok = !q || c.dataset.search.indexOf(q) !== -1; c.hidden = !ok; if (ok) n++; });
    empty.hidden = n > 0; count.textContent = q ? n + " specialties match" : "";
  });

  var dlg = document.getElementById("doctorsDialog"), list = document.getElementById("doctorsList"), title = document.getElementById("dlgTitle");
  function esc(s) { var d = document.createElement("div"); d.textContent = s == null ? "" : s; return d.innerHTML; }
  document.querySelectorAll("[data-doctors]").forEach(function (b) {
    b.addEventListener("click", function () {
      title.textContent = b.dataset.name + " - doctors"; list.innerHTML = "<p>Loading…</p>";
      if (dlg.showModal) dlg.showModal(); else dlg.setAttribute("open", "");
      fetch("/api/specialists?specialty=" + encodeURIComponent(b.dataset.doctors)).then(function (r) { return r.json(); }).then(function (d) {
        if (!d.success) { list.innerHTML = "<p>Could not load doctors.</p>"; return; }
        if (!d.doctors.length) { list.innerHTML = "<p class='muted'>No doctors are registered for this specialty yet. You can still request an appointment.</p>"; }
        else list.innerHTML = d.doctors.map(function (x) {
          return "<div class='card'><b>Dr. " + esc(x.first_name + " " + (x.last_name || "")) + "</b><br><span class='muted small'>" + esc(x.qualifications || "") +
            (x.experience_years ? " · " + esc(x.experience_years) + " yrs experience" : "") + "</span></div>";
        }).join("");
        list.innerHTML += "<p class='gap-top'><a class='btn btn-primary' href='/appointment?specialty=" + encodeURIComponent(b.dataset.doctors) + "'>Book appointment</a></p>";
      }).catch(function () { list.innerHTML = "<p>Could not load doctors. Please try again.</p>"; });
    });
  });
  var close = document.getElementById("dlgClose"); if (close) close.addEventListener("click", function () { dlg.close(); });

  var form = document.getElementById("doctorForm");
  if (form) form.addEventListener("submit", function (e) {
    e.preventDefault();
    var g = function (id) { return document.getElementById(id).value; }, msg = document.getElementById("doctorMsg");
    fetch(form.dataset.url, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": form.dataset.csrf },
      body: JSON.stringify({ first_name: g("d_first"), last_name: g("d_last"), specialty: g("d_spec"), experience_years: g("d_exp"), email: g("d_email"), phone: g("d_phone"), qualifications: g("d_qual") }) })
      .then(function (r) { return r.json(); }).then(function (d) { msg.textContent = d.success ? "Doctor added ✓" : d.message; if (d.success) form.reset(); })
      .catch(function () { msg.textContent = "Network error."; });
  });
})();
