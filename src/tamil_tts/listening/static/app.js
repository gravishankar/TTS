// Tamil listening evaluation page. Plain JavaScript, no external resources.
"use strict";

(function () {
  const params = new URLSearchParams(window.location.search);
  const token = params.get("token") || "";
  // Keep the token out of the visible address bar after loading.
  window.history.replaceState(null, "", window.location.pathname);

  const $ = (id) => document.getElementById(id);
  const player = $("player");
  let state = null;
  let current = 0;
  let problemWords = new Set();

  function el(tag, attrs, text) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) {
      if (value === true) node.setAttribute(key, "");
      else if (value !== false && value !== null && value !== undefined) node.setAttribute(key, value);
    }
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function announce(message) {
    $("status").textContent = message;
  }

  function showErrors(errors) {
    const box = $("errors");
    box.textContent = "";
    if (!errors || !errors.length) return;
    box.appendChild(el("p", {}, "The rating was not saved:"));
    const list = el("ul");
    errors.forEach((e) => list.appendChild(el("li", {}, e)));
    box.appendChild(list);
  }

  async function api(path, options) {
    const opts = options || {};
    opts.headers = Object.assign({ "X-Session-Token": token }, opts.headers || {});
    const response = await fetch(path, opts);
    const data = await response.json();
    return { ok: response.ok, data };
  }

  function buildCriteria() {
    const box = $("criteria");
    box.textContent = "";
    state.criteria.forEach((c) => {
      const fs = el("fieldset", { id: `crit-${c.name}`, class: "options" });
      fs.appendChild(el("legend", {}, c.label + (c.required ? " (required)" : "")));
      if (c.type === "TBD") {
        fs.disabled = true;
        fs.appendChild(el("p", {}, "Not collected: the scale is not defined yet (TBD)."));
      } else {
        const values = c.type === "scale"
          ? Array.from({ length: c.max - c.min + 1 }, (_, i) => String(c.min + i))
          : c.options;
        const labels = c.labels || {};
        if (Object.keys(labels).length) fs.classList.add("labelled-scale");
        values.forEach((v) => {
          const id = `crit-${c.name}-${v}`;
          const input = el("input", { type: "radio", name: c.name, id, value: v });
          const label = el("label", { for: id }, labels[v] ? ` ${v} — ${labels[v]}` : ` ${v}`);
          label.prepend(input);
          fs.appendChild(label);
        });
      }
      box.appendChild(fs);
    });
    const cats = $("category-options");
    cats.textContent = "";
    state.taxonomy.forEach((tag) => {
      const id = `cat-${tag}`;
      const input = el("input", { type: "checkbox", name: "category", id, value: tag });
      const label = el("label", { for: id }, ` ${tag}`);
      label.prepend(input);
      cats.appendChild(label);
    });
    $("notes").maxLength = state.notes_max_chars;
  }

  function buildItemList() {
    const list = $("item-list");
    list.textContent = "";
    state.items.forEach((item) => {
      const done = item.locked ? "rated, final" : item.saved ? "rated"
        : item.rateable ? "not rated" : "cannot be rated";
      const button = el(
        "button",
        { type: "button", "data-index": item.index, "aria-current": item.index === current ? "true" : false },
        `Item ${item.number}: ${done} (${item.audio_kind})`,
      );
      button.addEventListener("click", () => show(item.index, true));
      const li = el("li");
      li.appendChild(button);
      list.appendChild(li);
    });
  }

  function showReveal(item) {
    const box = $("reveal");
    const reveal = item.reveal;
    box.hidden = !reveal;
    if (!reveal) return;
    $("reveal-model").textContent =
      `System: ${reveal.system_id}. Model: ${reveal.model_id} ${reveal.model_version}.`;
    $("reveal-text").textContent = reveal.text || "";
    $("reveal-text").hidden = !reveal.text;
    $("reveal-note").textContent = item.locked
      ? "This blind rating is final. It was saved before the identity and text were shown."
      : "";
  }

  function fillForm(item) {
    $("rating-form").reset();
    problemWords = new Set();
    const saved = item.saved;
    if (!saved) return;
    for (const [name, value] of Object.entries(saved.ratings || {})) {
      const input = document.getElementById(`crit-${name}-${value}`);
      if (input) input.checked = true;
    }
    (saved.error_categories || []).forEach((tag) => {
      const input = document.getElementById(`cat-${tag}`);
      if (input) input.checked = true;
    });
    (saved.problem_word_indices || []).forEach((i) => problemWords.add(i));
    $("notes").value = saved.notes || "";
  }

  function buildText(item) {
    const section = $("text-section");
    const textBox = $("ref-text");
    const note = $("text-note");
    textBox.textContent = "";
    note.hidden = true;
    if (state.mode !== "text") {
      section.hidden = true;
      return;
    }
    section.hidden = false;
    if (!item.text) {
      note.hidden = false;
      note.textContent = `Reference text unavailable: ${item.text_note || "unknown reason"}.`;
      return;
    }
    item.words.forEach((word, i) => {
      const pressed = problemWords.has(i);
      const button = el(
        "button",
        { type: "button", lang: "ta", "aria-pressed": pressed ? "true" : "false",
          "aria-label": `Word ${i + 1} of ${item.words.length}: ${word}. Problem word` },
        word,
      );
      button.addEventListener("click", () => {
        if (problemWords.has(i)) problemWords.delete(i);
        else problemWords.add(i);
        button.setAttribute("aria-pressed", problemWords.has(i) ? "true" : "false");
      });
      textBox.appendChild(button);
      textBox.appendChild(document.createTextNode(" "));
    });
  }

  function show(index, focusHeading) {
    current = Math.max(0, Math.min(index, state.items.length - 1));
    const item = state.items[current];
    player.pause();
    player.removeAttribute("src");
    if (item.rateable) {
      player.src = `/audio/${item.index}?token=${encodeURIComponent(token)}`;
    }
    player.load();
    $("item-heading").textContent = `Item ${item.number} of ${state.items.length}`;
    const badge = $("audio-kind");
    badge.textContent = item.audio_label;
    badge.className = `badge ${item.rateable ? "real" : "unrateable"}`;
    $("play").disabled = !item.rateable;
    $("replay").disabled = !item.rateable;
    $("prev").disabled = current === 0;
    $("next").disabled = current === state.items.length - 1;
    $("rating-fields").disabled = !item.rateable || item.locked;
    $("categories").hidden = state.mode !== "text";
    fillForm(item);
    showReveal(item);
    buildText(item);
    buildItemList();
    showErrors([]);
    const p = state.progress;
    $("progress").textContent = `${p.rated} of ${p.rateable} rateable items rated (${p.total} items in total).`;
    announce(`Item ${item.number}. ${item.audio_label}.${item.saved ? " Previously rated." : ""}`);
    if (focusHeading) $("item-heading").focus();
  }

  function togglePlay() {
    if (!state.items[current].rateable) return;
    if (player.paused) player.play();
    else player.pause();
  }

  function replay() {
    if (!state.items[current].rateable) return;
    player.currentTime = 0;
    player.play();
  }

  function collect() {
    const ratings = {};
    state.criteria.forEach((c) => {
      if (c.type === "TBD") return;
      const checked = document.querySelector(`input[name="${c.name}"]:checked`);
      if (checked) ratings[c.name] = c.type === "scale" ? Number(checked.value) : checked.value;
    });
    const categories = Array.from(document.querySelectorAll('input[name="category"]:checked')).map(
      (i) => i.value,
    );
    return {
      index: state.items[current].index,
      ratings,
      error_categories: categories,
      problem_word_indices: Array.from(problemWords).sort((a, b) => a - b),
      notes: $("notes").value,
    };
  }

  async function save(event) {
    if (event) event.preventDefault();
    const item = state.items[current];
    if (!item.rateable) {
      showErrors([`This item cannot be rated: ${item.audio_label}`]);
      return;
    }
    if (item.locked) {
      showErrors(["This blind rating is final and cannot be changed."]);
      return;
    }
    const body = collect();
    const { ok, data } = await api("/api/rating", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!ok) {
      showErrors(data.errors);
      return;
    }
    if (!item.saved) state.progress.rated += 1;
    item.saved = { ratings: body.ratings, error_categories: body.error_categories,
      problem_word_indices: body.problem_word_indices, notes: body.notes };
    item.reveal = data.reveal;
    item.locked = state.mode === "blind";
    $("rating-fields").disabled = item.locked;
    showReveal(item);
    buildItemList();
    showErrors([]);
    $("progress").textContent = `${state.progress.rated} of ${state.progress.rateable} rateable items rated (${state.progress.total} items in total).`;
    announce(`Saved rating for item ${item.number}. Revealed: ${data.reveal.system_id}.`);
  }

  function onKey(event) {
    if (event.altKey || event.ctrlKey || event.metaKey) return;
    const target = event.target;
    if (target.tagName === "TEXTAREA" || (target.tagName === "INPUT" && target.type === "text")) return;
    const key = event.key.toLowerCase();
    if (key === "p") togglePlay();
    else if (key === "r") replay();
    else if (key === "n" && current < state.items.length - 1) show(current + 1, true);
    else if (key === "b" && current > 0) show(current - 1, true);
    else if (key === "s") save();
    else return;
    event.preventDefault();
  }

  player.addEventListener("play", () => { $("play").textContent = "Pause "; $("play").appendChild(el("kbd", {}, "P")); });
  player.addEventListener("pause", () => { $("play").textContent = "Play "; $("play").appendChild(el("kbd", {}, "P")); });
  player.addEventListener("ended", () => announce("Playback finished."));
  player.addEventListener("error", () => {
    if (state && state.items[current].rateable) announce("The audio could not be played.");
  });

  async function start() {
    const { ok, data } = await api("/api/state");
    if (!ok) {
      $("session-info").textContent = `Cannot load the session: ${(data.errors || []).join(", ")}`;
      return;
    }
    state = data;
    $("session-info").textContent =
      `${state.experiment}, run ${state.run_id}. Session ${state.session_id}, reviewer ${state.reviewer_id}.`;
    $("mode-info").textContent = state.mode === "blind"
      ? "Blind listening: the model and the text stay hidden until you save each rating, and a "
        + "saved blind rating is final. Perceived intelligibility does not show that every word "
        + "was spoken; completeness is checked in text-assisted verification."
      : "Text-assisted verification: the Tamil reference text is shown. Judge pronunciation, "
        + "completeness and intelligibility. The model is revealed after you save.";
    $("mock-banner").hidden = !state.excluded_mock;
    $("mock-banner").textContent =
      `${state.excluded_mock} mock item(s) were excluded from this session. Mock audio is silent test output, not speech.`;
    buildCriteria();
    $("play").addEventListener("click", togglePlay);
    $("replay").addEventListener("click", replay);
    $("prev").addEventListener("click", () => show(current - 1, true));
    $("next").addEventListener("click", () => show(current + 1, true));
    $("rating-form").addEventListener("submit", save);
    document.addEventListener("keydown", onKey);
    const firstUnrated = state.items.findIndex((i) => i.rateable && !i.saved);
    show(firstUnrated >= 0 ? firstUnrated : 0, false);
  }

  start();
})();
