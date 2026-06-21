let currentlyPlaying = null;
let lineCounter = 1;

let currentMethodology = "line_v1";
let trialStarted = false;


document.body.classList.toggle(
  "vector-trial",
  currentMethodology === "vector_v1"
);

const methodologyOptions = document.querySelectorAll(".methodology-option");

methodologyOptions.forEach((option) => {
  option.addEventListener("click", () => {
    if (trialStarted) return;

    methodologyOptions.forEach((item) => {
      item.classList.remove("selected");
    });

    option.classList.add("selected");
    currentMethodology = option.dataset.methodology;

    document.body.classList.toggle(
      "vector-trial",
      currentMethodology === "vector_v1"
    );

    updateInstructions();

  });
});

let tonicDroneAudio = null;
let tonicDroneElement = null;
let tonicDroneEnabled = false;
let droneResumeTimer = null;

const dropZone = document.getElementById("drop-zone");
const NEAREST_CONNECTIONS = 5;
const allAudioLines = [];
const connectionLayer = document.getElementById("connection-layer");

const instructions = document.getElementById("instructions");
const instructionsToggle = document.getElementById("instructions-toggle");
const instructionsContent =
  document.getElementById("instructions-content");

const exportButton = document.getElementById("export-button");
const resetButton = document.getElementById("reset-button");
const exportMessage = document.getElementById("export-message");
const VECTOR_RADIUS_FACTOR = 0.38;
const vectorReadout = document.getElementById("vector-readout");

const LINE_V1_INSTRUCTIONS = `
Lines represent motion.

Move lines by dragging the handles.

Drag the start (0) and end (1) of each line to the perceived location relative to each other.

Use the labeled axes as general guides for sorting them.

After finished, evaluate whether the lines sit in the correct location relative to the others you have placed.

Adjust lines as needed until the arrangement most accurately reflects your perception of the feeling.
`;

const VECTOR_V1_INSTRUCTIONS = `
Vectors represent perceived change.

Drag a vector to adjust both its direction and strength.

Direction describes the perceived affective movement.

Length describes the perceived magnitude of that movement.

Use the labeled axes as general guides.

Adjust vectors until they most accurately reflect the feeling of each sample relative to the others.
`;

updateInstructions();

instructionsToggle.addEventListener("click", () => {
  instructions.classList.toggle("visible");
});

resetButton.addEventListener("click", () => {
  const confirmed = confirm(
    "Reset canvas and start over?"
  );

  if (confirmed) {
    window.location.reload();
  }
});

exportButton.addEventListener("click", () => {
  const hasLines = allAudioLines.length > 0;
  const allLocked = allAudioLines.every((line) => line.locked);

  if (!hasLines) {
    showExportMessage("No lines to export.");
    return;
  }

  if (!allLocked) {
    showExportMessage("Please lock all lines to export.");
    return;
  }

  const exportData = buildExportData();
  const timestamp = getTimestampString();

  downloadJSON(exportData, `audio-canvas-${timestamp}.json`);

  showExportMessage("Export downloaded.");
});

dropZone.addEventListener("dragover", (event) => {
  event.preventDefault();
});

dropZone.addEventListener("drop", (event) => {
  event.preventDefault();

  const files = event.dataTransfer.files;
  trialStarted = true;
  document.body.classList.add("trial-started");

  for (let file of files) {
    const fileName = file.name.toLowerCase();

    if (fileName.includes("tonic-drone")) {
    createTonicDrone(file);
    } else {
    createAudioLine(file, event.clientX, event.clientY);
    }
  }
});

