/* The section links on phones (October 2026). Inserted right after the .sectnav on the finding and on
   every profile, by sectnav_script() in build_college_pages.py.

   Without this script the links wrap (article.css), so none can be hidden. With it, the row scrolls
   sideways under a fade. Measured in Chromium and Firefox, moving focus takes no account of the fade,
   which can leave a link partly under it (review of 11 October). So the row is scrolled to
   clear the focused link when focus lands on it, and again when the row or a link changes size, which
   no focus event reports (review of 5 November). Without ResizeObserver, only the focus move does it.
   Only the row scrolls, and only for a link that has focus: focus is never moved, the page is never
   scrolled, and a row swiped by hand stays put. The class that turns the scrolling row on is added
   last, so a failure anywhere above it leaves the wrapped list. */
(function () {
  var nav = document.querySelector(".sectnav");
  var list = nav && nav.querySelector("ul");
  var wrap = nav && nav.querySelector(".sectnav__scroll");
  if (!list || !wrap || !window.requestAnimationFrame) return;
  var GAP = 4, EDGE = 2; // between the link and the fade, and the link and the left edge
  var waiting = false;
  function fade() {
    var f = getComputedStyle(wrap, "::after");
    return f.content === "none" || f.display === "none" ? 0 : parseFloat(f.width) || 0;
  }
  function reveal() {
    waiting = false;
    var a = document.activeElement;
    if (!a || a.tagName !== "A" || !list.contains(a) || getComputedStyle(list).overflowX === "visible") return;
    var b = list.getBoundingClientRect(), r = a.getBoundingClientRect();
    var left = b.left + list.clientLeft + EDGE, right = b.left + list.clientLeft + list.clientWidth - fade() - GAP;
    if (r.right > right) list.scrollLeft += r.right - right;
    else if (r.left < left) list.scrollLeft -= left - r.left;
  }
  function soon() {
    if (!waiting) { waiting = true; requestAnimationFrame(reveal); }
  }
  list.addEventListener("focusin", soon);
  if (window.ResizeObserver) {
    var sizes = new ResizeObserver(soon);
    sizes.observe(list);
    list.querySelectorAll("a").forEach(function (a) { sizes.observe(a); });
  }
  nav.classList.add("sectnav--scroll");
})();
