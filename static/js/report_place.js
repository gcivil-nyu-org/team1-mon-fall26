// Explore: "Report wrong info" opens the report form in a pop-up (Figma
// "Report wrong info"), sends it in the background, then shows "Report sent".
// Works like reporting a message (report_message.js); without JavaScript the
// link opens the form as a page.
(function () {
  "use strict";

  var dialog = document.getElementById("report-dialog");
  if (!dialog || typeof dialog.showModal !== "function") return;

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

  document.addEventListener("click", function (event) {
    var link = event.target.closest("[data-report-place]");
    if (!link) return;
    event.preventDefault();
    send(link.href).then(show).catch(function () { window.location.assign(link.href); });
  });

  dialog.addEventListener("submit", function (event) {
    var form = event.target.closest("[data-report-form]");
    if (!form) return;
    event.preventDefault();
    var button = form.querySelector('button[type="submit"]');
    if (button) button.disabled = true;
    send(form.action, { method: "POST", body: new FormData(form) })
      .then(show)
      .catch(function () { form.submit(); });
  });

  dialog.addEventListener("click", function (event) {
    if (event.target.closest("[data-close-report]")) {
      event.preventDefault();
      dialog.close();
    } else if (event.target.closest("[data-report-done]")) {
      // Reload so the place shows its "Reported" tag.
      window.location.reload();
    } else if (event.target === dialog) {
      dialog.close();
    }
  });
})();
