"use strict";
const $ = (id) => document.getElementById(id);
let state = null;
let busy = false;
const node = (tag, text) => {
  const el = document.createElement(tag);
  if (text) el.textContent = text;
  return el;
};
function message(text) {
  $("message").textContent = text;
}
async function request(path, data) {
  const response = await fetch(
    path,
    data === undefined
      ? { cache: "no-store" }
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(data),
        },
  );
  const result = await response.json();
  if (!response.ok) {
    if (response.status === 401) {
      $("pair").hidden = false;
      $("controls").hidden = true;
    }
    throw new Error(
      result.error || "The device could not complete this request.",
    );
  }
  return result;
}
async function action(data) {
  if (busy) return;
  busy = true;
  try {
    await request("/api/action", data);
    message("Saved on the device.");
    await refresh();
  } catch (error) {
    message(error.message);
  } finally {
    busy = false;
  }
}
function button(text, data, consent = false) {
  const el = node("button", text);
  el.type = "button";
  el.onclick = () => {
    if (
      !consent ||
      confirm(
        "Send this photo to the selected provider? This uses API credits. A retry may be charged again.",
      )
    )
      action(data);
  };
  return el;
}
function photo(id) {
  const img = node("img");
  img.src = `/api/photo/${encodeURIComponent(id)}`;
  img.alt = "Saved photo";
  img.loading = "lazy";
  return img;
}
function render() {
  $("pair").hidden = true;
  $("controls").hidden = false;
  $("online-state").textContent =
    state.provider === "none"
      ? "No AI provider configured. Local filters and games are available."
      : state.offline
        ? "New transformations are paused."
        : "Approved transformations can run online.";
  $("pause").disabled = state.provider === "none";
  $("pause").textContent = state.offline
    ? "Allow approved requests"
    : "Pause new requests";
  $("pause").onclick = () =>
    action({ action: "offline", value: !state.offline });
  $("jobs").replaceChildren();
  for (const job of state.jobs) {
    const card = node("div");
    card.className = "card";
    card.append(
      node("h3", `${job.style} · ${job.provider}`),
      photo(job.id),
      node("p", job.state.replaceAll("_", " ")),
    );
    if (job.error)
      card.append(node("p", `Details: ${job.error.replaceAll("_", " ")}`));
    if (
      ["awaiting_approval", "failed", "unknown"].includes(job.state) &&
      job.attempts < 3
    )
      card.append(
        button(
          job.attempts ? "Review and retry" : "Approve transformation",
          { action: "approve", id: job.id, consent: true },
          true,
        ),
      );
    if (!["succeeded", "cancelled"].includes(job.state))
      card.append(button("Cancel request", { action: "cancel", id: job.id }));
    $("jobs").append(card);
  }
  if (!state.jobs.length)
    $("jobs").append(node("p", "No transformations waiting."));
  $("missions").replaceChildren();
  for (const mission of state.missions) {
    const card = node("div");
    card.className = "card";
    const label = node("label"),
      check = node("input");
    check.type = "checkbox";
    check.checked = state.outing.includes(mission.id);
    check.onchange = () =>
      action({
        action: "outing",
        missions: check.checked
          ? [...state.outing, mission.id]
          : state.outing.filter((id) => id !== mission.id),
      });
    label.append(check, document.createTextNode(mission.title));
    card.append(label, node("p", mission.hint));
    const evidence = state.photos
      .filter((p) => p.mission === mission.id)
      .at(-1);
    if (evidence) card.append(photo(evidence.id));
    if (state.stamps.includes(mission.id))
      card.append(node("p", "★ Stamp earned"));
    else if (mission.evidence)
      card.append(
        button("Confirm discovery", { action: "mission", id: mission.id }),
      );
    $("missions").append(card);
  }
  $("export").disabled = state.export_busy;
  $("export").textContent = state.export_busy
    ? "Preparing ZIP…"
    : "Prepare photo ZIP";
  $("export").onclick = () => action({ action: "export" });
  $("download").hidden = !state.export_ready;
  $("photos").replaceChildren();
  for (const item of state.photos.slice(-100).reverse()) {
    const card = node("div");
    card.className = "card";
    card.append(photo(item.id));
    const label = node("label"),
      check = node("input");
    check.type = "checkbox";
    check.checked = item.eligible;
    check.onchange = () =>
      action({ action: "eligible", id: item.id, value: check.checked });
    label.append(check, document.createTextNode("Include in games"));
    card.append(label);
    $("photos").append(card);
  }
}
async function refresh() {
  state = await request("/api/state");
  render();
}
$("pair-form").onsubmit = async (event) => {
  event.preventDefault();
  try {
    await request("/api/pair", { code: $("code").value });
    $("code").value = "";
    message("Paired with Pocket Quest.");
    await refresh();
  } catch (error) {
    message(error.message);
  }
};
refresh().catch(() => {});
setInterval(() => {
  if (!$("controls").hidden && !busy && document.visibilityState === "visible")
    refresh().catch((error) => message(error.message));
}, 5000);
