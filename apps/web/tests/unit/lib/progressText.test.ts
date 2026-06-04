/**
 * Tests for live progress text fixes across Flows 4-6:
 *
 * 1. useSimulation thinking preservation — empty string from backend must not
 *    overwrite the last non-empty thinking value (root cause of agent card flip).
 *
 * 2. loadingOverlayController — show() must cancel a pending dismiss timer so
 *    a subsequent show() call always wins and the overlay doesn't flicker off.
 *
 * 3. loadingOverlayController — updateText() must update text without resetting
 *    showTime (so MIN_DISPLAY guard is not re-armed on every pipeline message).
 */

// ── 1. Thinking preservation logic ────────────────────────────────────────────

/**
 * Pure implementation of the fixed thinking merger so we can unit-test the
 * logic without mounting the full React hook.
 */
function mergeThinking(
  incoming: string | null | undefined,
  previous: string | undefined,
): string {
  return (incoming?.trim() ? incoming : previous) ?? "";
}

describe("mergeThinking — preserve last non-empty thinking", () => {
  it("keeps a new non-empty thinking value", () => {
    expect(mergeThinking("Scanning pixel density...", "")).toBe("Scanning pixel density...");
  });

  it("preserves previous thinking when incoming is empty string", () => {
    expect(mergeThinking("", "Analyzing compression artifacts...")).toBe(
      "Analyzing compression artifacts...",
    );
  });

  it("preserves previous thinking when incoming is whitespace-only", () => {
    expect(mergeThinking("   ", "Cross-referencing noise signatures...")).toBe(
      "Cross-referencing noise signatures...",
    );
  });

  it("preserves previous thinking when incoming is null", () => {
    expect(mergeThinking(null, "Validating spectral consistency...")).toBe(
      "Validating spectral consistency...",
    );
  });

  it("preserves previous thinking when incoming is undefined", () => {
    expect(mergeThinking(undefined, "Running ELA differential analysis...")).toBe(
      "Running ELA differential analysis...",
    );
  });

  it("returns empty string when both incoming and previous are empty", () => {
    expect(mergeThinking("", undefined)).toBe("");
    expect(mergeThinking("", "")).toBe("");
    expect(mergeThinking(null, undefined)).toBe("");
  });

  it("updates when a new non-empty thinking follows a non-empty previous", () => {
    expect(mergeThinking("New tool running...", "Old tool running...")).toBe("New tool running...");
  });

  it("does not flip to pipeline-level message: empty incoming keeps agent thinking", () => {
    const agentThinking = "Analyzing compression artifacts...";
    const pipelineMessage = "Coordinating agents...";

    // Simulate what happens in AgentProgressDisplay:
    // thinking={agentUpdates[agent.id]?.thinking || pipelineMessage || progressText}
    const merged = mergeThinking("", agentThinking);
    const displayed = merged || pipelineMessage;

    // After fix, merged === agentThinking, so displayed !== pipelineMessage
    expect(displayed).toBe(agentThinking);
    expect(displayed).not.toBe(pipelineMessage);
  });
});


// ── 2. LoadingOverlayController — show() cancels pending dismiss ───────────────

class _TestableController {
  visible = false;
  text = "";
  showTime = 0;
  private dismissTimer: ReturnType<typeof setTimeout> | null = null;
  private notified: Array<{ visible: boolean; text: string }> = [];

  show(text?: string): void {
    this.clearTimer();  // the fix
    this.visible = true;
    this.showTime = Date.now();
    this.text = text || "Initializing workspace";
    this.notified.push({ visible: this.visible, text: this.text });
  }

  updateText(text: string): void {
    this.text = text;
    this.notified.push({ visible: this.visible, text: this.text });
  }

  dismiss(minMs = 0): void {
    this.clearTimer();
    const elapsed = Date.now() - this.showTime;
    const delay = Math.max(0, minMs - elapsed);
    this.dismissTimer = setTimeout(() => {
      this.visible = false;
      this.text = "";
      this.notified.push({ visible: false, text: "" });
    }, delay);
  }

  private clearTimer(): void {
    if (this.dismissTimer) {
      clearTimeout(this.dismissTimer);
      this.dismissTimer = null;
    }
  }

  getState() { return { visible: this.visible, text: this.text }; }
  getNotifications() { return this.notified; }
}

describe("LoadingOverlayController — show() cancels pending dismiss", () => {
  beforeEach(() => jest.useFakeTimers());
  afterEach(() => jest.useRealTimers());

  it("calling show() after dismiss() cancels the dismiss timer", async () => {
    const ctrl = new _TestableController();
    ctrl.show("Initializing workspace");
    ctrl.dismiss(800);  // schedule dismiss in 800ms

    // Before timer fires, new show() arrives (e.g. pipelineMessage update)
    ctrl.show("Uploading evidence to secure pipeline");

    // Advance past the original dismiss deadline
    jest.advanceTimersByTime(1000);

    // Overlay must still be visible because show() cancelled the dismiss
    expect(ctrl.getState().visible).toBe(true);
    expect(ctrl.getState().text).toBe("Uploading evidence to secure pipeline");
  });

  it("dismiss() still fires when no subsequent show() intervenes", () => {
    const ctrl = new _TestableController();
    ctrl.show("Initializing workspace");
    ctrl.dismiss(0);  // immediate dismiss

    jest.advanceTimersByTime(10);
    expect(ctrl.getState().visible).toBe(false);
  });
});


// ── 3. updateText() vs show() — showTime must not reset on text updates ────────

describe("LoadingOverlayController — updateText does not reset showTime", () => {
  it("updateText leaves showTime unchanged so MIN_DISPLAY guard is not re-armed", () => {
    const ctrl = new _TestableController();
    ctrl.show("Initializing workspace");
    const firstShowTime = ctrl.showTime;

    // Simulate pipeline messages arriving while overlay is visible
    ctrl.updateText("Uploading evidence to secure pipeline");
    ctrl.updateText("Agents dispatching");

    expect(ctrl.showTime).toBe(firstShowTime);
    expect(ctrl.getState().text).toBe("Agents dispatching");
  });

  it("updateText while visible does not set visible=true again (no-op for show flag)", () => {
    const ctrl = new _TestableController();
    ctrl.show("first");
    ctrl.visible = false;  // simulate external dismiss
    ctrl.updateText("second");
    // visible should still be false — updateText doesn't call show()
    expect(ctrl.getState().visible).toBe(false);
    expect(ctrl.getState().text).toBe("second");
  });
});
