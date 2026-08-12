// extension/executor.js - DOM Action Executor via chrome.scripting

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
      return { success: true, message: `Clicked at (${x}, ${y}) [Scaled: ${cx}, ${cy}]` };
    }

    if (actionType === "type") {
      const { x, y, text } = actionData;
      const strText = text || "";
      if (x !== null && x !== undefined && y !== null && y !== undefined) {
        const { cx, cy } = scaleCoords(x, y);
        const targetEl = document.elementFromPoint(cx, cy) || document.activeElement;
        simulateClick(targetEl, cx, cy);
        typeIntoElement(targetEl, strText);
        return { success: true, message: `Typed '${strText}' at (${x}, ${y})` };
      } else {
        const active = document.activeElement || document.body;
        typeIntoElement(active, strText);
        return { success: true, message: `Typed '${strText}' into active element` };
      }
    }

    if (actionType === "batch_type") {
      const inputs = actionData.batch_inputs || [];
      let count = 0;
      for (const item of inputs) {
        if (!item) continue;
        const itemText = item.text || item.value || "";
        if (item.x !== undefined && item.y !== undefined) {
          const { cx, cy } = scaleCoords(item.x, item.y);
          const targetEl = document.elementFromPoint(cx, cy);
          if (targetEl) {
            simulateClick(targetEl, cx, cy);
            typeIntoElement(targetEl, itemText);
            count++;
          }
        }
      }
      return { success: true, message: `Batch typed ${count} form fields` };
    }

    if (actionType === "scroll") {
      const dir = (actionData.direction || "down").toLowerCase();
      const amount = actionData.amount || 500;
      const dy = dir === "down" ? amount : (dir === "up" ? -amount : 0);
      window.scrollBy({ top: dy, behavior: "smooth" });
      return { success: true, message: `Scrolled ${dir} by ${amount}px` };
    }

    if (actionType === "key") {
      const keyName = actionData.key || "Enter";
      const active = document.activeElement || document.body;
      active.dispatchEvent(new KeyboardEvent("keydown", { key: keyName, bubbles: true }));
      active.dispatchEvent(new KeyboardEvent("keypress", { key: keyName, bubbles: true }));
      active.dispatchEvent(new KeyboardEvent("keyup", { key: keyName, bubbles: true }));
      return { success: true, message: `Pressed key '${keyName}'` };
    }

    if (actionType === "done") {
      return { success: true, message: `Goal marked done: ${actionData.reasoning || ""}` };
    }

    return { success: true, message: `Action ${actionType} executed` };
  } catch (err) {
    return { success: false, message: `Executor error: ${err.message}` };
  }
}
