import { useEffect, useId, useMemo, useRef, useState } from "react";

/**
 * TestNameInput - an autocomplete for lab test names.
 *
 * Replaces a native `<datalist>`, which promised this for free and delivered
 * badly: it does not open on click in most browsers, shows nothing until you
 * type, cannot be styled, and renders its option labels inconsistently - so
 * the range hint attached to each test was invisible in some browsers and a
 * grey suffix in others.
 *
 * This opens on focus, lists everything before a character is typed, matches
 * on name, alias and category, and shows the range beside each test so the
 * list doubles as a reminder of what normal looks like.
 *
 * The name must come from the list. Free text was allowed at first, on the
 * reasoning that the server resolves aliases and reports what it cannot match
 * - but what the reader got back for a typo was a card saying "no reference
 * range is defined for insulinhsyty", which spends a full analysis to say the
 * name was wrong. The list already holds every test that can be classified, so
 * a name outside it has no possible good outcome.
 *
 * Enforced by discarding, not by warning. Marking the field invalid and
 * disabling the submit button still left "hu" sitting in a row that looked
 * like every other row, with only a greyed-out button to say otherwise. Now
 * leaving the field either resolves what was typed to a test or clears it, so
 * the control cannot hold a value the server would reject.
 *
 * Typing still works and still filters, and a term with exactly one match
 * resolves to it - "pot" then Tab selects Potassium rather than throwing the
 * word away. A CSV is unaffected: a file is not typed, and its unknown rows
 * are reported per row rather than rejecting the upload.
 */

const MAX_VISIBLE = 60;

/** The chevron that marks this as a thing you pick from, not a thing you type. */
function Chevron() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M6 9l6 6 6-6" />
    </svg>
  );
}

function matches(test, term) {
  if (!term) return true;
  return (
    test.test_name.toLowerCase().includes(term) ||
    (test.category ?? "").toLowerCase().includes(term) ||
    (test.aliases ?? []).some((alias) => alias.includes(term))
  );
}

