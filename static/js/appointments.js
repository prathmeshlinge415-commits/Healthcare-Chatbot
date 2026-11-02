(function () {
  // Reschedule toggles
  document.querySelectorAll("[data-resched]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var f = document.getElementById(btn.dataset.resched);
      f.hidden = !f.hidden;
      if (!f.hidden) f.querySelector("input").focus();
    });
  });
  // On the booking form: if the date is today, hide time slots that already passed.
  var date = document.getElementById("appointment_date"), time = document.getElementById("appointment_time");
  if (date && time) {
    var refresh = function () {
      var now = new Date(), today = now.getFullYear() + "-" + String(now.getMonth() + 1).padStart(2, "0") + "-" + String(now.getDate()).padStart(2, "0");
      var nowMin = now.getHours() * 60 + now.getMinutes();
      Array.prototype.forEach.call(time.options, function (o) {
        if (!o.value) return;
        var p = o.value.split(":"); o.disabled = date.value === today && (+p[0] * 60 + +p[1]) <= nowMin;
        if (o.disabled && o.selected) time.value = "";
      });
    };
    date.addEventListener("change", refresh); refresh();
  }
})();
