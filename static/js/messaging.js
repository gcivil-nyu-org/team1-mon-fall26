// Messages page: start at the newest message, avoid double sends, and show
// new messages (like care updates during a booking) without a manual refresh.
(function () {
  "use strict";

  var list = document.getElementById("chat-messages");
  var form = document.getElementById("chat-composer");
  var input = document.getElementById("chat-input");
  if (!list || !form) return;

  list.scrollTop = list.scrollHeight;

  form.addEventListener("submit", function (event) {
    if (!input.value.trim()) {
      event.preventDefault();
      input.focus();
      return;
    }
    form.querySelector("button[type=submit]").disabled = true;
  });

  // Check for new messages every few seconds while the page is open. Reload
  // only when nothing is being typed, so a draft is never lost.
  var known = list.dataset.latest;
  var url = list.dataset.latestUrl;
  setInterval(function () {
    if (document.hidden || input.value.trim()) return;
    fetch(url, { headers: { Accept: "application/json" }, credentials: "same-origin" })
      .then(function (response) { return response.ok ? response.json() : null; })
      .then(function (data) {
        if (data && String(data.latest_id) !== String(known)) window.location.reload();
      })
      .catch(function () {}); // try again next time
  }, 8000);
})();
