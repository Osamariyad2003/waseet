import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

const NAVY = "#334d8f";
const NAVY_BRIGHT = "#4060b2";

export const Card: React.FC<{
  kind: "intro" | "outro";
  title: string;
  subtitle: string;
  note: string;
}> = ({ kind, title, subtitle, note }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame, fps, config: { damping: 26, mass: 0.7 } });
  const y = interpolate(enter, [0, 1], [26, 0]);

  return (
    <AbsoluteFill
      style={{
        background: `linear-gradient(135deg, ${NAVY} 0%, ${NAVY_BRIGHT} 100%)`,
        alignItems: "center",
        justifyContent: "center",
        color: "#fff",
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <div style={{ textAlign: "center", opacity: enter, transform: `translateY(${y}px)`, maxWidth: 900 }}>
        {kind === "intro" ? (
          <>
            <div style={{ fontSize: 76, fontWeight: 800, letterSpacing: -1 }}>{title}</div>
            <div style={{ fontSize: 28, color: "rgba(255,255,255,0.88)", marginTop: 6 }}>
              {subtitle}
            </div>
            <div
              style={{
                fontSize: 20,
                color: "rgba(255,255,255,0.78)",
                marginTop: 28,
                lineHeight: 1.5,
                padding: "0 40px",
              }}
            >
              {note}
            </div>
          </>
        ) : (
          <>
            <div style={{ fontSize: 52, fontWeight: 800, letterSpacing: -0.5 }}>{title}</div>
            <div style={{ fontSize: 26, color: "rgba(255,255,255,0.9)", marginTop: 14 }}>
              {subtitle}
            </div>
            <div
              style={{
                marginTop: 34,
                fontSize: 17,
                letterSpacing: 0.5,
                color: "rgba(255,255,255,0.72)",
              }}
            >
              {note}
            </div>
          </>
        )}
      </div>
    </AbsoluteFill>
  );
};
