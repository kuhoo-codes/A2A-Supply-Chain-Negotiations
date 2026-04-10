"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";


export function LiveRunsRefresh() {
  const router = useRouter();

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      router.refresh();
    }, 2500);

    return () => window.clearInterval(intervalId);
  }, [router]);

  return <p className="text-link">Runs auto-refresh every 2.5s.</p>;
}
