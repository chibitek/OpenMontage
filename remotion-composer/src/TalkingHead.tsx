import {
  AbsoluteFill,
  Img,
  OffthreadVideo,
  Sequence,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { CaptionOverlay, WordCaption } from "./components/CaptionOverlay";

// Resolve an asset path for Img/OffthreadVideo. Remotion's renderer refuses
// file:// URIs and can't serve arbitrary absolute filesystem paths — the
// only reliable local path is staticFile() against files placed under
// remotion-composer/public/. http(s)/data URLs pass through unchanged.
function resolveAsset(src: string): string {
  if (src.startsWith("http://") || src.startsWith("https://") || src.startsWith("data:")) {
    return src;
  }
  const clean = src.replace(/^file:\/\/\/?/, "");
  return staticFile(clean);
}
import { TextCard } from "./components/TextCard";
import { StatCard } from "./components/StatCard";
import { CalloutBox } from "./components/CalloutBox";
import { ComparisonCard } from "./components/ComparisonCard";
import { BarChart } from "./components/charts/BarChart";
import { LineChart } from "./components/charts/LineChart";
import { PieChart } from "./components/charts/PieChart";
import { KPIGrid } from "./components/charts/KPIGrid";
import { HeroTitle } from "./components/HeroTitle";
import { SectionTitle } from "./components/SectionTitle";
import { StatReveal } from "./components/StatReveal";

// ---------------------------------------------------------------------------
// Overlay types for talking-head video
// ---------------------------------------------------------------------------

export interface TalkingHeadOverlay {
  id?: string;
  type: string;
  in_seconds: number;
  out_seconds: number;
  position?:
    | "lower_third"
    | "upper_third"
    | "left_panel"
    | "right_panel"
    | "full_overlay";
  // Component-specific props (same as Explainer Cut)
  text?: string;
  stat?: string;
  subtitle?: string;
  callout_type?: "info" | "warning" | "tip" | "quote";
  title?: string;
  leftLabel?: string;
  rightLabel?: string;
  leftValue?: string;
  rightValue?: string;
  chartData?: any[];
  chartSeries?: any[];
  chartColors?: string[];
  chartAnimation?: string;
  donut?: boolean;
  centerLabel?: string;
  centerValue?: string;
  showGrid?: boolean;
  showValues?: boolean;
  showLegend?: boolean;
  showMarkers?: boolean;
  columns?: 2 | 3 | 4;
  // broll_video / cta_card specific
  videoSrc?: string;
  logoSrc?: string;
  // Styling
  backgroundColor?: string;
  color?: string;
  accentColor?: string;
  fontSize?: number;
}

// ---------------------------------------------------------------------------
// Position presets for 9:16 (1080x1920) frame
// ---------------------------------------------------------------------------

const POSITION_STYLES: Record<string, React.CSSProperties> = {
  lower_third: {
    position: "absolute",
    // Pushed down + shortened from the original bottom:320/height:480 —
    // that box overlapped the chin on tight `closeUp`-style avatar framing,
    // where the face fills much more of a 1080x1920 frame than `normal`
    // style. This span (1920-250-340=1330 to 1920-250=1670) clears both the
    // chin (~1220 in closeUp framing) and the caption area (~1750+).
    bottom: 250,
    left: 40,
    right: 40,
    height: 340,
  },
  upper_third: {
    position: "absolute",
    top: 80,
    left: 40,
    right: 40,
    height: 480,
  },
  left_panel: {
    position: "absolute",
    top: 200,
    left: 40,
    width: 480,
    bottom: 400,
  },
  right_panel: {
    position: "absolute",
    top: 200,
    right: 40,
    width: 480,
    bottom: 400,
  },
  full_overlay: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
  },
};

// ---------------------------------------------------------------------------
// Overlay component dispatcher — maps overlay type to Remotion component
// ---------------------------------------------------------------------------

