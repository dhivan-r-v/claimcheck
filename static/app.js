const EXAMPLES = [
  "PM Kisan Yojana ki 21vi kist mein sabhi kisano ko 6000 ki jagah 12000 milenge! Abhi register karo: pmkisan-gov.in.apply-now.xyz/reg  Last date aaj hi hai, jaldi karo aur 10 groups mein forward karo",
  "அன்புள்ள மின் நுகர்வோரே, உங்கள் கடந்த மாத மின் கட்டணம் செலுத்தப்படவில்லை. இன்றிரவு 9.30 மணிக்கு உங்கள் மின் இணைப்பு துண்டிக்கப்படும். உடனே எங்கள் அதிகாரியை அழைக்கவும் 9876543210",
  "प्रिय ग्राहक, आपका SBI YONO खाता आज बंद हो जाएगा। तुरंत अपना PAN कार्ड अपडेट करें: sbi-yono-kyc.in/update नहीं तो खाता ब्लॉक हो जाएगा।",
  "PM-KISAN: The 21st instalment of Rs 2,000 has been released to eligible farmers. Check your beneficiary status at https://pmkisan.gov.in",
];

const STAGES = {
  read_image: "Reading the screenshot",
  understand: "Understanding the message",
  fingerprint: "Analysing manipulation tactics",
  red_flags: "Checking links and scam patterns",
  plan: "Planning the searches",
  search: "Searching official sites, fact-checkers and news",
  read: "Reading the official pages",
  weigh: "Weighing the evidence",
  verdict: "Reaching a verdict",
};
const VERDICT_TEXT = {
  SCAM: "Likely scam / false",
  VERIFIED: "Confirmed by official sources",
  UNVERIFIED: "Could not confirm — be careful",
};

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const shortModel = (m) => (m || "").split("/").pop();

document.querySelectorAll("[data-ex]").forEach((b) =>
  b.addEventListener("click", () => {
    $("text").value = EXAMPLES[+b.dataset.ex];
    clearImage();
    $("text").focus();
  })
);

function clearImage() {
  $("image").value = "";
  $("fileName").textContent = "";
  $("preview").hidden = true;
}
function showImage(file) {
  $("fileName").textContent = file.name || "pasted image";
  $("preview").src = URL.createObjectURL(file);
  $("preview").hidden = false;
}
$("image").addEventListener("change", () => ($("image").files[0] ? showImage($("image").files[0]) : clearImage()));

// Paste a screenshot straight into the page.
document.addEventListener("paste", (e) => {
  const item = [...(e.clipboardData?.items || [])].find((i) => i.type.startsWith("image/"));
  if (!item) return;
  const dt = new DataTransfer();
  dt.items.add(item.getAsFile());
  $("image").files = dt.files;
  showImage(dt.files[0]);
});

$("form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData($("form"));
  if (!fd.get("text").trim() && !$("image").files.length) {
    $("text").focus();
    return;
  }
  if (!$("image").files.length) fd.delete("image");

  $("submit").disabled = true;
  $("steps").innerHTML = "";
  $("progress").hidden = false;
  $("progress").querySelector("h2").textContent = "Checking…";
  $("result").hidden = true;

  try {
    const res = await fetch("/api/check", { method: "POST", body: fd });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `Request failed (${res.status})`);
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf("\n\n")) >= 0) {
        const chunk = buf.slice(0, i);
        buf = buf.slice(i + 2);
        if (chunk.startsWith("data: ")) handle(JSON.parse(chunk.slice(6)));
      }
    }
  } catch (err) {
    showError(err.message);
  } finally {
    $("submit").disabled = false;
  }
});

function handle(ev) {
  if (ev.type === "stage") return step(ev);
  if (ev.type === "result") return render(ev);
  if (ev.type === "error") return showError(ev.message);
}

