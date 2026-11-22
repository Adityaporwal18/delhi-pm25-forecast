import { useEffect, useState } from "react";

export type Load<T> = { state: "loading" } | { state: "error"; message: string } | { state: "ready"; data: T };

/** Runs `load` whenever `key` changes (or on retry); a newer request cancels the older one. */
export function useLoad<T>(load: (signal: AbortSignal) => Promise<T>, key: string): [Load<T>, () => void] {
  const [result, setResult] = useState<Load<T>>({ state: "loading" });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setResult({ state: "loading" });
    load(controller.signal).then(
      (data) => setResult({ state: "ready", data }),
      (error: unknown) => {
        if (!controller.signal.aborted) {
          setResult({ state: "error", message: error instanceof Error ? error.message : String(error) });
        }
      },
    );
    return () => controller.abort();
    // `load` is a new closure on every render; `key` names what it loads.
  }, [key, attempt]); // eslint-disable-line react-hooks/exhaustive-deps
  return [result, () => setAttempt((count) => count + 1)];
}

export function Status({ load, what, retry }: { load: Load<unknown>; what: string; retry: () => void }) {
  if (load.state === "error") {
    return (
      <p className="status error" role="alert">
        Could not load {what}: {load.message}{" "}
        <button type="button" className="button" onClick={retry}>
          Retry
        </button>
      </p>
    );
  }
  return (
    <p className="status" aria-live="polite">
      Loading {what}…
    </p>
  );
}
