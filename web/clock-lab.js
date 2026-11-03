"use strict";

(() => {
  const model = new window.ClockModel();
  const $ = (id) => document.getElementById(id);
  const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const colors = ["#91e3c1", "#7eb9ed", "#e3b16a"];
  const cards = [...document.querySelectorAll(".client-clock")];
  const svgNS = "http://www.w3.org/2000/svg";
  let playing = !motion.matches;
  let previous = 0;
  let renderedAt = 0;
  let observation = "";

  function svg(tag, attributes, parent) {
    const element = document.createElementNS(svgNS, tag);
    for (const [name, value] of Object.entries(attributes))
      element.setAttribute(name, value);
    parent.appendChild(element);
    return element;
  }
  const traces = colors.map((color) =>
    svg(
      "path",
      { fill: "none", stroke: color, "stroke-width": 2 },
      $("timeline-traces"),
    ),
  );

  function clockTime(offset = 0) {
    const milliseconds = Math.round(36000000 + model.time * 1000 + offset);
    const date = new Date(milliseconds);
    return date.toISOString().slice(11, 23);
  }
  const signed = (number) =>
    `${number < 0 ? "−" : "+"}${Math.abs(number).toFixed(1)}`;

  function drawTimeline() {
    const chartWidth = Math.max(300, $("error-timeline").clientWidth);
    const right = chartWidth - 15;
    const plotWidth = right - 64;
    $("error-timeline").setAttribute("viewBox", `0 0 ${chartWidth} 210`);
    $("error-timeline")
      .querySelector(".timeline-axis-title")
      .setAttribute("x", chartWidth / 2);
    const history = [
      ...model.history,
      { time: model.time, errors: model.clients.map((c) => c.offset) },
    ];
    const start = Math.max(0, model.time - 60);
    const span = Math.max(15, Math.min(60, model.time));
    const bound = Math.max(
      125,
      Math.ceil(
        Math.max(...history.flatMap((p) => p.errors.map(Math.abs))) / 50,
      ) * 50,
    );
    const x = (time) => 64 + ((time - start) / span) * plotWidth;
    const y = (error) => 95 - (error / bound) * 74;
    const grid = $("timeline-grid");
    grid.replaceChildren();
    for (const error of [-bound, 0, bound]) {
      svg(
        "line",
        {
          x1: 64,
          x2: right,
          y1: y(error),
          y2: y(error),
          stroke: error === 0 ? "#718f84" : "#24313c",
          "stroke-dasharray": error === 0 ? "4 4" : "0",
        },
        grid,
      );
      const label = svg(
        "text",
        { x: 52, y: y(error) + 4, "text-anchor": "end" },
        grid,
      );
      label.textContent = `${error > 0 ? "+" : ""}${error} ms`;
    }
    for (let i = 0; i < 5; i++) {
      const label = svg(
        "text",
        { x: 64 + (i * plotWidth) / 4, y: 186, "text-anchor": "middle" },
        grid,
      );
      label.textContent = (start + (span * i) / 4).toFixed(0);
    }
    traces.forEach((trace, index) =>
      trace.setAttribute(
        "d",
        history
          .filter((p) => p.time >= start)
          .map(
            (point, i) =>
              `${i ? "L" : "M"}${x(point.time).toFixed(2)},${y(point.errors[index]).toFixed(2)}`,
          )
          .join(" "),
      ),
    );
  }

  function render() {
    $("reference-time").textContent = clockTime();
    $("clock-route").textContent =
      `Path ${model.route} · ${model.route === "B" ? (model.busy ? "sync rerouted" : "waiting for recovery polls") : model.busy ? "busy" : "clear"}`;
    $("model-elapsed").textContent = `${model.time.toFixed(1)} s elapsed`;
    cards.forEach((card, index) => {
      const client = model.clients[index];
      card.querySelector(".clock-time").textContent = clockTime(client.offset);
      const rate = client.rate * model.drift;
      card.querySelector(".clock-card-title small").textContent =
        rate === 0
          ? "No artificial drift"
          : `Runs ${rate > 0 ? "fast" : "slow"} · ${signed(rate)} ms/s`;
      card.querySelector(".clock-gap b").textContent =
        `${signed(client.offset)} ms`;
      card.querySelector(".clock-gap span").textContent =
        Math.abs(client.offset) < 2
          ? "within 2 ms of server"
          : client.offset > 0
            ? "ahead of server"
            : "behind server";
      card.classList.toggle("aligned", Math.abs(client.offset) < 2);
      card.querySelector(".alignment-track span").style.left =
        `${50 + Math.max(-47, Math.min(47, (client.offset / 300) * 47))}%`;
      card.querySelector(".clock-last").textContent = client.replies
        ? `Last correction ${signed(client.correction)} ms → ${signed(client.residual)} ms gap`
        : client.pending
          ? "Request in flight…"
          : "No correction yet";
    });
    $("sync-toggle").textContent = model.sync
      ? "Stop synchronization"
      : "Enable synchronization";
    $("sync-toggle").setAttribute("aria-pressed", String(model.sync));
    $("traffic-toggle").textContent = model.busy
      ? "Clear congestion"
      : "Add congestion";
    $("traffic-toggle").setAttribute("aria-pressed", String(model.busy));
    $("clock-play").textContent = playing ? "Pause time" : "Play time";
    document
      .querySelectorAll("[data-clock-policy]")
      .forEach((button) =>
        button.setAttribute(
          "aria-pressed",
          String(button.dataset.clockPolicy === model.policy),
        ),
      );
    let message;
    if (!model.sync) {
      if (model.clients[0].replies && model.busy && model.route === "A")
        message =
          "A reply arrived, but unequal travel times left a gap. Try SDN optimized, wait for its poll, then send another exchange.";
      else if (model.drift === 0)
        message =
          "Artificial drift is off, so existing gaps stay constant. Send an exchange to see how the current path affects the correction.";
      else
        message = model.clients[0].replies
          ? "One exchange corrected the clocks. With automatic synchronization off, the gaps grow again when time plays."
          : "Synchronization is off. The clocks keep ticking at different rates. Enable it, or send one exchange to see a single correction.";
    } else if (model.busy && model.route === "A")
      message =
        model.policy === "optimized"
          ? "The primary path is busy. Wait for the next 2-second controller poll: sync traffic will move to Path B."
          : "Replies still arrive, but the outward trip is longer than the return. Part of that delay is mistaken for clock error. Try SDN optimized.";
    else if (model.route === "B" && !model.busy)
      message = `Load has stopped. ${model.lowPolls} of 3 low-load polls observed; the controller will restore Path A automatically.`;
    else if (model.drift === 0)
      message =
        "Artificial drift is off: no new gap builds up between replies. Increase drift to see why synchronization must repeat.";
    else
      message =
        "Each reply brings the clocks close to the server. They drift again between replies: correction changes the time, not the ticking rate. Try a longer sync interval.";
    if (message !== observation) {
      $("clock-observation").textContent = message;
      observation = message;
    }
    drawTimeline();
  }

  $("sync-toggle").addEventListener("click", () => {
    model.setSync(!model.sync);
    render();
  });
  $("traffic-toggle").addEventListener("click", () => {
    model.busy = !model.busy;
    render();
  });
  $("clock-play").addEventListener("click", () => {
    playing = !playing;
    render();
  });
  $("clock-step").addEventListener("click", () => {
    playing = false;
    model.advance(1);
    render();
  });
  $("clock-send").addEventListener("click", () => {
    playing = false;
    model.send();
    const wait = Math.max(
      ...model.clients.map((client) =>
        client.pending ? client.pending.arrival - model.time : 0,
      ),
    );
    model.advance(wait);
    render();
  });
  function reset() {
    model.reset();
    $("sync-interval").value = 1;
    $("sync-interval-value").textContent = "1 s";
    $("drift-scale").value = 1;
    $("drift-value").textContent = "1×";
  }
  $("clock-reset").addEventListener("click", () => {
    reset();
    render();
  });
  $("sync-interval").addEventListener("input", (event) => {
    model.setInterval(Number(event.target.value));
    $("sync-interval-value").textContent = `${model.interval} s`;
    render();
  });
  $("drift-scale").addEventListener("input", (event) => {
    model.setDrift(Number(event.target.value));
    $("drift-value").textContent = `${model.drift}×`;
    render();
  });
  document.querySelectorAll("[data-clock-policy]").forEach((button) =>
    button.addEventListener("click", () => {
      model.setPolicy(button.dataset.clockPolicy);
      render();
    }),
  );
  document.querySelectorAll("[data-challenge]").forEach((button) =>
    button.addEventListener("click", () => {
      const challenge = button.dataset.challenge;
      if (challenge === "drift") reset();
      else {
        if (!model.sync) model.setSync(true);
        if (["busy", "reroute"].includes(challenge)) model.busy = true;
        if (challenge === "busy") model.setPolicy("baseline");
        if (challenge === "reroute") model.setPolicy("optimized");
      }
      playing = !motion.matches;
      render();
    }),
  );
  motion.addEventListener("change", () => {
    if (motion.matches) playing = false;
    render();
  });
  window.addEventListener("resize", render);
  function frame(now) {
    const delta = previous ? Math.min(0.1, (now - previous) / 1000) : 0;
    previous = now;
    if (playing && !document.hidden) model.advance(delta);
    if (now - renderedAt > 100 && playing && !document.hidden) {
      render();
      renderedAt = now;
    }
    requestAnimationFrame(frame);
  }
  render();
  requestAnimationFrame(frame);
})();
