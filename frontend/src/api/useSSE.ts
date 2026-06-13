import { useEffect, useRef } from "react";
import { eventsUrl } from "./client";
import type { BusEvent } from "./types";

// One shared SSE subscription hook (plan §4.1). The worker fans every event
// (db-changed, lock, job progress) over a single /api/events stream. Each event
// arrives as a named SSE event with a JSON data payload.
//
// `onEvent` is kept in a ref so the EventSource isn't torn down/recreated on
// every render — the stream lives for as long as the component is mounted.
export function useSSE(onEvent: (e: BusEvent) => void, enabled = true) {
  const cb = useRef(onEvent);
  cb.current = onEvent;

  useEffect(() => {
    if (!enabled) return;
    const es = new EventSource(eventsUrl());

    const handler = (type: string) => (ev: MessageEvent) => {
      let data: Record<string, unknown> = {};
      try {
        data = ev.data ? JSON.parse(ev.data) : {};
      } catch {
        /* keep empty */
      }
      cb.current({ event: type, data });
    };

    // Known named events from the worker's EventBus.
    for (const name of ["db-changed", "lock", "lock_lost", "job"]) {
      es.addEventListener(name, handler(name) as EventListener);
    }
    // Fallback for unnamed messages.
    es.onmessage = handler("message");

    return () => es.close();
  }, [enabled]);
}
