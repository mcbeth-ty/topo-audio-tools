// One page-local controller shared by every Ambient v2 component instance.
function controller() {
  if (!window.__hsgAmbientPlayback) {
    window.__hsgAmbientPlayback = {
      epoch: null, players: new Set(), playRequests: new Set(), positions: new Map(), batch: null,
      reset(audio) { audio.pause(); try { audio.currentTime = 0; } catch (_) {} },
      stop() { this.players.forEach(audio => this.reset(audio)); },
      context(epoch) { if (this.epoch !== epoch) { this.stop(); this.epoch = epoch; } },
      activate(audio) { this.players.forEach(other => { if (other !== audio) this.reset(other); }); },
      register(audio) {
        this.players.add(audio);
        const start = () => this.activate(audio);
        audio.addEventListener("play", start);
        return () => { this.reset(audio); this.players.delete(audio); audio.removeEventListener("play", start); audio.removeAttribute("src"); audio.load(); };
      }
    };
  }
  return window.__hsgAmbientPlayback;
}

export default function ({parentElement, data, setTriggerValue}) {
  const shared = controller();
  if (!shared.playRequests) shared.playRequests = new Set();
  shared.context(data.epoch);
  const root = parentElement.querySelector(".ambient-root");
  // v2 may update data without unmounting: dispose the previous render too.
  if (root.__ambientDispose) root.__ambientDispose();
  root.replaceChildren();
  const cleanups = []; let disposed = false;
  const dispose = () => {
    if (disposed) return;
    disposed = true; cleanups.forEach(fn => fn());
    if (root.__ambientDispose === dispose) { root.replaceChildren(); delete root.__ambientDispose; }
  };
  root.__ambientDispose = dispose;
  if (data.kind === "scope") return dispose;
  const makeAudio = (url) => {
    const audio = document.createElement("audio");
    audio.src = url; audio.preload = "none";
    cleanups.push(shared.register(audio));
    return audio;
  };
  if (data.kind === "player") {
    const audio = makeAudio(data.url);
    audio.controls = true; audio.setAttribute("aria-label", "Stimulus playback");
    const host = parentElement.host || parentElement;
    const row = host.closest('[class*="st-key-ambient_library_row_"]');
    if (row) {
      const startRow = () => row.classList.add("ambient-playing-row");
      const stopRow = () => row.classList.remove("ambient-playing-row");
      audio.addEventListener("play", startRow); audio.addEventListener("pause", stopRow); audio.addEventListener("ended", stopRow);
      cleanups.push(() => { stopRow(); audio.removeEventListener("play", startRow); audio.removeEventListener("pause", stopRow); audio.removeEventListener("ended", stopRow); });
    }
    if (data.compact) {
      audio.controls = false;
      const toggle = document.createElement("button"); toggle.className = "compact-toggle"; toggle.textContent = "▶";
      const playerLabel=data.preview_seconds?`${data.preview_seconds}-second fast preview`:'saved stimulus';
      if(data.preview_seconds){toggle.classList.add('preview-toggle');toggle.title=`Fast preview · ${data.preview_seconds} seconds · click to restart`;}
      toggle.setAttribute("aria-label", `Play ${playerLabel}`);
      toggle.onclick = async () => {
        if(data.preview_seconds)shared.reset(audio);
        else if (!audio.paused) { audio.pause(); return; }
        shared.activate(audio);
        try { await audio.play(); } catch (_) { toggle.textContent = "Unavailable"; }
      };
      const start = () => { toggle.textContent = data.preview_seconds ? "▶" : "Ⅱ"; toggle.setAttribute("aria-label", data.preview_seconds ? `Restart ${playerLabel}` : `Pause ${playerLabel}`); };
      const stop = () => { toggle.textContent = "▶"; toggle.setAttribute("aria-label", `Play ${playerLabel}`); };
      audio.addEventListener("play", start); audio.addEventListener("pause", stop); audio.addEventListener("ended", stop);
      cleanups.push(() => { audio.removeEventListener("play", start); audio.removeEventListener("pause", stop); audio.removeEventListener("ended", stop); });
      root.append(toggle);
      if (data.play_request && !shared.playRequests.has(data.play_request)) {
        shared.playRequests.add(data.play_request); shared.activate(audio);
        audio.play().catch(() => { toggle.textContent = "▶"; });
      }
    } else { root.append(audio); }
    return dispose;
  }
  if (shared.batch !== data.batch) {
    shared.batch = data.batch; shared.positions.clear();
  }
  const canvas = document.createElement("div"); canvas.className = "canvas";
  canvas.setAttribute("aria-label", "Free stimulus arrangement");
  const transport = document.createElement("div"); transport.className = "transport";
  const status = document.createElement("div"); status.className = "status";
  status.textContent = "Drag nodes to arrange. Use ▶ to listen; i opens details.";
  transport.append(status); root.append(canvas, transport);
  const nodes = []; let popover = null;
  const closeDetails = () => { if (popover) popover.remove(); popover = null; };
  const outside = event => { if (popover && !popover.contains(event.target) && !event.target.closest(".details")) closeDetails(); };
  root.addEventListener("pointerdown", outside);
  const clamp = (v, min, max) => Math.max(min, Math.min(max, v));
  let columns = 1;
  const layout = () => {
    const width = canvas.clientWidth;
    columns = Math.max(1, Math.min(Math.ceil(data.items.length / 2), Math.floor((width - 110) / 140)));
    const rows = Math.ceil(data.items.length / columns);
    canvas.style.height = `${Math.max(560, rows * 130)}px`;
    const maxX = Math.max(0, width - 110), maxY = Math.max(0, canvas.clientHeight - 88);
    nodes.forEach(({item, element}, index) => {
      if (!shared.positions.has(item.id)) {
        const row = Math.floor(index / columns), col = index % columns;
        shared.positions.set(item.id, {x: (col + .5) / columns, y: (row + .5) / rows});
      }
      const point = shared.positions.get(item.id);
      element.style.left = `${clamp(point.x, 0, 1) * maxX}px`;
      element.style.top = `${clamp(point.y, 0, 1) * maxY}px`;
    });
  };
  data.items.forEach(item => {
    const element = document.createElement("div"); element.className = "node"; element.dataset.id = item.id;
    const circle = document.createElement("div"); circle.className = "circle";
    const play = document.createElement("button"); play.className = "play"; play.textContent = "▶";
    play.setAttribute("aria-label", `Play stimulus ${item.number}`);
    const number = document.createElement("span"); number.textContent = item.number;
    circle.append(play, number);
    const info = document.createElement("button"); info.className = "details"; info.textContent = "i";
    info.setAttribute("aria-label", `Details for stimulus ${item.number}`);
    const save = document.createElement("button"); save.className = "save-node";
    save.textContent = item.saved ? "✓" : "Save"; save.disabled = !!item.saved;
    save.setAttribute("aria-label", `Save stimulus ${item.number}`);
    save.addEventListener("click", () => {
      save.disabled = true; save.textContent = "…";
      setTriggerValue("save", {id: item.id, token: item.save_token});
    });
    const bypass = document.createElement("button"); bypass.className = "bypass-node";
    bypass.textContent = item.status === "bypassed" ? "−" : "Bypass";
    bypass.disabled = !item.can_bypass || item.status === "bypassed";
    bypass.setAttribute("aria-label", `Bypass stimulus ${item.number}`);
    bypass.addEventListener("click", () => {
      bypass.disabled = true;
      setTriggerValue("bypass", {id: item.id, token: item.save_token});
    });
    element.append(circle, info, save);
    if (item.can_bypass) element.append(bypass);
    canvas.append(element);
    const audio = makeAudio(item.url); audio.controls = true;
    audio.setAttribute("aria-label", `Stimulus ${item.number} transport`);
    const playing = () => { circle.classList.add("playing"); play.textContent = "Ⅱ"; play.setAttribute("aria-label", `Pause stimulus ${item.number}`); };
    const paused = () => { circle.classList.remove("playing"); play.textContent = "▶"; play.setAttribute("aria-label", `Play stimulus ${item.number}`); };
    audio.addEventListener("play", playing); audio.addEventListener("pause", paused); audio.addEventListener("ended", paused);
    cleanups.push(() => { audio.removeEventListener("play", playing); audio.removeEventListener("pause", paused); audio.removeEventListener("ended", paused); });
    let drag = null, suppressUntil = 0;
    circle.addEventListener("pointerdown", event => {
      if (event.button !== 0) return;
      drag = {id: event.pointerId, x: event.clientX, y: event.clientY,
              left: parseFloat(element.style.left), top: parseFloat(element.style.top), moved: false,
              capture: event.target.closest(".play") || circle};
      drag.capture.setPointerCapture(event.pointerId);
    });
    circle.addEventListener("pointermove", event => {
      if (!drag || event.pointerId !== drag.id) return;
      const dx = event.clientX - drag.x, dy = event.clientY - drag.y;
      if (!drag.moved && Math.hypot(dx, dy) < 5) return;
      drag.moved = true;
      const maxX = Math.max(0, canvas.clientWidth - 110), maxY = Math.max(0, canvas.clientHeight - 88);
      const x = clamp(drag.left + dx, 0, maxX), y = clamp(drag.top + dy, 0, maxY);
      element.style.left = `${x}px`; element.style.top = `${y}px`;
      shared.positions.set(item.id, {x: maxX ? x / maxX : 0, y: maxY ? y / maxY : 0});
      event.preventDefault();
    });
    const endDrag = event => {
      if (!drag || event.pointerId !== drag.id) return;
      if (drag.moved) suppressUntil = Date.now() + 350;
      if (drag.capture.hasPointerCapture(event.pointerId)) drag.capture.releasePointerCapture(event.pointerId);
      drag = null;
    };
    circle.addEventListener("pointerup", endDrag); circle.addEventListener("pointercancel", endDrag);
    play.addEventListener("click", async () => {
      if (Date.now() < suppressUntil) return;
      if (!audio.paused) { audio.pause(); return; }
      shared.activate(audio); transport.querySelectorAll("audio").forEach(other => other.remove());
      transport.append(audio); status.textContent = `Stimulus ${item.number}`;
      try { await audio.play(); } catch (_) { status.textContent = "Playback unavailable. Try again or check the audio setup."; }
    });
    info.addEventListener("click", () => {
      closeDetails(); popover = document.createElement("div"); popover.className = "popover";
      const close = document.createElement("button"); close.className = "close"; close.textContent = "×"; close.setAttribute("aria-label", "Close details"); close.onclick = closeDetails;
      popover.append(close);
      const paragraph = text => { const p = document.createElement("p"); p.textContent = text; popover.append(p); };
      paragraph(`Stimulus ${item.number} · ${item.label} · ${item.family}`);
      item.states.forEach((state, index) => {
        paragraph(`State ${index + 1} (${state.time.toFixed(1)}s): ${state.notes.join(", ")} · MIDI ${state.midi.join(", ")}`);
        if (index) paragraph(state.movement.map(move => `V${move.voice}: ${move.semitones > 0 ? "+" : ""}${move.semitones} st`).join("; "));
      });
      paragraph(`${item.duration}s · ${item.preset} · Reverb: ${item.reverb}${item.level == null ? "" : ` (${item.level})`}`);
      canvas.append(popover);
      popover.style.left = `${clamp(parseFloat(element.style.left) + 95, 5, Math.max(5, canvas.clientWidth - popover.offsetWidth - 5))}px`;
      popover.style.top = `${clamp(parseFloat(element.style.top), 5, Math.max(5, canvas.clientHeight - popover.offsetHeight - 5))}px`;
    });
    nodes.push({item, element});
  });
  const observer = new ResizeObserver(layout); observer.observe(canvas); layout();
  cleanups.push(() => { observer.disconnect(); root.removeEventListener("pointerdown", outside); });
  return dispose;
}