const OverlayContent: React.FC<{ overlay: TalkingHeadOverlay }> = ({
  overlay,
}) => {
  const bgColor = overlay.backgroundColor || "#0F172A";

  if (overlay.type === "text_card" && overlay.text) {
    return (
      <TextCard
        text={overlay.text}
        fontSize={overlay.fontSize}
        color={overlay.color}
        backgroundColor={bgColor}
      />
    );
  }
  if (overlay.type === "stat_card" && overlay.stat) {
    return (
      <StatCard
        stat={overlay.stat}
        subtitle={overlay.subtitle}
        accentColor={overlay.accentColor}
        backgroundColor={bgColor}
      />
    );
  }
  if (overlay.type === "callout" && overlay.text) {
    return (
      <CalloutBox
        text={overlay.text}
        type={overlay.callout_type}
        title={overlay.title}
        borderColor={overlay.accentColor}
        backgroundColor={overlay.backgroundColor}
        textColor={overlay.color}
        containerBackgroundColor={bgColor}
      />
    );
  }
  if (
    overlay.type === "comparison" &&
    overlay.leftLabel &&
    overlay.rightLabel
  ) {
    return (
      <ComparisonCard
        leftLabel={overlay.leftLabel}
        rightLabel={overlay.rightLabel}
        leftValue={overlay.leftValue || ""}
        rightValue={overlay.rightValue || ""}
        title={overlay.title}
        backgroundColor={bgColor}
        textColor={overlay.color}
      />
    );
  }
  if (overlay.type === "bar_chart" && overlay.chartData) {
    return (
      <BarChart
        data={overlay.chartData}
        title={overlay.title}
        colors={overlay.chartColors}
        animationStyle={(overlay.chartAnimation as any) || "grow-up"}
        showValues={overlay.showValues}
        backgroundColor={bgColor}
      />
    );
  }
  if (overlay.type === "line_chart" && overlay.chartSeries) {
    return (
      <LineChart
        series={overlay.chartSeries}
        title={overlay.title}
        colors={overlay.chartColors}
        animationStyle={(overlay.chartAnimation as any) || "draw"}
        showGrid={overlay.showGrid}
        showMarkers={overlay.showMarkers}
        showLegend={overlay.showLegend}
        backgroundColor={bgColor}
      />
    );
  }
  if (overlay.type === "pie_chart" && overlay.chartData) {
    return (
      <PieChart
        data={overlay.chartData}
        title={overlay.title}
        colors={overlay.chartColors}
        animationStyle={(overlay.chartAnimation as any) || "expand"}
        donut={overlay.donut}
        centerLabel={overlay.centerLabel}
        centerValue={overlay.centerValue}
        showLegend={overlay.showLegend}
        backgroundColor={bgColor}
      />
    );
  }
  if (overlay.type === "kpi_grid" && overlay.chartData) {
    return (
      <KPIGrid
        metrics={overlay.chartData}
        title={overlay.title}
        columns={overlay.columns}
        colors={overlay.chartColors}
        animationStyle={(overlay.chartAnimation as any) || "count-up"}
        backgroundColor={bgColor}
      />
    );
  }
  if (overlay.type === "hero_title" && overlay.text) {
    return <HeroTitle title={overlay.text} subtitle={overlay.subtitle} />;
  }
  if (overlay.type === "section_title" && overlay.text) {
    return (
      <SectionTitle
        title={overlay.text}
        subtitle={overlay.subtitle}
        accentColor={overlay.accentColor}
        position="top-left"
      />
    );
  }
  if (overlay.type === "stat_reveal" && overlay.text) {
    return (
      <StatReveal
        stat={overlay.text}
        label={overlay.subtitle}
        accentColor={overlay.accentColor}
        position="bottom-right"
      />
    );
  }
  if (overlay.type === "broll_video" && overlay.videoSrc) {
    return (
      <OffthreadVideo
        src={resolveAsset(overlay.videoSrc)}
        muted
        style={{ width: "100%", height: "100%", objectFit: "cover" }}
      />
    );
  }
  if (overlay.type === "cta_card" && overlay.text) {
    return (
      <AbsoluteFill
        style={{
          backgroundColor: overlay.backgroundColor || "#F1E6B2",
          justifyContent: "center",
          alignItems: "center",
          flexDirection: "column",
          padding: "0 90px",
        }}
      >
        {overlay.logoSrc && (
          <Img
            src={resolveAsset(overlay.logoSrc)}
            style={{ width: 260, marginBottom: 56, objectFit: "contain" }}
          />
        )}
        <div
          style={{
            fontFamily: "'Raleway', 'Montserrat', system-ui, sans-serif",
            fontWeight: 800,
            fontSize: 58,
            lineHeight: 1.28,
            textAlign: "center",
            color: overlay.color || "#004F71",
          }}
        >
          {overlay.text}
        </div>
      </AbsoluteFill>
    );
  }
  return null;
};

// ---------------------------------------------------------------------------
// Positioned overlay wrapper — handles position + fade in/out
// ---------------------------------------------------------------------------

