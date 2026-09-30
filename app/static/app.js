/* Ohne Inline-Handler, damit eine strikte Content-Security-Policy greifen kann. */
(function () {
  "use strict";

  document.addEventListener("click", function (ereignis) {
    var ausloeser = ereignis.target.closest("[data-nav-umschalten]");
    if (ausloeser) {
      var ziel = document.getElementById(ausloeser.getAttribute("data-nav-umschalten"));
      if (ziel) {
        ziel.classList.toggle("offen");
      }
      return;
    }

    var kopierer = ereignis.target.closest("[data-kopieren]");
    if (kopierer) {
      ereignis.preventDefault();
      var quelle = document.getElementById(kopierer.getAttribute("data-kopieren"));
      if (!quelle || !navigator.clipboard) {
        return;
      }
      navigator.clipboard.writeText(quelle.innerText).then(function () {
        var alt = kopierer.textContent;
        kopierer.textContent = "Kopiert";
        window.setTimeout(function () {
          kopierer.textContent = alt;
        }, 1500);
      });
      return;
    }

    var zurueck = ereignis.target.closest("[data-zurueck]");
    if (zurueck) {
      ereignis.preventDefault();
      window.history.back();
    }
  });

  document.addEventListener("submit", function (ereignis) {
    var frage = ereignis.target.getAttribute("data-bestaetigen");
    if (frage && !window.confirm(frage)) {
      ereignis.preventDefault();
    }
  });
})();
