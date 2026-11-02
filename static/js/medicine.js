(function () {
  var input = document.getElementById("medicineSearch"), grid = document.getElementById("medicineGrid");
  if (!input || !grid) return;
  var cards = Array.prototype.slice.call(grid.querySelectorAll(".med")), count = document.getElementById("medCount"), empty = document.getElementById("medEmpty");
  var list = document.getElementById("medSuggest"), timer;
  function filter() {
    var q = input.value.trim().toLowerCase(), shown = 0;
    cards.forEach(function (c) { var ok = !q || c.dataset.search.indexOf(q) !== -1; c.hidden = !ok; if (ok) shown++; });
    count.textContent = "Showing " + shown + " of " + cards.length + " medicines"; empty.hidden = shown > 0;
  }
  function suggest() {
    var q = input.value.trim();
    if (!q) { list.innerHTML = ""; return; }
    fetch(input.dataset.suggest + "?q=" + encodeURIComponent(q)).then(function (r) { return r.json(); }).then(function (d) {
      list.innerHTML = "";
      (d.suggestions || []).forEach(function (n) { var o = document.createElement("option"); o.value = n; list.appendChild(o); });
    }).catch(function () {});
  }
  input.addEventListener("input", function () { filter(); clearTimeout(timer); timer = setTimeout(suggest, 200); });
  filter();
})();
