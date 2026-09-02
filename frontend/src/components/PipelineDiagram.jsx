/**
 * PipelineDiagram - what actually happened to a result, drawn.
 *
 * The explainability requirement is about more than a rule string: a reader
 * should be able to see that severity was decided before the model was ever
 * called, and that the clinical steps ran behind a process boundary.
 *
 * Drawn as inline SVG rather than an image or a chart library: it is a fixed
 * diagram of a fixed pipeline, it inherits the theme's colours through
 * `currentColor` and CSS variables, and it stays crisp at any zoom.
 *
 * `activeStage` optionally highlights where a live request has reached.
 */

const STAGES = [
  { id: "input", label: "Input", sub: "form / CSV", x: 8 },
  { id: "classify", label: "Classify", sub: "MCP tool", x: 158 },
  { id: "route", label: "Route", sub: "MCP tool", x: 308 },
  { id: "explain", label: "Explain", sub: "Gemini", x: 458 },
  { id: "display", label: "Display", sub: "React", x: 608 },
];

const BOX_W = 116;
const BOX_H = 46;
const BOX_Y = 44;

export default function PipelineDiagram({ activeStage = null }) {
  return (
    <figure className="diagram">
      <svg
        viewBox="0 0 736 132"
        className="diagram__svg"
        role="img"
        aria-label="Pipeline: input, then classify and route via MCP tools, then explain via Gemini, then display. Severity is decided before the model is called."
      >
        {/* The MCP process boundary, drawn around the two tool stages. */}
        <rect
          x={148}
          y={26}
          width={296}
          height={82}
          rx={10}
          className="diagram__boundary"
        />
        <text x={296} y={20} className="diagram__boundary-label">
          MCP server · separate process · stdio
        </text>

        {STAGES.map((stage, i) => {
          const next = STAGES[i + 1];
          const isActive = activeStage === stage.id;
          const isModel = stage.id === "explain";

          return (
            <g key={stage.id}>
              {next && (
                <>
                  <line
                    x1={stage.x + BOX_W}
                    y1={BOX_Y + BOX_H / 2}
                    x2={next.x - 4}
                    y2={BOX_Y + BOX_H / 2}
                    className="diagram__wire"
                  />
                  <polygon
                    points={`${next.x - 4},${BOX_Y + BOX_H / 2} ${next.x - 12},${BOX_Y + BOX_H / 2 - 4} ${next.x - 12},${BOX_Y + BOX_H / 2 + 4}`}
                    className="diagram__arrow"
                  />
                </>
              )}

              <rect
                x={stage.x}
                y={BOX_Y}
                width={BOX_W}
                height={BOX_H}
                rx={8}
                className={`diagram__box ${isModel ? "diagram__box--model" : ""} ${
                  isActive ? "diagram__box--active" : ""
                }`}
              />
              <text x={stage.x + BOX_W / 2} y={BOX_Y + 19} className="diagram__label">
                {stage.label}
              </text>
              <text x={stage.x + BOX_W / 2} y={BOX_Y + 34} className="diagram__sub">
                {stage.sub}
              </text>
            </g>
          );
        })}

        {/* The point of the whole diagram. */}
        <text x={296} y={124} className="diagram__note">
          severity decided here — deterministically
        </text>
        <line x1={148} y1={104} x2={148} y2={112} className="diagram__tick" />
        <line x1={444} y1={104} x2={444} y2={112} className="diagram__tick" />
        <line x1={148} y1={112} x2={444} y2={112} className="diagram__tick" />
      </svg>

      <figcaption className="diagram__caption">
        The model is called <strong>after</strong> classification, and is given
        the verdict rather than asked for it. If it is unavailable, the
        severities either side of it are unaffected.
      </figcaption>
    </figure>
  );
}
