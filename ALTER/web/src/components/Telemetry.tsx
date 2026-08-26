"use client";

import { usePathname } from "next/navigation";
import { useEffect } from "react";

const POSTHOG_PROJECT_KEY = "phc_z9CGwpT6bvMMD3BNaqb3XMUfSHvDbqR2kfbNENKgvTrf";
const POSTHOG_CAPTURE_URL = "https://us.i.posthog.com/capture/";
const DEVICE_KEY = "alter_telemetry_device";

function deviceId(): string {
  try {
    const existing = window.localStorage.getItem(DEVICE_KEY);
    if (existing) return existing;
    const value = window.crypto?.randomUUID?.() || `alter-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    window.localStorage.setItem(DEVICE_KEY, value);
    return value;
  } catch {
    return "alter-owner-browser";
  }
}

export function captureAlterEvent(event: string, properties: Record<string, string | number | boolean | null> = {}) {
  if (typeof window === "undefined") return;
  const payload = {
    api_key: POSTHOG_PROJECT_KEY,
    event,
    properties: {
      distinct_id: deviceId(),
      app: "ALTER",
      surface: "web",
      path: window.location.pathname,
      ...properties,
    },
  };

  void fetch(POSTHOG_CAPTURE_URL, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
    keepalive: true,
    mode: "cors",
    credentials: "omit",
  }).catch(() => {
    // Telemetry must never block or break the product.
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