function createAudioLine(file, x, y) {
  const group = document.createElement("div");
  group.className = "audio-line-group";

  const line = document.createElement("div");
  line.className = "audio-line";

  const startHandle = document.createElement("div");
  startHandle.className = "handle start-handle";

  const endHandle = document.createElement("div");
  endHandle.className = "handle end-handle";

  const motionDot = document.createElement("div");
  motionDot.className = "motion-dot";

  const startLabel = document.createElement("div");
  startLabel.className = "point-label";
  startLabel.textContent = "0";

  const endLabel = document.createElement("div");
  endLabel.className = "point-label";
  endLabel.textContent = "1";

  const nameLabel = document.createElement("div");
  nameLabel.className = "audio-label";

  const indexString = String(lineCounter).padStart(2, "0");
  nameLabel.textContent = indexString;

  lineCounter++;

  const centerGroup = document.createElement("div");
  centerGroup.className = "center-group";

  const audio = document.createElement("audio");
  audio.src = URL.createObjectURL(file);

  let start;
  let end;

  if (currentMethodology === "vector_v1") {

    const centerX = window.innerWidth / 2;
    const centerY = window.innerHeight / 2;

    const defaultHalfLength = getVectorMaxRadius() * 0.5;

    start = {
      x: centerX - defaultHalfLength,
      y: centerY
    };

    end = {
      x: centerX + defaultHalfLength,
      y: centerY
    };

  } else {

    start = {
      x: x,
      y: y
    };

    end = {
      x: x + 140,
      y: y
    };

  }
  const sampleId = file.name.replace(/\.[^/.]+$/, "");

  const lineData = {
    sample_id: sampleId,
    start,
    end,
    locked: false
  };

  if (currentMethodology === "vector_v1") {
    group.classList.add("vector-mode");
  }

  allAudioLines.push(lineData);


  document.body.appendChild(group);

  group.appendChild(line);
  group.appendChild(startHandle);
  group.appendChild(endHandle);
  group.appendChild(startLabel);
  group.appendChild(endLabel);
  group.appendChild(motionDot);
  centerGroup.appendChild(nameLabel);
  group.appendChild(centerGroup);

  updateLine();

  if (currentMethodology !== "vector_v1") {

    makeHandleDraggable(startHandle, (newX, newY) => {
      start.x = newX;
      start.y = newY;
      updateLine();
    });

    makeHandleDraggable(endHandle, (newX, newY) => {
      end.x = newX;
      end.y = newY;
      updateLine();
    });

  }

  if (currentMethodology !== "vector_v1") {

    makeLineDraggable(line, (dx, dy) => {
      start.x += dx;
      start.y += dy;

      end.x += dx;
      end.y += dy;

      updateLine();
    });

  }

  if (currentMethodology === "vector_v1") {
    makeVectorEditable(line, group, lineData, updateLine, togglePlayback);
  } else {
    line.addEventListener("click", togglePlayback);
    startHandle.addEventListener("click", togglePlayback);
    endHandle.addEventListener("click", togglePlayback);
  }

  audio.addEventListener("ended", () => {
    if (currentlyPlaying === audio) {
      currentlyPlaying = null;
    }

    group.classList.remove("is-playing");
    resetMotionDot();
    scheduleTonicDroneResume();
  });

  group.addEventListener("contextmenu", (event) => {
    event.preventDefault();

    group.classList.toggle("is-selected");

    lineData.locked = group.classList.contains("is-selected");

    updateExportButtonState();
  });

  function togglePlayback(event) {
    event.stopPropagation();

    if (audio.paused) {
      pauseTonicDrone();

      if (currentlyPlaying && currentlyPlaying !== audio) {
        currentlyPlaying.pause();
        currentlyPlaying.currentTime = 0;

        if (currentlyPlaying.groupRef) {
          currentlyPlaying.groupRef.classList.remove("is-playing");
        }
      }

      audio.currentTime = 0;
      audio.play();

      currentlyPlaying = audio;
      audio.groupRef = group;

      group.classList.add("is-playing");
      animateMotionDot();
    } else {
      audio.pause();
      audio.currentTime = 0;

      if (currentlyPlaying === audio) {
        currentlyPlaying = null;
      }

      group.classList.remove("is-playing");
      resetMotionDot();
    }
  }

  function updateLine() {
    const dx = end.x - start.x;
    const dy = end.y - start.y;
    const length = Math.sqrt(dx * dx + dy * dy);
    const angle = (Math.atan2(dy, dx) * 180) / Math.PI;

    line.style.left = start.x + "px";
    line.style.top = start.y + "px";
    line.style.width = length + "px";
    line.style.transform = `rotate(${angle}deg)`;

    startHandle.style.left = start.x + "px";
    startHandle.style.top = start.y + "px";

    endHandle.style.left = end.x + "px";
    endHandle.style.top = end.y + "px";

    startLabel.style.left = start.x - 20 + "px";
    startLabel.style.top = start.y - 8 + "px";

    endLabel.style.left = end.x + 12 + "px";
    endLabel.style.top = end.y - 8 + "px";

    if (currentMethodology === "vector_v1") {

      centerGroup.style.left = end.x + 16 + "px";
      centerGroup.style.top = end.y + "px";

    } else {

      const midX = (start.x + end.x) / 2;
      const midY = (start.y + end.y) / 2;

      centerGroup.style.left = midX + "px";
      centerGroup.style.top = midY + "px";

    }

    updateConnections();
    if (audio.paused) {
      resetMotionDot();
    }
  }
  function animateMotionDot() {
    motionDot.style.transition = "none";

    let dotStartX = start.x;
    let dotStartY = start.y;

    if (currentMethodology === "vector_v1") {
      dotStartX = window.innerWidth / 2;
      dotStartY = window.innerHeight / 2;
    }

    motionDot.style.left = dotStartX + "px";
    motionDot.style.top = dotStartY + "px";
    motionDot.style.opacity = "1";

    requestAnimationFrame(() => {
      const duration = audio.duration || 1;

      motionDot.style.transition =
        `left ${duration}s linear, top ${duration}s linear`;

      motionDot.style.left = end.x + "px";
      motionDot.style.top = end.y + "px";
    });
  }

  function resetMotionDot() {
    motionDot.style.transition = "none";

    if (currentMethodology === "vector_v1") {
      motionDot.style.left = window.innerWidth / 2 + "px";
      motionDot.style.top = window.innerHeight / 2 + "px";
    } else {
      motionDot.style.left = start.x + "px";
      motionDot.style.top = start.y + "px";
    }

    motionDot.style.opacity = "0";
  }

}

