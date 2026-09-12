import { getJson, postJson } from "../shared/api-client.js";

const UNREACHABLE = { refused: { rule: "request_failed", message: "無法連線到伺服器，請稍後再試。" } };

const panel = document.querySelector("[data-skill-package-panel]");
if (panel) {
  bindSkillPackagePanel(panel);
}

function bindSkillPackagePanel(root) {
  const list = root.querySelector("[data-skill-package-list]");
  const empty = root.querySelector("[data-skill-package-empty]");
  const note = root.querySelector("[data-skill-package-note]");
  const preview = root.querySelector("[data-skill-package-preview]");
  const uploadForm = root.querySelector("[data-skill-upload-form]");
  const uploadInput = root.querySelector("[data-skill-upload-input]");
  const gitForm = root.querySelector("[data-skill-git-form]");

  async function refresh() {
    const data = await reach(() => getJson("/playground/builder/skills"));
    if (data.refused) {
      showResult(data);
      return;
    }
    renderMounted(data.packages || []);
    if (note) {
      note.hidden = data.can_save !== false;
      note.textContent = "目前是匿名試用：掛上的技能包只在這次工作階段有效，登入並儲存 agent 後其他人才看得到。";
    }
  }

  function renderMounted(packages) {
    list.replaceChildren(...packages.map(mountedItem));
    empty.hidden = packages.length > 0;
  }

  function mountedItem(pkg) {
    const item = element("li", "skill-package-item");
    item.dataset.skillPackage = pkg.name;
    item.append(packageSummary(pkg));
    const actions = element("div", "skill-package-item-actions");
    const change = element("button", "button button-ghost skill-package-change", "更換版本");
    change.type = "button";
    change.addEventListener("click", () => startVersionChange(pkg));
    const remove = element("button", "button button-ghost skill-package-remove", "移除");
    remove.type = "button";
    remove.addEventListener("click", async () => {
      remove.disabled = true;
      const data = await reach(() => postJson("/playground/builder/skills/remove", { name: pkg.name }));
      if (data.refused) {
        remove.disabled = false;
        showResult(data);
        return;
      }
      renderMounted(data.packages || []);
    });
    actions.append(change, remove);
    item.append(actions);
    return item;
  }

  // A new version goes through the same check and confirmation as a first
  // mount; this only points the person at the form that starts it.
  function startVersionChange(pkg) {
    preview.hidden = false;
    preview.classList.remove("is-refused", "is-passed");
    if (pkg.source === "git") {
      const url = gitForm?.querySelector("#skill-package-git-url");
      const version = gitForm?.querySelector("#skill-package-git-version");
      if (url) {
        url.value = pkg.url || "";
      }
      if (version) {
        version.value = "";
        version.focus();
      }
      preview.replaceChildren(
        element("h3", "", `更換「${pkg.name}」的版本`),
        element("p", "", `目前鎖定在 ${pkg.version}。填入新的版本標籤或 commit 後按「檢查」，確認後才會取代目前的版本。`),
      );
      return;
    }
    uploadInput?.focus();
    preview.replaceChildren(
      element("h3", "", `更換「${pkg.name}」的版本`),
      element("p", "", "選擇新版本的壓縮檔後按「檢查」，確認後才會取代目前的版本。"),
    );
  }

  function packageSummary(pkg) {
    const wrapper = element("div", "skill-package-summary");
    const head = element("div", "skill-package-item-head");
    head.append(element("strong", "", pkg.name), element("span", "skill-package-version", pkg.version));
    wrapper.append(head);
    if (pkg.missing) {
      wrapper.append(element("p", "skill-package-missing", "這台伺服器上找不到這個技能包的檔案。請移除後重新掛載。"));
    }
    const source = pkg.source === "git" ? `來源：${pkg.url}` : "來源：上傳的壓縮檔";
    const maintainer = pkg.maintainer?.name ? `維護者：${pkg.maintainer.name}${pkg.maintainer.contact ? `（${pkg.maintainer.contact}）` : ""}` : "維護者：未填寫";
    wrapper.append(element("p", "skill-package-meta", `${source}　${maintainer}`));
    const skills = element("ul", "skill-package-skills");
    (pkg.skills || []).forEach((skill) => {
      const row = element("li", "");
      row.append(element("code", "", `/${skill.name}`), document.createTextNode(`　${skill.description}`));
      skills.append(row);
    });
    wrapper.append(skills);
    return wrapper;
  }

  function showResult(result) {
    preview.hidden = false;
    preview.classList.toggle("is-refused", Boolean(result.refused));
    preview.classList.toggle("is-passed", !result.refused);
    if (result.refused) {
      const refused = result.refused;
      preview.replaceChildren(
        element("h3", "", "無法掛載這個技能包"),
        element("p", "", refused.message || refused.detail || "檢查沒有通過。"),
      );
      if (refused.rule !== "request_failed") {
        preview.append(element("p", "skill-package-refusal-rule", `違反規則：${refused.rule}${refused.path ? `　檔案：${refused.path}` : ""}`));
      }
      if (refused.detail && refused.detail !== refused.message) {
        preview.append(element("p", "skill-package-meta", refused.detail));
      }
      return;
    }
    const heading = result.replaces ? `檢查通過：將以新版本取代已掛載的「${result.replaces}」` : "檢查通過：確認後會掛上以下技能";
    const actions = element("div", "skill-package-actions");
    const confirm = element("button", "button button-primary", "確認掛載");
    confirm.type = "button";
    confirm.dataset.skillPackageConfirm = "";
    const cancel = element("button", "button button-ghost", "取消");
    cancel.type = "button";
    confirm.addEventListener("click", async () => {
      confirm.disabled = true;
      const data = await reach(() => postJson("/playground/builder/skills/mount", { staging_id: result.staging_id }));
      if (data.error) {
        showResult({ refused: { rule: "request_failed", message: data.error } });
        return;
      }
      if (data.refused) {
        showResult(data);
        return;
      }
      renderMounted(data.packages || []);
      preview.hidden = true;
      uploadForm?.reset();
      gitForm?.reset();
    });
    cancel.addEventListener("click", () => {
      preview.hidden = true;
    });
    actions.append(confirm, cancel);
    preview.replaceChildren(element("h3", "", heading), packageSummary(result.package), actions);
  }

  uploadForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const file = uploadInput?.files?.[0];
    if (!file) {
      showResult({ refused: { rule: "missing_source", message: "請先選擇一個技能包壓縮檔。" } });
      return;
    }
    const body = new FormData();
    body.append("package", file);
    showResult(await reach(async () => (await fetch("/playground/builder/skills/inspect", { method: "POST", body })).json()));
  });

  gitForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(gitForm);
    showResult(
      await reach(() =>
        postJson("/playground/builder/skills/inspect", {
          git_url: String(formData.get("git_url") || ""),
          version: String(formData.get("version") || ""),
        }),
      ),
    );
  });

  refresh();
}

// Every request here answers with JSON; a dropped connection or a page the
// server could not render becomes a message instead of a panel that stops responding.
async function reach(send) {
  try {
    return await send();
  } catch {
    return UNREACHABLE;
  }
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) {
    node.className = className;
  }
  if (text !== undefined) {
    node.textContent = text;
  }
  return node;
}
