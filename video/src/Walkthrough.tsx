import { TransitionSeries, linearTiming } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";

import { Card } from "./Card";
import { ScreenSlide } from "./ScreenSlide";
import { FPS, INTRO_SECONDS, OUTRO_SECONDS, screens } from "./config";

const sec = (s: number) => Math.round(s * FPS);

export const Walkthrough: React.FC = () => {
  return (
    <TransitionSeries>
      <TransitionSeries.Sequence durationInFrames={sec(INTRO_SECONDS)}>
        <Card
          kind="intro"
          title="Waseet"
          subtitle="AI-mediated escrow on PayPal"
          note="An agent reads the work, judges it, and moves money — inside a trust layer that makes that safe."
        />
      </TransitionSeries.Sequence>

      <TransitionSeries.Transition
        presentation={fade()}
        timing={linearTiming({ durationInFrames: 14 })}
      />

      {screens.flatMap((screen, i) => {
        const nodes = [
          <TransitionSeries.Sequence key={`s-${i}`} durationInFrames={sec(screen.seconds)}>
            <ScreenSlide screen={screen} />
          </TransitionSeries.Sequence>,
        ];
        nodes.push(
          <TransitionSeries.Transition
            key={`t-${i}`}
            presentation={fade()}
            timing={linearTiming({ durationInFrames: 12 })}
          />,
        );
        return nodes;
      })}

      <TransitionSeries.Sequence durationInFrames={sec(OUTRO_SECONDS)}>
        <Card
          kind="outro"
          title="Decide, don't disburse."
          subtitle="The agent judges. A policy gates. A human resolves."
          note="PayPal sandbox · Orders · Payouts · Refunds · Webhooks"
        />
      </TransitionSeries.Sequence>
    </TransitionSeries>
  );
};