function makeHandleDraggable(handle, onMove) {
  let isDragging = false;
  let didMove = false;

  handle.addEventListener("mousedown", (event) => {
    if (handle.parentElement.classList.contains("is-selected")) return;

    event.stopPropagation();
    isDragging = true;
    didMove = false;
  });

  document.addEventListener("mousemove", (event) => {
    if (!isDragging) return;

    didMove = true;
    onMove(event.clientX, event.clientY);
  });

  document.addEventListener("mouseup", () => {
    isDragging = false;
  });

  handle.addEventListener(
    "click",
    (event) => {
      if (didMove) {
        event.preventDefault();
        event.stopPropagation();
      }
    },
    true
  );
}

function updateConnections() {
  connectionLayer.innerHTML = "";

  const handles = [];

  for (let audioLine of allAudioLines) {
    handles.push(audioLine.start);
    handles.push(audioLine.end);
  }

  for (let handle of handles) {
    const nearest = handles
      .filter((other) => other !== handle)
      .map((other) => {
        const dx = other.x - handle.x;
        const dy = other.y - handle.y;
        const distance = Math.sqrt(dx * dx + dy * dy);

        return { other, distance };
      })
      .sort((a, b) => a.distance - b.distance)
      .slice(0, NEAREST_CONNECTIONS);

    for (let item of nearest) {
      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");

      line.setAttribute("x1", handle.x);
      line.setAttribute("y1", handle.y);
      line.setAttribute("x2", item.other.x);
      line.setAttribute("y2", item.other.y);
      line.setAttribute("class", "connection-line");

      connectionLayer.appendChild(line);
    }
  }
}

