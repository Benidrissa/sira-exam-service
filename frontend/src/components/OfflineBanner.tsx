"use client";

import { useEffect, useState } from "react";
import type { ConnectivityState } from "@/hooks/useConnectivityProbe";

interface OfflineBannerProps {
  state: ConnectivityState;
  offlineDurationSeconds: number;
}

export function OfflineBanner({ state, offlineDurationSeconds }: OfflineBannerProps) {
  const [showSuccess, setShowSuccess] = useState(false);
  const [prevState, setPrevState] = useState<ConnectivityState>(state);

  useEffect(() => {
    if (prevState === "DRAINING" && state === "ONLINE") {
      setShowSuccess(true);
      const timer = setTimeout(() => setShowSuccess(false), 3_000);
      return () => clearTimeout(timer);
    }
    setPrevState(state);
  }, [state, prevState]);

  if (state === "ONLINE" && !showSuccess) return null;

  if (showSuccess) {
    return (
      <div className="fixed top-0 left-0 right-0 z-[9998] flex items-center justify-center h-8 bg-green-50 border-b border-green-300 text-xs text-green-700">
        All data synchronized.
      </div>
    );
  }

  if (state === "PROBING") {
    return (
      <div className="fixed top-0 left-0 right-0 z-[9998] flex items-center justify-center h-8 bg-amber-50 border-b border-amber-300 text-xs text-amber-700">
        Connection lost — your exam is saved. Proctoring continues locally. Do not close this tab.
        {offlineDurationSeconds > 600 && (
          <span className="ml-2 font-medium">The exam timer is still running.</span>
        )}
      </div>
    );
  }

  if (state === "RECONNECTING" || state === "DRAINING") {
    return (
      <div className="fixed top-0 left-0 right-0 z-[9998] flex items-center justify-center h-8 bg-blue-50 border-b border-blue-300 text-xs text-blue-700">
        Connection restored — syncing data…
      </div>
    );
  }

  return null;
}
