// Find caregivers page: location suggestions (neighborhoods + NYC GeoSearch
// addresses), "Use my current location", filters and the map toggle.
(function () {
  "use strict";

  var AUTOCOMPLETE_URL = "https://geosearch.planninglabs.nyc/v2/autocomplete";
  var form = document.getElementById("caregiver-search");
  var input = document.getElementById("search-location");
  var list = document.getElementById("location-suggestions");
  var lat = document.getElementById("search-lat");
  var lng = document.getElementById("search-lng");
  var here = document.getElementById("search-here");
  var mapInput = document.getElementById("search-map");
  var neighborhoods = JSON.parse(document.getElementById("neighborhood-options").textContent);
  var timer = null;
  var latest = 0;

  function readJSON(id) {
    var element = document.getElementById(id);
    return element ? JSON.parse(element.textContent) : null;
  }

  // ---------- Location suggestions ----------
  function hideSuggestions() {
    list.hidden = true;
    list.replaceChildren();
    input.setAttribute("aria-expanded", "false");
  }

  // "70 WASHINGTON SQUARE SOUTH" -> "70 Washington Square South"
  function titleCase(text) {
    return text.toLowerCase().replace(/\b[a-z]/g, function (c) { return c.toUpperCase(); });
  }

  function choose(label, latitude, longitude) {
    input.value = label;
    lat.value = latitude;
    lng.value = longitude;
    here.value = "";
    hideSuggestions();
    form.submit();
  }

  function addOption(text, kind, onPick) {
    var item = document.createElement("li");
    item.setAttribute("role", "option");
    item.id = "suggestion-" + list.children.length;
    var label = document.createElement("span");
    label.textContent = text;
    var tag = document.createElement("span");
    tag.className = "suggestion-kind";
    tag.textContent = kind;
    item.append(label, tag);
    item.addEventListener("mousedown", function (event) {
      event.preventDefault();
      onPick();
    });
    list.appendChild(item);
  }

  function showSuggestions(text, features) {
    list.replaceChildren();
    var query = text.toLowerCase();
    neighborhoods
      .filter(function (n) { return n.label.toLowerCase().indexOf(query) !== -1; })
      .slice(0, 4)
      .forEach(function (n) {
        addOption(n.label, "Neighborhood", function () { choose(n.label, n.latitude, n.longitude); });
      });
    features.slice(0, 4).forEach(function (feature) {
      var coords = feature.geometry.coordinates;
      var label = feature.properties.label.replace(/, USA$/, "");
      addOption(label, "Address", function () {
        choose(titleCase(feature.properties.label.split(",")[0]), coords[1], coords[0]);
      });
    });
    var count = list.children.length;
    list.hidden = count === 0;
    input.setAttribute("aria-expanded", String(count > 0));
  }

  if (input) {
    input.addEventListener("input", function () {
      // Typing forgets the coordinates of the last pick.
      lat.value = "";
      lng.value = "";
      here.value = "";
      clearTimeout(timer);
      var text = input.value.trim();
      if (text.length < 2) { hideSuggestions(); return; }
      showSuggestions(text, []);
      // Only look up street addresses once there's a house number.
      if (!/\d/.test(text) || /^\d{1,5}$/.test(text)) return;
      timer = setTimeout(function () {
        var request = ++latest;
        fetch(AUTOCOMPLETE_URL + "?text=" + encodeURIComponent(text))
          .then(function (response) { return response.json(); })
          .then(function (data) {
            if (request === latest) showSuggestions(text, data.features || []);
          })
          .catch(function () {}); // the server still looks the place up on submit
      }, 250);
    });
    input.addEventListener("blur", hideSuggestions);
    input.addEventListener("keydown", function (event) {
      if (event.key === "Escape") hideSuggestions();
    });
  }

  // ---------- Use my current location ----------
  var locate = document.getElementById("use-current-location");
  var status = document.getElementById("current-location-status");
  if (locate && "geolocation" in navigator) {
    locate.hidden = false;
    locate.addEventListener("click", function () {
      status.textContent = "Finding your location…";
      locate.disabled = true;
      navigator.geolocation.getCurrentPosition(
        function (position) {
          input.value = "";
          lat.value = position.coords.latitude.toFixed(3);
          lng.value = position.coords.longitude.toFixed(3);
          here.value = "1";
          form.submit();
        },
        function () {
          locate.disabled = false;
          status.textContent = "We couldn't get your location. Check your browser's location permission.";
        },
        { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 }
      );
    });
  }

  // ---------- Filters ----------
  // Changing a filter or the sort runs the search again right away.
  document.querySelectorAll("[data-autosubmit]").forEach(function (select) {
    select.addEventListener("change", function () {
      // Leave out an empty map field so the address stays clean.
      select.form.querySelectorAll("input[name=map]").forEach(function (field) {
        field.disabled = !field.value;
      });
      select.form.submit();
    });
  });

  // ---------- Map (hidden until the owner asks for it) ----------
  var toggle = document.getElementById("map-toggle");
  var panel = document.getElementById("map-panel");
  var layout = document.getElementById("search-layout");
  var data = readJSON("caregiver-map-data");
  var map = null;

  function drawMap() {
    if (map || typeof L === "undefined") return;
    map = L.map("caregiver-map", { scrollWheelZoom: false }).setView([40.7128, -74.006], 11);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 18,
      // OpenStreetMap blocks tile requests without a Referer, and Django's
      // default Referrer-Policy (same-origin) sends none to other sites.
      // Send just our origin (e.g. http://127.0.0.1:8000), never the page URL.
      referrerPolicy: "strict-origin-when-cross-origin",
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);

    var bounds = [];
    if (data.origin) {
      var origin = [data.origin.latitude, data.origin.longitude];
      L.circleMarker(origin, { radius: 8, color: "#1c1a1a", fillColor: "#f4a27a", fillOpacity: 1, weight: 2 })
        .addTo(map).bindTooltip("You searched here");
      bounds.push(origin);
    }
    data.points.forEach(function (point) {
      var spot = [point.latitude, point.longitude];
      var marker = L.marker(spot).addTo(map);
      var link = document.createElement("a");
      link.href = point.url;
      link.textContent = point.name;
      marker.bindPopup(link);
      var card = document.getElementById("caregiver-" + point.id);
      marker.on("click", function () {
        if (!card) return;
        document.querySelectorAll(".caregiver-result.is-highlighted").forEach(function (c) {
          c.classList.remove("is-highlighted");
        });
        card.classList.add("is-highlighted");
        card.scrollIntoView({ behavior: "smooth", block: "nearest" });
      });
      if (card) card.addEventListener("mouseenter", function () { marker.openPopup(); });
      bounds.push(spot);
    });
    if (bounds.length > 1) map.fitBounds(bounds, { padding: [30, 30], maxZoom: 14 });
    else if (bounds.length === 1) map.setView(bounds[0], 13);
  }

  function setMap(open) {
    panel.hidden = !open;
    layout.classList.toggle("with-map", open);
    toggle.textContent = open ? "Hide map" : "Show map";
    toggle.setAttribute("aria-expanded", String(open));
    mapInput.value = open ? "1" : "";
    // Keep the choice when the owner searches again or reloads.
    var url = new URL(window.location.href);
    if (open) url.searchParams.set("map", "1");
    else url.searchParams.delete("map");
    window.history.replaceState(null, "", url);
    document.querySelectorAll("#caregiver-filters input[name=map]").forEach(function (field) {
      field.value = open ? "1" : "";
    });
    // The service chips are links, so they carry the map choice too.
    document.querySelectorAll(".filter-chip").forEach(function (chip) {
      var target = new URL(chip.href);
      if (open) target.searchParams.set("map", "1");
      else target.searchParams.delete("map");
      chip.href = target.toString();
    });
    if (open) {
      drawMap();
      if (map) map.invalidateSize();
    }
  }

  if (toggle && panel && data && typeof L !== "undefined") {
    toggle.hidden = false;
    toggle.addEventListener("click", function () { setMap(panel.hidden); });
    if (!panel.hidden) drawMap();
  }
})();
