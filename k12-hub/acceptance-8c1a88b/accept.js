// PR #14 pre-merge acceptance (High Schools hub and lookup). Recreated on 5 October after the
// scratchpad was cleared, from the checklist in acceptance-pr14.md (76 checks). Extended on 6
// October after review of 14f0c92: the keyboard pass continues through the Compare schools tile,
// and populated and no-match searches are checked (see NOTES.md for the full list).
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
  // Populated search: every result card's text stays inside the card, not only inside the screen.
  for (const [label, prefs] of [["normal", {}], ["200%", { "ui.textScaleFactor": 200, "browser.display.os-zoom-behavior": 2 }]]) {
    const b = await pw.firefox.launch({ firefoxUserPrefs: prefs });
    console.log(`\n== Populated search "international", Firefox ${label}`);
    for (const w of [320, 390, 768, 1280]) {
      const p = await b.newPage({ viewport: { width: w, height: 800 } });
      const resp = await p.goto(B + "/k12/advanced-courses/?q=international", { waitUntil: "load" });
      await p.waitForSelector(".school-card", { timeout: 10000 });
      const m = await p.evaluate(() => {
        const cards = [...document.querySelectorAll(".school-card")];
        let past = 0, worst = 0;
        for (const c of cards) {
          const r = c.getBoundingClientRect(), cs = getComputedStyle(c), left = r.left + parseFloat(cs.borderLeftWidth), right = r.right - parseFloat(cs.borderRightWidth);
          const tw = document.createTreeWalker(c, NodeFilter.SHOW_TEXT);
          for (let n; (n = tw.nextNode());) { if (!n.textContent.trim()) continue; const g = document.createRange(); g.selectNodeContents(n); for (const q of g.getClientRects()) { const o = Math.max(q.right - right, left - q.left); if (o > 1) { past++; worst = Math.max(worst, o); } } }
        }
        return { body: parseFloat(getComputedStyle(document.body).fontSize), cards: cards.length, past, worst: Math.round(worst), over: document.documentElement.scrollWidth - innerWidth };
      });
      const textOk = label === "normal" ? m.body === 15 : m.body >= 28;
      ok(resp.status() === 200 && textOk && m.cards > 0 && m.past === 0 && m.over <= 0, `international at ${w}px: HTTP ${resp.status()}, body ${m.body}px, ${m.cards} cards, text past a card ${m.past}${m.past ? ` (up to ${m.worst}px)` : ""}, page overflow ${m.over}`);
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
    const s = await p.evaluate(() => ({ val: document.querySelector("#q").value, focus: document.activeElement && document.activeElement.id, first: document.querySelector(".school-card h2").textContent }));
    ok(s.val === "Lane Tech" && s.focus === "q" && s.first === "LANE TECHNICAL HIGH SCHOOL", `Enter hands off: ?q=Lane+Tech, lookup field "${s.val}", focus #${s.focus}, first result ${s.first}`);
    await p.goto(B + "/k12/"); await p.fill("#k-q", "Stuyvesant"); await p.click(".k-search button");
    await p.waitForURL(/q=Stuyvesant/); await p.waitForSelector(".school-card");
    ok((await p.$$eval(".school-card h2", (h) => h.map((x) => x.textContent))).includes("STUYVESANT HIGH SCHOOL"), "the Search button hands off (Stuyvesant found)");
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
    for (let i = 0; i < 40 && seq.length < 13; i++) {
      await p.keyboard.press("Tab");
      const d = await p.evaluate(() => { const a = document.activeElement; if (!a || a === document.body || a.closest("header")) return null; if (a.closest("footer")) return "FOOTER"; const cs = getComputedStyle(a); return { t: (a.textContent || a.placeholder || "").trim().replace(/\s+/g, " ").slice(0, 26), ring: cs.outlineStyle !== "none" && parseFloat(cs.outlineWidth) >= 2 }; });
      if (d) seq.push(d);
    }
    const inMain = seq.filter((x) => x !== "FOOTER");
    ok(inMain.slice(4).every((x) => x.ring), "focus is visible (outline at least 2px) on the field, button, examples and tiles");
    console.log("      order:", inMain.map((x) => x.t).join(" | "));
    const want = ["e.g. Lane Tech", "Search", "Lane Tech Chicago", "Stuyvesant New York", "Garfield Seattle", "Central High School Little", "Santa Fe High New Mexico", "State report cards", "Compare schools"];
    ok(want.every((w, i) => (inMain[4 + i] || {}).t && inMain[4 + i].t.startsWith(w.slice(0, 12))), "after the section links: field, Search, five examples, then both tiles (State report cards, Compare schools)");
    await p.goto(B + "/k12/"); await p.focus('.k-ex a[href$="school=530771001171"]'); await p.keyboard.press("Enter"); await p.waitForSelector(".sub");
    ok((await p.textContent("h1")).trim() === "GARFIELD HIGH SCHOOL", "Enter on a focused example opens it");
    await p.goBack(); await p.waitForSelector("#k-q"); ok(true, "Back returns to the hub");
    // No match is said in the status region, once; changing and clearing the query update it.
    await p.goto(B + "/k12/advanced-courses/"); await p.waitForSelector("#q");
    const status = async () => (await p.textContent("#rescount")).trim();
    await p.fill("#q", "zzqxv"); await p.waitForTimeout(400);
    ok(await status() === "No high schools match \u201czzqxv\u201d." && (await p.$$("#results li")).length === 0, `no match in the status region, not the list ("${await status()}")`);
    await p.fill("#q", "lane technical"); await p.waitForTimeout(400);
    ok(/^\d+\+? schools?$/.test(await status()) && (await p.$$(".school-card")).length > 0, `a new query replaces it with the count ("${await status()}")`);
    await p.fill("#q", "zzqxv"); await p.waitForTimeout(400); await p.fill("#q", ""); await p.waitForTimeout(400);
    ok(await status() === "", `clearing the field clears the status ("${await status()}")`);
    await p.close(); await b.close();
  }
  console.log(`\n${pass} passed, ${fail} failed`);
  process.exit(fail ? 1 : 0);
})();
