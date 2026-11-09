// Messages: right-click someone else's message for "Copy text" and "Report message"
// (Kat's Figma "Report Inappropriate Content"). Reporting opens a pop-up with
// the report form, sent in the background, then "Report sent".
(function () {
  "use strict";

  var menu = document.getElementById("bubble-menu");
  var dialog = document.getElementById("report-dialog");
  if (!menu || !dialog) return;
  var reportButton = menu.querySelector("[data-report-message]");
  var reportLabel = reportButton.querySelector("span");
  var current = null;

  function closeMenu() {
    menu.hidden = true;
    if (current) current.classList.remove("is-active");
    current = null;
  }

  function openMenu(bubble) {
    if (current === bubble) { closeMenu(); return; }
    closeMenu();
    current = bubble;
    bubble.classList.add("is-active");
    var reported = bubble.hasAttribute("data-reported");
    reportButton.disabled = reported;
    reportLabel.textContent = reported ? "Reported" : "Report message";
    menu.hidden = false;
    // Beside the message, like the Figma; below it when there's no room.
    var box = bubble.getBoundingClientRect();
    var left = box.right + 10;
    var top = box.top;
    if (left + menu.offsetWidth > window.innerWidth - 12) {
      left = Math.max(12, box.left);
      top = box.bottom + 8;
    }
    menu.style.left = left + "px";
    menu.style.top = top + "px";
    menu.querySelector("button:not([disabled])").focus();
  }

  document.querySelectorAll(".chat-bubble.is-menu-target").forEach(function (bubble) {
    // Right-click (or a long press on phones) opens the menu instead of the
    // browser's. A normal click does nothing, so text can still be selected.
    bubble.addEventListener("contextmenu", function (event) {
      event.preventDefault();
      if (current !== bubble) openMenu(bubble);
    });
    bubble.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openMenu(bubble);
      }
    });
  });

  document.addEventListener("click", function (event) {
    // Any normal click outside the menu closes it, including on a message.
    if (!menu.hidden && !menu.contains(event.target)) {
      closeMenu();
    }
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && !menu.hidden) {
      var bubble = current;
      closeMenu();
      if (bubble) bubble.focus();
    }
  });
  window.addEventListener("resize", closeMenu);
  var list = document.getElementById("chat-messages");
  if (list) list.addEventListener("scroll", closeMenu);

  menu.querySelector("[data-copy-text]").addEventListener("click", function () {
    var text = current ? current.innerText : "";
    if (navigator.clipboard && text) navigator.clipboard.writeText(text).catch(function () {});
    closeMenu();
  });

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

  reportButton.addEventListener("click", function () {
    if (!current || reportButton.disabled) return;
    var url = current.getAttribute("data-report-url");
    closeMenu();
    send(url).then(show).catch(function () { window.location.assign(url); });
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
      // Reload so the message shows its "Reported" tag.
      window.location.reload();
    } else if (event.target === dialog) {
      dialog.close();
    }
  });
})();