function makeLineDraggable(line, onMove) {
  let isDragging = false;
  let didMove = false;
  let lastX = 0;
  let lastY = 0;

  line.addEventListener("mousedown", (event) => {
    if (line.parentElement.classList.contains("is-selected")) return;

    event.stopPropagation();

    isDragging = true;
    didMove = false;

    lastX = event.clientX;
    lastY = event.clientY;
  });

  document.addEventListener("mousemove", (event) => {
    if (!isDragging) return;

    const dx = event.clientX - lastX;
    const dy = event.clientY - lastY;

    if (Math.abs(dx) > 0 || Math.abs(dy) > 0) {
      didMove = true;
    }

    onMove(dx, dy);

    lastX = event.clientX;
    lastY = event.clientY;
  });

  document.addEventListener("mouseup", () => {
    isDragging = false;
  });

  line.addEventListener(
    "click",
    (event) => {
      if (didMove) {
        event.preventDefault();
        event.stopPropagation();
      }
    },
    true
  );
}

function createTonicDrone(file) {
  // If a drone already exists, remove it first
  if (tonicDroneElement) {
    tonicDroneElement.remove();
  }

  tonicDroneAudio = document.createElement("audio");
  tonicDroneAudio.src = URL.createObjectURL(file);
  tonicDroneAudio.loop = true;
  tonicDroneAudio.volume = 0.25;

  tonicDroneEnabled = true;

  tonicDroneElement = document.createElement("div");
  tonicDroneElement.className = "tonic-drone";
  tonicDroneElement.textContent = "TONIC DRONE";

  document.body.appendChild(tonicDroneElement);

  tonicDroneElement.addEventListener("click", () => {
    tonicDroneEnabled = !tonicDroneEnabled;

    if (tonicDroneEnabled) {
      tonicDroneAudio.play();
      tonicDroneElement.classList.add("is-on");
    } else {
      tonicDroneAudio.pause();
      tonicDroneElement.classList.remove("is-on");
    }
  });

  tonicDroneAudio.play();
  tonicDroneElement.classList.add("is-on");
}

function pauseTonicDrone() {
  if (!tonicDroneAudio) return;

  clearTimeout(droneResumeTimer);
  tonicDroneAudio.pause();
}

function scheduleTonicDroneResume() {
  if (!tonicDroneAudio) return;
  if (!tonicDroneEnabled) return;

  clearTimeout(droneResumeTimer);

  droneResumeTimer = setTimeout(() => {
    tonicDroneAudio.play();
  }, 200);
}

function showExportMessage(message) {
  exportMessage.textContent = message;
  exportMessage.style.display = "block";

  setTimeout(() => {
    exportMessage.style.display = "none";
  }, 2500);
}