function step(ev) {
  let li = document.getElementById("step-" + ev.stage);
  if (!li) {
    li = document.createElement("li");
    li.id = "step-" + ev.stage;
    li.innerHTML = `<span class="icon" aria-hidden="true"></span><div><div class="name"></div><div class="who"></div><div class="detail"></div></div>`;
    $("steps").appendChild(li);
  }
  li.className = ev.status;
  li.querySelector(".icon").textContent = ev.status === "done" ? "✓" : "";
  li.querySelector(".name").textContent = STAGES[ev.stage] || ev.stage;
  li.querySelector(".who").textContent = ev.model ? shortModel(ev.model) : ev.tool || "rule-based checks";
  let detail = "";
  if (ev.stage === "red_flags") detail = ev.flags.length ? `${ev.flags.length} warning sign(s) found` : "No warning signs in links or wording";
  if (ev.stage === "understand" && ev.info) detail = `${ev.info.reply_language} · ${ev.info.claims.length} claim(s) to check`;
  if (ev.stage === "fingerprint" && ev.fingerprint)
    detail = `${ev.fingerprint.level} manipulation (${ev.fingerprint.score}/100)` +
      (ev.fingerprint.active.length ? ` · ${ev.fingerprint.active.length} tactic(s)` : "");
  if (ev.stage === "search" && ev.status === "done") detail = `${ev.count} sources found`;
  if (ev.stage === "read" && ev.status === "done")
    detail = ev.read ? `${ev.read} official page(s) read in full` : "Official pages blocked full reading — using search excerpts";
  if (ev.stage === "read_image" && ev.text) detail = ev.text.slice(0, 140) + (ev.text.length > 140 ? "…" : "");
  li.querySelector(".detail").textContent = detail;
}

function render(r) {
  const v = r.verdict;
  $("progress").querySelector("h2").textContent = r.cached ? "Checked before — showing saved result" : `Checked in ${r.seconds}s`;
  if (r.cached) $("steps").innerHTML = "";
  const byN = Object.fromEntries(r.sources.map((s) => [s.n, s]));
  const stances = {};
  (r.assessments || []).forEach((a) => (a.stances || []).forEach((s) => (stances[s.n] = s)));
  const cite = (ns) => (ns || []).filter((n) => byN[n]).map((n) => `<a href="${esc(byN[n].url)}" target="_blank" rel="noopener">[${n}]</a>`).join(" ");

  const flags = r.red_flags.flags.map((f) => `<li class="flag ${f.severity}"><strong>${esc(f.label)}</strong><br><code>${esc(defang(f.evidence))}</code></li>`).join("");
  const claims = (v.claims || []).map((c) => {
    const orig = r.claims.find((x) => x.id === c.id);
    return `<li class="claim"><span class="status ${esc(c.status)}">${esc(c.status)}</span>${esc(orig?.claim_en || "")}<div class="muted">${esc(c.note_en)} ${cite(c.sources)}</div></li>`;
  }).join("");

  // Sources the model actually relied on first, then the rest collapsed.
  const decisive = Object.values(stances).filter((s) => s.stance !== "neutral").map((s) => s.n);
  const used = new Set((v.claims || []).flatMap((c) => c.sources || []).concat(decisive));
  const srcItem = (s) => {
    const st = stances[s.n]?.stance === "neutral" ? null : stances[s.n];
    return `<li><span>[${s.n}]</span><div><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title || s.domain)}</a>
      <span class="kind ${esc(s.kind)}">${esc(s.kind)}</span><div class="muted">${esc(s.domain)}${st ? ` · <span class="stance-${esc(st.stance)}">${esc(st.stance)}</span>` : ""}</div>
      ${st?.quote ? `<span class="quote">“${esc(st.quote)}”</span>` : ""}</div></li>`;
  };
  const key = r.sources.filter((s) => used.has(s.n));
  const rest = r.sources.filter((s) => !used.has(s.n));

  $("result").innerHTML = `
    <div class="verdict ${esc(v.verdict)}">
      <span class="badge">${esc(v.verdict)}</span> <span class="muted">${esc(VERDICT_TEXT[v.verdict] || "")}</span>
      <h2>${esc(v.headline_en)}</h2>
      <p class="reply">${esc(v.reply_local)}</p>
      ${v.reply_local !== v.explanation_en ? `<p class="en">${esc(v.explanation_en)}</p>` : ""}
      ${(v.guardrail_notes || []).map((n) => `<p class="meta">🛡 ${esc(n)}</p>`).join("")}
      <div class="share">
        <a id="shareWa" class="wa" target="_blank" rel="noopener">Share on WhatsApp</a>
        <button id="shareCopy" type="button">Copy / share</button>
        <span class="muted">Send the answer back to the group it came from.</span>
      </div>
    </div>
    ${fingerprintCard(r.fingerprint)}
    ${flags ? `<div class="card"><h2>Warning signs in links and wording</h2><ul class="flags">${flags}</ul></div>` : ""}
    ${claims ? `<div class="card"><h2>Claims checked</h2><ul class="claims">${claims}</ul></div>` : ""}
    ${(v.advice_en || []).length ? `<div class="card"><h2>What to do</h2><ul class="advice">${v.advice_en.map((a) => `<li>• ${esc(a)}</li>`).join("")}</ul></div>` : ""}
    ${r.sources.length ? `<div class="card"><h2>Evidence</h2><ul class="sources">${key.map(srcItem).join("")}</ul>
      ${rest.length ? `<details><summary class="muted">${rest.length} more sources searched</summary><ul class="sources">${rest.map(srcItem).join("")}</ul></details>` : ""}</div>` : ""}
    <p class="meta">Verdict by ${esc(shortModel(r.models.verdict_used))} · evidence weighed by ${esc(shortModel(r.models.assess))} · on Nebius Token Factory</p>`;
  wireShare(r);
  $("result").hidden = false;
  $("result").scrollIntoView({ behavior: "smooth", block: "start" });
}

