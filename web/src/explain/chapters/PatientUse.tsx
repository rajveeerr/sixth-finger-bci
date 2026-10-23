import { Chapter, FollowUp, More } from "../../components/Chapter";
import { data, pct } from "../data";
import { LaterBars, LiveFigures, SetupCurves } from "../figures/Evidence";
import { Journey } from "../figures/Journey";
import { LearnTest } from "../figures/LearnTest";
import { about, AGAIN_K, AGAIN_MIN, FIRST, PRACTICE_S, SPLITS, timesWord } from "../findings";

const C = data.calibration;
const L = data.later;
const W = data.switch;
const S_END = C.scratch[C.scratch.length - 1];
const T_END = C.transfer[C.transfer.length - 1];

export function PatientUse() {
  return (
    <Chapter
      q="use"
      answer={
        <>
          About {PRACTICE_S} seconds of practice gets a new patient started, if the model has already learned from other
          patients; the model, its server and this page are built, but not the live headset, its bridge or the finger.
        </>
      }
      dial={{
        value: FIRST.mean,
        other: C.scratch[0].mean,
        guess: 1 / 3,
        reading: (
          <>
            <span>
              <b>{pct(FIRST.mean)}</b> after {PRACTICE_S} s, from others
            </span>
            <span className="q-reading-other">
              {pct(C.scratch[0].mean)} after {PRACTICE_S} s, from nothing
            </span>
          </>
        ),
      }}
    >
      <Journey />
      <More what="the first day, another day, live, and how each was tested">
        <FollowUp ask="How much practice does a new patient need?">
          <p>
            Every brain is a little different, so the model needs a few examples from each new patient. Learning from
            others saves time at the start, not in the end: after about {Math.round(S_END.minutes)} minutes, the model
            that started from nothing is a little ahead, {pct(S_END.mean)} against {pct(T_END.mean)}.
          </p>
          <SetupCurves />
          <p className="figure-note">
            Three choices (rest, hand, sixth finger), so guessing gets 33%. The shaded bands show where the true average
            very likely lies, given only {data.leak.subjects.length} patients.
          </p>
          <LearnTest split={SPLITS.setup} />
          <p className="figure-note">
            Already learned from other patients: the model also learned from every recording of all the others, after
            each person&apos;s signals were shifted to a common centre so the differences between people matter less.
          </p>
        </FollowUp>
        <FollowUp ask="Does it still work another day?">
          <p>
            Not unchanged: two weeks later it falls from {pct(L.same_session)} to {pct(L.post.as_is.mean)}, because the
            cap sits differently and the brain may have changed. {AGAIN_K} practice trials of each movement,{" "}
            {about(AGAIN_MIN)}, bring it back to {pct(L.post.re_setup.mean)}.
          </p>
          <LaterBars />
          <p className="figure-note">
            {L.post.as_is.n} patients two weeks later and {L.follow.as_is.n} a month later, those with usable recordings
            of both days.
          </p>
          <LearnTest split={SPLITS.later} />
        </FollowUp>
        <FollowUp ask="Would it work live?">
          <p>
            Partly. Played as if live, without being told when the instruction came, it catches {pct(W.detection)} of
            imagined movements, but switches on by mistake about {timesWord(W.false_per_minute)} a minute of rest: too
            often for a device yet.
          </p>
          <LiveFigures />
          <p className="figure-note">
            Every half second the model reads the newest 4 s; the finger turns on when the chance of a movement is above
            60% twice in a row, and off below 45%. A simpler model on the 14 sensors over the movement strip, played the
            same way, caught {pct(W.central.detection)} with {W.central.false_per_minute.toFixed(1)} mistakes a minute.
            Average of {W.n} patients.
          </p>
          <LearnTest split={SPLITS.live} />
        </FollowUp>
      </More>
    </Chapter>
  );
}
