import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import ErrorPanel from "../components/ErrorPanel";
import { listDatasets } from "../api/client";

/**
 * DatasetsPage - one-click analysis of the sample files in the repository.
 *
 * A reviewer should be able to see the whole pipeline work without first
 * finding a CSV on disk, so the backend publishes its own bundled files and
 * this page runs them directly. On success it moves to the Analyze page,
 * where the results already live.
 *
 * Only the card that was pressed shows a running state. An earlier version
 * disabled every button on the shared `loading` flag, so pressing one made all
 * four look as though they were analysing at once.
 */

function DatasetCard({ dataset, pending, onRun }) {
  const isRunning = pending === dataset.id;
  const otherRunning = pending !== null && !isRunning;

  if (!dataset.available) {
    return (
      <article className="dataset dataset--missing">
        <header className="dataset__header">
          <h3 className="dataset__name">{dataset.name}</h3>
          <span className="tag tag--synthetic">Missing</span>
        </header>
        <p className="dataset__description">{dataset.description}</p>
        <p className="dataset__unavailable">
          File not found in this checkout. See the README for where to place it.
        </p>
      </article>
    );
  }

  return (
    <article
      className={`dataset ${isRunning ? "dataset--running" : ""} ${
        otherRunning ? "dataset--waiting" : ""
      }`}
    >
      <header className="dataset__header">
        <h3 className="dataset__name">{dataset.name}</h3>
        <span
          className={`tag ${dataset.synthetic ? "tag--synthetic" : "tag--real"}`}
        >
          {dataset.synthetic ? "Synthetic" : "Kaggle"}
        </span>
      </header>

      <p className="dataset__description">{dataset.description}</p>

      {/* Rows, not kilobytes. Someone choosing a sample wants to know how much
          they are about to analyse; file size does not tell them that. */}
      <div className="dataset__facts">
        <span className="dataset__rows">
          {dataset.rows} result{dataset.rows === 1 ? "" : "s"}
        </span>
        <span className="dataset__source">{dataset.source}</span>
      </div>

      <button
        type="button"
        className="btn btn--primary dataset__run"
        onClick={() => onRun(dataset)}
        disabled={pending !== null}
      >
        {isRunning ? (
          <>
            <span className="spinner spinner--on-accent" aria-hidden="true" />
            Analyzing {dataset.rows} results…
          </>
        ) : (
          "Analyze this dataset"
        )}
      </button>
    </article>
  );
}

export default function DatasetsPage({ error, runAnalysis, dismissError }) {
  const [datasets, setDatasets] = useState(null);
  const [listError, setListError] = useState(null);
  const [pending, setPending] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;

    listDatasets()
      .then((body) => !cancelled && setDatasets(body.datasets))
      .catch((err) => !cancelled && setListError(err));

    return () => {
      cancelled = true;
    };
  }, []);

  async function handleRun(dataset) {
    setPending(dataset.id);
    const result = await runAnalysis({ kind: "dataset", datasetId: dataset.id });
    setPending(null);
    if (result) navigate("/");
  }

  return (
    <>
      <ErrorPanel error={listError ?? error} onDismiss={dismissError} />

      <section className="band band--flush ground--paper">
        <h2 className="band__title">Run a dataset in one click</h2>
        <p className="band__lede">
          Every file below ships with the repository. Running one sends it
          through the same pipeline as an upload: parse, classify against
          reference ranges, route by severity, explain.
        </p>
      </section>

      {!datasets && !listError && (
        <div className="loading" role="status">
          <span className="spinner" aria-hidden="true" />
          Loading datasets…
        </div>
      )}

      {datasets && (
        <section className="band ground--mist">
          <div className="dataset-grid">
            {datasets.map((dataset) => (
              <DatasetCard
                key={dataset.id}
                dataset={dataset}
                pending={pending}
                onRun={handleRun}
              />
            ))}
          </div>
        </section>
      )}
    </>
  );
}
