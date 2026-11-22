// #105 Community guidelines (admin): Save stays gray until the rule has a
// title and text and something changed, as in Kat's Figma "Edit Community
// Guidelines" (gray Save) and "... (Edited)" (dark Save). Without JavaScript
// Save always works, and the server checks the form.
(function () {
  "use strict";

  document.querySelectorAll("[data-guideline-form]").forEach(function (form) {
    var title = form.querySelector("input[type=text]");
    var text = form.querySelector("textarea");
    var save = form.querySelector("[data-guideline-save]");
    if (!title || !text || !save) return;
    var start = [title.value.trim(), text.value.trim()];
    // A form that came back with errors can be saved again right away.
    var hadErrors = !!form.querySelector(".field-error");

    function update() {
      var now = [title.value.trim(), text.value.trim()];
      var filled = now[0] !== "" && now[1] !== "";
      var changed = now[0] !== start[0] || now[1] !== start[1];
      save.disabled = !(filled && (changed || hadErrors));
    }

    title.addEventListener("input", update);
    text.addEventListener("input", update);
    update();
    // Put the cursor at the end of the title when editing.
    title.setSelectionRange(title.value.length, title.value.length);
  });
})();
