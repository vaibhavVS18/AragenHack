"""Curated, user-facing knowledge about this application.

The repository's Markdown is written for developers. Retrieved against a user's
question it produces developer answers - "how can I test this?" matched the
setup guide and came back with `cd backend && pytest`, which is correct and
useless to someone looking at their results.

So the assistant's primary corpus is written here, in the second person, in the
words a user would actually use. The docs stay indexed as a fallback for
genuinely technical questions, but these entries match a user's phrasing more
closely and therefore rank above them.

Facts here are duplicated from the docs, which is a real cost - but the
alternative is answering users in developer language, and the numbers that
matter (thresholds, ranges) are not restated here at all. Those come from the
reference table over MCP, so they cannot drift.
"""

from __future__ import annotations

# (title, body). Titles are phrased as the question a user would ask, because
# the title is embedded along with the body.
ENTRIES: list[tuple[str, str]] = [
    (
        "What does this app do?",
        "This app reads laboratory test results and tells you which ones are "
        "outside their normal range, what that means, and what to do next. "
        "You enter results by hand or upload a CSV file. Each result is "
        "graded Normal, Warning or Critical, and every abnormal result comes "
        "with a plain-English explanation and suggested next steps.",
    ),
    (
        "How do I use it? How do I get started?",
        "Go to the Analyze page. You can type results in directly - test name, "
        "value and unit - or switch to the Upload CSV tab and drop in a file. "
        "Then press Analyze results. If you have nothing to hand, open the "
        "Datasets page and press Analyze on any of the bundled sample files; "
        "that runs the whole thing in one click.",
    ),
    (
        "How can I test the app? How do I try it out?",
        "There are three ways, easiest first. Type results in yourself: on the "
        "Analyze page, enter a test name, a value and a unit, then press "
        "Analyze results - or press 'Load sample' to fill the form with a few "
        "examples in one click. Upload a CSV: switch to the Upload CSV tab and "
        "drop in a file, and the app shows you what it read before analysing "
        "anything. Or run a bundled file: the Datasets page has four sample "
        "files you can analyse with a single press.",
    ),
    (
        "How do I get tested for glucose? Can this app do a blood test?",
        "This app does not perform laboratory tests and cannot arrange one. It "
        "reads results you already have from a laboratory and explains them. "
        "Getting a blood test done, how a sample is taken, and where to have "
        "one are matters for your doctor or clinic. What this app can tell you "
        "is what a glucose result means once you have the number: enter it on "
        "the Analyze page and it will be compared against the reference range "
        "and explained.",
    ),
    (
        "What can I type in to test it quickly?",
        "On the Analyze page, try Sodium 118 mEq/L to see a Critical result, "
        "Calcium 11.2 mg/dL for a Warning, and TSH 2.1 uIU/mL for a Normal "
        "one. That gives you all three severities at once. The 'Load sample' "
        "button fills in a similar set for you if you would rather not type.",
    ),
    (
        "What sample datasets come with the app?",
        "Four, on the Datasets page. The Kaggle laboratory dataset, which is "
        "the real anonymised data the app was built against. A normal panel, "
        "where every value is in range. A critical panel, full of dangerous "
        "values. And a mixed messy panel that deliberately includes broken "
        "rows, so you can see how unreadable entries are handled. Press "
        "Analyze on any of them.",
    ),
    (
        "What do Normal, Warning and Critical mean?",
        "Normal means the value sits inside its reference range, including the "
        "range's own bounds. Warning means it is outside the range but not "
        "far enough to be dangerous on its own - worth following up, not an "
        "emergency. Critical means it has passed a threshold where the value "
        "itself can be harmful and needs prompt medical attention. Colours "
        "follow the same order: green, amber, red.",
    ),
    (
        "How does the app decide the severity of a result?",
        "It compares the number against a reference range using fixed "
        "arithmetic. If the value is inside the range it is Normal. Outside "
        "the range but inside the critical thresholds it is a Warning. Past a "
        "critical threshold it is Critical. Nothing about that decision is "
        "guessed - the exact comparison is shown on each result card under "
        "'How this was classified'.",
    ),
    (
        "Does the AI decide whether my result is normal or abnormal?",
        "No. The severity is worked out by fixed rules in code before the AI "
        "is involved at all. The AI is then given the finished result and "
        "asked to explain it in plain language and suggest next steps. It is "
        "never asked what the severity is. This matters because an AI can "
        "phrase the same answer differently on two runs, whereas comparing a "
        "number against a threshold gives the same answer every time and can "
        "be checked by hand.",
    ),
    (
        "How do I know the AI is not making things up?",
        "Every result shows the arithmetic behind it. Open 'How this was "
        "classified' on any card and you will see the literal comparison that "
        "was made, such as 'value (6.9) > critical_high (6.5)', along with the "
        "reference range used and where that range came from. The AI wrote the "
        "wording, but it did not choose the verdict, and the verdict is "
        "reproducible.",
    ),
    (
        "What happens if the AI is unavailable?",
        "The results still work. Severity, reference ranges and the reasoning "
        "are all computed locally, so they are unaffected. Only the written "
        "explanations go missing, and a notice appears in their place.",
    ),
    (
        "Where do the reference ranges come from?",
        "In order of preference: first, the range supplied with the result "
        "itself. Some datasets, including the Kaggle one, carry a reference "
        "range on every row, and a laboratory's own range is authoritative for "
        "its own result. Second, the app's built-in clinical table, which is "
        "also the only source of critical thresholds. If neither is available "
        "the result is returned uninterpreted rather than guessed at. Each "
        "card tells you which source was used.",
    ),
    (
        "What does 'derived' mean next to a critical threshold?",
        "It means the app did not have a published critical value for that "
        "test, so it estimated one from the width of the supplied reference "
        "range. It is labelled because an estimate should never be mistaken "
        "for a clinically established danger threshold. Treat a critical flag "
        "marked derived as indicative rather than definitive.",
    ),
    (
        "How do I enter results manually?",
        "On the Analyze page, in the Enter results tab, fill in the test name, "
        "the value and the unit. Press '+ Add row' for each additional test. "
        "The test name box suggests names as you type, and filling one in "
        "offers the usual unit automatically. 'Load sample' fills the form "
        "with a few example results if you want to see it work quickly.",
    ),
    (
        "What CSV format does the upload need?",
        "A header row and one result per line. The simplest form is three "
        "columns: test_name, value, unit. Common alternative headings are "
        "accepted too, such as 'Test Name', 'Result' or 'Units'. If your file "
        "carries its own reference range in columns like Min_Reference and "
        "Max_Reference, those are picked up and used. After you choose a file "
        "the app shows exactly what it read, before anything is analysed.",
    ),
    (
        "My CSV did not work. What went wrong?",
        "After choosing a file the app shows a preview of what it parsed, "
        "including any rows it could not read. Common causes are a missing "
        "header row, a value column that contains text such as 'N/A', a blank "
        "test name, or a unit that does not match the test. Rows that cannot "
        "be read are skipped and listed separately - the rest are still "
        "analysed, so one bad row never loses the whole file.",
    ),
    (
        "What does it mean when a result could not be read?",
        "The app could not interpret that entry, so it refused to grade it "
        "rather than guess. Usual reasons: the test name is not one it knows, "
        "the value is not a number, the value is negative, or the unit cannot "
        "be compared with the reference range. These appear in their own "
        "section with the reason given for each.",
    ),
    (
        "Why was my result refused because of the unit?",
        "Because converting it would risk a confidently wrong answer. For "
        "example glucose of 5.4 mmol/L is perfectly normal, but 5.4 mg/dL "
        "would be dangerously low. Rather than assume which you meant, the app "
        "declines to grade the result and tells you the unit it expected.",
    ),
    (
        "Can I download or print my results?",
        "Yes. Under the summary there is a 'Download PDF report' button. It "
        "produces a report with every result, what it means, how urgent it is "
        "and what to do next, laid out to hand to a doctor. There is also an "
        "Export CSV button if you want the numbers in a spreadsheet.",
    ),
    (
        "What is in the PDF report?",
        "A letterhead with the date and patient label, a summary of how many "
        "results were checked and how many need attention, the headline "
        "verdict, and then each result in full: the value, the range it was "
        "compared against, what it means, common causes, how soon to act, what "
        "to do, and questions to ask a doctor. Every page carries a footer "
        "noting the results were graded by fixed rules and that the report is "
        "not a diagnosis.",
    ),
    (
        "Which order are results shown in?",
        "Most urgent first. Critical results come before Warnings, which come "
        "before Normal ones, and anything that could not be read comes last. "
        "Within each group the result furthest outside its range leads, so the "
        "worst finding is always the first thing you see.",
    ),
    (
        "Can I filter the results?",
        "Yes. The coloured chips under the summary bar are filters - click "
        "Critical to show only critical results. There is also a search box "
        "once there are more than three results, which matches the test name, "
        "its category, or the text of the explanation. Filtering only changes "
        "what is displayed; the counts always describe the full set.",
    ),
    (
        "What is the bar above the results?",
        "It shows the make-up of the whole panel at a glance - how much of it "
        "is critical, warning or normal - so you can see whether things are "
        "mostly fine or mostly concerning before reading any numbers. The "
        "chips underneath give the exact counts.",
    ),
    (
        "Which AI does this app use?",
        "Google Gemini writes the explanations for lab results. This help "
        "assistant is separate and runs entirely on your own machine, through "
        "Ollama - both the model that answers and the one that indexes the "
        "documentation. It has no cloud fallback, so if Ollama is not running "
        "it says so rather than sending your questions elsewhere. The AI is "
        "used only for wording - never for deciding whether a result is "
        "normal.",
    ),
    (
        "What is MCP and why does this app use it?",
        "MCP, the Model Context Protocol, is a standard way for a program to "
        "offer tools that an AI agent can call. In this app all the clinical "
        "logic - looking up a reference range, grading a value, sorting by "
        "severity - lives in a separate MCP server process, and the agent "
        "reaches it over that protocol rather than calling the code directly. "
        "The practical benefit is that the same tools could be used by any "
        "other MCP-compatible application.",
    ),
    (
        "Which lab tests does this app know about?",
        "It has built-in ranges for a set of common blood tests covering "
        "haematology, general chemistry, thyroid and liver function. The full "
        "list with every threshold is on the Reference ranges page. Tests "
        "outside that list can still be graded if your file supplies its own "
        "reference range.",
    ),
    (
        "Does it understand other names for the same test?",
        "Yes. Common abbreviations and alternative spellings are recognised - "
        "HGB for Hemoglobin, K+ for Potassium, SGPT for ALT, and Turkish names "
        "from the Kaggle dataset such as Trombosit and Lokosit. Minor typos "
        "are matched too, and when that happens the result says so, so you can "
        "check it guessed correctly.",
    ),
    (
        "Is this a medical diagnosis? Can I rely on it?",
        "No. This is a demonstration application, not a medical device, and "
        "nothing it produces is a diagnosis. It compares numbers against "
        "published reference ranges and explains what those comparisons "
        "generally mean. Ranges are adult and sex-agnostic with no adjustment "
        "for age, sex or medical history. Any decision about your health "
        "belongs with a doctor who knows your circumstances.",
    ),
    (
        "Can you tell me if I am ill, or what I should take?",
        "No. This assistant can only explain how the application works - how "
        "results are graded, what the ranges are, and how to use the "
        "interface. Questions about your health, a diagnosis, or treatment "
        "need a doctor who can see your full picture.",
    ),
]


def knowledge_entries() -> list[tuple[str, str]]:
    """The curated entries, as ``(title, body)`` pairs."""
    return list(ENTRIES)
