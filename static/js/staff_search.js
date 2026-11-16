// Admin Users page: the list updates while the admin types in the search box,
// without pressing Enter (#90). It loads the same page the form would and swaps
// in the tabs, the list and the selected account, so the box keeps its focus.
// Without JavaScript the form still searches on Enter.
(function () {
  "use strict";

  var form = document.querySelector(".staff-search");
  var input = document.getElementById("staff-search");
  if (!form || !input || !window.fetch || !window.DOMParser) return;

  var DELAY = 250;
  var timer = null;
  var latest = 0;
  var lastQuery = input.value.trim();

  function pageUrl() {
    var params = new URLSearchParams(new FormData(form));
    if (!params.get("q").trim()) params.delete("q");
    var query = params.toString();
    return form.action + (query ? "?" + query : "");
  }

  // Everything in the list card after the search form: the count, the rows,
  // the pages or the "No accounts found" box.
  function swapList(fresh) {
    var list = form.parentElement;
    var freshList = fresh.querySelector(".staff-list");
    if (!freshList) return;
    while (form.nextSibling) list.removeChild(form.nextSibling);
    var freshForm = freshList.querySelector(".staff-search");
    var node = freshForm ? freshForm.nextSibling : freshList.firstChild;
    while (node) {
      var next = node.nextSibling;
      list.appendChild(document.importNode(node, true));
      node = next;
    }
  }

  function swap(selector, fresh, parent) {
    var current = document.querySelector(selector);
    var replacement = fresh.querySelector(selector);
    if (current && replacement) {
      current.replaceWith(document.importNode(replacement, true));
    } else if (current) {
      current.remove();
    } else if (replacement && parent) {
      parent.appendChild(document.importNode(replacement, true));
    }
  }

  function search() {
    var query = input.value.trim();
    if (query === lastQuery) return;
    lastQuery = query;
    var url = pageUrl();
    var mine = ++latest;
    fetch(url, { headers: { "X-Requested-With": "fetch" }, credentials: "same-origin" })
      .then(function (response) {
        return response.ok ? response.text() : null;
      })
      .then(function (html) {
        // Drop answers to an older search that came back late.
        if (!html || mine !== latest) return;
        var fresh = new DOMParser().parseFromString(html, "text/html");
        swap(".admin-tabs", fresh);
        swapList(fresh);
        swap(".staff-account", fresh, document.querySelector(".staff-layout"));
        var title = fresh.querySelector("title");
        if (title) document.title = title.textContent;
        window.history.replaceState(null, "", url);
      })
      .catch(function () {
        // Offline or the server is down: Enter still submits the form.
      });
  }

  input.addEventListener("input", function () {
    window.clearTimeout(timer);
    timer = window.setTimeout(search, DELAY);
  });

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    window.clearTimeout(timer);
    lastQuery = null;
    search();
  });
})();
