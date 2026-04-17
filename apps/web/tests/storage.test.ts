import { persistentStorage, sessionOnlyStorage } from "@/lib/storage";

describe("Storage Abstraction", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  it("persistentStorage sets and gets values", () => {
    persistentStorage.setItem("test_key", "test-token");
    expect(persistentStorage.getItem("test_key")).toBe("test-token");
  });

  it("sessionOnlyStorage sets and gets values", () => {
    sessionOnlyStorage.setItem("session_key", JSON.stringify({ id: "test" }));
    const raw = sessionOnlyStorage.getItem("session_key");
    expect(raw).toBe(JSON.stringify({ id: "test" }));
  });

  it("persistentStorage removes values", () => {
    persistentStorage.setItem("test_key", "test-token");
    persistentStorage.removeItem("test_key");
    expect(persistentStorage.getItem("test_key")).toBeNull();
  });

  it("persistentStorage returns null for missing key", () => {
    expect(persistentStorage.getItem("nonexistent_key")).toBeNull();
  });
});
