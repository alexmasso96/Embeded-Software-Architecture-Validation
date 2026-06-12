/* Shared interactive engine for all design_survey mockups.
   Each design HTML provides: the chrome, a workspace section
   (<section data-view="workspace">) and 5 empty sections for the other views.
   This script injects the other views, wires tab switching by matching the
   design's own tab labels, and adds mock behaviour everywhere. */

(function () {
"use strict";

/* ============================== demo data ============================== */

const MODEL = "DoorControl_ECU";

const PORTS = [
  { id: "TC_001", port: "DoorLock_Cmd",     sym: "DoorLock_Cmd",     conf: 98, init: "Yes", cyclic: "10 ms", review: "Reviewed",     state: "Released" },
  { id: "TC_002", port: "DoorUnlock_Cmd",   sym: "DoorUnlock_Cmd",   conf: 97, init: "Yes", cyclic: "10 ms", review: "Reviewed",     state: "Released" },
  { id: "TC_003", port: "WindowPos_Req",    sym: "WindowPos_Req",    conf: 91, init: "No",  cyclic: "5 ms",  review: "In Review",    state: "Released" },
  { id: "TC_004", port: "MirrorFold_Cmd",   sym: "MirrorFold_Cmd",   conf: 95, init: "No",  cyclic: "20 ms", review: "Reviewed",     state: "Released" },
  { id: "TC_005", port: "ChildLock_State",  sym: "Lock_State",       conf: 62, init: "Yes", cyclic: "50 ms", review: "Not Reviewed", state: "Retired"  },
  { id: "TC_006", port: "DoorAjar_Status",  sym: "DoorAjar_Status",  conf: 99, init: "No",  cyclic: "5 ms",  review: "Reviewed",     state: "Released" },
  { id: "TC_007", port: "CentralLock_Sync", sym: "CentralLock_Sync", conf: 88, init: "No",  cyclic: "10 ms", review: "Not Reviewed", state: "In Work"  },
];

const REVIEW_OPTS = ["Not Reviewed", "In Review", "Reviewed"];
const STATE_OPTS  = ["Released", "In Work", "Retired", "Deleted"];
const TONE = {
  "Reviewed": "ok", "Released": "ok",
  "In Review": "warn", "In Work": "warn",
  "Not Reviewed": "err", "Deleted": "err",
  "Retired": "grey",
};

const FUNCS = {
  WLC_Init:               { addr: "0x8001100", size: 120, file: "wlc_main.c",  line: 12,  callees: ["WLC_MotorInit", "WLC_LegacyInit", "WLC_Scale"] },
  WLC_LegacyInit:         { addr: "0x80011a0", size: 40,  file: "wlc_main.c",  line: 48,  callees: [] },
  WLC_Cyclic:             { addr: "0x80012f0", size: 64,  file: "wlc_main.c",  line: 60,  callees: ["WLC_UpdateStateMachine", "WLC_ReadCurrent"] },
  WLC_UpdateStateMachine: { addr: "0x8001980", size: 96,  file: "wlc_main.c",  line: 27,  callees: ["WLC_ReadHallPosition", "WLC_DetectPinch", "WLC_MotorStop", "WLC_MotorSetDuty"] },
  WLC_DetectPinch:        { addr: "0x8001a10", size: 72,  file: "wlc_main.c",  line: 84,  callees: ["WLC_ReadCurrent"] },
  WLC_GetState:           { addr: "0x8001a90", size: 24,  file: "wlc_main.c",  line: 102, callees: [] },
  WLC_MotorInit:          { addr: "0x8001b00", size: 56,  file: "wlc_motor.c", line: 9,   callees: [] },
  WLC_MotorSetDuty:       { addr: "0x8001b40", size: 88,  file: "wlc_motor.c", line: 24,  callees: ["WLC_Scale"] },
  WLC_MotorStop:          { addr: "0x8001ba0", size: 32,  file: "wlc_motor.c", line: 51,  callees: [] },
  WLC_MotorGetDuty:       { addr: "0x8001bc0", size: 20,  file: "wlc_motor.c", line: 63,  callees: [] },
  WLC_ReadCurrent:        { addr: "0x8001c00", size: 44,  file: "wlc_motor.c", line: 72,  callees: [] },
  WLC_ReadHallPosition:   { addr: "0x8001c40", size: 52,  file: "wlc_motor.c", line: 88,  callees: [] },
  WLC_Scale:              { addr: "0x8001c80", size: 36,  file: "wlc_motor.c", line: 104, callees: [] },
};
Object.keys(FUNCS).forEach(n => { FUNCS[n].callers = []; });
Object.keys(FUNCS).forEach(n => FUNCS[n].callees.forEach(c => { if (FUNCS[c]) FUNCS[c].callers.push(n); }));

const SRC = {
  WLC_UpdateStateMachine:
`<span class="k">static void</span> WLC_UpdateStateMachine(<span class="k">void</span>)
{
    g_wlc_state.position = WLC_ReadHallPosition();

    <span class="k">if</span> (WLC_DetectPinch()) {
        g_wlc_state.phase      = (uint8_t)WLC_PINCH_STOP;
        g_wlc_state.pinch_flag = 1u;
        WLC_MotorStop();
    } <span class="k">else if</span> (g_wlc_state.phase == (uint8_t)WLC_MOVING_UP) {
        WLC_MotorSetDuty(g_wlc_cfg.max_duty);
    }
}`,
  WLC_DetectPinch:
`<span class="k">static bool</span> WLC_DetectPinch(<span class="k">void</span>)
{
    uint16_t current = WLC_ReadCurrent();

    <span class="c">/* R1.2: threshold is configurable (was hardcoded 850) */</span>
    <span class="k">if</span> (current > g_wlc_cfg.pinch_threshold_max) {
        <span class="k">return</span> true;
    }
    <span class="k">return</span> (g_wlc_state.position < WLC_POS_MIN_VALID);
}`,
  WLC_MotorSetDuty:
`<span class="k">void</span> WLC_MotorSetDuty(uint16_t duty)
{
    <span class="c">/* R1.2: clamp through WLC_Scale before writing PWM */</span>
    uint16_t clamped = WLC_Scale(duty, 0u, WLC_DUTY_MAX);

    PWM_SetCompare(WLC_PWM_CH, clamped);
    g_wlc_state.duty = clamped;
}`,
  WLC_Cyclic:
`<span class="k">void</span> WLC_Cyclic(<span class="k">void</span>)   <span class="c">/* called every 5 ms */</span>
{
    WLC_UpdateStateMachine();

    <span class="k">if</span> ((g_wlc_tick++ & 0x3u) == 0u) {
        g_wlc_diag.current = WLC_ReadCurrent();
    }
}`,
  WLC_Init:
`<span class="k">void</span> WLC_Init(<span class="k">const</span> WLC_Config_t *cfg)
{
    g_wlc_cfg = *cfg;
    WLC_MotorInit();

    <span class="k">if</span> (g_wlc_cfg.legacy_mode != 0u) {
        WLC_LegacyInit();
    }
}`,
};

const DIFFS = {
  "wlc_main.c": { changes: 6, rows: [
    ["ctx",  82, "static bool WLC_DetectPinch(void)",                    82, "static bool WLC_DetectPinch(void)"],
    ["ctx",  83, "{",                                                    83, "{"],
    ["ctx",  84, "    uint16_t current = WLC_ReadCurrent();",            84, "    uint16_t current = WLC_ReadCurrent();"],
    ["del",  85, "    if (current > 850u) {",                            null, ""],
    ["add",  null, "",                                                   85, "    /* R1.2: configurable threshold */"],
    ["add",  null, "",                                                   86, "    if (current > g_wlc_cfg.pinch_threshold_max) {"],
    ["ctx",  86, "        return true;",                                 87, "        return true;"],
    ["ctx",  87, "    }",                                                88, "    }"],
    ["del",  88, "    return false;",                                    null, ""],
    ["add",  null, "",                                                   89, "    return (g_wlc_state.position < WLC_POS_MIN_VALID);"],
    ["ctx",  89, "}",                                                    90, "}"],
  ]},
  "wlc_motor.c": { changes: 3, rows: [
    ["ctx",  24, "void WLC_MotorSetDuty(uint16_t duty)",                 24, "void WLC_MotorSetDuty(uint16_t duty)"],
    ["ctx",  25, "{",                                                    25, "{"],
    ["del",  26, "    PWM_SetCompare(WLC_PWM_CH, duty);",                null, ""],
    ["add",  null, "",                                                   26, "    uint16_t clamped = WLC_Scale(duty, 0u, WLC_DUTY_MAX);"],
    ["add",  null, "",                                                   27, "    PWM_SetCompare(WLC_PWM_CH, clamped);"],
    ["del",  27, "    g_wlc_state.duty = duty;",                         null, ""],
    ["add",  null, "",                                                   28, "    g_wlc_state.duty = clamped;"],
    ["ctx",  28, "}",                                                    29, "}"],
  ]},
  "wlc_cfg.h": { changes: 2, rows: [
    ["ctx",   8, "#define WLC_VERSION_MAJOR  1u",                         8, "#define WLC_VERSION_MAJOR  1u"],
    ["del",   9, "#define WLC_VERSION_MINOR  1u",                        null, ""],
    ["add",  null, "",                                                    9, "#define WLC_VERSION_MINOR  2u"],
    ["add",  null, "",                                                   10, "#define WLC_DUTY_MAX       9500u"],
    ["ctx",  10, "",                                                     11, ""],
    ["ctx",  11, "typedef struct {",                                     12, "typedef struct {"],
    ["ctx",  12, "    uint16_t max_duty;",                               13, "    uint16_t max_duty;"],
    ["add",  null, "",                                                   14, "    uint16_t pinch_threshold_max;"],
    ["ctx",  13, "} WLC_Config_t;",                                      15, "} WLC_Config_t;"],
  ]},
};

const CL_SUMMARY = "Between R1.1 and R1.2, 3 files changed (11 additions, 4 deletions). " +
  "Pinch detection now uses the configurable g_wlc_cfg.pinch_threshold_max instead of a hardcoded 850, and " +
  "gained a hall-position validity check. Motor duty is now clamped through WLC_Scale() before the PWM write. " +
  "WLC_Config_t grew a new field (pinch_threshold_max) — initialisation data must be updated. " +
  "No functions were removed. Ports likely impacted: WindowPos_Req (state machine path) and CentralLock_Sync.";

const CHAT_REPLIES = [
  { tool: "read_source(wlc_main.c) · search_symbols(g_wlc_state)",
    text: "Two functions write to `g_wlc_state.position`:\n\n" +
      "```\n// wlc_main.c:29\ng_wlc_state.position = WLC_ReadHallPosition();\n```\n\n" +
      "`WLC_UpdateStateMachine()` refreshes it every cycle from the hall sensor, and `WLC_Init()` zeroes the whole " +
      "struct at startup. No other writer exists in the indexed source — `WLC_GetState()` only reads it." },
  { tool: "read_source(wlc_motor.c) · call_graph(WLC_MotorSetDuty)",
    text: "Since R1.2, `WLC_MotorSetDuty()` clamps its input:\n\n" +
      "```\nuint16_t clamped = WLC_Scale(duty, 0u, WLC_DUTY_MAX);\nPWM_SetCompare(WLC_PWM_CH, clamped);\n```\n\n" +
      "So a request above `WLC_DUTY_MAX` (9500) can no longer reach the PWM hardware. Callers: " +
      "`WLC_UpdateStateMachine()` and `WLC_Init()`." },
];

const GEN_OUTPUT =
"## TC_003: Validate WindowPos_Req in DoorControl_ECU\n\n" +
"### Description\nVerify that the WindowPos_Req port is correctly mapped to `WindowPos_Req` (91% match)\nand behaves as specified in the DoorControl_ECU model for release R1.2.\n\n" +
"### Preconditions\n- ECU flashed with R1.2, halted at reset\n- Debugger attached, symbol file loaded\n\n" +
"### Steps\n- [ ] Set a breakpoint in `WindowPos_Req`\n- [ ] Run the target and wait for halt\n- [ ] Confirm the symbol runs cyclically every 5 ms (no init call expected)\n- [ ] Drive the window position request over LIN and observe `g_wlc_state.position`\n- [ ] Record the observed behaviour\n\n" +
"### Expected Result\nThe port behaves as specified; mapping to `WindowPos_Req` is correct.\n\n" +
"### Source grounding\n`WLC_UpdateStateMachine()` (wlc_main.c:27) consumes the request via `WLC_ReadHallPosition()`.";

const TD_DEFAULT_TEMPLATE =
"## Description\nVerify that the **[Input Port]** port is correctly mapped to `[Mapped Symbol]`\nin the *[Model]* software model.\n\n" +
"## Preconditions\n> The ECU is flashed with the release under test and halted at reset.\n\n" +
"## Steps\n- [ ] Set a breakpoint in `[Mapped Symbol]`\n- [ ] Run the target and wait for halt\n" +
"#if [Init] is equal 'Yes' {\n- [ ] Confirm the symbol is reached **once** during initialisation\n}\n" +
"#if [Cyclic] does not contain 'init' {\n- [ ] Confirm the symbol runs cyclically every [Cyclic]\n}\n" +
"- [ ] Record the observed behaviour\n\n" +
"## Expected Result\nThe port behaves as specified and the mapping to `[Mapped Symbol]` is correct.";

/* ============================== utilities ============================== */

const win = () => document.querySelector(".window");
const esc = s => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

function inline(md) {
  return esc(md)
    .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
    .replace(/`(.+?)`/g, "<code>$1</code>")
    .replace(/\*(.+?)\*/g, "<i>$1</i>");
}

/* tiny markdown renderer: ## / ### headings, - [ ] checkboxes, - bullets,
   > quotes, ``` fences, paragraphs */
function renderMd(md) {
  const out = [];
  let inFence = false, fence = [];
  for (const raw of md.split("\n")) {
    if (raw.trim().startsWith("```")) {
      if (inFence) { out.push('<pre class="v-codeblock">' + esc(fence.join("\n")) + "</pre>"); fence = []; }
      inFence = !inFence; continue;
    }
    if (inFence) { fence.push(raw); continue; }
    const line = raw.trimEnd();
    if (!line.trim()) continue;
    if (line.startsWith("### "))      out.push("<h3>" + inline(line.slice(4)) + "</h3>");
    else if (line.startsWith("## ")) out.push("<h3>" + inline(line.slice(3)) + "</h3>");
    else if (line.startsWith("- [ ] ")) out.push('<div class="v-check-row"><input type="checkbox">' + inline(line.slice(6)) + "</div>");
    else if (line.startsWith("> "))  out.push("<blockquote>" + inline(line.slice(2)) + "</blockquote>");
    else if (line.startsWith("- "))  out.push('<div class="v-check-row">•&nbsp;' + inline(line.slice(2)) + "</div>");
    else out.push("<p>" + inline(line) + "</p>");
  }
  if (fence.length) out.push('<pre class="v-codeblock">' + esc(fence.join("\n")) + "</pre>");
  return out.join("");
}

function fillTemplate(tpl, p) {
  let t = tpl
    .replaceAll("[TC. ID]", p.id).replaceAll("[Input Port]", p.port)
    .replaceAll("[Mapped Symbol]", p.sym).replaceAll("[Model]", MODEL)
    .replaceAll("[Init]", p.init).replaceAll("[Cyclic]", p.cyclic);
  /* #if X is equal 'Y' { ... }   /   #if X does not contain 'Y' { ... } */
  t = t.replace(/#if (.+?) is equal '(.+?)' \{\n([\s\S]*?)\n\}/g,
    (_, val, want, body) => val.trim() === want ? body : "");
  t = t.replace(/#if (.+?) does not contain '(.+?)' \{\n([\s\S]*?)\n\}/g,
    (_, val, what, body) => !val.toLowerCase().includes(what.toLowerCase()) ? body : "");
  return t;
}

let menuEl = null;
function closeMenu() { if (menuEl) { menuEl.remove(); menuEl = null; } }
function openMenu(anchor, items, onPick) {
  closeMenu();
  const w = win(), wr = w.getBoundingClientRect(), ar = anchor.getBoundingClientRect();
  menuEl = document.createElement("div");
  menuEl.className = "v-menu";
  for (const it of items) {
    if (it === "-") { menuEl.appendChild(document.createElement("hr")); continue; }
    const d = document.createElement("div");
    if (it.danger) d.className = "v-danger";
    d.innerHTML = "<span>" + it.label + "</span>" + (it.checked ? '<span class="v-check">✓</span>' : "");
    d.addEventListener("click", e => { e.stopPropagation(); closeMenu(); onPick(it); });
    menuEl.appendChild(d);
  }
  w.appendChild(menuEl);
  let top = ar.bottom - wr.top + 4, left = Math.min(ar.left - wr.left, wr.width - 215);
  if (top + menuEl.offsetHeight > wr.height - 10) top = ar.top - wr.top - menuEl.offsetHeight - 4;
  menuEl.style.top = top + "px"; menuEl.style.left = Math.max(8, left) + "px";
}
document.addEventListener("click", e => { if (menuEl && !menuEl.contains(e.target)) closeMenu(); });

let toastEl = null, toastTimer = null;
function toast(html, ms = 2600) {
  if (toastEl) toastEl.remove();
  clearTimeout(toastTimer);
  toastEl = document.createElement("div");
  toastEl.className = "v-toast";
  toastEl.innerHTML = html;
  win().appendChild(toastEl);
  if (ms) toastTimer = setTimeout(() => { toastEl.remove(); toastEl = null; }, ms);
  return toastEl;
}

function fakeJob(label, steps, done) {
  const t = toast(`<span>${label}</span><div class="v-progress"><div></div></div><span class="v-muted j-pct">0%</span>`, 0);
  const bar = t.querySelector(".v-progress div"), pct = t.querySelector(".j-pct");
  let i = 0;
  const iv = setInterval(() => {
    i++;
    const p = Math.min(100, Math.round(i * 100 / steps));
    bar.style.width = p + "%"; pct.textContent = p + "%";
    if (p >= 100) {
      clearInterval(iv);
      setTimeout(() => { t.remove(); toastEl = null; if (done) done(); }, 350);
    }
  }, 220);
}

function typewriter(el, text, cps, doneCb) {
  el.classList.add("v-cursor");
  let i = 0;
  const iv = setInterval(() => {
    i = Math.min(text.length, i + cps);
    el.textContent = text.slice(0, i);
    el.scrollTop = el.scrollHeight;
    const sc = el.closest(".v-stream, .v-thread"); if (sc) sc.scrollTop = sc.scrollHeight;
    if (i >= text.length) { clearInterval(iv); el.classList.remove("v-cursor"); if (doneCb) doneCb(); }
  }, 40);
}

/* ============================== view templates ============================== */

const VIEWS = {

testdesign: `
<div class="v-root">
  <div class="v-td-left">
    <div><div class="v-label">Project Title Template</div>
      <input class="v-input" id="td-title" value="[TC. ID]: Validate [Input Port] in [Model]"></div>
    <div class="v-row" style="margin:0">
      <div class="v-label" style="margin:0">Test Case Design Template</div>
      <select class="v-select" style="width:auto" id="td-group">
        <option>Grouped — one test case per port</option><option>Split — one per operation</option>
      </select></div>
    <textarea class="v-textarea" id="td-src" spellcheck="false"></textarea>
  </div>
  <div class="v-td-right">
    <div class="v-td-bar">
      <div class="v-label" style="margin:0">Live Preview</div><span class="v-flex"></span>
      <button class="v-btn" id="td-prev">◀ Previous</button>
      <span class="v-pos" id="td-pos"></span>
      <button class="v-btn" id="td-next">Next ▶</button>
      <button class="v-btn" id="td-export">⇩ Export…</button>
    </div>
    <div class="v-card v-preview" id="td-preview"></div>
  </div>
</div>`,

aigen: `
<div class="v-root">
  <div class="v-ai-side">
    <div class="v-card v-pad">
      <div class="v-label">Source Mind Map</div>
      <div class="v-row"><span>wlc_src_v1</span><span class="v-ok">✓ built</span></div>
      <button class="v-btn" id="aigen-rebuild" style="width:100%">Rebuild Mind Map</button>
    </div>
    <div class="v-card v-pad">
      <div class="v-label">Requirements</div>
      <div class="v-row"><span>WLC_Req_v2.docx</span><span class="v-ok">✓ 38 reqs</span></div>
      <button class="v-btn" style="width:100%">Import requirements…</button>
    </div>
    <div class="v-card v-pad">
      <div class="v-label">Provider</div>
      <select class="v-select"><option>Claude Sonnet 4.6</option><option>GitHub Copilot</option><option>OpenAI GPT-5</option><option>Gemini 3.5</option></select>
      <div class="v-label" style="margin-top:10px">Target Port</div>
      <select class="v-select" id="aigen-port"></select>
      <button class="v-btn v-primary" id="aigen-go" style="width:100%;margin-top:12px">✦ Generate Test Case</button>
    </div>
  </div>
  <div class="v-card v-ai-main">
    <div class="v-ai-head">
      <span id="aigen-status">Idle</span>
      <div class="v-progress"><div id="aigen-bar"></div></div>
      <span class="v-flex"></span><span class="v-muted">job: —</span>
    </div>
    <div class="v-stream" id="aigen-out"><span class="v-muted">Pick a port and press Generate — the mock streams the
      result exactly the way the real SSE endpoint will.</span></div>
    <div class="v-ai-foot">
      <button class="v-btn" id="aigen-copy">Copy</button>
      <button class="v-btn" id="aigen-insert">Insert into Test Design</button>
    </div>
  </div>
</div>`,

aichat: `
<div class="v-root">
  <div class="v-chat">
    <div class="v-thread" id="chat-thread">
      <div class="v-msg user">Which function writes g_wlc_state.position?</div>
      <div class="v-msg bot">
        <div class="v-tool">🔧 read_source(wlc_main.c) · search_symbols(g_wlc_state)</div>
        <div>Only <code>WLC_UpdateStateMachine()</code> writes it during runtime — line 29 of
        <code>wlc_main.c</code> assigns <code>WLC_ReadHallPosition()</code> into it every 5 ms cycle.
        <code>WLC_Init()</code> zeroes the struct once at startup.</div>
      </div>
    </div>
    <div class="v-composer">
      <input class="v-input" id="chat-in" placeholder="Ask about the indexed source… (grounded in wlc_src_v1)">
      <button class="v-btn v-primary" id="chat-send">Send</button>
    </div>
  </div>
</div>`,

codemap: `
<div class="v-root">
  <div class="v-cm-left">
    <input class="v-input" id="cm-search" placeholder="Type function name…">
    <div class="v-card v-cm-list" id="cm-list"></div>
    <div class="v-card v-pad">
      <div class="v-label">Graph Depth</div>
      <div class="v-kv"><span>Backward (callers)</span><span>1</span></div>
      <div class="v-kv"><span>Forward (callees)</span><span>1</span></div>
    </div>
    <div class="v-card v-pad" id="cm-details"></div>
  </div>
  <div class="v-card v-cm-graph"><svg id="cm-svg" xmlns="http://www.w3.org/2000/svg"></svg></div>
  <div class="v-card v-cm-src">
    <div class="v-cm-srchead" id="cm-srchead">// pick a function</div>
    <div class="v-cm-code" id="cm-code"></div>
  </div>
</div>`,

changelog: `
<div class="v-root" style="flex-direction:column">
  <div class="v-cl-head">
    <div class="v-label" style="margin:0">Compare</div>
    <select class="v-select" style="width:auto"><option>R1.1</option></select>
    <span class="v-muted">→</span>
    <select class="v-select" style="width:auto"><option>R1.2 (active)</option></select>
    <span class="v-flex"></span>
    <button class="v-btn" id="cl-ai">✦ AI Change Summary</button>
  </div>
  <div class="v-card v-summary" id="cl-summary" style="display:none"></div>
  <div class="v-cl-body">
    <div class="v-card v-cl-files" id="cl-files"></div>
    <div class="v-card v-diff" id="cl-diff"></div>
  </div>
</div>`,
};

/* ============================== tab switching ============================== */

const TAB_LABELS = {
  "Workspace": "workspace", "Test Design": "testdesign", "AI Generation": "aigen",
  "AI Chat": "aichat", "Code Map": "codemap", "Change Log": "changelog",
};
let tabButtons = [];

function switchTab(view) {
  document.querySelectorAll("section[data-view]").forEach(s =>
    s.classList.toggle("active", s.dataset.view === view));
  for (const { el, view: v } of tabButtons) {
    el.classList.toggle("active", v === view);
    el.classList.toggle("on", v === view);
  }
  closeMenu();
}

function wireTabs() {
  const norm = t => (t || "").replace(/[^A-Za-z ]/g, "").replace(/\s+/g, " ").trim();
  document.querySelectorAll("button, .nav-item, .apptab, .tab, span, div").forEach(el => {
    if (el.closest("section[data-view]") || el.children.length > 3) return;
    const key = TAB_LABELS[norm(el.textContent)] || TAB_LABELS[norm(el.getAttribute("title"))];
    if (!key) return;
    if (tabButtons.some(t => t.el.contains(el) || el.contains(t.el))) return;
    tabButtons.push({ el, view: key });
    el.style.cursor = "pointer";
    el.addEventListener("click", () => switchTab(key));
  });
}

/* ============================== workspace ============================== */

function toneOf(label) { return TONE[label] || "grey"; }

function setPillEl(el, label) {
  const tone = toneOf(label);
  const dot = el.querySelector(".d");
  if (dot) {
    el.innerHTML = `<span class="d d-${{ ok: "green", warn: "yellow", err: "red", grey: "grey" }[tone]}"></span>${label}`;
  } else {
    el.className = el.className.replace(/\bp-(green|yellow|red|grey)\b/g, "").trim()
      + " p-" + { ok: "green", warn: "yellow", err: "red", grey: "grey" }[tone];
    el.textContent = label;
  }
}

function wireWorkspace() {
  const ws = document.querySelector('section[data-view="workspace"]');
  if (!ws) return;
  const tbody = ws.querySelector("tbody");

  ws.addEventListener("click", e => {
    const pill = e.target.closest(".pill, .state");
    const kebab = e.target.closest(".kebab");
    const row = e.target.closest("tbody tr");

    if (pill) {
      e.stopPropagation();
      const current = pill.textContent.trim();
      const opts = REVIEW_OPTS.includes(current) ? REVIEW_OPTS : STATE_OPTS;
      openMenu(pill, opts.map(o => ({ label: o, checked: o === current })), it => {
        setPillEl(pill, it.label);
        if (row) row.classList.toggle("dim", it.label === "Retired" || it.label === "Deleted");
        if (STATE_OPTS.includes(it.label) && it.label !== current)
          toast(`Port state → <b>${it.label}</b> &nbsp;<span class="v-muted">(propagation dialog would confirm dependent ports here)</span>`);
      });
      return;
    }
    if (kebab) {
      e.stopPropagation();
      openMenu(kebab, [
        { label: "Edit cell" }, { label: "Pick match candidate…" },
        { label: "Show in Code Map" }, { label: "Port history…" }, "-",
        { label: "Duplicate row" }, { label: "Retire port…", danger: true },
      ], it => {
        if (it.label === "Show in Code Map") { switchTab("codemap"); return; }
        if (it.label === "Duplicate row" && row) {
          const clone = row.cloneNode(true); clone.classList.remove("selected");
          row.after(clone); toast("Row duplicated");
          return;
        }
        if (it.label === "Retire port…" && row) {
          const statePill = row.querySelector("td:nth-last-child(2) .pill, td:nth-last-child(2) .state");
          if (statePill) setPillEl(statePill, "Retired");
          row.classList.add("dim"); toast("Port retired (soft) — restorable from the model manager");
          return;
        }
        toast("Mock action: " + it.label);
      });
      return;
    }
    if (row && tbody && tbody.contains(row)) {
      tbody.querySelectorAll("tr.selected").forEach(r => r.classList.remove("selected"));
      row.classList.add("selected");
    }
  });

  /* search boxes → real filtering input */
  document.querySelectorAll(".search, .cmdk").forEach(box => {
    if (box.querySelector("input")) return;
    const ph = box.textContent.replace(/[⌕🔍]/g, "").trim();
    box.innerHTML = "🔍&nbsp;";
    const inp = document.createElement("input");
    inp.className = "v-searchinput"; inp.placeholder = ph || "Search ports…";
    box.appendChild(inp);
    inp.addEventListener("input", () => {
      const q = inp.value.toLowerCase();
      if (!tbody) return;
      tbody.querySelectorAll("tr").forEach(tr =>
        tr.style.display = tr.textContent.toLowerCase().includes(q) ? "" : "none");
    });
    inp.addEventListener("click", e => e.stopPropagation());
  });

  /* text-matched chrome buttons */
  document.querySelectorAll("button").forEach(btn => {
    const t = btn.textContent.trim();
    if (/Add Port/.test(t)) btn.addEventListener("click", () => {
      if (!tbody || !tbody.rows.length) return;
      const tpl = tbody.rows[0], clone = tpl.cloneNode(true);
      clone.classList.remove("selected", "dim");
      const tds = clone.querySelectorAll("td");
      tds[0].textContent = "TC_0" + (tbody.rows.length + 1).toString().padStart(2, "0");
      tds[1].textContent = "New_Port";
      tds[2].innerHTML = '<span class="v-muted">— unmatched —</span>';
      const pills = clone.querySelectorAll(".pill, .state");
      if (pills[0]) setPillEl(pills[0], "Not Reviewed");
      if (pills[1]) setPillEl(pills[1], "In Work");
      tbody.appendChild(clone);
      clone.scrollIntoView({ block: "nearest" });
      toast("Port added — fuzzy match runs when a symbol column is filled");
    });
    else if (/Re-match/.test(t)) btn.addEventListener("click", () =>
      fakeJob("Re-matching 7 ports against R1.2 symbols…", 9, () =>
        toast("Re-match complete — <b>0 changes</b> (manual overrides preserved)")));
    else if (/^Save$/.test(t)) btn.addEventListener("click", () =>
      fakeJob("Saving project…", 3, () => {
        toast("Saved ✓");
        document.querySelectorAll("*").forEach(el => {
          if (el.children.length === 0 && /Auto-saved/.test(el.textContent)) el.textContent = "Saved just now";
        });
      }));
    else if (/Generate Test Cases/.test(t)) btn.addEventListener("click", () => {
      switchTab("aigen");
      setTimeout(() => { const go = document.getElementById("aigen-go"); if (go) go.click(); }, 350);
    });
    else if (/Create Baseline/.test(t)) btn.addEventListener("click", () =>
      fakeJob("Creating baseline from current state…", 6, () => toast("Baseline <b>BL_2026-06-12</b> created")));
    else if (/Load Baseline/.test(t)) btn.addEventListener("click", () =>
      openMenu(btn, [{ label: "BL_2026-05-30 (R1.1)" }, { label: "BL_2026-04-17 (R1.0)" }],
        it => toast("Loaded " + it.label + " — table now shows baseline snapshot")));
    else if (/Show in Code Map/.test(t)) btn.addEventListener("click", () => switchTab("codemap"));
    else if (/Pick match candidate/.test(t)) btn.addEventListener("click", () =>
      openMenu(btn, [
        { label: "WindowPos_Req — 91%", checked: true },
        { label: "WindowPos_ReqHandler — 74%" },
        { label: "WinPos_ReqShadow — 58%" },
        "-", { label: "Manual entry…" },
      ], it => toast("Match set: <b>" + it.label + "</b> — marked as manual override")));
    else if (/Port history/.test(t)) btn.addEventListener("click", () =>
      toast("Mock: change-history dialog for the selected port"));
    else if (/^(Duplicate|Retire)…?$/.test(t)) btn.addEventListener("click", () =>
      toast("Mock action: " + t));
    else if (/Import/.test(t) && !/requirements/i.test(t)) btn.addEventListener("click", () =>
      openMenu(btn, [{ label: "Excel / CSV…" }, { label: "Rhapsody export…" }],
        it => toast("Mock import: " + it.label)));
    else if (/Columns/.test(t)) btn.addEventListener("click", () =>
      openMenu(btn, [
        { label: "TC. ID (pinned)", checked: true }, { label: "Input Port", checked: true },
        { label: "Mapped Symbol", checked: true }, { label: "Init", checked: true },
        { label: "Cyclic", checked: true }, { label: "Review", checked: true },
        { label: "Port State", checked: true }, "-", { label: "＋ Add column…" }, { label: "Reorder…" },
      ], it => toast("Mock column action: " + it.label)));
  });
}

/* ============================== test design ============================== */

let tdIndex = 2; /* start on TC_003 like the workspace selection */

function tdRender() {
  const tpl = document.getElementById("td-src"), title = document.getElementById("td-title");
  const prev = document.getElementById("td-preview"), pos = document.getElementById("td-pos");
  if (!tpl || !prev) return;
  const p = PORTS[tdIndex];
  pos.textContent = `Port ${tdIndex + 1} of ${PORTS.length}`;
  prev.innerHTML = "<h2>" + inline(fillTemplate(title.value, p)) + "</h2>" + renderMd(fillTemplate(tpl.value, p));
}

function wireTestDesign() {
  const tpl = document.getElementById("td-src");
  if (!tpl) return;
  tpl.value = TD_DEFAULT_TEMPLATE;
  tpl.addEventListener("input", tdRender);
  document.getElementById("td-title").addEventListener("input", tdRender);
  document.getElementById("td-prev").addEventListener("click", () => { tdIndex = (tdIndex + PORTS.length - 1) % PORTS.length; tdRender(); });
  document.getElementById("td-next").addEventListener("click", () => { tdIndex = (tdIndex + 1) % PORTS.length; tdRender(); });
  document.getElementById("td-export").addEventListener("click", e =>
    openMenu(e.currentTarget, [{ label: "Export as Markdown" }, { label: "Export as DOCX" }, { label: "Copy all to clipboard" }],
      it => toast("Mock export: " + it.label)));
  tdRender();
}

/* ============================== AI generation ============================== */

function wireAiGen() {
  const go = document.getElementById("aigen-go");
  if (!go) return;
  const sel = document.getElementById("aigen-port");
  sel.innerHTML = PORTS.map((p, i) => `<option value="${i}" ${i === 2 ? "selected" : ""}>${p.id} — ${p.port}</option>`).join("");
  const out = document.getElementById("aigen-out"), bar = document.getElementById("aigen-bar"),
        status = document.getElementById("aigen-status");
  let busy = false;
  go.addEventListener("click", () => {
    if (busy) return; busy = true;
    out.innerHTML = ""; bar.style.width = "8%";
    status.textContent = "POST /api/jobs/generate_tests → 202";
    const pre = document.createElement("pre"); out.appendChild(pre);
    setTimeout(() => { status.textContent = "Streaming (SSE)…"; bar.style.width = "35%"; }, 500);
    setTimeout(() => typewriter(pre, GEN_OUTPUT, 6, () => {
      bar.style.width = "100%"; status.textContent = "Completed ✓";
      out.innerHTML = renderMd(GEN_OUTPUT);
      busy = false;
    }), 700);
  });
  document.getElementById("aigen-insert").addEventListener("click", () => { switchTab("testdesign"); toast("Inserted into Test Design (mock)"); });
  document.getElementById("aigen-copy").addEventListener("click", () => toast("Copied to clipboard (mock)"));
  document.getElementById("aigen-rebuild").addEventListener("click", () =>
    fakeJob("Rebuilding mind map from 41 source files…", 8, () => toast("Mind map rebuilt ✓")));
}

/* ============================== AI chat ============================== */

function wireChat() {
  const input = document.getElementById("chat-in");
  if (!input) return;
  const thread = document.getElementById("chat-thread"), send = document.getElementById("chat-send");
  let n = 0, busy = false;
  function submit() {
    const q = input.value.trim();
    if (!q || busy) return;
    busy = true; input.value = "";
    const u = document.createElement("div"); u.className = "v-msg user"; u.textContent = q; thread.appendChild(u);
    const reply = CHAT_REPLIES[n++ % CHAT_REPLIES.length];
    const b = document.createElement("div"); b.className = "v-msg bot";
    b.innerHTML = `<div class="v-tool">🔧 ${reply.tool}</div><div class="v-body"></div>`;
    thread.appendChild(b); thread.scrollTop = thread.scrollHeight;
    const body = b.querySelector(".v-body");
    setTimeout(() => typewriter(body, reply.text.replace(/```[\s\S]*?```/g, m => m), 5, () => {
      body.innerHTML = renderMd(reply.text); busy = false; thread.scrollTop = thread.scrollHeight;
    }), 600);
  }
  send.addEventListener("click", submit);
  input.addEventListener("keydown", e => { if (e.key === "Enter") submit(); });
}

/* ============================== code map ============================== */

let cmSel = "WLC_UpdateStateMachine";

function cmRender() {
  const list = document.getElementById("cm-list");
  if (!list) return;
  const q = (document.getElementById("cm-search").value || "").toLowerCase();
  list.innerHTML = "";
  Object.keys(FUNCS).sort().forEach(name => {
    if (q && !name.toLowerCase().includes(q)) return;
    const d = document.createElement("div");
    d.textContent = name;
    if (name === cmSel) d.className = "sel";
    d.addEventListener("click", () => { cmSel = name; cmRender(); });
    list.appendChild(d);
  });

  const f = FUNCS[cmSel];
  document.getElementById("cm-details").innerHTML =
    `<div class="v-label">Function Details</div>
     <div class="v-kv"><span>Name</span><span>${cmSel}</span></div>
     <div class="v-kv"><span>Address</span><span>${f.addr}</span></div>
     <div class="v-kv"><span>Size</span><span>${f.size} bytes</span></div>
     <div class="v-kv"><span>Called by</span><span>${f.callers.length}</span></div>
     <div class="v-kv"><span>Calls out</span><span>${f.callees.length}</span></div>`;

  document.getElementById("cm-srchead").textContent = `// File: ${f.file} | Line: ${f.line}`;
  document.getElementById("cm-code").innerHTML =
    SRC[cmSel] || `<span class="c">/* ${cmSel} — source not indexed (ELF-only symbol).\n   Disassembly view would appear here. */</span>`;

  /* graph: callers left, selected centre, callees right */
  const svg = document.getElementById("cm-svg");
  const W = svg.clientWidth || 420, H = svg.clientHeight || 480;
  const nodeW = 138, nodeH = 24;
  let parts = [];
  const edge = (x1, y1, x2, y2) =>
    parts.push(`<path class="v-cm-edge" d="M ${x1} ${y1} C ${(x1 + x2) / 2} ${y1}, ${(x1 + x2) / 2} ${y2}, ${x2} ${y2}"/>`);
  const node = (name, x, y, sel) =>
    parts.push(`<g class="v-cm-node ${sel ? "sel" : ""}" data-fn="${name}" transform="translate(${x},${y})">
      <rect width="${nodeW}" height="${nodeH}" rx="6"></rect>
      <text x="${nodeW / 2}" y="${nodeH / 2 + 3.5}" text-anchor="middle">${name}</text></g>`);
  const cy = H / 2, cx = W / 2 - nodeW / 2;
  const place = (arr, x) => arr.map((n, i) => {
    const y = cy - ((arr.length - 1) / 2 - i) * (nodeH + 18) - nodeH / 2;
    return { n, x, y };
  });
  const callers = place(f.callers, 18), callees = place(f.callees, W - nodeW - 18);
  callers.forEach(c => edge(c.x + nodeW, c.y + nodeH / 2, cx, cy));
  callees.forEach(c => edge(cx + nodeW, cy, c.x, c.y + nodeH / 2));
  callers.forEach(c => node(c.n, c.x, c.y, false));
  callees.forEach(c => node(c.n, c.x, c.y, false));
  node(cmSel, cx, cy - nodeH / 2, true);
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.innerHTML = parts.join("");
  svg.querySelectorAll(".v-cm-node").forEach(g =>
    g.addEventListener("click", () => { cmSel = g.dataset.fn; cmRender(); }));
}

function wireCodeMap() {
  const search = document.getElementById("cm-search");
  if (!search) return;
  search.addEventListener("input", cmRender);
  cmRender();
  /* re-render on tab activation so SVG gets real dimensions */
  tabButtons.filter(t => t.view === "codemap").forEach(t => t.el.addEventListener("click", () => setTimeout(cmRender, 30)));
}

/* ============================== change log ============================== */

let clSel = "wlc_main.c";

function clRender() {
  const files = document.getElementById("cl-files");
  if (!files) return;
  files.innerHTML = "";
  Object.keys(DIFFS).forEach(name => {
    const d = document.createElement("div");
    d.className = "v-cl-file" + (name === clSel ? " sel" : "");
    d.innerHTML = `<span>${name}</span><span class="n">${DIFFS[name].changes}</span>`;
    d.addEventListener("click", () => { clSel = name; clRender(); });
    files.appendChild(d);
  });
  const rows = DIFFS[clSel].rows.map(([t, ln, lc, rn, rc]) => {
    const lcls = t === "del" ? "del" : (t === "add" ? "emp" : "");
    const rcls = t === "add" ? "add" : (t === "del" ? "emp" : "");
    return `<tr><td class="ln">${ln ?? ""}</td><td class="half ${lcls}">${esc(lc)}</td>
            <td class="ln">${rn ?? ""}</td><td class="half ${rcls}">${esc(rc)}</td></tr>`;
  }).join("");
  document.getElementById("cl-diff").innerHTML = `<table>${rows}</table>`;
}

function wireChangeLog() {
  if (!document.getElementById("cl-files")) return;
  clRender();
  document.getElementById("cl-ai").addEventListener("click", () => {
    const box = document.getElementById("cl-summary");
    box.style.display = "block"; box.textContent = "";
    typewriter(box, CL_SUMMARY, 5);
  });
}

/* ============================== boot ============================== */

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("section[data-view]").forEach(s => {
    const v = s.dataset.view;
    if (v !== "workspace" && VIEWS[v]) s.innerHTML = VIEWS[v];
  });
  wireTabs();
  wireWorkspace();
  wireTestDesign();
  wireAiGen();
  wireChat();
  wireCodeMap();
  wireChangeLog();
});

})();
