import { getJson } from "../shared/api-client.js";

/**
 * The `/` menu in the composer.
 *
 * Typing `/` lists the skills mounted on the agent; typing more narrows the list;
 * Space (or Enter, or Tab) picks the highlighted one. A `/` that matches nothing
 * stays ordinary text, so a path or an address can still be typed. One message
 * carries one skill, shown as a chip that can be removed.
 */
export function bindSkillMenu(form) {
  const textarea = form?.querySelector("textarea[name='message']");
  const menu = form?.querySelector("[data-skill-menu]");
  const chipRow = form?.querySelector("[data-skill-chip-row]");
  if (!textarea || !menu || !chipRow) {
    return { selectedSkill: () => "", clear() {} };
  }
  let skills = [];
  let matches = [];
  let active = 0;
  let selected = "";

  getJson("/playground/run/skills")
    .then((data) => {
      skills = Array.isArray(data?.skills) ? data.skills : [];
    })
    .catch(() => {
      skills = [];
    });

  textarea.setAttribute("aria-autocomplete", "list");

  function query() {
    const match = /^\/(\S*)$/.exec(textarea.value);
    return match ? match[1] : null;
  }

  function update() {
    const typed = query();
    if (typed === null || selected || !skills.length) {
      close();
      return;
    }
    const lowered = typed.toLowerCase();
    matches = skills
      .filter((skill) => skill.name.toLowerCase().includes(lowered))
      .sort((left, right) => rank(left, lowered) - rank(right, lowered));
    if (!matches.length) {
      close();
      return;
    }
    active = 0;
    render();
  }

  function rank(skill, lowered) {
    const name = skill.name.toLowerCase();
    if (name === lowered) {
      return 0;
    }
    return name.startsWith(lowered) ? 1 : 2;
  }

  function render() {
    menu.replaceChildren(
      ...matches.map((skill, index) => {
        const option = document.createElement("div");
        option.className = `skill-menu-option${index === active ? " is-active" : ""}`;
        option.setAttribute("role", "option");
        option.setAttribute("aria-selected", index === active ? "true" : "false");
        option.dataset.skillOption = skill.name;
        const name = document.createElement("strong");
        name.textContent = `/${skill.name}`;
        const description = document.createElement("span");
        description.textContent = skill.description || "";
        option.append(name, description);
        option.addEventListener("mousedown", (event) => {
          event.preventDefault();
          choose(index);
        });
        return option;
      }),
    );
    menu.hidden = false;
    textarea.setAttribute("aria-expanded", "true");
  }

  function close() {
    menu.hidden = true;
    matches = [];
    textarea.setAttribute("aria-expanded", "false");
  }

  function choose(index) {
    const skill = matches[index];
    if (!skill) {
      return;
    }
    selected = skill.name;
    textarea.value = "";
    renderChip();
    close();
    textarea.focus();
  }

  function renderChip() {
    chipRow.replaceChildren();
    if (!selected) {
      chipRow.hidden = true;
      return;
    }
    const chip = document.createElement("span");
    chip.className = "skill-chip";
    chip.dataset.skillChip = selected;
    chip.append(document.createTextNode(`/${selected}`));
    const remove = document.createElement("button");
    remove.type = "button";
    remove.setAttribute("aria-label", `移除技能 ${selected}`);
    remove.textContent = "×";
    remove.addEventListener("click", () => {
      clear();
      textarea.focus();
    });
    chip.append(remove);
    chipRow.append(chip);
    chipRow.hidden = false;
  }

  function clear() {
    selected = "";
    renderChip();
  }

  textarea.addEventListener("input", update);
  textarea.addEventListener("keydown", (event) => {
    if (menu.hidden) {
      if (event.key === "Backspace" && selected && textarea.value === "") {
        event.preventDefault();
        clear();
      }
      return;
    }
    if (event.isComposing) {
      return;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      active = (active + step + matches.length) % matches.length;
      render();
      return;
    }
    if (event.key === " " || event.key === "Tab" || (event.key === "Enter" && !event.shiftKey)) {
      // Picking, not typing: this must reach nobody else, or Enter would also send.
      event.preventDefault();
      event.stopImmediatePropagation();
      choose(active);
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      close();
    }
  });

  return { selectedSkill: () => selected, clear };
}
