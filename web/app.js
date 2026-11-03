"use strict";
const $ = (id) => document.getElementById(id);
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
const state = {
  scene: 0,
  mode: "optimized",
  playing: false,
  elapsed: 0,
  metric: "Mean Clock Error (ms)",
};
const scenes = [
  {
    kicker: "THE PROBLEM",
    title: "Every clock drifts.",
    copy: "Each client has a virtual clock that runs at a slightly different rate. Without correction, their timestamps move apart. One server gives them a common reference.",
    label: "Virtual clocks only",
    value: "+20 / −15 / +30 ms/s",
    note: "Artificial drift rates used in the experiment",
  },
  {
    kicker: "THE PROTOCOL",
    title: "Ask. Timestamp. Correct.",
    copy: "A UDP request carries t0. The server records t1 and t2; the client records t3 on receipt. The four timestamps estimate round-trip delay and the correction to add to virtual time.",
    label: "Application protocol",
    value: "UDP · port 12300",
    note: "35-byte messages, with client ID and sequence",
  },
  {
    kicker: "THE CHALLENGE",
    title: "A busy path changes the estimate.",
    copy: "Background packets compete with sync traffic on the 10 Mbps primary path. Unequal forward and reverse delay biases the estimated offset. The next chapter shows the controller response.",
    label: "Background load",
    value: "12M offered / 10 Mbps link",
    note: "Sync and background traffic share the primary uplink",
  },
  {
    kicker: "THE RESPONSE",
    title: "Move the flow, not the clock.",
    copy: "The controller sees load above 4 Mbps and installs priority-200 rules. Sync requests and replies use s3 on Path B; background traffic remains on Path A, including its impaired forward link.",
    label: "Observed trigger policy",
    value: "≥ 4 Mbps → Path B",
    note: "OpenFlow port counters are polled every 2 seconds",
  },
  {
    kicker: "THE RECOVERY",
    title: "When load clears, return.",
    copy: "Stopping the UDP load does not immediately switch the path back. Three consecutive low-load polls remove the reroute rules, leaving the original Path A rules in place.",
    label: "Low-load polls",
    value: "0 / 3 polls",
    note: "The real recovery test verifies flow removal and packet counters",
  },
  {
    kicker: "THE EVIDENCE",
    title: "Measure the outcome.",
    copy: "The actual Linux VM experiments compare baseline and optimized modes. Five comparisons show lower optimized RTT and post-correction clock error. A separate recovery test verifies the return to Path A.",
    label: "Recorded optimized samples",
    value: "1,800 / 1,800 successful",
    note: "Explore the recorded results below",
  },
];
const NS = "http://www.w3.org/2000/svg";
const packets = [];
for (let i = 0; i < 9; i++) {
  const p = document.createElementNS(NS, i >= 6 ? "rect" : "circle");
  if (i >= 6) {
    p.setAttribute("width", "6");
    p.setAttribute("height", "6");
    p.setAttribute("rx", "1");
  } else {
    p.setAttribute("r", i < 3 ? "4" : "3");
  }
  p.setAttribute("fill", i < 3 ? "#91e3c1" : i < 6 ? "#7eb9ed" : "#e3b16a");
  $("packet-layer").appendChild(p);
  packets.push(p);
}
const paths = { a: $("path-a"), b: $("path-b") };
const lengths = { a: paths.a.getTotalLength(), b: paths.b.getTotalLength() };
function route() {
  if (state.mode === "baseline") return "a";
  if (state.scene === 3) return "b";
  if (state.scene === 4 && state.elapsed < 6) return "b";
  return "a";
}
function updateScene() {
  const s = scenes[state.scene];
  $("scene-number").textContent =
    `${String(state.scene + 1).padStart(2, "0")} / 06`;
  $("scene-kicker").textContent = s.kicker;
  $("scene-title").textContent = s.title;
  $("scene-copy").textContent = s.copy;
  $("detail-label").textContent = s.label;
  $("detail-value").textContent = s.value;
  $("detail-note").textContent = s.note;
  if (state.mode === "baseline" && state.scene === 3) {
    $("scene-title").textContent = "Baseline stays on the busy path.";
    $("scene-copy").textContent =
      "Baseline has no application prioritization or dynamic rerouting. Even with a second path available, sync packets continue through s2. Switch to SDN optimized to see the alternate route.";
    $("detail-value").textContent = "Path A · best effort";
  }
  if (state.mode === "baseline" && state.scene === 4) {
    $("scene-copy").textContent =
      "Baseline never left Path A. Once background load stops, the primary path becomes less busy. Switch to SDN optimized to see the controller remove its temporary reroute rules.";
  }
  document.querySelectorAll("[data-scene]").forEach((b) => {
    if (Number(b.dataset.scene) === state.scene)
      b.setAttribute("aria-current", "step");
    else b.removeAttribute("aria-current");
  });
  document
    .querySelectorAll("[data-mode]")
    .forEach((b) =>
      b.setAttribute("aria-pressed", String(b.dataset.mode === state.mode)),
    );
  $("previous").disabled = state.scene === 0;
  $("next").disabled = state.scene === 5;
  $("timestamp-tags").classList.toggle("visible", state.scene === 1);
  updateFrame();
}
function selectScene(index) {
  state.scene = Math.max(0, Math.min(5, index));
  state.elapsed = 0;
  updateScene();
}
function togglePlay() {
  if (!state.playing && state.scene === 5 && state.elapsed >= 10)
    selectScene(0);
  state.playing = !state.playing;
  $("play").innerHTML = state.playing
    ? "Ⅱ <span>Pause walkthrough</span>"
    : "▶ <span>Play walkthrough</span>";
  $("play").setAttribute(
    "aria-label",
    state.playing
      ? "Pause the animated walkthrough"
      : "Play the animated walkthrough",
  );
}
function updateFrame() {
  const active = route();
  const loaded = state.scene === 2 || state.scene === 3;
  paths.a.classList.toggle("active", active === "a");
  paths.b.classList.toggle("active", active === "b");
  paths.a.classList.toggle("congested", loaded);
  $("load-host").classList.toggle("on", loaded);
  $("queue-packets").classList.toggle("visible", loaded);
  $("route-label").textContent =
    active === "b" ? "Alternate path B" : "Primary path A";
  if (state.scene === 4 && state.mode === "optimized") {
    const polls = Math.min(3, Math.floor(state.elapsed / 2));
    $("detail-value").textContent = `${polls} / 3 low-load polls`;
  }
  for (let i = 0; i < 3; i++) {
    $("clock-" + (i + 1)).textContent =
      state.scene === 0
        ? "Virtual clock drifts"
        : state.scene === 1
          ? "Four timestamps"
          : active === "b"
            ? "Sync via Path B"
            : "Sync via Path A";
  }
  $("scene-progress").style.width = `${Math.min(100, state.elapsed * 10)}%`;
  packets.forEach((packet, i) => {
    const background = i >= 6;
    packet.style.opacity = background
      ? loaded
        ? ".8"
        : "0"
      : state.scene === 0
        ? ".35"
        : "1";
    const key = background ? "a" : active;
    let progress =
      (state.elapsed * (loaded && active === "a" && !background ? 0.11 : 0.26) +
        i * 0.173) %
      1;
    if (reducedMotion.matches) progress = (i * 0.173) % 1;
    if (i >= 3 && i < 6) progress = 1 - progress;
    const point = paths[key].getPointAtLength(progress * lengths[key]);
    if (background)
      packet.setAttribute(
        "transform",
        `translate(${point.x - 3},${point.y - 3})`,
      );
    else {
      packet.setAttribute("cx", String(point.x));
      packet.setAttribute("cy", String(point.y));
    }
  });
}
let previous = 0;
function tick(now) {
  const dt = previous ? Math.min((now - previous) / 1000, 0.1) : 0;
  previous = now;
  if (state.playing && !document.hidden) {
    state.elapsed += dt;
    if (state.elapsed >= 10) {
      if (state.scene < 5) selectScene(state.scene + 1);
      else {
        state.elapsed = 10;
        togglePlay();
      }
    }
    updateFrame();
  }
  requestAnimationFrame(tick);
}
document
  .querySelectorAll("[data-scene]")
  .forEach((b) =>
    b.addEventListener("click", () => selectScene(Number(b.dataset.scene))),
  );