function buildExportData() {
  const width = window.innerWidth;
  const height = window.innerHeight;

  const timestamp = getTimestampString();
  const participantId = "P001";
  const trialId = `${participantId}_${timestamp}`;

  return {
    trial_metadata: {
      participant_id: participantId,
      methodology_id: currentMethodology,
      trial_id: trialId,
      export_timestamp: timestamp,

      canvas_width: width,
      canvas_height: height,

      mapping_methodology:
        currentMethodology === "line_v1"
          ? "2-point Line"
          : "Center-pinned Vector",

      x_axis_definition: "stability",
      y_axis_definition: "positive/light to dark/negative"
    },

    mapping_observations: allAudioLines.map((line, index) => {
      const dx = line.end.x - line.start.x;
      const dy = line.end.y - line.start.y;

      const fullLengthPixels = Math.sqrt(dx * dx + dy * dy);
      const halfLengthPixels = fullLengthPixels / 2;

      const angleRad = Math.atan2(dy, dx);
      const angleDeg = angleRad * 180 / Math.PI;

      const vectorMaxRadius = getVectorMaxRadius();

      const strengthNorm =
        currentMethodology === "vector_v1"
          ? halfLengthPixels / vectorMaxRadius
          : null;

      const unitX = Math.cos(angleRad);
      const unitY = Math.sin(angleRad);

      const vectorDeltaX =
        currentMethodology === "vector_v1"
          ? unitX * strengthNorm
          : null;

      const vectorDeltaY =
        currentMethodology === "vector_v1"
          ? unitY * strengthNorm
          : null;      

      const lengthPixels =
        currentMethodology === "vector_v1"
          ? halfLengthPixels
          : fullLengthPixels;

      const lengthNorm =
        currentMethodology === "vector_v1"
          ? strengthNorm
          : fullLengthPixels / Math.sqrt(width * width + height * height);
      return {
        line_index: index + 1,
        sample_id: line.sample_id,

        start_x: line.start.x,
        start_y: line.start.y,

        end_x: line.end.x,
        end_y: line.end.y,

        start_x_norm: line.start.x / width,
        start_y_norm: line.start.y / height,

        end_x_norm: line.end.x / width,
        end_y_norm: line.end.y / height,

        length_pixels: lengthPixels,
        length_norm: lengthNorm,
        angle_deg: angleDeg,

        angle_rad: angleRad,

        vector_unit_x:
          currentMethodology === "vector_v1" ? unitX : null,

        vector_unit_y:
          currentMethodology === "vector_v1" ? unitY : null,

        strength_norm:
          currentMethodology === "vector_v1" ? strengthNorm : null,

        vector_delta_x:
          currentMethodology === "vector_v1" ? vectorDeltaX : null,

        vector_delta_y:
          currentMethodology === "vector_v1" ? vectorDeltaY : null,          
        full_display_length_pixels:
          currentMethodology === "vector_v1" ? fullLengthPixels : null,

        locked: line.locked
      };
    })
  };
}


function makeVectorEditable(line, group, lineData, updateLine, togglePlayback) {
  let isDragging = false;
  let didMove = false;

  line.addEventListener("pointerdown", (event) => {
    if (lineData.locked) return;

    event.stopPropagation();

    isDragging = true;
    didMove = false;

    line.setPointerCapture(event.pointerId);
    group.classList.add("is-editing");
  });

  line.addEventListener("pointermove", (event) => {
    if (!isDragging) return;

    didMove = true;

    const centerX = window.innerWidth / 2;
    const centerY = window.innerHeight / 2;

    const dxMouse = event.clientX - centerX;
    const dyMouse = event.clientY - centerY;

    const angle = Math.atan2(dyMouse, dxMouse);
    const mouseDistance = Math.sqrt(dxMouse * dxMouse + dyMouse * dyMouse);

    const maxHalfLength = getVectorMaxRadius();
    const minHalfLength = maxHalfLength * 0.05;

    const halfLength = Math.max(
      minHalfLength,
      Math.min(maxHalfLength, mouseDistance)
    );

    setVectorFromAngleAndHalfLength(lineData, angle, halfLength);

    updateLine();
    showVectorReadout(buildVectorReadout(lineData));
  });

  line.addEventListener("pointerup", (event) => {
    isDragging = false;
    group.classList.remove("is-editing");
    hideVectorReadout();

    try {
      line.releasePointerCapture(event.pointerId);
    } catch (error) {}
  });

  line.addEventListener("pointercancel", () => {
    isDragging = false;
    group.classList.remove("is-editing");
    hideVectorReadout();
  });

  line.addEventListener("click", (event) => {
    if (didMove) {
      event.preventDefault();
      event.stopPropagation();
      return;
    }

    hideVectorReadout();
    togglePlayback(event);
  });
}


function getLineLength(lineData) {
  const dx = lineData.end.x - lineData.start.x;
  const dy = lineData.end.y - lineData.start.y;

  return Math.sqrt(dx * dx + dy * dy);
}

function getLineAngleRadians(lineData) {
  const dx = lineData.end.x - lineData.start.x;
  const dy = lineData.end.y - lineData.start.y;

  return Math.atan2(dy, dx);
}

