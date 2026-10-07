// PR #14 pre-merge acceptance (High Schools hub and lookup), recreated after the scratchpad was
// cleared; same checks as the 76-check pass on d6054e9.
const path = require("path");
const pw = require(path.join(process.cwd(), "node_modules", "playwright"));
const B = "http://localhost:8787";
let pass = 0, fail = 0; const ok = (c, m) => { c ? pass++ : fail++; console.log(`${c ? "ok  " : "FAIL"}  ${m}`); };
const EX = { "170993000942": "LANE TECHNICAL HIGH SCHOOL", "362058002877": "STUYVESANT HIGH SCHOOL", "530771001171": "GARFIELD HIGH SCHOOL", "050900000607": "CENTRAL HIGH SCHOOL", "350237000551": "SANTA FE HIGH" };
const SIZES = [[320, 568], [320, 700], [375, 667], [390, 844], [768, 1024], [1100, 800], [1280, 800], [1440, 900]];
(async () => {
  for (const [label, prefs] of [["normal", {}], ["200%", { "ui.textScaleFactor": 200, "browser.display.os-zoom-behavior": 2 }]]) {
    const b = await pw.firefox.launch({ firefoxUserPrefs: prefs });
    console.log(`\n== Layout, Firefox ${label}`);
    for (const u of ["/k12/", "/k12/advanced-courses/", "/k12/advanced-courses/?school=170993000942"]) for (const [w, h] of SIZES) {
      const p = await b.newPage({ viewport: { width: w, height: h } });
      await p.goto(B + u, { waitUntil: "load" }); await p.waitForSelector(u.includes("school=") ? ".sub" : u.includes("advanced") ? "#q" : "#k-q"); await p.waitForTimeout(300);
      const m = await p.evaluate(() => {
        const body = parseFloat(getComputedStyle(document.body).fontSize), over = document.documentElement.scrollWidth - innerWidth;
        const f = document.querySelector("#k-q"), btn = document.querySelector(".k-search button"), form = document.querySelector(".k-search");
        const clipped = [...document.querySelectorAll(".k-search *, .k-ex a, .k-fact *")].filter((e) => { const r = e.getBoundingClientRect(), fr = form && form.getBoundingClientRect(); return e.closest(".k-search") && fr && (r.right > fr.right + 1 || r.left < fr.left - 1); }).length;
        return { body, over, clipped, field: f ? Math.round(f.getBoundingClientRect().width) : null, btnFits: btn ? btn.scrollWidth <= btn.clientWidth + 1 : null };
      });
      const textOk = label === "normal" ? m.body === 15 : m.body >= 28;
      ok(textOk && m.over <= 0 && m.clipped === 0 && m.btnFits !== false, `${u} ${w}x${h}: body ${m.body}px, page overflow ${m.over}, clipped in form ${m.clipped}${m.field ? `, field ${m.field}px` : ""}${m.btnFits === false ? ", BUTTON TEXT CLIPPED" : ""}`);
      await p.close();
    }
    await b.close();
  }
  for (const [bname, launcher] of [["Firefox", pw.firefox], ["Chromium", pw.chromium]]) {
    const b = await launcher.launch();
    console.log(`\n== Handoff, examples, keyboard (${bname})`);
    const p = await b.newPage({ viewport: { width: 390, height: 844 } });
    await p.goto(B + "/k12/"); await p.focus("#k-q"); await p.keyboard.type("Lane Tech"); await p.keyboard.press("Enter");
    await p.waitForURL(/advanced-courses\/\?q=Lane\+Tech/); await p.waitForSelector(".school-card");
    const s = await p.evaluate(() => ({ val: document.querySelector("#q").value, focus: document.activeElement && document.activeElement.id, first: document.querySelector(".school-card h3").textContent }));
    ok(s.val === "Lane Tech" && s.focus === "q" && s.first === "LANE TECHNICAL HIGH SCHOOL", `Enter hands off: ?q=Lane+Tech, lookup field "${s.val}", focus #${s.focus}, first result ${s.first}`);
    await p.goto(B + "/k12/"); await p.fill("#k-q", "Stuyvesant"); await p.click(".k-search button");
    await p.waitForURL(/q=Stuyvesant/); await p.waitForSelector(".school-card");
    ok((await p.$$eval(".school-card h3", (h) => h.map((x) => x.textContent))).includes("STUYVESANT HIGH SCHOOL"), "the Search button hands off (Stuyvesant found)");
    await p.goto(B + "/k12/"); await p.click(".k-search button"); await p.waitForURL(/advanced-courses/); await p.waitForSelector("#q");
    ok((await p.textContent("#results")).includes("at least three letters") || (await p.$eval("#q", (e) => e.value)) === "", "an empty search lands on the lookup with an empty field (no error)");
    await p.goto(B + "/k12/"); await p.fill("#k-q", "La"); await p.press("#k-q", "Enter"); await p.waitForSelector("#results li");
    ok((await p.textContent("#results")).includes("Type at least three letters"), "a two-letter search asks for three letters");
    for (const [k, name] of Object.entries(EX)) {
      await p.goto(B + "/k12/"); await p.click(`.k-ex a[href$="school=${k}"]`); await p.waitForSelector(".sub");
      const h = await p.textContent("h1");
      const shown = await p.evaluate(() => document.getElementById("app").innerText);
      ok(h.trim() === name && !shown.includes("School not found") && !shown.includes("No data for this school"), `example ${k} opens "${h.trim()}"`);
    }
    await p.click("#back"); await p.waitForSelector("#q"); ok(true, "Find another school returns to the search");
    await p.goto(B + "/k12/"); await p.waitForTimeout(300);
    const seq = [];
    for (let i = 0; i < 40 && seq.length < 12; i++) {
      await p.keyboard.press("Tab");
      const d = await p.evaluate(() => { const a = document.activeElement; if (!a || a === document.body || a.closest("header")) return null; if (a.closest("footer")) return "FOOTER"; const cs = getComputedStyle(a); return { t: (a.textContent || a.placeholder || "").trim().replace(/\s+/g, " ").slice(0, 26), ring: cs.outlineStyle !== "none" && parseFloat(cs.outlineWidth) >= 2 }; });
      if (d) seq.push(d);
    }
    const inMain = seq.filter((x) => x !== "FOOTER");
    ok(inMain.slice(4).every((x) => x.ring), "focus is visible (outline at least 2px) on the field, button, examples and tiles");
    console.log("      order:", inMain.map((x) => x.t).join(" | "));
    const want = ["e.g. Lane Tech", "Search", "Lane Tech Chicago", "Stuyvesant New York", "Garfield Seattle", "Central High School Little", "Santa Fe High New Mexico", "State report cards"];
    ok(want.every((w, i) => (inMain[4 + i] || {}).t && inMain[4 + i].t.startsWith(w.slice(0, 12))), "after the section links: field, Search, five examples, then the tiles");
    await p.goto(B + "/k12/"); await p.focus('.k-ex a[href$="school=530771001171"]'); await p.keyboard.press("Enter"); await p.waitForSelector(".sub");
    ok((await p.textContent("h1")).trim() === "GARFIELD HIGH SCHOOL", "Enter on a focused example opens it");
    await p.goBack(); await p.waitForSelector("#k-q"); ok(true, "Back returns to the hub");
    await p.close(); await b.close();
  }
  console.log(`\n${pass} passed, ${fail} failed`);
  process.exit(fail ? 1 : 0);
})();
