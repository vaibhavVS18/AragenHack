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
 */
export default function DatasetsPage({ loading, error, runAnalysis, dismissError }) {
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

      {!datasets && !listError && (
        <div className="loading" role="status">
          <span className="spinner" aria-hidden="true" />
          Loading datasets…
        </div>
      )}

      <div className="dataset-grid">
        {(datasets ?? []).map((dataset) => (
          <article
            key={dataset.id}
            className={`dataset ${dataset.available ? "" : "dataset--missing"}`}
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

            <dl className="dataset__meta">
              <div>
                <dt>Source</dt>
                <dd>{dataset.source}</dd>
              </div>
              <div>
                <dt>Size</dt>
                <dd>
                  {dataset.available
                    ? `${(dataset.size_bytes / 1024).toFixed(1)} KB`
                    : "not present"}
                </dd>
              </div>
            </dl>

            {dataset.available ? (
              <button
                type="button"
                className="btn btn--primary dataset__run"
                onClick={() => handleRun(dataset)}
                disabled={loading}
              >
                {pending === dataset.id ? "Analyzing…" : "Analyze this dataset"}
              </button>
            ) : (
              <p className="dataset__unavailable">
                File not found in this checkout. See the README for where to
                place it.
              </p>
            )}
          </article>
        ))}
      </div>
    </>
  );
}