function setVectorFromAngleAndHalfLength(lineData, angle, halfLength) {
  const centerX = window.innerWidth / 2;
  const centerY = window.innerHeight / 2;

  lineData.start.x = centerX - Math.cos(angle) * halfLength;
  lineData.start.y = centerY - Math.sin(angle) * halfLength;

  lineData.end.x = centerX + Math.cos(angle) * halfLength;
  lineData.end.y = centerY + Math.sin(angle) * halfLength;
}








function downloadJSON(data, filename) {
  const jsonString = JSON.stringify(data, null, 2);

  const blob = new Blob([jsonString], {
    type: "application/json"
  });

  const url = URL.createObjectURL(blob);

  const link = document.createElement("a");
  link.href = url;
  link.download = filename;

  document.body.appendChild(link);
  link.click();

  document.body.removeChild(link);

  URL.revokeObjectURL(url);
}







function getComponentLabel(value, positiveLabel, negativeLabel) {
  const magnitude = Math.abs(value);

  if (magnitude < 0.01) return null;

  let strengthWord;

  if (magnitude < 0.35) {
    strengthWord = "SLIGHTLY";
  } else if (magnitude < 0.65) {
    strengthWord = "MODERATELY";
  } else {
    strengthWord = "STRONGLY";
  }

  const directionLabel =
    value > 0 ? positiveLabel : negativeLabel;

  return `${strengthWord} ${directionLabel}`;
}

function getStrengthLabel(lineData) {
  const strength =
    getLineLength(lineData) / 2 / getVectorMaxRadius();

  if (strength < 0.2) {
    return "VERY SUBTLE CHANGE";
  }

  if (strength < 0.45) {
    return "SUBTLE CHANGE";
  }

  if (strength < 0.7) {
    return "MODERATE CHANGE";
  }

  if (strength < 0.9) {
    return "SIGNIFICANT CHANGE";
  }

  return "EXTREME CHANGE";
}

function buildVectorReadout(lineData) {
  const angle = getLineAngleRadians(lineData);

  const strength =
    getLineLength(lineData) / 2 / getVectorMaxRadius();

  const unitX = Math.cos(angle);
  const unitY = Math.sin(angle);

  const x = unitX * strength;
  const y = unitY * strength;

  const lines = [];

  const brightnessLabel = getComponentLabel(
    -y,
    "BRIGHTER / MORE OPEN",
    "DARKER / MORE NEGATIVE"
  );

  const stabilityLabel = getComponentLabel(
    x,
    "MORE UNSTABLE",
    "MORE STABLE"
  );

  if (brightnessLabel) lines.push(brightnessLabel);
  if (stabilityLabel) lines.push(stabilityLabel);

  return lines.join("<br>");
}

function showVectorReadout(text) {
  if (!vectorReadout) return;

  vectorReadout.innerHTML = text;
  vectorReadout.classList.add("visible");
}

function hideVectorReadout() {
  if (!vectorReadout) return;

  vectorReadout.classList.remove("visible");
}

function getTimestampString() {
  const now = new Date();

  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");

  const hours = String(now.getHours()).padStart(2, "0");
  const minutes = String(now.getMinutes()).padStart(2, "0");
  const seconds = String(now.getSeconds()).padStart(2, "0");

  return `${year}${month}${day}_${hours}_${minutes}_${seconds}`;
}

function updateExportButtonState() {
  const allLocked =
    allAudioLines.length > 0 &&
    allAudioLines.every((line) => line.locked);

  if (allLocked) {
    exportButton.classList.add("ready");
  } else {
    exportButton.classList.remove("ready");
  }
}

function getVectorMaxRadius() {
  const boundary = document.getElementById("vector-boundary");
  const rect = boundary.getBoundingClientRect();

  return rect.width * 0.38;
}

function updateInstructions() {
  if (currentMethodology === "vector_v1") {
    instructionsContent.innerText = VECTOR_V1_INSTRUCTIONS;
  } else {
    instructionsContent.innerText = LINE_V1_INSTRUCTIONS;
  }
}