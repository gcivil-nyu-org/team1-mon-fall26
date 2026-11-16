// Admin "Pet-friendly places" edit form: add and remove pet amenities
// (Figma "Manage Pet-Friendly Location (Edit)").
(function () {
  "use strict";

  var list = document.querySelector("[data-amenities]");
  var add = document.querySelector("[data-add-amenity]");
  var template = document.getElementById("amenity-row");
  if (!list || !add || !template) return;

  add.hidden = false;

  add.addEventListener("click", function () {
    var row = template.content.firstElementChild.cloneNode(true);
    list.appendChild(row);
    row.querySelector("input").focus();
  });

  list.addEventListener("click", function (event) {
    var button = event.target.closest("[data-remove-amenity]");
    if (!button) return;
    button.closest("li").remove();
    add.focus();
  });
})();
