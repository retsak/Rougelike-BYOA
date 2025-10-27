const startForm = document.getElementById("start-form");
const actionForm = document.getElementById("action-form");
const resetBtn = document.getElementById("reset-btn");
const storyPanel = document.getElementById("story-panel");
const builder = document.getElementById("builder");
const storyLog = document.getElementById("story-log");
const heroName = document.getElementById("hero-name");
const heroDetails = document.getElementById("hero-details");
const heroCompanion = document.getElementById("hero-companion");
const actionInput = document.getElementById("action");

let sessionId = null;

const appendStory = (text) => {
  const block = document.createElement("p");
  block.textContent = text;
  storyLog.appendChild(block);
  storyLog.scrollTop = storyLog.scrollHeight;
};

const populateHero = (state) => {
  heroName.textContent = state.hero;
  heroDetails.textContent = `${state.trait} ${state.archetype}`;
  heroCompanion.textContent = `Companion: ${state.companion}`;
};

startForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(startForm);
  const payload = Object.fromEntries(formData.entries());

  const response = await fetch("/api/start", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    appendStory("The weave of magic falters. Try again.");
    return;
  }

  const data = await response.json();
  sessionId = data.sessionId;
  storyLog.innerHTML = "";
  populateHero(data.state);
  appendStory(data.state.history.at(-1));

  builder.classList.add("hidden");
  storyPanel.classList.remove("hidden");
  actionInput.focus();
});

actionForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!sessionId) return;
  const actionValue = actionInput.value.trim();
  if (!actionValue) {
    appendStory("Share a plan before the city drifts away.");
    return;
  }
  const response = await fetch("/api/step", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ session_id: sessionId, action: actionValue }),
  });
  if (!response.ok) {
    appendStory("The thread slips from your grasp. Refresh the tale.");
    return;
  }
  const data = await response.json();
  const newest = data.state.history.at(-1);
  appendStory(newest);
  actionInput.value = "";
  actionInput.focus();
});

resetBtn.addEventListener("click", async () => {
  if (!sessionId) return;
  await fetch("/api/reset", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ session_id: sessionId }),
  });
  sessionId = null;
  builder.classList.remove("hidden");
  storyPanel.classList.add("hidden");
  storyLog.innerHTML = "";
  startForm.reset();
  startForm.querySelector("input")?.focus();
});
