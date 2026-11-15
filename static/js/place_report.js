// Explore: "Report wrong info" opens in a pop-up over the map (Figma "Report
// Wrong Info"), is sent in the background and shows "Report sent". Done
// closes it and the place shows "Reported". Without JavaScript the link
// opens the report page instead.
(function () {
  "use strict";

  var dialog = document.getElementById("report-dialog");
  if (!dialog || typeof dialog.showModal !== "function") return;
  var link = null;

  function send(url, options) {
    options = options || {};
    options.headers = { "X-Requested-With": "fetch" };
    options.credentials = "same-origin";
    return fetch(url, options).then(function (response) {
      if (!response.ok) throw new Error("report failed");
      return response.text();
    });
  }

  function show(html) {
    dialog.innerHTML = html;
    if (!dialog.open) dialog.showModal();
    var first = dialog.querySelector('input[type="radio"]:checked, input[type="radio"], [data-report-done]');
    if (first) first.focus();
  }

  function markReported() {
    if (!link) return;
    var tag = document.createElement("span");
    tag.className = "place-reported";
    tag.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M5 21V4"/><path d="M5 4h11l-2 4 2 4H5"/></svg> Reported';
    link.replaceWith(tag);
    link = null;
  }

  document.addEventListener("click", function (event) {
    var target = event.target.closest("[data-report-place]");
    if (!target) return;
    event.preventDefault();
    link = target;
    send(target.href).then(show).catch(function () { window.location.assign(target.href); });
  });

  dialog.addEventListener("submit", function (event) {
    var form = event.target.closest("[data-report-form]");
    if (!form) return;
    event.preventDefault();
    var button = form.querySelector('button[type="submit"]');
    if (button) button.disabled = true;
    send(form.action, { method: "POST", body: new FormData(form) })
      .then(function (html) {
        show(html);
        if (dialog.querySelector("[data-report-done]")) markReported();
      })
      .catch(function () { form.submit(); });
  });

  dialog.addEventListener("click", function (event) {
    if (event.target.closest("[data-close-report]") || event.target.closest("[data-report-done]")) {
      event.preventDefault();
      dialog.close();
    } else if (event.target === dialog) {
      dialog.close();
    }
  });
})();
