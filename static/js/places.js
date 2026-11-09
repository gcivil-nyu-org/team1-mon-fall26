// Explore nearby, pet-friendly places: the map with a pin for each place, the
// list beside it and the detail card. Picking a place in the list or on the map
// shows its card without reloading the page. Without JavaScript the list items
// are plain links that do the same.
(function () {
  "use strict";

  var dataElement = document.getElementById("places-map-data");
  if (!dataElement) return;
  var data = JSON.parse(dataElement.textContent);
  var rows = document.querySelectorAll(".place-row");
  var cards = document.querySelectorAll(".place-detail");
  var mapElement = document.getElementById("places-map");
  var wide = window.matchMedia("(min-width: 861px)");
  var map = null;
  var markers = {};
  var selected = data.selected;

  // "Try another area" in the empty state jumps to the Location box.
  document.querySelectorAll("[data-focus-location]").forEach(function (link) {
    link.addEventListener("click", function (event) {
      var input = document.getElementById("search-location");
      if (!input) return;
      event.preventDefault();
      input.focus();
      input.select();
    });
  });

  function byId(id) {
    return data.places.filter(function (place) { return place.id === id; })[0];
  }

  function escapeHtml(text) {
    var div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  // The list already has each category's icon; the pins reuse it.
  function iconFor(place) {
    var row = document.querySelector('.place-row[data-place="' + place.id + '"] .place-icon');
    return row ? row.innerHTML : "";
  }

  function pinIcon(place, isSelected) {
    var html =
      '<span class="map-pin cat-' + place.category + (isSelected ? " is-selected" : "") + '">' +
      (isSelected ? '<span class="map-pin-label">' + escapeHtml(place.name) + "</span>" : "") +
      '<span class="map-pin-dot">' + iconFor(place) + "</span></span>";
    return L.divIcon({ className: "place-marker", html: html, iconSize: [0, 0] });
  }

  // Keep the picked place, and its name label, clear of the list (left) and
  // the card (bottom right).
  function padding() {
    return wide.matches
      ? { paddingTopLeft: [480, 80], paddingBottomRight: [420, 300] }
      : { padding: [40, 40] };
  }

  function select(id, options) {
    options = options || {};
    var previous = selected;
    selected = id;
    rows.forEach(function (row) {
      var on = Number(row.dataset.place) === id;
      row.classList.toggle("is-selected", on);
      if (on) row.setAttribute("aria-current", "true");
      else row.removeAttribute("aria-current");
      if (on && options.scrollList) row.scrollIntoView({ block: "nearest" });
    });
    cards.forEach(function (card) {
      card.hidden = Number(card.dataset.place) !== id;
    });
    if (map) {
      [previous, id].forEach(function (key) {
        var marker = markers[key];
        if (!marker) return;
        marker.setIcon(pinIcon(byId(key), key === id));
        marker.setZIndexOffset(key === id ? 1000 : 0);
      });
      if (options.pan && markers[id]) map.panInside(markers[id].getLatLng(), padding());
    }
    var url = new URL(window.location.href);
    url.searchParams.set("place", id);
    window.history.replaceState(null, "", url);
  }

  rows.forEach(function (row) {
    row.addEventListener("click", function (event) {
      event.preventDefault();
      select(Number(row.dataset.place), { pan: true });
    });
  });

  if (!mapElement || typeof L === "undefined") return;

  map = L.map(mapElement, {
    // Zoom with a trackpad pinch or the mouse wheel, as well as the +/- buttons.
    scrollWheelZoom: true,
    zoomControl: false,
    attributionControl: false,
    zoomSnap: 0.5,
  });
  L.control.zoom({ position: "topleft" }).addTo(map);
  L.control.attribution({ position: "bottomleft", prefix: '<a href="https://leafletjs.com">Leaflet</a>' }).addTo(map);
  // CARTO Voyager, as in the design. CARTO needs a (free) key; without one,
  // a quiet light gray Esri map (soft roads, no shop icons, names on top).
  if (data.carto_key) {
    L.tileLayer(
      "https://basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png?key=" +
        encodeURIComponent(data.carto_key),
      {
        maxZoom: 19,
        attribution:
          '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, ' +
          '&copy; <a href="https://carto.com/attributions">CARTO</a>',
      }
    ).addTo(map);
  } else {
    var esri = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/";
    var tiles = { maxZoom: 19, maxNativeZoom: 16 };
    L.tileLayer(esri + "World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}", L.extend({
      className: "places-base-tiles",
      attribution:
        'Map &copy; <a href="https://www.esri.com">Esri</a>, HERE, Garmin, ' +
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }, tiles)).addTo(map);
    L.tileLayer(esri + "World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}", tiles).addTo(map);
  }

  // Smaller pins when zoomed out, so nearby places don't pile up.
  function sizePins() {
    mapElement.classList.toggle("is-far", map.getZoom() < 15);
  }
  map.on("zoomend", sizePins);

  var bounds = [];
  if (data.origin) {
    var origin = [data.origin.latitude, data.origin.longitude];
    L.marker(origin, {
      icon: L.divIcon({ className: "origin-marker", html: '<span class="origin-dot"></span>', iconSize: [0, 0] }),
      keyboard: false,
      interactive: false,
    }).addTo(map);
    bounds.push(origin);
  }
  data.places.forEach(function (place) {
    var spot = [place.latitude, place.longitude];
    var isSelected = place.id === selected;
    var marker = L.marker(spot, {
      icon: pinIcon(place, isSelected),
      title: place.name,
      alt: place.name,
      zIndexOffset: isSelected ? 1000 : 0,
    }).addTo(map);
    marker.on("click", function () { select(place.id, { scrollList: true }); });
    markers[place.id] = marker;
    bounds.push(spot);
  });

  // Open at street level around where the owner searched from, as in the
  // design: closest for 1 mi, a little further out for larger distances, but
  // never so far that the streets disappear. Places outside the view are still
  // in the list, and picking one moves the map to it.
  var STREET_ZOOM = { 1: 16, 2: 15.5, 5: 15, 10: 14.5 };
  if (data.origin) {
    map.setView([data.origin.latitude, data.origin.longitude], STREET_ZOOM[data.distance] || 15);
  } else if (bounds.length > 1) {
    // No search yet: show every place, leaving room for the list.
    var fit = wide.matches
      ? { paddingTopLeft: [400, 50], paddingBottomRight: [50, 50] }
      : { padding: [30, 30] };
    fit.maxZoom = 16;
    map.fitBounds(bounds, fit);
  } else {
    map.setView(bounds[0], 15);
  }
  if (markers[selected]) map.panInside(markers[selected].getLatLng(), padding());
  sizePins();
})();
