/* The section links on phones (October 2026). Inserted right after the .sectnav on the finding and on
   every profile, by sectnav_script() in build_college_pages.py.

   Without this script the links wrap (article.css), so none can be hidden. With it, the row scrolls
   sideways under a fade, and a link reached by Tab or Shift+Tab is moved clear of the fade and the
   edges, focus ring included: browsers scroll a focused element only just into view and ignore
   scroll-padding when moving focus, which left links partly under the fade (review of 11 October).
   Focus itself is never moved; only the row scrolls. The class that turns the scrolling row on is
   added last, so a failure anywhere above it leaves the wrapped list. */
(function () {
  var nav = document.querySelector(".sectnav");
  var list = nav && nav.querySelector("ul");
  var wrap = nav && nav.querySelector(".sectnav__scroll");
  if (!list || !wrap || !window.requestAnimationFrame || !Element.prototype.closest) return;
  var GAP = 4, EDGE = 2; // between the ring and the fade, and the ring and the left edge
  function ring(a) {
    var s = getComputedStyle(a);
    return s.outlineStyle === "none" ? 0 : (parseFloat(s.outlineWidth) || 0) + (parseFloat(s.outlineOffset) || 0);
  }
  function fade() {
    var f = getComputedStyle(wrap, "::after");
    return f.content === "none" || f.display === "none" ? 0 : parseFloat(f.width) || 0;
  }
  list.addEventListener("focusin", function (e) {
    var a = e.target.closest("a");
    if (!a || getComputedStyle(list).overflowX === "visible") return;
    requestAnimationFrame(function () {
      var b = list.getBoundingClientRect(), r = a.getBoundingClientRect(), k = ring(a);
      var left = b.left + list.clientLeft + EDGE, right = b.left + list.clientLeft + list.clientWidth - fade() - GAP;
      if (r.right + k > right) list.scrollLeft += r.right + k - right;
      else if (r.left - k < left) list.scrollLeft -= left - (r.left - k);
    });
  });
  nav.classList.add("sectnav--scroll");
})();
