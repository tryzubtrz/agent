"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

const routes: Record<string, string> = {
  "Файли": "/files",
  "Сховище": "/vault",
  "Моделі": "/models",
  "Люди": "/people",
};

export default function ModuleRouteBridge() {
  const router = useRouter();

  useEffect(() => {
    function onClick(event: MouseEvent) {
      const target = event.target as HTMLElement | null;
      const button = target?.closest("button") as HTMLButtonElement | null;
      if (!button) return;

      const isQuickModule = Boolean(button.closest(".quickModules"));
      const isFilesShortcut = button.getAttribute("aria-label") === "Відкрити файли";
      if (!isQuickModule && !isFilesShortcut) return;

      const label = isFilesShortcut ? "Файли" : (button.textContent || "").trim();
      const href = routes[label];
      if (!href) return;

      event.preventDefault();
      event.stopPropagation();
      router.push(href);
    }

    document.addEventListener("click", onClick, true);
    return () => document.removeEventListener("click", onClick, true);
  }, [router]);

  return null;
}
