import { AbsoluteFill, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";

import type { Screen } from "./config";

const NAVY = "#334d8f";
const CANVAS = "#f3f4f8";

export const ScreenSlide: React.FC<{ screen: Screen }> = ({ screen }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const enter = spring({ frame, fps, config: { damping: 22, mass: 0.6 } });
  // A very gentle Ken Burns so a static shot does not feel dead.
  const scale = interpolate(frame, [0, 180], [1.02, 1.06], { extrapolateRight: "clamp" });
  const imgY = interpolate(enter, [0, 1], [18, 0]);

  const captionIn = spring({ frame: frame - 8, fps, config: { damping: 24 } });

  return (
    <AbsoluteFill style={{ backgroundColor: CANVAS }}>
      {/* The screenshot, framed like a browser window floating on canvas. */}
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "flex-start", paddingTop: 48 }}>
        <div
          style={{
            width: 1060,
            borderRadius: 14,
            overflow: "hidden",
            boxShadow: "0 24px 70px rgba(31,41,68,0.22)",
            transform: `translateY(${imgY}px) scale(${scale})`,
            opacity: enter,
            background: "#fff",
          }}
        >
          <Img src={staticFile(screen.image)} style={{ width: "100%", display: "block" }} />
        </div>
      </AbsoluteFill>

      {/* Caption band at the bottom. */}
      <AbsoluteFill style={{ justifyContent: "flex-end" }}>
        <div
          style={{
            margin: "0 60px 40px",
            padding: "20px 26px",
            borderRadius: 16,
            background: "rgba(255,255,255,0.92)",
            borderLeft: `5px solid ${NAVY}`,
            boxShadow: "0 10px 30px rgba(31,41,68,0.12)",
            transform: `translateY(${interpolate(captionIn, [0, 1], [24, 0])}px)`,
            opacity: captionIn,
          }}
        >
          <div
            style={{
              fontSize: 15,
              fontWeight: 700,
              letterSpacing: 1.4,
              textTransform: "uppercase",
              color: NAVY,
            }}
          >
            {screen.chapter}
          </div>
          <div style={{ fontSize: 30, fontWeight: 700, color: "#242838", marginTop: 4 }}>
            {screen.title}
          </div>
          <div style={{ fontSize: 19, color: "#474a56", marginTop: 6, lineHeight: 1.45 }}>
            {screen.caption}
          </div>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
