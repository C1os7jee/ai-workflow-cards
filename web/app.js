const state = {
  contentGoal: "",
  visualPlan: null,
  renderInput: null,
};

const statusEl = document.querySelector("#status");
const planForm = document.querySelector("#plan-form");
const feedbackForm = document.querySelector("#feedback-form");
const contentGoalEl = document.querySelector("#content-goal");
const imageProviderEl = document.querySelector("#image-provider");
const renderJsonEl = document.querySelector("#render-json");
const primaryGenerateBtn = document.querySelector("#generate-primary");
const pngGenerateBtn = document.querySelector("#generate-png");

function setStatus(text, kind = "normal") {
  statusEl.textContent = text;
  statusEl.dataset.kind = kind;
}

function setBusy(isBusy) {
  primaryGenerateBtn.disabled = isBusy;
  pngGenerateBtn.disabled = isBusy;
  imageProviderEl.disabled = isBusy;
}

function selectedImageProvider() {
  return imageProviderEl.value || "volcengine-seedream";
}

function numberValue(id) {
  const value = Number(document.querySelector(id).value || 0);
  return Number.isFinite(value) ? value : 0;
}

async function postJson(url, payload) {
  if (window.location.protocol === "file:") {
    throw new Error("请通过本地服务打开：python3 main.py --mode web");
  }
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "请求失败");
  }
  return data;
}

function renderPlan(data) {
  state.visualPlan = data.visual_plan;
  state.renderInput = data.render_input;
  const plan = state.visualPlan;
  const renderInput = state.renderInput;

  document.querySelector("#strategy-title").textContent = plan.recommended_strategy;
  document.querySelector("#strategy-signal").textContent = "AI decided / human checks";
  document.querySelector("#rail-strategy").textContent = plan.recommended_strategy;
  document.querySelector("#rail-render").textContent = `${renderInput.style} / ${renderInput.layout_id}`;
  document.querySelector("#cover-title").textContent = plan.cover_direction.title;
  document.querySelector("#cover-hook").textContent = plan.cover_direction.hook;
  document.querySelector("#cover-visual").textContent = plan.cover_direction.visual;
  document.querySelector("#alternatives").textContent = plan.alternatives.join(" / ");
  document.querySelector("#reason").textContent = plan.reason;
  document.querySelector("#risk").textContent = plan.risk;
  document.querySelector("#render-style").textContent = `style ${renderInput.style}`;
  document.querySelector("#render-theme").textContent = `theme ${renderInput.theme}`;
  document.querySelector("#render-layout").textContent = `layout ${renderInput.layout_id}`;
  document.querySelector("#render-provider").textContent = `provider ${renderInput.image_provider || selectedImageProvider()}`;
  renderJsonEl.textContent = JSON.stringify(renderInput, null, 2);

  renderCreativePlan(renderInput);
  renderCheckpoints(plan.human_checkpoints);
}

function renderCreativePlan(renderInput) {
  const jobs = renderInput.visual_blueprint?.image_jobs || [];
  if (jobs.length > 0) {
    renderImageJobs(jobs);
    return;
  }
  renderSlides(renderInput.slides);
}

function renderImageJobs(jobs) {
  const strip = document.querySelector("#slide-strip");
  strip.replaceChildren();
  jobs.forEach((job, index) => {
    const card = document.createElement("article");
    card.className = `slide-card image-job ${index === 0 ? "cover" : ""}`;

    const type = document.createElement("span");
    type.className = "slide-type";
    type.textContent = `${String(index + 1).padStart(2, "0")} / ${job.role || "image"}`;

    const title = document.createElement("h3");
    title.textContent = job.title || job.id || `card_${index + 1}`;

    const message = document.createElement("p");
    message.textContent = job.message || job.source_detail || "";

    const prompt = document.createElement("small");
    prompt.className = "job-prompt";
    prompt.textContent = job.prompt || "";

    card.append(type, title, message, prompt);
    strip.append(card);
  });
}

function renderSlides(slides) {
  const strip = document.querySelector("#slide-strip");
  strip.replaceChildren();
  slides.forEach((slide, index) => {
    const card = document.createElement("article");
    card.className = `slide-card ${slide.type}`;

    const type = document.createElement("span");
    type.className = "slide-type";
    type.textContent = `${String(index + 1).padStart(2, "0")} / ${slide.type}`;
    card.append(type);

    if (slide.type === "cover") {
      const title = document.createElement("h3");
      title.textContent = slide.title;
      const hook = document.createElement("p");
      hook.textContent = slide.hook;
      card.append(title, hook);
    } else if (slide.type === "content") {
      const title = document.createElement("h3");
      title.textContent = slide.heading;
      const list = document.createElement("ul");
      slide.points.forEach((point) => {
        const item = document.createElement("li");
        item.textContent = point;
        list.append(item);
      });
      card.append(title, list);
    } else {
      const text = document.createElement("h3");
      text.textContent = slide.text;
      card.append(text);
    }

    strip.append(card);
  });
}

function renderCheckpoints(checkpoints) {
  const list = document.querySelector("#checkpoints");
  list.replaceChildren();
  checkpoints.forEach((checkpoint) => {
    const item = document.createElement("li");
    item.textContent = checkpoint;
    list.append(item);
  });
}

