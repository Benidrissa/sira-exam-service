"use client";

import { useEffect } from "react";

export function useLockdownShell(enabled: boolean) {
  useEffect(() => {
    if (!enabled) return;

    // Request fullscreen
    document.documentElement.requestFullscreen?.().catch(() => {});

    // Block context menu
    const blockCtxMenu = (e: MouseEvent) => e.preventDefault();
    document.addEventListener("contextmenu", blockCtxMenu);

    // Block keyboard shortcuts
    const blockKeys = (e: KeyboardEvent) => {
      const forbidden = [
        e.key === "F12",
        e.ctrlKey && e.shiftKey && e.key === "I", // DevTools
        e.ctrlKey && e.shiftKey && e.key === "J", // Console
        e.altKey && e.key === "Tab", // Alt+Tab
        e.key === "PrintScreen",
      ];
      if (forbidden.some(Boolean)) {
        e.preventDefault();
        e.stopPropagation();
      }
    };
    document.addEventListener("keydown", blockKeys, true);

    // Detect fullscreen exit and warn
    const onFullscreenChange = () => {
      if (!document.fullscreenElement) {
        // Attempt to re-enter fullscreen
        document.documentElement.requestFullscreen?.().catch(() => {});
      }
    };
    document.addEventListener("fullscreenchange", onFullscreenChange);

    // user-select:none on body
    document.body.style.userSelect = "none";

    return () => {
      document.removeEventListener("contextmenu", blockCtxMenu);
      document.removeEventListener("keydown", blockKeys, true);
      document.removeEventListener("fullscreenchange", onFullscreenChange);
      document.body.style.userSelect = "";
      if (document.fullscreenElement) document.exitFullscreen?.().catch(() => {});
    };
  }, [enabled]);
}
