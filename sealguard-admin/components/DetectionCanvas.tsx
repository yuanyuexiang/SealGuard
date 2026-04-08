"use client";

import dynamic from "next/dynamic";

import type { Detection } from "@/types/domain";

const DetectionCanvasInner = dynamic(() => import("@/components/DetectionCanvasInner"), {
  ssr: false,
});

export default function DetectionCanvas({
  imageUrl,
  detections,
}: {
  imageUrl: string;
  detections: Detection[];
}) {
  return <DetectionCanvasInner imageUrl={imageUrl} detections={detections} />;
}
