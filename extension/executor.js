// extension/executor.js - DOM Form Inspector & Action Executor via chrome.scripting

export async function extractFormInputs(tabId) {
  if (!tabId) return [];
  const results = await chrome.scripting.executeScript({
    target: { tabId: tabId },
    func: () => {
      const elements = Array.from(document.querySelectorAll("input, select, textarea"));
      return elements.map((el, index) => {
        const type = (el.type || el.tagName).toLowerCase();
        if (type === "hidden" || type === "submit" || type === "button" || type === "reset") {
          return null;
        }
        let labelText = "";
        if (el.labels && el.labels.length > 0) {
          labelText = el.labels[0].innerText || el.labels[0].textContent || "";
        }
        if (!labelText) {
          const parentLabel = el.closest("label");
          if (parentLabel) labelText = parentLabel.innerText || parentLabel.textContent || "";
        }
        if (!labelText) {
          labelText = el.getAttribute("aria-label") || el.getAttribute("aria-placeholder") || "";
        }

        return {
          index,
          tag: el.tagName.toLowerCase(),
          type: type,
          name: el.name || "",
          id: el.id || "",
          placeholder: el.placeholder || "",
          label: labelText.trim(),
          value: el.value || ""
        };
      }).filter(Boolean);
    }
  });

  return results?.[0]?.result || [];
}

export async function fillFormBatch(tabId, fills, submit = false) {
  if (!tabId || !Array.isArray(fills)) return { count: 0, message: "No fills provided" };

  const results = await chrome.scripting.executeScript({
    target: { tabId: tabId },
    func: (fillsArray, shouldSubmit) => {
      const elements = Array.from(document.querySelectorAll("input, select, textarea"));
      let filledCount = 0;

      for (const item of fillsArray) {
        if (!item || item.index === undefined || item.index === null) continue;
        const el = elements[item.index];
        if (!el) continue;

        const val = item.value !== undefined && item.value !== null ? String(item.value) : "";
        if (!val) continue;

        el.scrollIntoView({ behavior: "smooth", block: "center" });
        if (typeof el.focus === "function") el.focus();

        if (el.tagName.toLowerCase() === "select") {
          let matched = false;
          for (const opt of Array.from(el.options)) {
            if (opt.text.toLowerCase().includes(val.toLowerCase()) || opt.value.toLowerCase().includes(val.toLowerCase())) {
              el.value = opt.value;
              matched = true;
              break;
            }
          }
          if (!matched) el.value = val;
          el.dispatchEvent(new Event("change", { bubbles: true }));
        } else {
          el.value = "";
          el.dispatchEvent(new Event("input", { bubbles: true }));
          el.value = val;
          el.dispatchEvent(new Event("input", { bubbles: true }));
          el.dispatchEvent(new Event("change", { bubbles: true }));
        }
        filledCount++;
      }

      if (shouldSubmit) {
        const submitBtn = document.querySelector("button[type='submit'], input[type='submit']") || elements.find(e => e.type === "submit");
        if (submitBtn) {
          submitBtn.click();
        } else {
          const form = document.querySelector("form");
          if (form) form.submit();
        }
      }

      return { count: filledCount, submitted: shouldSubmit };
    },
    args: [fills, submit]
  });

  return results?.[0]?.result || { count: 0, submitted: false };
}

export async function executeTabAction(tabId, actionData) {
  if (!tabId) throw new Error("No active tabId provided for action execution.");

  const results = await chrome.scripting.executeScript({
    target: { tabId: tabId },
    func: inContentExecutor,
    args: [actionData]
  });

  return results?.[0]?.result || { success: true, message: "Action executed" };
}

function inContentExecutor(actionData) {
  const VIEWPORT_W = 1280;
  const VIEWPORT_H = 800;

  function scaleCoords(x, y) {
    const scaleX = window.innerWidth / VIEWPORT_W;
    const scaleY = window.innerHeight / VIEWPORT_H;
    return {
      cx: Math.max(0, Math.min(Math.round(x * scaleX), window.innerWidth - 1)),
      cy: Math.max(0, Math.min(Math.round(y * scaleY), window.innerHeight - 1))
    };
  }

  function simulateClick(el, cx, cy) {
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "center", inline: "center" });

    const opts = {
      bubbles: true,
      cancelable: true,
      view: window,
      clientX: cx,
      clientY: cy
    };

    el.dispatchEvent(new PointerEvent("pointerdown", opts));
    el.dispatchEvent(new MouseEvent("mousedown", opts));
    if (typeof el.focus === "function") el.focus();
    el.dispatchEvent(new PointerEvent("pointerup", opts));
    el.dispatchEvent(new MouseEvent("mouseup", opts));
    el.click();
  }

  function typeIntoElement(el, text) {
    if (!el) return;
    if (typeof el.focus === "function") el.focus();

    if ("value" in el) {
      el.value = "";
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.value = text;
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
    } else if (el.isContentEditable) {
      el.textContent = text;
      el.dispatchEvent(new Event("input", { bubbles: true }));
    }
  }

  try {
    const actionType = actionData.action;

    if (actionType === "click" || actionType === "click_coordinate") {
      const { x, y } = actionData;
      if (x === null || x === undefined || y === null || y === undefined) {
        return { success: false, message: "Missing click coordinates" };
      }
      const { cx, cy } = scaleCoords(x, y);
      const targetEl = document.elementFromPoint(cx, cy) || document.body;
      simulateClick(targetEl, cx, cy);
      return { success: true, message: `Clicked at (${x}, ${y})` };
    }

    if (actionType === "type") {
      const { x, y, text } = actionData;
      const strText = text || "";
      if (x !== null && x !== undefined && y !== null && y !== undefined) {
        const { cx, cy } = scaleCoords(x, y);
        const targetEl = document.elementFromPoint(cx, cy) || document.activeElement;
        simulateClick(targetEl, cx, cy);
        typeIntoElement(targetEl, strText);
        return { success: true, message: `Typed '${strText}'` };
      } else {
        const active = document.activeElement || document.body;
        typeIntoElement(active, strText);
        return { success: true, message: `Typed '${strText}'` };
      }
    }

    if (actionType === "scroll") {
      const dir = (actionData.direction || "down").toLowerCase();
      const amount = actionData.amount || 500;
      const dy = dir === "down" ? amount : (dir === "up" ? -amount : 0);
      window.scrollBy({ top: dy, behavior: "smooth" });
      return { success: true, message: `Scrolled ${dir} by ${amount}px` };
    }

    return { success: true, message: `Action ${actionType} executed` };
  } catch (err) {
    return { success: false, message: `Executor error: ${err.message}` };
  }
}
