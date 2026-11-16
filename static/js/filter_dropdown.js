// Pet / Service filter menus on Explore: clicking outside a menu or pressing
// Escape closes it, and opening one closes the other.
(function () {
  "use strict";

  var menus = document.querySelectorAll("details.co-dropdown");
  if (!menus.length) return;

  function closeAll(except) {
    menus.forEach(function (menu) {
      if (menu !== except) menu.open = false;
    });
  }

  menus.forEach(function (menu) {
    menu.addEventListener("toggle", function () {
      if (menu.open) closeAll(menu);
    });
  });

  document.addEventListener("click", function (event) {
    var inside = event.target.closest && event.target.closest("details.co-dropdown");
    closeAll(inside);
  });

  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") return;
    var open = document.querySelector("details.co-dropdown[open]");
    if (!open) return;
    open.open = false;
    open.querySelector("summary").focus();
  });
})();
