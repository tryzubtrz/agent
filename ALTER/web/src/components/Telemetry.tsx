"use client";

import { usePathname } from "next/navigation";
import { useEffect } from "react";

type TelemetryValue = string | number | boolean | null;

export function captureAlterEvent(event: "alter_page_view" | "alter_client_error", properties: Record<string, TelemetryValue> = {}) {
  if (typeof window === "undefined") return;
  void fetch("/api/core/gateway/posthog/capture", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      event,
      properties: {
        route: window.location.pathname,
        ...properties,
      },
    }),
    keepalive: true,
    credentials: "same-origin",
  }).catch(() => {
    // Observability must never block or break ALTER.
  });
}

export default function Telemetry() {
  const pathname = usePathname();

  useEffect(() => {
    captureAlterEvent("alter_page_view", { route: pathname || "/" });
  }, [pathname]);

  useEffect(() => {
    function onError() {
      captureAlterEvent("alter_client_error", { source: "window_error" });
    }
    function onRejection() {
      captureAlterEvent("alter_client_error", { source: "unhandled_rejection" });
    }
    window.addEventListener("error", onError);
    window.addEventListener("unhandledrejection", onRejection);
    return () => {
      window.removeEventListener("error", onError);
      window.removeEventListener("unhandledrejection", onRejection);
    };
  }, []);

  return null;
}