function fingerprintCard(fp) {
  if (!fp) return "";
  const rows = fp.active.map((k) => {
    const t = fp.tactics[k];
    return `<li class="tactic">
      <div class="tactic-head"><span>${esc(t.label)}</span>
        <span class="by">${t.found_by.map((b) => `<span class="chip">${esc(b)}</span>`).join("")}</span></div>
      <div class="bar" role="img" aria-label="${t.score} of 3"><span style="width:${(t.score / 3) * 100}%"></span></div>
      ${t.evidence ? `<span class="quote">“${esc(defang(t.evidence))}”</span>` : ""}</li>`;
  }).join("");
  return `<div class="card fp ${esc(fp.level)}">
    <h2>Manipulation fingerprint <span class="level">${esc(fp.level)} · ${fp.score}/100</span></h2>
    <p class="muted">How the message tries to make you act, separate from whether its claims are true.
      This catches brand-new scams that have no search history yet.</p>
    ${fp.impersonates ? `<p><strong>Pretends to be:</strong> ${esc(fp.impersonates)}</p>` : ""}
    ${rows ? `<ul class="tactics">${rows}</ul>` : `<p>No manipulation tactics found.</p>`}
    ${fp.summary_en ? `<p class="muted">${esc(fp.summary_en)}</p>` : ""}
  </div>`;
}

// Same rule as the Telegram bot: official links stay, any other link is made untappable.
const OFFICIAL = /(\.gov\.in|\.nic\.in|\.gov|^rbi\.org\.in|^npci\.org\.in|^irctc\.co\.in|^sbi\.co\.in|^mygov\.in)$/i;
function defang(text) {
  return String(text || "").replace(/\b(?:https?:\/\/)?(?:[a-z0-9-]+\.)+[a-z]{2,}(?:\/[^\s]*)?/gi, (url) => {
    const host = url.replace(/^https?:\/\//i, "").split("/")[0].replace(/^www\./i, "");
    if (OFFICIAL.test(host)) return url;
    return url.replace(/^http/i, "hxxp").replace(/\./g, "[.]");
  });
}

function shareText(r) {
  const v = r.verdict;
  const icon = { SCAM: "🚫", VERIFIED: "✅", UNVERIFIED: "⚠️" }[v.verdict] || "⚠️";
  const official = r.sources.find((s) => s.kind === "official") || r.sources.find((s) => s.kind === "factcheck");
  return [
    `${icon} ClaimCheck: ${v.verdict} — ${defang(v.headline_en)}`,
    "",
    defang(v.reply_local || v.explanation_en),
    official ? `\nSource: ${official.url}` : "",
    `\nCheck any forward before you share: ${location.origin}`,
  ].join("\n").trim();
}

function wireShare(r) {
  const text = shareText(r);
  $("shareWa").href = "https://wa.me/?text=" + encodeURIComponent(text);
  $("shareCopy").onclick = async () => {
    try {
      if (navigator.share) await navigator.share({ text });
      else await navigator.clipboard.writeText(text);
      $("shareCopy").textContent = navigator.share ? "Shared" : "Copied ✓";
    } catch { /* user cancelled */ }
  };
}

function showError(msg) {
  $("result").innerHTML = `<div class="card error"><strong>Couldn't check this message.</strong><p>${esc(msg)}</p></div>`;
  $("result").hidden = false;
}
