import { Composition } from "remotion";

import { Walkthrough } from "./Walkthrough";
import { FPS, HEIGHT, WIDTH, totalDurationInFrames } from "./config";

export const RemotionRoot: React.FC = () => (
  <Composition
    id="Walkthrough"
    component={Walkthrough}
    durationInFrames={totalDurationInFrames}
    fps={FPS}
    width={WIDTH}
    height={HEIGHT}
  />
);