async function runVisualPlan(contentGoal, plannerMode = "skill") {
  const data = await postJson("/api/plan", {
    content_goal: contentGoal,
    image_provider: selectedImageProvider(),
    planner_mode: plannerMode,
  });
  renderPlan(data);
  return data;
}

async function renderPngDeck(contentGoal) {
  const data = await postJson("/api/render-deck", {
    content_goal: contentGoal,
    image_provider: selectedImageProvider(),
    planner_mode: "ai",
  });
  renderAssets(data);
  if (data.visual_plan && data.visual_plan.render_input_snapshot) {
    renderPlan({
      visual_plan: data.visual_plan,
      render_input: data.visual_plan.render_input_snapshot,
    });
  }
  return data;
}

async function generateFullDeck(event) {
  event.preventDefault();
  const contentGoal = contentGoalEl.value.trim();
  if (!contentGoal) {
    setStatus("需要内容 brief", "error");
    contentGoalEl.focus();
    return;
  }
  setBusy(true);
  setStatus("生成方案中");
  showAssetMessage("等待渲染 PNG...");
  state.contentGoal = contentGoal;
  try {
    await runVisualPlan(contentGoal, "ai");
    setStatus("生成 PNG 中");
    await renderPngDeck(contentGoal);
    setStatus("方案和 PNG 已生成", "success");
  } catch (error) {
    showAssetMessage(error.message, "error");
    setStatus(error.message, "error");
  } finally {
    setBusy(false);
  }
}

async function loadInitialPlan() {
  const contentGoal = contentGoalEl.value.trim();
  if (!contentGoal) {
    return;
  }
  setStatus("生成方案中");
  try {
    await runVisualPlan(contentGoal);
    setStatus("方案已生成，点击按钮出图", "success");
  } catch (error) {
    setStatus(error.message, "error");
  }
}

async function recordFeedback(event) {
  event.preventDefault();
  const contentGoal = contentGoalEl.value.trim();
  if (!contentGoal) {
    setStatus("需要内容 brief", "error");
    contentGoalEl.focus();
    return;
  }
  const payload = {
    content_goal: contentGoal,
    post_id: document.querySelector("#post-id").value.trim(),
    topic: document.querySelector("#topic").value.trim(),
    metrics: {
      views: numberValue("#views"),
      likes: numberValue("#likes"),
      saves: numberValue("#saves"),
      comments: numberValue("#comments"),
    },
    human_notes: document.querySelector("#human-notes").value.trim(),
  };
  setStatus("记录反馈中");
  try {
    const data = await postJson("/api/feedback", payload);
    document.querySelector("#feedback-result").textContent = `已写入 ${data.feedback_file}`;
    setStatus("反馈已记录", "success");
  } catch (error) {
    setStatus(error.message, "error");
  }
}

async function generatePngDeck() {
  const contentGoal = contentGoalEl.value.trim();
  if (!contentGoal) {
    setStatus("需要内容 brief", "error");
    contentGoalEl.focus();
    return;
  }
  setBusy(true);
  setStatus("生成 PNG 中");
  showAssetMessage("正在渲染 PNG...");
  try {
    await renderPngDeck(contentGoal);
    setStatus("PNG 已生成", "success");
  } catch (error) {
    showAssetMessage(error.message, "error");
    setStatus(error.message, "error");
  } finally {
    setBusy(false);
  }
}

function renderAssets(data) {
  const grid = document.querySelector("#asset-grid");
  grid.replaceChildren();
  document.querySelector("#asset-dir").textContent = data.task_dir || "生成完成";
  (data.png_paths || []).forEach((path, index) => {
    const link = document.createElement("a");
    link.className = "asset-card";
    link.href = toWebOutputPath(path);
    link.target = "_blank";
    const image = document.createElement("img");
    image.src = toWebOutputPath(path);
    image.alt = `生成图 ${index + 1}`;
    const label = document.createElement("span");
    label.textContent = path.split("/").pop() || `card_${String(index + 1).padStart(2, "0")}.png`;
    link.append(image, label);
    grid.append(link);
  });
}

function showAssetMessage(message, kind = "normal") {
  document.querySelector("#asset-dir").textContent = message;
  const grid = document.querySelector("#asset-grid");
  grid.replaceChildren();
  const empty = document.createElement("p");
  empty.className = "asset-message";
  empty.dataset.kind = kind;
  empty.textContent = message;
  grid.append(empty);
}

function toWebOutputPath(path) {
  const marker = "/output/";
  const index = path.indexOf(marker);
  if (index >= 0) {
    return path.slice(index);
  }
  return path;
}

async function copyRenderJson() {
  try {
    await navigator.clipboard.writeText(renderJsonEl.textContent);
    setStatus("JSON 已复制", "success");
  } catch (error) {
    setStatus("复制失败", "error");
  }
}

planForm.addEventListener("submit", generateFullDeck);
feedbackForm.addEventListener("submit", recordFeedback);
document.querySelector("#copy-render").addEventListener("click", copyRenderJson);
pngGenerateBtn.addEventListener("click", generatePngDeck);
imageProviderEl.addEventListener("change", loadInitialPlan);

if (window.location.protocol === "file:") {
  setStatus("请用本地服务打开", "error");
} else {
  loadInitialPlan();
}