export default function TestNameInput({
  value,
  onChange,
  catalogue,
  rowIndex,
  invalid = false,
}) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  // Set when leaving the field discarded what was typed. Cleared the moment
  // typing resumes, so it explains the empty box rather than nagging.
  const [discarded, setDiscarded] = useState(null);
  const wrapRef = useRef(null);
  const listRef = useRef(null);
  const listId = useId();

  const options = useMemo(() => {
    const all = catalogue ?? [];
    const term = value.trim().toLowerCase();

    // A committed choice stops filtering. Otherwise reopening the list after
    // picking "Potassium" shows one option - itself - and the control appears
    // to have lost every other test, which is the opposite of what a list you
    // pick from should do.
    const settled = all.some((t) => t.test_name.toLowerCase() === term);
    if (settled) return all.slice(0, MAX_VISIBLE);

    return all.filter((t) => matches(t, term)).slice(0, MAX_VISIBLE);
  }, [catalogue, value]);

  /**
   * Leaving the field commits a choice, or discards what was typed.
   *
   * Marking an unmatched name invalid and leaving it in the box was not enough:
   * the box still held "hu", the row still looked like a row, and the only
   * thing standing between it and an analysis was a disabled button. If the
   * name must come from the list, then a name that is not on the list cannot
   * survive leaving the field - so it doesn't.
   *
   * A single remaining match is taken as the choice. Typing "pot" and tabbing
   * away should select Potassium, not throw the word away.
   */
  function commit() {
    if (!value.trim() || !catalogue?.length) return;
    if (!invalid) return;

    if (options.length === 1) {
      onChange(options[0].test_name, options[0]);
      return;
    }

    setDiscarded(value.trim());
    onChange("");
  }

  // Held in a ref because the outside-click listener below is registered when
  // the list opens and would otherwise keep calling the version of `commit`
  // that closed over the value as it was at that moment.
  const commitRef = useRef(commit);
  commitRef.current = commit;

  // Close when the click lands outside this row's combobox. Each row has its
  // own instance, so this must not be global.
  useEffect(() => {
    if (!open) return undefined;

    function onPointerDown(event) {
      if (wrapRef.current?.contains(event.target)) return;
      setOpen(false);
      // Clicking away is leaving the field, so it commits like a blur does.
      // Without this, clicking straight from a half-typed name onto Analyze
      // left the half-typed name sitting in the row.
      commitRef.current();
    }
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [open]);

  // Opening highlights the current choice rather than the top of the list, so
  // the list opens showing where you already are.
  useEffect(() => {
    if (!open) return;
    const term = value.trim().toLowerCase();
    const at = options.findIndex((t) => t.test_name.toLowerCase() === term);
    setActive(at === -1 ? 0 : at);
    // Only when the list opens: recomputing on every keystroke would fight
    // the arrow keys.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Keep the highlighted option in view when arrowing past the fold.
  useEffect(() => {
    if (!open) return;
    listRef.current
      ?.querySelector(`[data-index="${active}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [active, open]);

  function choose(test) {
    onChange(test.test_name, test);
    setOpen(false);
    setDiscarded(null);
  }

  function onKeyDown(event) {
    if (event.key === "Escape") {
      setOpen(false);
      commit();
      return;
    }

    if (!open && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
      setOpen(true);
      setActive(0);
      event.preventDefault();
      return;
    }

    if (!open || options.length === 0) return;

    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((i) => (i + 1) % options.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((i) => (i - 1 + options.length) % options.length);
    } else if (event.key === "Enter") {
      // Only intercept Enter while a suggestion is highlighted; otherwise it
      // must still submit the form.
      event.preventDefault();
      choose(options[active]);
    } else if (event.key === "Tab") {
      setOpen(false);
      commit();
    }
  }

  return (
    <div className={`combo ${open ? "combo--open" : ""}`} ref={wrapRef}>
      <input
        className={`field combo__input ${invalid && value.trim() ? "field--invalid" : ""}`}
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          setOpen(true);
          setActive(0);
          setDiscarded(null);
        }}
        onFocus={() => setOpen(true)}
        onBlur={commit}
        onKeyDown={onKeyDown}
        placeholder="Choose a test…"
        aria-label={`Test name, row ${rowIndex + 1}`}
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={open && options.length ? `${listId}-${active}` : undefined}
        aria-invalid={(invalid && Boolean(value.trim())) || undefined}
        aria-describedby={discarded ? `${listId}-error` : undefined}
        autoComplete="off"
      />

      {/* The affordance. Without it the field looks like free text, and the
          rule that a name must come from the list arrives only as an error
          after the fact. mousedown, not click, for the same reason the options
          use it: the input's blur would close the list first, and the button
          would then reopen what it was meant to close. */}
      <button
        type="button"
        className="combo__toggle"
        tabIndex={-1}
        aria-label={open ? "Hide test list" : "Show test list"}
        onMouseDown={(e) => {
          e.preventDefault();
          setOpen((wasOpen) => !wasOpen);
          if (!open) wrapRef.current?.querySelector("input")?.focus();
        }}
      >
        <Chevron />
      </button>

      {discarded && !open && (
        <p className="combo__error" id={`${listId}-error`} role="alert">
          &ldquo;{discarded}&rdquo; isn&rsquo;t a test on the list, so it was
          cleared. Pick one from the list.
        </p>
      )}

      {open && (
        <ul className="combo__list" id={listId} role="listbox" ref={listRef}>
          {options.length === 0 && (
            <li className="combo__empty">
              No test matches that. Clear the box to see all{" "}
              {catalogue?.length ?? 0} of them.
            </li>
          )}

          {options.map((test, index) => (
            <li
              key={test.test_name}
              id={`${listId}-${index}`}
              data-index={index}
              role="option"
              aria-selected={index === active}
              className={`combo__option ${index === active ? "combo__option--active" : ""}`}
              // mousedown, not click: the input's blur would otherwise close
              // the list before the click landed.
              onMouseDown={(e) => {
                e.preventDefault();
                choose(test);
              }}
              onMouseEnter={() => setActive(index)}
            >
              <span className="combo__name">{test.test_name}</span>
              <span className="combo__range">
                {test.low}–{test.high} {test.unit}
              </span>
              <span className="combo__meta">
                {test.category}
                {test.aliases?.length
                  ? ` · ${test.aliases.slice(0, 3).join(", ")}`
                  : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