document.querySelectorAll("[data-mode]").forEach((b) =>
  b.addEventListener("click", () => {
    state.mode = b.dataset.mode;
    state.elapsed = 0;
    updateScene();
  }),
);
$("play").addEventListener("click", togglePlay);
$("previous").addEventListener("click", () => selectScene(state.scene - 1));
$("next").addEventListener("click", () => selectScene(state.scene + 1));
document.addEventListener("keydown", (e) => {
  if (e.target.closest("button,input,select,textarea,a,summary")) return;
  const bounds = $("lab").getBoundingClientRect();
  if (bounds.top > innerHeight / 2 || bounds.bottom < innerHeight / 2) return;
  if (e.key === "ArrowRight") {
    e.preventDefault();
    selectScene(state.scene + 1);
  }
  if (e.key === "ArrowLeft") {
    e.preventDefault();
    selectScene(state.scene - 1);
  }
  if (e.code === "Space") {
    e.preventDefault();
    togglePlay();
  }
});
reducedMotion.addEventListener("change", () => {
  if (state.playing) togglePlay();
  updateFrame();
});
function updateMath() {
  const forward = Number($("forward").value),
    reverse = Number($("reverse").value);
  $("forward-value").textContent = `${forward} ms`;
  $("reverse-value").textContent = `${reverse} ms`;
  $("t0").textContent = "100.100 s";
  $("t1").textContent = (100 + forward / 1000).toFixed(3) + " s";
  $("t2").textContent = (100 + forward / 1000 + 0.002).toFixed(3) + " s";
  $("t3").textContent =
    (100.1 + (forward + reverse) / 1000 + 0.002).toFixed(3) + " s";
  const correction = -100 + (forward - reverse) / 2;
  $("rtt-model").textContent = `${forward + reverse} ms`;
  $("offset-model").textContent =
    `${correction < 0 ? "−" : "+"}${Math.abs(correction)} ms`;
  const error = Math.abs((forward - reverse) / 2);
  $("asymmetry-note").textContent = error
    ? `Unequal path delay biases the correction. Residual error: ${error} ms. Half the directional delay difference is mistaken for clock offset.`
    : "Equal path delays give the correct offset. Residual error: 0 ms.";
  $("asymmetry-note").classList.toggle("biased", error !== 0);
}
$("forward").addEventListener("input", updateMath);
$("reverse").addEventListener("input", updateMath);
function results() {
  const data = window.RECORDED_RESULTS;
  if (!data) {
    $("result-chart").textContent =
      "Recorded results could not load. Keep results.js beside this page.";
    return;
  }
  const metric = state.metric,
    unit = metric.includes("(%)") ? "%" : "ms";
  const maximum = Math.max(...data.trials.map((r) => r[metric]), 0.001);
  const chart = $("result-chart");
  if (!chart.children.length) {
    for (let i = 0; i < data.runs.length; i++) {
      const row = document.createElement("div");
      row.className = "trial-row";
      row.innerHTML = `<div class="trial-name">Run ${i + 1}<small></small></div><div class="trial-bars"><div class="bar-line"><div class="bar baseline"><span></span></div></div><div class="bar-line"><div class="bar optimized"><span></span></div></div></div>`;
      row.querySelector("small").textContent = data.runs[i].split("-")[1];
      chart.appendChild(row);
    }
  }
  $("result-table").replaceChildren();
  data.runs.forEach((run, i) => {
    const values = ["baseline", "optimized"].map(
      (mode) =>
        data.trials.find((r) => r.run === run && r.mode === mode)[metric],
    );
    ["baseline", "optimized"].forEach((mode, j) => {
      const bar = chart.children[i].querySelector(".bar." + mode);
      bar.style.width = `${(values[j] / maximum) * 100}%`;
      bar.querySelector("span").textContent = values[j].toFixed(3);
      bar.setAttribute(
        "aria-label",
        `${mode}: ${values[j].toFixed(3)} ${unit}`,
      );
    });
    const row = document.createElement("tr");
    for (const value of [
      run,
      ...values.map((v) => `${v.toFixed(3)} ${unit}`),
    ]) {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.appendChild(cell);
    }
    $("result-table").appendChild(row);
  });
  chart.dataset.axis = `${metric} · linear scale · maximum ${maximum.toFixed(1)} ${unit}`;
  chart.setAttribute(
    "aria-label",
    `Five recorded trials comparing baseline and optimized ${metric}. Exact values are available in the table below.`,
  );
  document
    .querySelectorAll("[data-metric]")
    .forEach((b) =>
      b.setAttribute("aria-pressed", String(b.dataset.metric === metric)),
    );
}
document.querySelectorAll("[data-metric]").forEach((b) =>
  b.addEventListener("click", () => {
    state.metric = b.dataset.metric;
    results();
  }),
);
updateScene();
updateMath();
results();
requestAnimationFrame(tick);
