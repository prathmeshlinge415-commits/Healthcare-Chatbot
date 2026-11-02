// Hospital finder: Leaflet + OpenStreetMap tiles, Nominatim (search), Overpass (hospital data). No API keys needed.
(function () {
  var OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"];
  var map, userMarker, layer, current = { lat: null, lon: null }, places = [];
  var status = document.getElementById("statusMsg"), results = document.getElementById("results");
  var typeSel = document.getElementById("typeSelect"), radiusSel = document.getElementById("radiusSelect");
  var TAGS = { hospital: '["amenity"="hospital"]', clinic: '["amenity"~"^(clinic|doctors)$"]', pharmacy: '["amenity"="pharmacy"]' };

  function initMap() {
    if (typeof L === "undefined") {  // Leaflet CDN blocked/offline
      document.getElementById("map").textContent = "The map could not be loaded. Check your internet connection and refresh.";
      return false;
    }
    map = L.map("map").setView([20.5937, 78.9629], 5);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "&copy; OpenStreetMap contributors" }).addTo(map);
    layer = L.layerGroup().addTo(map);
    return true;
  }
  function say(msg) { status.textContent = msg; }
  function km(a, b, c, d) {
    var r = 6371, p = Math.PI / 180, dl = (c - a) * p, dn = (d - b) * p;
    var x = Math.sin(dl / 2) * Math.sin(dl / 2) + Math.cos(a * p) * Math.cos(c * p) * Math.sin(dn / 2) * Math.sin(dn / 2);
    return 2 * r * Math.atan2(Math.sqrt(x), Math.sqrt(1 - x));
  }
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text) e.textContent = text; return e; }

  function geocode(q) {
    return fetch("https://nominatim.openstreetmap.org/search?format=json&limit=1&q=" + encodeURIComponent(q)).then(function (r) { return r.json(); })
      .then(function (d) { if (!d.length) throw new Error("not-found"); return { lat: +d[0].lat, lon: +d[0].lon, label: d[0].display_name }; });
  }
  function overpass(lat, lon, radius, type, i) {
    var tag = TAGS[type] || TAGS.hospital;
    var q = "[out:json][timeout:25];nwr" + tag + "(around:" + radius + "," + lat + "," + lon + ");out center tags 80;";
    return fetch(OVERPASS[i || 0], { method: "POST", body: "data=" + encodeURIComponent(q), headers: { "Content-Type": "application/x-www-form-urlencoded" } })
      .then(function (r) { if (!r.ok) throw new Error("overpass " + r.status); return r.json(); })
      .catch(function (e) { if ((i || 0) + 1 < OVERPASS.length) return overpass(lat, lon, radius, type, (i || 0) + 1); throw e; });
  }
  function parse(data, lat, lon) {
    return (data.elements || []).map(function (e) {
      var t = e.tags || {}, la = e.lat || (e.center && e.center.lat), lo = e.lon || (e.center && e.center.lon);
      if (!la || !lo) return null;
      var addr = [t["addr:housename"], t["addr:housenumber"], t["addr:street"], t["addr:suburb"], t["addr:city"] || t["addr:town"] || t["addr:village"], t["addr:postcode"]].filter(Boolean).join(", ");
      return { name: t.name || t["name:en"] || "Unnamed (see map)", lat: la, lon: lo, addr: addr, phone: t.phone || t["contact:phone"] || "", hours: t.opening_hours || "",
        website: t.website || t["contact:website"] || "", emergency: t.emergency === "yes" || /emergency/i.test(t["healthcare:speciality"] || ""), dist: km(lat, lon, la, lo) };
    }).filter(Boolean).sort(function (a, b) { return a.dist - b.dist; });
  }
  function facets() { var f = {}; document.querySelectorAll("[data-facet]").forEach(function (c) { f[c.dataset.facet] = c.checked; }); return f; }
  function draw() {
    var f = facets(), shown = places.filter(function (p) { return (!f.emergency || p.emergency) && (!f.phone || p.phone) && (!f.hours || p.hours) && (!f.website || p.website); });
    layer.clearLayers(); results.innerHTML = "";
    if (!shown.length) { say(places.length ? "No results match the selected filters." : "No results found in this area. Try a larger radius."); return; }
    say(shown.length + " result" + (shown.length > 1 ? "s" : "") + " found, nearest first.");
    var pts = [];
    shown.forEach(function (p) {
      var dir = "https://www.google.com/maps/dir/?api=1&destination=" + p.lat + "," + p.lon;
      var card = el("div", "hosp"); card.appendChild(el("h3", "", p.name));
      card.appendChild(el("p", "muted", p.dist.toFixed(1) + " km away" + (p.emergency ? " · Emergency dept." : "")));
      card.appendChild(el("p", "", p.addr || "Address not listed"));
      if (p.phone) { var ph = el("p"); var a = el("a", "", "📞 " + p.phone); a.href = "tel:" + p.phone.replace(/[^+\d]/g, ""); ph.appendChild(a); card.appendChild(ph); } else card.appendChild(el("p", "muted", "Phone not listed"));
      if (p.hours) card.appendChild(el("p", "small", "🕒 " + p.hours));
      var row = el("div", "btn-row"), d = el("a", "btn btn-primary btn-sm", "🧭 Directions"); d.href = dir; d.target = "_blank"; d.rel = "noopener noreferrer"; row.appendChild(d);
      if (/^https?:\/\//i.test(p.website)) { var w = el("a", "btn btn-outline btn-sm", "Website"); w.href = p.website; w.target = "_blank"; w.rel = "noopener noreferrer"; row.appendChild(w); }
      card.appendChild(row); results.appendChild(card);
      var pop = el("div"); pop.appendChild(el("b", "", p.name)); pop.appendChild(el("br")); var pa = el("a", "", "Directions"); pa.href = dir; pa.target = "_blank"; pa.rel = "noopener noreferrer"; pop.appendChild(pa);
      L.marker([p.lat, p.lon]).bindPopup(pop).addTo(layer); pts.push([p.lat, p.lon]);
    });
    pts.push([current.lat, current.lon]); map.fitBounds(pts, { padding: [30, 30], maxZoom: 15 });
  }
  function load(lat, lon, label) {
    current = { lat: lat, lon: lon };
    if (userMarker) map.removeLayer(userMarker);
    userMarker = L.circleMarker([lat, lon], { radius: 9, color: "#0a7c8c", fillOpacity: .8 }).addTo(map).bindPopup(label || "Search centre");
    map.setView([lat, lon], 13); say("Searching…"); results.innerHTML = "";
    overpass(lat, lon, radiusSel.value, typeSel.value).then(function (d) { places = parse(d, lat, lon); draw(); })
      .catch(function () { say("The hospital data service is busy or unreachable. Please try again in a minute."); });
  }

  document.getElementById("searchForm").addEventListener("submit", function (e) {
    e.preventDefault(); var q = document.getElementById("locationInput").value.trim();
    if (!q) { say("Please type a city or area first."); return; }
    say("Finding location…");
    geocode(q).then(function (g) { load(g.lat, g.lon, g.label); }).catch(function (err) { say(err.message === "not-found" ? "We couldn't find that place. Try a nearby city name." : "Location search is unavailable right now. Please try again."); });
  });
  document.getElementById("useLocation").addEventListener("click", function () {
    if (!navigator.geolocation) { say("Your browser does not support location. Please type a city instead."); return; }
    say("Getting your location…");
    navigator.geolocation.getCurrentPosition(function (p) { load(p.coords.latitude, p.coords.longitude, "You are here"); },
      function () { say("We couldn't get your location. Please allow location access or type a city."); }, { timeout: 10000 });
  });
  [typeSel, radiusSel].forEach(function (s) { s.addEventListener("change", function () { if (current.lat !== null) load(current.lat, current.lon, "Search centre"); }); });
  document.querySelectorAll("[data-facet]").forEach(function (c) { c.addEventListener("change", function () { if (places.length) draw(); }); });
  if (!initMap()) { document.getElementById("statusMsg").textContent = "Map unavailable - results list will not load until the map loads."; }
})();
