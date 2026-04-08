"use client";

import { useEffect, useState } from "react";
import { Group, Image as KonvaImage, Layer, Rect, Stage, Text } from "react-konva";

import type { Detection } from "@/types/domain";

function resultColor(result: Detection["result"]): string {
  if (result === "true") return "#2b9348";
  if (result === "false") return "#c1121f";
  return "#f08c00";
}

export default function DetectionCanvasInner({
  imageUrl,
  detections,
}: {
  imageUrl: string;
  detections: Detection[];
}) {
  const [image, setImage] = useState<HTMLImageElement | null>(null);

  useEffect(() => {
    const img = new Image();
    img.src = imageUrl;
    img.onload = () => setImage(img);
  }, [imageUrl]);

  const width = image?.width ?? 760;
  const height = image?.height ?? 480;
  const scale = width > 760 ? 760 / width : 1;

  return (
    <div className="canvas-wrap">
      <Stage width={Math.round(width * scale)} height={Math.round(height * scale)}>
        <Layer>
          {image && <KonvaImage image={image} width={width * scale} height={height * scale} />}
          {detections.map((detection) => {
            const [x, y, w, h] = detection.bbox;
            const color = resultColor(detection.result);
            return (
              <Group key={detection.id}>
                <Rect
                  x={x * scale}
                  y={y * scale}
                  width={w * scale}
                  height={h * scale}
                  stroke={color}
                  strokeWidth={3}
                  cornerRadius={4}
                />
                <Text
                  x={x * scale}
                  y={Math.max(0, y * scale - 22)}
                  text={`${detection.type} ${detection.score.toFixed(2)}`}
                  fill="#ffffff"
                  fontSize={12}
                  padding={4}
                />
                <Rect
                  x={x * scale}
                  y={Math.max(0, y * scale - 22)}
                  width={110}
                  height={20}
                  fill={color}
                  opacity={0.85}
                  cornerRadius={4}
                />
                <Text
                  x={x * scale + 6}
                  y={Math.max(0, y * scale - 18)}
                  text={`${detection.type} ${detection.score.toFixed(2)}`}
                  fill="#ffffff"
                  fontSize={12}
                />
              </Group>
            );
          })}
        </Layer>
      </Stage>
    </div>
  );
}