const PositionedOverlay: React.FC<{ overlay: TalkingHeadOverlay }> = ({
  overlay,
}) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();

  // Fade in over 8 frames (~0.27s), fade out over 8 frames
  const fadeIn = interpolate(frame, [0, 8], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const fadeOut = interpolate(
    frame,
    [durationInFrames - 8, durationInFrames],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );
  const opacity = fadeIn * fadeOut;

  const position = overlay.position || "lower_third";
  const posStyle = POSITION_STYLES[position] || POSITION_STYLES.lower_third;
  const isFullOverlay = position === "full_overlay";
  // b-roll and CTA cards fill the frame with their own real content —
  // the dark scrim exists to make TEXT overlays legible over dimmed
  // video, and would make b-roll footage nearly invisible.
  const wantsScrim = isFullOverlay && overlay.type !== "broll_video" && overlay.type !== "cta_card";

  return (
    <div
      style={{
        ...posStyle,
        opacity,
        overflow: "hidden",
        borderRadius: isFullOverlay ? 0 : 16,
        boxShadow: isFullOverlay
          ? "none"
          : "0 8px 32px rgba(0, 0, 0, 0.4)",
      }}
    >
      {wantsScrim && (
        <AbsoluteFill style={{ background: "rgba(0, 0, 0, 0.7)" }} />
      )}
      <OverlayContent overlay={overlay} />
    </div>
  );
};

// ---------------------------------------------------------------------------
// Main TalkingHead composition
// ---------------------------------------------------------------------------

export interface TalkingHeadProps {
  [key: string]: unknown;
  videoSrc: string;
  captions: WordCaption[];
  overlays?: TalkingHeadOverlay[];
  wordsPerPage?: number;
  fontSize?: number;
  highlightColor?: string;
  captionColor?: string;
  captionBackgroundColor?: string;
  captionFontFamily?: string;
  logoSrc?: string;
  logoOutSeconds?: number;
}

export const TalkingHead: React.FC<TalkingHeadProps> = ({
  videoSrc,
  captions,
  overlays,
  wordsPerPage = 4,
  fontSize = 52,
  highlightColor = "#00B398",
  captionColor = "#FFFFFF",
  captionBackgroundColor = "rgba(0, 79, 113, 0.72)",
  captionFontFamily = "'Raleway', 'Montserrat', system-ui, sans-serif",
  logoSrc,
  logoOutSeconds,
}) => {
  const { fps, durationInFrames } = useVideoConfig();
  const logoOutFrame = logoOutSeconds
    ? Math.round(logoOutSeconds * fps)
    : durationInFrames;

  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      {/* Layer 1: Video background */}
      <OffthreadVideo
        src={resolveAsset(videoSrc)}
        style={{ width: "100%", height: "100%", objectFit: "cover" }}
      />

      {/* Layer 2: Overlays (charts, stats, callouts, b-roll, CTA card, etc.) */}
      {overlays?.map((overlay, i) => {
        const from = Math.round(overlay.in_seconds * fps);
        const duration = Math.round(
          (overlay.out_seconds - overlay.in_seconds) * fps
        );
        return (
          <Sequence
            key={overlay.id || `overlay-${i}`}
            from={from}
            durationInFrames={duration}
          >
            <PositionedOverlay overlay={overlay} />
          </Sequence>
        );
      })}

      {/* Layer 3: Captions (above overlays, so word highlighting still reads over b-roll) */}
      <CaptionOverlay
        words={captions}
        wordsPerPage={wordsPerPage}
        fontSize={fontSize}
        highlightColor={highlightColor}
        backgroundColor={captionBackgroundColor}
        color={captionColor}
        fontFamily={captionFontFamily}
      />

      {/* Layer 4: Persistent brand watermark — bottom-right, low-key, stops before the CTA card (which carries the full logo instead) */}
      {logoSrc && (
        <Sequence from={0} durationInFrames={logoOutFrame}>
          <AbsoluteFill
            style={{ justifyContent: "flex-end", alignItems: "flex-end" }}
          >
            <Img
              src={resolveAsset(logoSrc)}
              style={{
                width: 230,
                // Pulled closer to the true bottom-right corner and enlarged
                // per explicit feedback (was width:158/bottom:185, read as
                // too small and too far from the corner). Some overlap with
                // wide caption lines is possible since captions run maxWidth
                // 80% centered — re-check after render and nudge further if
                // it visibly collides.
                margin: "0 26px 130px 0",
                opacity: 0.95,
                filter: "drop-shadow(0 2px 10px rgba(0,0,0,0.45))",
              }}
            />
          </AbsoluteFill>
        </Sequence>
      )}
    </AbsoluteFill>
  );
};
