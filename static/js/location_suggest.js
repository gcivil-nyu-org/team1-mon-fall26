// Location suggestions for care posts, like the Explore search: NYC
// neighborhoods as you type, plus street addresses from NYC GeoSearch once
// there's a house number. Picking one fills the box (nothing is submitted).
(function () {
  "use strict";

  var AUTOCOMPLETE_URL = "https://geosearch.planninglabs.nyc/v2/autocomplete";
  var data = document.getElementById("neighborhood-options");
  var neighborhoods = data ? JSON.parse(data.textContent) : [];

  // "214 7 AVENUE" -> "214 7 Avenue"
  function titleCase(text) {
    return text.toLowerCase().replace(/\b[a-z]/g, function (c) { return c.toUpperCase(); });
  }

  function setUp(field) {
    var input = field.querySelector("input");
    var list = field.querySelector(".co-suggestions");
    if (!input || !list) return;
    var timer = null;
    var latest = 0;
    var active = -1;

    input.setAttribute("role", "combobox");
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-expanded", "false");
    input.setAttribute("aria-controls", list.id);
    input.setAttribute("autocomplete", "off");

    function hide() {
      list.hidden = true;
      list.replaceChildren();
      active = -1;
      input.setAttribute("aria-expanded", "false");
      input.removeAttribute("aria-activedescendant");
    }

    function pick(text) {
      input.value = text;
      hide();
      input.dispatchEvent(new Event("change", { bubbles: true }));
    }

    function add(text, kind) {
      var item = document.createElement("li");
      item.setAttribute("role", "option");
      item.id = list.id + "-" + list.children.length;
      var label = document.createElement("span");
      label.textContent = text;
      var tag = document.createElement("span");
      tag.className = "co-suggestion-kind";
      tag.textContent = kind;
      item.append(label, tag);
      item.addEventListener("mousedown", function (event) {
        event.preventDefault();
        pick(text);
      });
      list.appendChild(item);
    }

    function show(text, features) {
      list.replaceChildren();
      active = -1;
      var query = text.toLowerCase();
      // Best matches first: "park" -> Park Slope before Bedford Park.
      function rank(label) {
        var lower = label.toLowerCase();
        if (lower.indexOf(query) === 0) return 0;
        if (lower.indexOf(" " + query) !== -1 || lower.indexOf("-" + query) !== -1) return 1;
        return 2;
      }
      neighborhoods
        .filter(function (n) { return n.label.toLowerCase().indexOf(query) !== -1; })
        .sort(function (a, b) { return rank(a.label) - rank(b.label); })
        .slice(0, 4)
        .forEach(function (n) { add(n.label, "Neighborhood"); });
      features.slice(0, 4).forEach(function (feature) {
        var props = feature.properties || {};
        var street = titleCase(props.name || (props.label || "").split(",")[0]);
        add(props.borough ? street + ", " + props.borough : street, "Address");
      });
      var count = list.children.length;
      list.hidden = count === 0;
      input.setAttribute("aria-expanded", String(count > 0));
    }

    function highlight(index) {
      var items = list.children;
      if (!items.length) return;
      active = (index + items.length) % items.length;
      Array.prototype.forEach.call(items, function (item, i) {
        item.classList.toggle("is-active", i === active);
        item.setAttribute("aria-selected", String(i === active));
      });
      input.setAttribute("aria-activedescendant", items[active].id);
    }

    input.addEventListener("input", function () {
      clearTimeout(timer);
      var text = input.value.trim();
      if (text.length < 2) { hide(); return; }
      show(text, []);
      // Only look up street addresses once there's a house number.
      if (!/\d/.test(text) || /^\d{1,5}$/.test(text)) return;
      timer = setTimeout(function () {
        var request = ++latest;
        fetch(AUTOCOMPLETE_URL + "?text=" + encodeURIComponent(text))
          .then(function (response) { return response.json(); })
          .then(function (result) {
            if (request === latest) show(text, result.features || []);
          })
          .catch(function () {}); // suggestions are optional; typing still works
      }, 250);
    });

    input.addEventListener("keydown", function (event) {
      if (list.hidden) return;
      if (event.key === "ArrowDown") { event.preventDefault(); highlight(active + 1); }
      else if (event.key === "ArrowUp") { event.preventDefault(); highlight(active - 1); }
      else if (event.key === "Enter" && active >= 0) {
        // Pick the highlighted suggestion instead of submitting the form.
        event.preventDefault();
        pick(list.children[active].firstChild.textContent);
      } else if (event.key === "Escape") { hide(); }
    });

    input.addEventListener("blur", hide);
  }

  document.querySelectorAll("[data-location-field]").forEach(setUp);
})();
