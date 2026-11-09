// Delete account pop-up on the profile pages (Figma "Delete Account … Warning").
// "Delete account" in the "…" menu opens it. The form is sent in the
// background: a wrong password shows its error in the pop-up, and a deleted
// account goes on to the "Account deleted" page.
(function () {
  "use strict";

  var dialog = document.getElementById("delete-account-dialog");
  if (!dialog || typeof dialog.showModal !== "function") return;

  function open(event) {
    event.preventDefault();
    var menu = event.target.closest("details");
    if (menu) menu.open = false;
    dialog.showModal();
    var input = dialog.querySelector('input[type="password"]');
    if (input) input.focus();
  }

  document.querySelectorAll("[data-open-delete-account]").forEach(function (link) {
    link.addEventListener("click", open);
  });

  // Clicking the dimmed area outside the card closes it, like Keep my account.
  dialog.addEventListener("click", function (event) {
    if (event.target === dialog) dialog.close();
  });

  dialog.addEventListener("click", function (event) {
    if (event.target.closest("[data-close-dialog]")) {
      event.preventDefault();
      dialog.close();
    }
  });

  dialog.addEventListener("submit", function (event) {
    var form = event.target.closest("[data-delete-account-form]");
    if (!form) return;
    event.preventDefault();
    var button = form.querySelector('button[type="submit"]');
    if (button) button.disabled = true;
    fetch(form.action, {
      method: "POST",
      body: new FormData(form),
      headers: { "X-Requested-With": "fetch" },
      credentials: "same-origin",
    })
      .then(function (response) {
        if (response.redirected) {
          window.location.assign(response.url);
          return null;
        }
        return response.text();
      })
      .then(function (html) {
        if (html === null) return;
        dialog.innerHTML = html;
        var input = dialog.querySelector('input[type="password"]');
        if (input) input.focus();
      })
      .catch(function () {
        // Fall back to a normal page load if the background request fails.
        form.submit();
      });
  });
})();
