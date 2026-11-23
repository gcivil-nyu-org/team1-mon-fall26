// #93: the "…" More actions menu on the Users page. Clicking outside it or
// pressing Escape closes it.
(function () {
  "use strict";

  var menu = document.querySelector("details.staff-actions-more");
  if (!menu) return;

  document.addEventListener("click", function (event) {
    if (menu.open && !menu.contains(event.target)) menu.open = false;
  });

  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape" || !menu.open) return;
    menu.open = false;
    menu.querySelector("summary").focus();
  });
})();
