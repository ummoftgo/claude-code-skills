import json
import re
import tempfile
import unicodedata
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# The file extensions a SKILL.md may point at inside its own references/ directory.
#
# An allowlist, not a generic `\.\w+`: the right-hand boundary below earns its keep only
# because the set of endings is closed. With any extension accepted, `references/foo.mdx`
# would stop being a rejected truncation of `references/foo.md` and become a pointer to a
# file of its own, and ordinary prose ("the patterns in references/x.php") would start
# demanding files. `html` is here because skills/report-output/SKILL.md makes
# `references/report-template.html` a required asset (its HTML skeleton); before it was
# listed, that file could vanish and nothing failed. Adding a further asset kind is a
# one-word edit here.
REFERENCE_EXTENSIONS = "md|html"

# One path segment of a reference path: a run of name characters that is not, in its
# entirety, `.` or `..`.
#
# `[\w.\-]+` on its own accepted `..` as a segment, and `references/../outside.md` was
# therefore extracted as one of this skill's references - then *passed* the containment
# assertion in read_skill_dir(), because it resolves inside the skill directory, merely
# outside references/. So a pointer could climb out of references/ and claim any `.md` or
# `.html` file sitting elsewhere in the skill: the existence check passed and that file
# stopped looking orphaned, which is the same silent success the boundary rules below
# exist to prevent. Every reference this repository ships lives under references/, and
# that is the only shape SKILL.md is allowed to name, so a segment that navigates
# (`.`, `..`) is rejected outright rather than resolved.
#
# A leading `./` is still admitted, by the explicit prefix in the patterns below. The
# guard is deliberately about *whole* segments: a period inside a name (`foo.bar.md`,
# `..md`) is an ordinary filename character and stays legal.
REFERENCE_SEGMENT = r"(?!\.{1,2}(?![\w.\-]))[\w.\-]+"

# A pointer from SKILL.md to one of its own reference documents. Both notations in use
# in this repository count, because both tell the model which file to open:
#   Markdown link  - [references/plugin-diagnostics.md](references/plugin-diagnostics.md)
#   inline code    - Read `references/reviewer-prompts.md` and use its ...
#
# The two notations are parsed in *separate* passes, because they end differently. This
# pattern is the body-text pass - inline code and plain prose - where a path is embedded
# in a sentence and the sentence's own punctuation follows it. The bracketed destination
# of a Markdown link is handled by LINK_DESTINATION_PATTERN instead, which anchors both
# ends; see reference_links().
#
# Only the POSIX spelling counts: a path is written with `/`, the separator every
# SKILL.md in this repository already uses and the only one Markdown treats as a path
# separator. `references\foo.md` is therefore deliberately *not* a link - the file it
# names is then reported as an orphan, which pushes the author back to `/` instead of
# quietly blessing a second notation. Accepting backslashes would also mean teaching the
# containment and cross-skill checks below to understand them, and every separator this
# extractor half-understands is a way for an outside path to pose as a local one.
#
# The boundary pieces each rule out a specific misread. Every one of them exists because
# the shape it rejects was, before it, *truncated or shaved into* the bare local path
# `references/foo.md` - and where a real foo.md sat next door that was the worst possible
# outcome: the existence check passed, the neighbour stopped looking orphaned, and nothing
# failed at all.
#   * the lookbehind drops paths carrying an earlier segment (for example
#     `web-security-review/references/php-backend-security.md`): those name a different
#     skill's document and are not this skill's to ship or resolve. It also blocks
#     `../references/x.md`, which leaves the skill for the same reason. `\\` is in the
#     class for exactly that reason: a mixed-separator path such as
#     `..\references/foo.md` or `other-skill\references/foo.md` used to have its leading
#     segments shaved off and match as the bare local `references/foo.md`.
#     `:` is in the class for the prefix disguises, which are the same trick with a
#     non-path lead-in: `C:references/foo.md` is drive-relative (resolved against the
#     current directory of drive C:, not this skill) and `file:references/foo.md` is a URI
#     scheme. Both used to have the prefix shaved off and match as the local path.
#   * `(?:\./)?` admits the equivalent `./references/x.md` spelling, which the
#     lookbehind alone would reject along with the cross-skill paths.
#   * REFERENCE_SEGMENT forbids a `.` or `..` segment, so `references/../outside.md`
#     cannot borrow a file from outside references/; see its comment above.
#   * the two lookaheads require the path to *end* at `.md`. Without them a path that
#     merely starts with a real one - `references/foo.mdx`, `references/foo.md.bak`,
#     `references/foo.md-bak`, `references/foo.md/extra`, `references/foo.md\extra`,
#     `references/foo.md%2Fextra` - was truncated to `references/foo.md`. Anything that
#     continues the name (`\w`, `-`) or the path (`/`, `\`), the `%` that opens a percent
#     escape (`%2F` is an encoded separator, so the real target is a path *inside*
#     foo.md), and any `.` that starts a further extension therefore disqualifies the
#     match. A bare trailing period is still allowed, so a path ending a sentence ("Read
#     references/foo.md.") matches - this tolerance is what confines the pattern to body
#     text: inside a link destination the same period is part of the path and must
#     disqualify it.
SKILL_REFERENCE_PATTERN = re.compile(
    rf"(?<![\w.\-/\\:])(?:\./)?references/{REFERENCE_SEGMENT}(?:/{REFERENCE_SEGMENT})*"
    rf"\.(?:{REFERENCE_EXTENSIONS})(?![\w\-/\\%])(?!\.\w)"
)

# The other pass: a Markdown inline link, `[label](destination)`.
#
# Inside the parentheses there is no surrounding sentence - the whole run between `(` and
# `)` is the path - so nothing may be shaved off either end. Splitting this out fixes a
# family of destinations that the body-text pattern above truncated into a valid-looking
# path: `references/foo.md.`, `references/foo.md..` (a trailing period is sentence
# punctuation in prose but part of the filename here), `references/foo.md%2Fextra` (a
# percent-encoded `/`, so the real target is a file *inside* foo.md), `C:references/foo.md`
# (a drive-relative path) and `file:references/foo.md` (a URI scheme). Each named
# something other than `references/foo.md`, yet matched as `references/foo.md`; where a
# real foo.md sat next door, the existence check passed *and* foo.md stopped looking
# orphaned, so nothing failed at all.
#
# The label is consumed along with the destination, and the whole link - both halves - is
# masked out of the body pass. Keeping the label as body text is what made the five
# rejections above worthless in this repository, because the spelling every SKILL.md here
# uses puts the path in the label as well:
#
#     [references/atomic-publish.md](references/atomic-publish.md)
#
# A destination rejected for being `references/foo.md.`, `references/foo.md%2Fextra`,
# `C:references/foo.md` or `file:references/foo.md` was re-admitted a moment later under
# the looser body rules, out of its own label, as exactly the `references/foo.md` the
# destination rules had just refused to grant. With a real foo.md next door the broken
# pointer once again passed the existence check and cleared the orphan report.
#
# A label is display text: it names the link for a reader, it does not tell the model
# which file to open. So a path may be a reference only on the strength of a destination
# that survives LINK_DESTINATION_PATTERN, never on the strength of the words it is
# written under.
MARKDOWN_LINK_PATTERN = re.compile(
    r"\[[^\]\n]*\]\((?P<destination>[^()\n]*)\)"
)

# Matched with fullmatch() against a destination, so both ends are anchored: the same
# containment rules as the body pattern (`references/` or `./references/` only - never a
# leading segment, never a `.` or `..` segment, never a backslash), and the path must
# *end* at an allowed extension, which rules out a prefix (`C:`, `file:`) or a suffix (a
# trailing period, `%2Fextra`) without needing either boundary assertion. A fragment is
# the one permitted suffix, because it selects a place inside the very file being named
# rather than a different file.
LINK_DESTINATION_PATTERN = re.compile(
    rf"(?:\./)?references/{REFERENCE_SEGMENT}(?:/{REFERENCE_SEGMENT})*"
    rf"\.(?:{REFERENCE_EXTENSIONS})(?:#[\w.\-]+)?"
)

# Regions of a SKILL.md that are shown to the model as text rather than issued to it as
# an instruction, and so cannot be the reason a reference document is shipped.
HTML_COMMENT_PATTERN = re.compile(r"<!--.*?-->", re.DOTALL)
CODE_FENCE_PATTERN = re.compile(r"(?P<fence>`{3,}|~{3,})(?P<info>.*)$")


# HTML elements whose contents a reader does not see, or sees only after acting.
#
# This is a *finite* structural check, unlike verifying that no earlier prose disclaims
# what follows: there is a fixed list of ways HTML hides an element, and a document using
# none of them cannot hide anything this way.
HIDING_TAGS = {"template", "script", "style", "details"}
# One HTML attribute: a name, and optionally a quoted or bare value.
HTML_ATTRIBUTE = re.compile(
    r"""(?P<name>[\w:-]+)(?:\s*=\s*(?P<value>"[^"]*"|'[^']*'|[^\s>]+))?"""
)


def has_attribute(attrs: str, wanted: str) -> bool:
    """Whether `attrs` declares `wanted`, as an attribute rather than as a value.

    `<details class="x open y">` is closed; searching the raw attribute string for the
    word `open` said otherwise.
    """
    return any(
        match.group("name").lower() == wanted for match in HTML_ATTRIBUTE.finditer(attrs)
    )


def hides_by_attribute(attrs: str) -> bool:
    """Whether `attrs` makes its element invisible.

    Attributes are parsed rather than searched. A substring test for `hidden` reported
    `aria-hidden="false"`, `data-hidden="false"`, and `class="not-hidden"` as hiding -
    all three are ordinary markup, all three rejected a visible contract, and a checker
    that fires on those gets deleted rather than fixed.

    **Inline CSS is deliberately not interpreted.** A `style` heuristic was tried and
    every version of it was wrong in both directions at once: `/* display:none */` in a
    comment and `display:none;display:block` were called hidden, `display:none-block`
    was an invalid value read as valid, and `visibility:hidden` - a real way to hide -
    was missed. Getting those right means implementing a CSS parser inside a contract
    test, which is more machinery than the thing it protects. What is checked instead is
    the small closed set HTML defines exactly: the `hidden` attribute, `aria-hidden`,
    and the element names in HIDING_TAGS. Inline CSS in a skill document is out of scope
    and is stated as such rather than half-handled.
    """
    for match in HTML_ATTRIBUTE.finditer(attrs):
        name = match.group("name").lower()
        value = (match.group("value") or "").strip("\"'").strip().lower()
        if name == "hidden":
            # A boolean attribute: its *presence* hides the element. `hidden="false"`
            # is still hidden - HTML has no way to say "hidden, but not really".
            return True
        if name == "aria-hidden" and value == "true":
            return True
    return False
# The attribute run is quote-aware: `<div title="a > b" hidden>` used to be cut at the
# `>` inside the title, so the `hidden` that followed was never seen.
HTML_TAG = re.compile(
    r"""<(?P<close>/?)(?P<name>[a-zA-Z][\w-]*)"""
    r"""(?P<attrs>(?:"[^"]*"|'[^']*'|[^>"'])*?)(?P<self>/?)>"""
)
# Elements that never have contents, so they never open a container.
VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}

# An inline code span. `` `<script>` `` is prose *about* a tag, not a tag - report-output
# discusses one while explaining CSP hashes - and counting it as a container made a
# document that hides nothing fail. Only markup outside code spans can hide anything.
INLINE_CODE = re.compile(r"`[^`\n]*`")


def hiding_ancestors(markup: str) -> list[str]:
    """The hiding elements still open at the end of `markup`.

    A real tag stack, not a count. Subtracting every closer from every opener was the
    first attempt and it was wrong in both directions: an ordinary `<div>…</div>`
    earlier in the document cancelled a later `<details>`, and a *closed*
    `<span aria-hidden="true">…</span>` made everything after it look hidden.

    Two element-specific rules, both narrower than they first were:

    * `<details>` hides its contents unless it carries `open` - and `open` is read from
      the parsed attributes, because searching the raw string for the word matched
      `class="x open y"`. Its own `hidden` attribute still counts, so
      `<details open hidden>` hides.
    * A `<summary>` is the click target and renders even when its `<details>` is
      collapsed. It therefore cancels *that one* `<details>` and nothing else: an
      earlier blanket "a summary means visible" let `<div hidden><details><summary>`
      report nothing hidden, which is the opposite of true.
    """
    stack: list[tuple[str, bool]] = []
    for match in HTML_TAG.finditer(markup):
        name = match.group("name").lower()
        if match.group("close"):
            for index in range(len(stack) - 1, -1, -1):
                if stack[index][0] == name:
                    del stack[index:]
                    break
            continue
        if match.group("self") or name in VOID_TAGS:
            continue
        attrs = match.group("attrs")
        hides = hides_by_attribute(attrs)
        if name == "details":
            hides = hides or not has_attribute(attrs, "open")
        elif name in HIDING_TAGS:
            hides = True
        stack.append((name, hides))

    exempt = set()
    for index, (name, _) in enumerate(stack):
        if name != "summary":
            continue
        for below in range(index - 1, -1, -1):        # the details this summary opens
            if stack[below][0] == "details":
                exempt.add(below)
                break
    return [name for index, (name, hides) in enumerate(stack) if hides and index not in exempt]


def assert_not_hidden(test, text: str, needle: str, label: str) -> None:
    """`needle` is not inside a hiding element, and is not indented into a code block.

    Scoped to the ancestry of `needle` rather than to the whole document: a file may
    legitimately *mention* `<script>` - report-output does, explaining CSP hashes - and
    rejecting the file for that is a false positive that gets the check deleted.

    The indentation half is here for the same reason the template check has one. Four
    spaces or a tab makes a line an indented code block in CommonMark, so a re-indented
    instruction still reads as an instruction to a substring check while a reader sees a
    code sample. Whitespace normalisation in block_containing() erases exactly that
    difference, which is why the raw line has to be looked at separately.
    """
    # Masked, not stripped: offsets have to keep matching the original, because the
    # needle itself normally *is* inside a code span (`FR-001(feature/label)`). Only the
    # tags inside spans are neutralised, and every character keeps its position.
    masked = INLINE_CODE.sub(lambda m: " " * len(m.group(0)), text)
    index = text.find(needle)
    test.assertNotEqual(index, -1, f"{label}: {needle!r} not found")
    while index != -1:
        hidden = hiding_ancestors(masked[:index])
        test.assertEqual(
            hidden, [], f"{label}: {needle!r} sits inside {hidden}"
        )
        line_start = text.rfind("\n", 0, index) + 1
        line = text[line_start : text.find("\n", index)]
        test.assertRegex(
            line,
            r"^ {0,3}(?![ \t])",
            f"{label}: {needle!r} is indented into a code block",
        )
        index = text.find(needle, index + len(needle))


def instructional_text(markdown: str) -> str:
    """`markdown` with HTML comments and fenced code blocks removed.

    A path inside `<!-- ... -->` is invisible to the model, and a path inside a fenced
    block is an example of a command rather than a pointer to follow; neither should
    make a reference document count as linked. Inline code spans (single backticks) are
    kept, because that is one of the two notations this repository uses for real
    pointers.

    A line closes the block only on CommonMark's terms: the same fence character, at
    least as many of them as the opening run, and nothing but whitespace afterwards. A
    looser test let ```` ```not-a-close ```` end the block, exposing the example paths
    below it as if they were instructions.

    Deliberately not a full Markdown parser. Known gaps: an unterminated `<!--` is left
    alone rather than swallowing the rest of the file; a fence opened and closed on one
    line counts as an opening fence; indentation is ignored rather than capped at three
    spaces, so a fence inside an indented code block or a blockquote still toggles; and
    an info string containing a backtick is accepted as an opener even though CommonMark
    rejects it. None of these shapes occur in this repository's SKILL.md files.
    """
    kept: list[str] = []
    fence: str | None = None
    for line in HTML_COMMENT_PATTERN.sub("", markdown).splitlines():
        match = CODE_FENCE_PATTERN.match(line.lstrip())
        if fence is None:
            if match:
                fence = match.group("fence")
            else:
                kept.append(line)
        elif (
            match
            and match.group("fence")[0] == fence[0]
            and len(match.group("fence")) >= len(fence)
            and not match.group("info").strip()
        ):
            fence = None
    return "\n".join(kept)


# Constructions that invert an imperative. A contract test that pins a substring proves
# the words are present, not that they still say what the contract needs: `Do not Write
# ...` contains `Write ...`, so an assertion on the bare phrase survives having its
# meaning reversed. Measured - injecting exactly that reversal into skills/readable-ids
# left every assertion about the rendering rule green.
#
# The set is deliberately narrow. Bare `not` and bare `no` are excluded because they
# occur constantly in legitimate prose around these very sentences ("`CH-1` alone is not
# enough", "carries no meaning for the reader", "someone who does not have this
# session's context"), and a checker that fires on those would be turned off rather than
# fixed. What is listed is what an inverting edit actually reaches for.
#
# It is a net, not a proof: a vocabulary list can always be walked around ("it is wrong
# to Write ...", a strikethrough). That is why the instruction that carries the contract
# is *also* checked structurally, by sentence position - see assertPositiveInstruction's
# `sentence_initial`. Every reversal listed above and every one found while probing this
# set displaces the imperative from the start of its sentence, which no synonym fixes.
INVERTING_NEGATION = re.compile(
    r"\b(?:do(?:es)?\s+not|don't|never|must\s+not|shall\s+not|no\s+longer|instead\s+of"
    r"|avoid|refrain|forbidden|forbids|prohibit(?:ed|s)?|omit|rather\s+than"
    r"|under\s+no\s+circumstances|wrong\s+to|cannot|can't|may\s+not|should\s+not"
    r"|shouldn't|mustn't|couldn't|won't|will\s+not)\b",
    re.IGNORECASE,
)

# Where one sentence ends and the next begins, for the purpose above. Single newlines
# are not boundaries: every SKILL.md in this repository hard-wraps prose, so cutting on
# `\n` would split most sentences in half and hide a negation in the discarded piece.
SENTENCE_BOUNDARY = re.compile(r"(?:\n\s*\n|(?<=[.!?;])[ \n])")


def sentences_containing(text: str, needle: str) -> list[str]:
    """Every sentence `needle` sits in, whitespace normalised, in document order.

    Scoped to one sentence rather than one paragraph on purpose. A paragraph here
    routinely carries a positive instruction and its exception side by side - "render
    the labels inline and create no registry", "Do not write its registry here" - and a
    paragraph-wide negation check would reject the document for saying both, which is
    exactly what these documents are supposed to say.

    *Every* occurrence, not the first. Checking only the first was itself a hole: Codex
    reversed a second occurrence while leaving an explanatory first one intact, and the
    contract stayed green. A pinned phrase that appears twice has to survive both times,
    because a reader who follows the second one is no less misled.
    """
    boundaries = [match.end() for match in SENTENCE_BOUNDARY.finditer(text)]
    found: list[str] = []
    index = text.find(needle)
    while index != -1:
        starts = [end for end in boundaries if end <= index]
        start = starts[-1] if starts else 0
        end_match = SENTENCE_BOUNDARY.search(text, index + len(needle))
        end = end_match.start() if end_match else len(text)
        found.append(" ".join(text[start:end].split()))
        index = text.find(needle, index + len(needle))
    return found


# Where one readable unit ends and the next begins: a blank line, or the start of a list
# item. Coarser than SENTENCE_BOUNDARY on purpose - a rule stated in one paragraph is
# reversed just as effectively by a sentence *added in front of it* ("Never follow the
# next instruction. Write ...") as by editing the sentence itself, and a sentence-scoped
# check cannot see that. Finer than a paragraph on the list side, so pinning one bullet
# does not pin its neighbours and freeze prose that has nothing to do with the contract.
BLOCK_BOUNDARY = re.compile(r"(?:\n\s*\n|\n(?=\s*[-*+] ))")


def block_containing(text: str, needle: str) -> list[str]:
    """Every block `needle` sits in, whitespace normalised, in document order."""
    boundaries = [match.end() for match in BLOCK_BOUNDARY.finditer(text)]
    found: list[str] = []
    index = text.find(needle)
    while index != -1:
        starts = [end for end in boundaries if end <= index]
        start = starts[-1] if starts else 0
        end_match = BLOCK_BOUNDARY.search(text, index + len(needle))
        end = end_match.start() if end_match else len(text)
        found.append(" ".join(text[start:end].split()))
        index = text.find(needle, index + len(needle))
    return found


def fenced_blocks(markdown: str) -> list[str]:
    """The contents of `markdown`'s fenced code blocks.

    The complement of instructional_text(), and needed for the same reason. A report
    template's structure *is* its fenced block, so a contract about the shape a report
    takes has to be asserted against that block - not against the whole file, where the
    same string sitting in an HTML comment or in prose about the template would satisfy
    it while the template itself no longer carried it.
    """
    blocks: list[str] = []
    current: list[str] | None = None
    fence: str | None = None
    for line in HTML_COMMENT_PATTERN.sub("", markdown).splitlines():
        match = CODE_FENCE_PATTERN.match(line.lstrip())
        if fence is None:
            if match:
                fence = match.group("fence")
                current = []
        elif (
            match
            and match.group("fence")[0] == fence[0]
            and len(match.group("fence")) >= len(fence)
            and not match.group("info").strip()
        ):
            blocks.append("\n".join(current or []))
            fence, current = None, None
        elif current is not None:
            current.append(line)
    if current is not None:                      # unterminated fence: keep what we saw
        blocks.append("\n".join(current))
    return blocks


def reference_links(markdown: str) -> list[str]:
    """The reference paths `markdown` actually instructs the model to open, sorted.

    Two passes, because the two notations this repository uses end differently:

      * every Markdown inline link's destination is taken whole and matched end to end
        (LINK_DESTINATION_PATTERN). Anything trailing the extension - a period, a colon,
        a percent escape, a scheme prefix - names a different file, so the destination is
        simply not a pointer to this skill's document;
      * whatever remains, which is inline code and plain prose, is scanned with
        SKILL_REFERENCE_PATTERN, which tolerates the period that ends a sentence ("Read
        references/foo.md.").

    Each link is replaced *in full* - label and destination alike - by a space before the
    second pass, so a rejected destination cannot be re-read under the looser body rules
    out of its own label. This repository writes its links as
    `[references/foo.md](references/foo.md)`, so a surviving label is not a harmless
    leftover but a complete second copy of the path being rejected; see
    MARKDOWN_LINK_PATTERN. The consequence is that a label alone never makes a reference
    count as linked, which is deliberate: `[references/foo.md](https://example.com)`
    points at the web, whatever it calls itself.

    Deliberately not a full CommonMark link parser. Known gaps, all of which fail *loud*
    (the destination is not counted, so its file is reported unreachable rather than
    silently accepted): a link title (`[x](references/foo.md "t")`), an angle-bracketed
    destination (`[x](<references/foo.md>)`), a destination containing parentheses, and a
    reference-style link whose definition sits elsewhere. Percent-encoding is never
    decoded, so `%2F` is a rejection rather than a path separator. One gap fails the other
    way: in a link whose label holds an image (`[![alt](x.png)](references/foo.md)`) the
    inner link is masked first, leaving the outer destination as body text where the
    looser rules judge it. None of these shapes occur in this repository's SKILL.md files,
    where every destination is a bare path.
    """
    found: set[str] = set()

    def take_destination(match: re.Match[str]) -> str:
        destination = match.group("destination").strip()
        if LINK_DESTINATION_PATTERN.fullmatch(destination):
            found.add(destination.split("#", 1)[0])
        # A space, not an empty string: removing the link outright would join the text on
        # either side of it, which can only invent tokens that were never adjacent.
        return " "

    body = MARKDOWN_LINK_PATTERN.sub(take_destination, instructional_text(markdown))
    found.update(SKILL_REFERENCE_PATTERN.findall(body))
    return sorted(found)


# The wiring sentence each emitting document carries, pinned verbatim.
#
# Pinned rather than probed for negations because the net has measured holes that no
# vocabulary closes - "It is pointless to invoke ...", "Skip this: invoke ...", "This
# rule is obsolete." all reverse the sense without a listed word. Each of these blocks
# is exactly one paragraph or one list item, so equality is available here and equality
# is what no rephrasing survives.
#
# The cost is real: rewording one of these fails this test. That is the intended
# trade. These sentences are the wiring contract, and changing what they instruct
# should cost a deliberate test edit rather than passing unnoticed.
EMITTING_CONTRACT_BLOCKS = {
    "skills/plan-and-build/SKILL.md": (
        "- **Readable form:** an identifier that reaches the user — in a plan summary, a "
        "status report, or a question asking them to decide — needs a label a person can "
        "read. Invoke `readable-ids` if it is installed to register the identifier and render "
        "it as `FR-001(feature/label)`. Without that skill, keep a label beside every "
        "identifier in the plan itself; a bare `FR-001` in a sentence costs the reader a "
        "document lookup that the writer could have spent one phrase avoiding."
    ),
    "skills/branch-merge-review/SKILL.md": (
        "**Finding identifiers**: the report is read by a person and its blocking-items line "
        "asks them to decide, so `CH-1` alone is not enough. Render each identifier as "
        "`CH-1(feature/label)` on first mention, following the `readable-ids` convention when "
        "that skill is installed. **Do not write its registry**: the delivery rule above "
        "forbids a review from changing the working tree, and that holds for every review "
        "rather than only an explicitly read-only one — rendering a label needs no file. "
        "Without that skill, still write a short label beside each identifier, because a "
        "later recheck refers to these findings by number across a different document, which "
        "is exactly where a bare number stops meaning anything."
    ),
    "skills/branch-merge-review/references/consolidated-report-template.md": (
        "`(feature/label)` below is the readable form of a finding identifier, owned by the "
        "`readable-ids` skill: full form on first mention in the report — the blocking-items "
        "line and each finding heading — and the bare identifier everywhere after that. When "
        "`readable-ids` is not installed, keep a short label in the same position anyway; a "
        "recheck later refers to these findings by number from a different document."
    ),
    "skills/evidence-first-review/SKILL.md": (
        "A recheck refers to findings that were numbered in a different document, so the "
        "identifier alone carries no meaning for the reader. Render each prior finding as "
        "`H-2(feature/label)` on first mention, following the `readable-ids` convention when "
        "that skill is installed; otherwise carry a short label beside every identifier in "
        "the ledger. **Do not write its registry here** — this skill is read-only in every "
        "mode, and rendering a label needs no file. Read an existing `.uniqid/` entry to "
        "reuse the label a prior pass already published; where none exists, say the label is "
        "unregistered rather than creating one."
    ),
    "skills/report-output/SKILL.md": (
        "- **Identifiers**: A report is human-facing output. When it refers to work by a "
        "short identifier (`A1`, `FR-001`, `CH-2`), write `A1(feature/label)` on first "
        "mention, short form afterwards, following the `readable-ids` convention when that "
        "skill is installed. Rendering needs no file, so it applies under the read-only rule "
        "above too; creating the `.uniqid/` registry is a write, and `readable-ids` owns when "
        "that is permitted — never when the invoking skill says the report is a review. Where "
        "that skill is unavailable, keep a label beside the identifier anyway — a reader who "
        "has to open another document to learn what `A1` is has lost the summary."
    ),
    "skills/safe-checkpoint/references/handoff-template.md": (
        "A handoff is read by someone who does not have this session's context. When it names "
        "work by a short identifier, write the readable form — `A1(feature/label)` — on first "
        "mention and the short form afterwards; `readable-ids` owns that convention and its "
        "registry when the skill is installed. Rendering the label is part of writing the "
        "handoff; **creating or updating `.uniqid/` is a separate write** and needs its own "
        "authority under the table in SKILL.md §2 — authority to write the handoff does not "
        "extend to it. That is this skill's per-artifact rule, which `readable-ids` defers to "
        "by name."
    ),
}


class SkillReadingMixin:
    """Reading helpers shared by the contract tests and the tests covering them."""

    def read(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def readable_ids_body(self) -> str:
        """skills/readable-ids/SKILL.md: frontmatter stripped, comments and fences too.

        Three narrowings, each because a wider read let a broken document pass.

        The frontmatter goes because the description restates the convention -
        `.uniqid/`, `A1(feature/label)` - to route the model here in the first place.
        Asserting against the whole file therefore passed while the *rules* were deleted
        from the body: measured, a mutation removing the rendering sentence left every
        assertion green because the description still carried the same literal.

        read_skill() is wrong here for the neighbouring reason. It appends the reference
        documents, and references/registry-format.md legitimately repeats the path and
        the status vocabulary; a rule deleted from the body would go on being satisfied
        by the elaboration a model only reaches after following a pointer.

        instructional_text() goes on top so a rule cannot be satisfied from inside an
        HTML comment or a fenced example - text the model either never sees or reads as
        an illustration rather than an instruction.
        """
        body = self.read("skills/readable-ids/SKILL.md")
        self.assertTrue(body.startswith("---\n"))
        return instructional_text(body.split("\n---\n", 1)[1])

    def assertPositiveInstruction(
        self, text: str, needle: str, sentence_initial: bool = False
    ) -> None:
        """`needle` is present and **no** occurrence of it has been inverted.

        assertIn alone proves the words are there, not that they still instruct. Codex
        demonstrated the gap by injecting `Do not Write ...` and `Never invoke
        readable-ids and never render (feature/label).`: every substring assertion
        stayed green while the contract said the opposite.

        Two checks, because they fail differently. The negation vocabulary is a net with
        known holes - probing it turned up "avoid", "refrain from", "it is forbidden
        to", "under no circumstances", "rather than", "cannot", "may not", and a
        strikethrough. Widening the list closes those and invites the next synonym, so
        this is drift detection, not proof against an adversary.

        `sentence_initial` is the check that does not depend on vocabulary: an imperative
        starts its sentence, and every reversal above has to put something in front of
        it to work. Use it wherever the pinned phrase is the instruction itself.

        Where a whole block can be pinned, assertContractBlock is stronger still and
        should be preferred - the six emitting documents started on this looser check
        and did not survive it. What remains here is the case where neither applies.

        One documented limit: a negation in the *preceding* sentence is not seen.
        Widening the window would reject the shape these documents are built from - an
        instruction beside its exception, "Do not create the registry. Render inline." -
        so the window stays at one sentence and the hole is pinned in
        test_the_known_limits_of_the_checker_are_the_ones_documented.

        And a limit no scope closes: a sentence in the *preceding block* saying to
        ignore the next one defeats a block-scoped check the same way, a preceding
        section defeats a section-scoped one, and so on. The regress has no fixed point,
        because what would have to be verified is the document's meaning as a whole.
        The threat model here is drift - a rule quietly rewritten while its test keeps
        passing - not a document authored to lie about itself. Sabotage is caught by
        reading the diff, which is what a review is for.
        """
        self.assertIn(needle, text)
        for sentence in sentences_containing(text, needle):
            negation = INVERTING_NEGATION.search(sentence)
            self.assertIsNone(
                negation,
                f"instruction inverted by {negation.group(0)!r}: {sentence}"
                if negation
                else "",
            )
            if sentence_initial:
                self.assertTrue(
                    sentence.startswith(needle),
                    f"instruction no longer starts its sentence: {sentence}",
                )

    def assertContractBlock(self, text: str, anchor: str, expected: str) -> None:
        """The block around `anchor` is exactly `expected`, whitespace normalised.

        The strongest form available, and the answer to chasing negation synonyms: no
        prefix, suffix, synonym, or reordering survives an equality check, so a reversal
        cannot be phrased around it. The cost is that any rewrite of the block fails the
        test - which for the two blocks that *are* the contract is the point, not a
        defect. Reword them and a human decides whether the contract changed.

        Scoped to the block rather than the sentence because that is what closes the
        last measured hole. A rule is reversed just as well by a sentence placed in
        front of it - "Never follow the next instruction. Write ..." - which every
        sentence-scoped check misses by construction, and which an equality check over
        the surrounding block catches without any vocabulary at all.

        Used only where one block carries the rule. The six emitting documents word
        their pointers differently on purpose, so they keep the looser check above.
        """
        found = block_containing(text, anchor)
        self.assertTrue(found, f"anchor not present: {anchor!r}")
        for block in found:
            self.assertEqual(block, expected)

    def read_skill(self, name: str) -> str:
        """SKILL.md joined with the reference documents SKILL.md explicitly points at.

        Guarantees: every string found through this helper sits either in the skill body
        or one documented hop away, on a path the model is actually told to open. Detail
        may therefore move from SKILL.md into references/ without breaking a contract.

        Does not guarantee that the string is in SKILL.md itself. Contracts about the
        body specifically - frontmatter, section ordering, instructions the model must
        see without following a pointer - should keep using
        self.read("skills/<name>/SKILL.md").

        Also does not guarantee that a path mentioned only inside an HTML comment or a
        fenced code block is followed: see instructional_text(). Nor that a path written
        only as a link's *label* is followed - a label is display text, and only a
        destination routes the model to a file: see reference_links().

        Asserts three structural properties along the way:
          * every reference named by SKILL.md stays inside the skill directory - the
            installer copies one skill at a time, so a path escaping it cannot resolve
            on an installed machine and is not this skill's document to claim;
          * every reference named by SKILL.md exists - a broken pointer makes the detail
            unreachable, which is a defect in its own right. This covers non-Markdown
            assets too (REFERENCE_EXTENSIONS): report-output requires
            `references/report-template.html`, and until it was covered that file could
            vanish with every test still passing;
          * every file under the skill whose extension is in REFERENCE_EXTENSIONS is
            named by SKILL.md - an unlinked document is installed but never routed to, so
            its text must not be allowed to satisfy a contract on behalf of the skill.
            The orphan rule is scoped to those extensions rather than to every shipped
            file on purpose: `.md`/`.html` references are what SKILL.md routes the model
            to directly, whereas installer or client metadata (`agents/openai.yaml`) is
            read by tooling and never linked from prose, and a future image or data file
            may legitimately be referenced only by another reference document. Requiring
            SKILL.md to link those would force decorative pointers.
        """
        return self.read_skill_dir(ROOT / "skills" / name)

    def read_skill_dir(self, skill_dir: Path) -> str:
        """read_skill() against an arbitrary directory, so its rules can be tested."""
        # Paths that reach an assertion message or an expected value are spelled with
        # forward slashes, matching the notation SKILL.md itself uses. str(Path) would
        # produce `references\foo.md` on native Windows, so the same failure would read
        # differently - and compare unequal - depending on the platform.
        skill_dir = skill_dir.resolve()
        try:
            label = skill_dir.relative_to(ROOT).as_posix()
        except ValueError:
            label = skill_dir.as_posix()
        body = (skill_dir / "SKILL.md").read_text(encoding="utf-8")

        linked: list[Path] = []
        for relative_path in reference_links(body):
            reference = (skill_dir / relative_path).resolve()
            # Containment is checked against the skill root, not against references/,
            # even though every extracted path now starts at `references/` and carries no
            # `.` or `..` segment (REFERENCE_SEGMENT), which makes a *lexical* escape
            # impossible. What is left for this assertion is the escape a path cannot
            # show: a symlinked references/ - or a symlinked directory beneath it -
            # pointing out of the skill, which resolve() follows and the installer would
            # not carry. Tightening the check to `skill_dir/"references"` would lose
            # exactly that case, since a file inside a symlinked references/ is trivially
            # inside its own resolved directory while being nowhere near the skill.
            self.assertTrue(
                reference.is_relative_to(skill_dir),
                f"{label}/SKILL.md points at {relative_path}, which leaves the skill "
                "directory; a reference outside the skill is not installed with it",
            )
            self.assertTrue(
                reference.is_file(),
                f"{label}/SKILL.md points at {relative_path}, which does not exist",
            )
            if reference not in linked:
                linked.append(reference)

        shipped = {
            path.resolve()
            for extension in REFERENCE_EXTENSIONS.split("|")
            for path in skill_dir.rglob(f"*.{extension}")
            if path.name != "SKILL.md"
        }
        orphans = sorted(
            path.relative_to(skill_dir).as_posix() for path in shipped - set(linked)
        )
        self.assertEqual(
            orphans,
            [],
            f"{label}/SKILL.md never points at {orphans}; unlinked references are "
            "installed but unreachable",
        )

        return "\n".join(
            [body] + [path.read_text(encoding="utf-8") for path in linked]
        )


class SkillContractTest(SkillReadingMixin, unittest.TestCase):
    def test_plan_and_build_requires_proportional_design_approval(self) -> None:
        skill = self.read("skills/plan-and-build/SKILL.md")
        self.assertIn("Design approval checkpoint", skill)
        self.assertIn("wait for explicit user approval", skill)
        self.assertIn("does not need to be asked again", skill)

    def test_web_parallel_dispatch_requires_approval_before_workers(self) -> None:
        skill = self.read("skills/web-parallel-dispatch/SKILL.md")
        approval = skill.index("wait for explicit user approval")
        dispatch = skill.index("Dispatch in parallel")
        self.assertLess(approval, dispatch)

    def test_systematic_debugging_has_no_template_placeholders(self) -> None:
        skill = self.read("skills/systematic-debugging/SKILL.md")
        self.assertNotIn("TODO", skill)
        self.assertIn("do not edit production code until", skill)
        self.assertIn("Confirm the root cause", skill)
        self.assertIn("Add regression protection", skill)

    def test_systematic_debugging_is_registered_for_install_and_uninstall(self) -> None:
        catalog = self.read("components.json")
        install = self.read("install.sh")
        uninstall = self.read("uninstall.sh")
        self.assertIn('"name": "systematic-debugging"', catalog)
        self.assertIn("catalog_names skill claude", install)
        self.assertIn("catalog_names skill codex", install)
        self.assertIn("catalog_names skill claude", uninstall)
        self.assertIn("catalog_names skill codex", uninstall)

    def test_windows_supported_complex_skills_include_concrete_powershell(self) -> None:
        branch_review = self.read_skill("branch-merge-review")
        codex_delegate = self.read_skill("codex-delegate")
        for expected in (
            "```powershell", "try {", "finally {", "Select-String",
            "SqlInjection", "Csrf", "Secrets", "BackendQuality",
        ):
            self.assertIn(expected, branch_review)
        # `[version]$numericPrefix` used to be required here. It only ever existed in the
        # block that discovered the Codex plugin's cache directory by sorting version
        # folders, which codex-delegate no longer does: reviews go through the native
        # `codex exec review`, and reaching into another plugin's internals is not a
        # contract worth pinning. The remaining tokens still prove the skill ships
        # concrete PowerShell rather than POSIX-only instructions.
        #
        # `Wait-Process` used to be required too, and passed for the wrong reason: the
        # skill stopped using it - PowerShell 5.1 can report `$null` as the `ExitCode` of
        # a `-PassThru` object that was not waited on directly - and now says so in a
        # *negative* sentence, which the token check happily matched. The replacements
        # name what the block actually does: redirect the two streams to files, wait in
        # place, and branch on the exit status. `.ExitCode` carries the leading dot on
        # purpose: prose discusses "the ExitCode", only code reads it off an object.
        for expected in (
            "```powershell", "$env:TEMP", "Start-Process", "-RedirectStandardOutput",
            "-Wait -PassThru", ".ExitCode", "try {", "finally {",
        ):
            self.assertIn(expected, codex_delegate)

    def test_evidence_first_review_defines_modes_and_read_only_contract(self) -> None:
        skill = self.read("skills/evidence-first-review/SKILL.md")
        for mode in ("initial", "recheck", "final-approval"):
            self.assertIn(f"`{mode}`", skill)
        for status in ("resolved", "partially resolved", "unresolved", "regressed"):
            self.assertIn(f"`{status}`", skill)
        self.assertIn("branch-merge-review", skill)
        self.assertIn("Do not create or modify files", skill)
        self.assertIn("Do not install tools", skill)
        self.assertIn("Do not create checkouts or worktrees", skill)
        self.assertIn("Do not stage changes", skill)
        self.assertIn("message only", skill)

    def test_safe_checkpoint_requires_explicit_write_authority(self) -> None:
        skill = self.read("skills/safe-checkpoint/SKILL.md")
        self.assertIn("Do not infer write authority", skill)
        self.assertIn("Create or update a handoff document", skill)
        self.assertIn("Stage and commit", skill)
        self.assertIn("Push to a remote", skill)
        self.assertIn("failed WIP checkpoint", skill)
        self.assertIn("`wip:`", skill)
        self.assertIn(".tasks/handoffs/YYYY-MM-DD-{slug}.md", skill)
        self.assertIn("runtime manifests", skill)
        self.assertIn("upstream synchronization", skill)

    def test_readable_ids_defines_the_registry_and_rendering_contract(self) -> None:
        skill = self.readable_ids_body()

        # Registry shape and the closed status vocabulary (SC-001). Pinned as a whole
        # sentence: the location of the registry is the contract, and an equality check
        # is the only form a reversal cannot be phrased around.
        self.assertContractBlock(
            skill,
            ".uniqid/{yyyy-mm-dd}-{slug}.md",
            "- One file per identifier set: `.uniqid/{yyyy-mm-dd}-{slug}.md` at the "
            "project root.",
        )
        for status in ("open", "in-progress", "done", "withdrawn"):
            self.assertIn(f"`{status}`", skill)

        # The rendering rule, and the constraint that keeps it readable (SC-002).
        self.assertContractBlock(
            skill,
            "Write `A1(feature/label)`",
            "Write `A1(feature/label)` — for example "
            "`C1(리뷰신뢰경계/신뢰상태-전달-누락)` — in:",
        )
        self.assertIn("full form on the first mention", skill)

        # A heading or an index line is reached without reading what precedes it, so the
        # short form cannot start there. Without this the report template - which spells
        # the full form in both the blocking-items line and every finding heading -
        # contradicts the rule it is supposed to follow.
        self.assertIn("Structural positions each count as a first mention", skill)

        # The threshold that stops the registry filling with dead rows, and the label
        # rules (SC-003). The slash ban matters because the slash is the separator.
        for threshold in (
            "another document will refer to it",
            "outlives one session or one report",
            "asked to decide something by that identifier",
        ):
            self.assertIn(threshold, skill)
        self.assertIn("no `/`", skill)

        # Lifecycle, sharing plan-and-build's vocabulary (SC-004). `feature` is pinned
        # alongside the label because both are rendered into references already read.
        self.assertIn("Never renumber and never reuse an identifier", skill)
        self.assertIn("A published label is fixed, and so is its `feature`", skill)

        # `feature` is rendered inside every identifier a person reads, so it needs the
        # label's format rules. Without this a `feature` carrying a space or a slash
        # produces a rendered form the separator can no longer be read out of.
        self.assertIn("the label rules above apply to it too", skill)

        # Dropping to the short form is only safe while it resolves to one thing.
        self.assertIn("two identifiers that share a short form", skill)

    def test_registering_is_separated_from_rendering_for_read_only_callers(self) -> None:
        """Registering writes a file; rendering does not. Conflating them breaks callers.

        Three of the six emitting documents run under a contract that forbids writing:
        evidence-first-review is read-only in every mode, branch-merge-review has a
        read-only priority rule, and safe-checkpoint refuses to infer write authority
        across its table. A first version of this wiring told all three to *register*
        identifiers, which each of them is forbidden to do - so the instruction was
        either ignored or obeyed in violation of the skill's own contract.
        """
        skill = self.readable_ids_body()
        self.assertIn("Registering is a workspace write; rendering is not", skill)
        # Writing, staging, and committing are three permissions, stated once here so
        # the callers stop each inventing their own answer - Codex found report-output,
        # safe-checkpoint, and this skill giving three different ones.
        # Pinned as a block rather than probed: this rule decides whether a review may
        # touch the working tree, and an assertIn over its phrases survived having the
        # rule rewritten around them.
        self.assertIn("Three permissions, and none of them implies the next", skill)
        # Delegation must not launder the prohibition: branch-merge-review hands its
        # report to report-output, and report-output is otherwise allowed to write.
        self.assertContractBlock(
            skill,
            "A review never registers",
            "**A review never registers, whoever ends up writing its report.** The "
            "prohibition follows the work, not the caller: `branch-merge-review` "
            "delegating a report file to `report-output` does not turn a review into "
            "something that may change the working tree, and permission to write *that* "
            "file is not permission to write this one.",
        )
        self.assertContractBlock(
            skill,
            "**Staging** is not part of writing",
            "1. **Writing the registry** follows the caller's authority to write files "
            "for this task. A caller already creating a plan or a report may create the "
            "registry beside it. Where the caller grants authority *per artifact* rather "
            "than per task — `safe-checkpoint` does, deliberately, so a checkpoint "
            "cannot absorb unrelated work — the registry is a separate artifact and "
            "needs its own permission. 2. **Staging** is not part of writing. Leave the "
            "file untracked unless the caller stages this task's output. 3. "
            "**Committing** is not part of staging. Where the caller has no standing "
            "permission to commit — an ordinary task has none — say the entry is "
            "uncommitted rather than committing it.",
        )

        # evidence-first-review may never write, in any mode.
        evidence = self.read("skills/evidence-first-review/SKILL.md")
        self.assertIn("Do not write its registry here", evidence)

        # branch-merge-review never writes the registry. Its delivery rule already
        # forbids a review from changing the working tree - for *every* review, not only
        # an explicitly read-only one - and an earlier version of this wiring carved out
        # only the read-only case, which left an ordinary PHP branch review free to add
        # `.uniqid/` files and commit candidates. Newlines are collapsed first: the
        # sentence is hard-wrapped, so a rewrap that changed nothing would fail.
        branch = " ".join(self.read("skills/branch-merge-review/SKILL.md").split())
        self.assertIn(
            "**Do not write its registry**: the delivery rule above forbids a review "
            "from changing the working tree, and that holds for every review",
            branch,
        )

        # report-output already refuses report files under the same constraint; the
        # rendering half has to survive it, or identifiers go bare exactly when the
        # report is the only output the user gets.
        self.assertIn(
            "Rendering needs no file, so it applies under the read-only rule above too",
            self.read("skills/report-output/SKILL.md"),
        )

        # safe-checkpoint's whole contract is that authority does not cross rows.
        self.assertIn(
            "is a separate write",
            self.read("skills/safe-checkpoint/references/handoff-template.md"),
        )

    def test_identifier_emitting_skills_point_at_readable_ids(self) -> None:
        """Every place that mints an identifier a person later reads must route here.

        Checked against the emitting document rather than the skill bundle: the
        consolidated report template and the handoff template are what a model has open
        while it writes the identifier down, so the pointer has to be in those files and
        not merely somewhere in their parent skill.

        Both halves are required. Naming the skill routes a machine that has it
        installed; carrying the rendered form `(feature/label)` is what keeps the
        identifier readable on a machine that does not, which is the majority case for a
        skill this repository has just added. An earlier version asserted the word
        "label" instead and proved nothing - "feature/label" contains it, so the check
        could not fail while the example was present.

        The block is then pinned verbatim. A negation probe was tried first and did not
        hold: Codex reversed these pointers with `Never invoke ...`, and probing further
        turned up "It is pointless to invoke", "Skip this:", and "This rule is obsolete."
        - none of which any vocabulary list reaches. Equality does, and each of these
        documents states its pointer in exactly one paragraph or list item.
        """
        for relative_path, expected in EMITTING_CONTRACT_BLOCKS.items():
            with self.subTest(relative_path=relative_path):
                document = instructional_text(self.read(relative_path))
                self.assertIn("readable-ids", document)
                self.assertContractBlock(document, "(feature/label)", expected)
                # Equality proves the words; it does not prove a reader sees them.
                # Wrapping the block in `<details>` or `<div hidden>` satisfied every
                # assertion above while removing the rule from the rendered document.
                assert_not_hidden(self, document, "(feature/label)", relative_path)

    def test_the_report_template_carries_the_readable_form_where_a_person_decides(
        self,
    ) -> None:
        """Asserted line by line against the template's fenced block.

        Two narrowings, each closing a measured bypass.

        The block, not the file: the block *is* the template - the shape a report takes.
        Against the whole file the same strings sitting in an HTML comment, or in the
        prose that explains the convention, satisfy every assertion while the template
        itself has gone back to bare identifiers. Codex demonstrated exactly that.

        Whole lines, not substrings: `assertIn` over the block text is satisfied by the
        string appearing *anywhere* in it, so Codex hid the expected form inside a
        `<template>` element and reverted the visible heading, and the check held.
        A line has to open with the heading for a reader to arrive at it.
        """
        blocks = fenced_blocks(
            self.read("skills/branch-merge-review/references/consolidated-report-template.md")
        )
        self.assertEqual(len(blocks), 1)
        template = blocks[0]

        # A container that hides its contents from the reader would let the pinned lines
        # live somewhere no one sees while the visible template reverted. Codex did
        # exactly that with a multi-line `<template>`, and then again with `<div hidden>`.
        self.assertEqual(
            hiding_ancestors(INLINE_CODE.sub(lambda m: " " * len(m.group(0)), template)),
            [],
            "report template leaves a hiding element open",
        )
        for tag in HIDING_TAGS:
            self.assertNotRegex(template, rf"(?i)<\s*{tag}\b")

        # A nested fence turns everything after it into a code sample rather than part
        # of the template. The outer fence is ```, so a ~~~ or a longer ``` run inside it
        # is content to fenced_blocks() and a code block to a reader - two different
        # answers, which is the gap.
        self.assertNotRegex(template, r"(?m)^\s*(?:~{3,}|`{3,})")

        # Indentation is *not* stripped. CommonMark makes four spaces (or a tab) an
        # indented code block, so `    ### [CH-1(feature/label)]` renders as a sample of
        # a heading rather than as one - and line.strip() turned exactly that into a
        # satisfied assertion. Up to three spaces stays an ordinary line.
        lines = template.splitlines()

        def opening_with(prefix: str) -> list[str]:
            return [
                line
                for line in lines
                if re.match(r"^ {0,3}(?![ \t])", line) and line.lstrip(" ").startswith(prefix)
            ]

        # The blocking-items line *is* the decision request, and each finding heading is
        # the definition site a later recheck refers back to. Both are entry points a
        # reader reaches without reading forward, so both carry the full form. Exactly
        # one of each: a second copy is either a decoy or a template with two answers.
        self.assertEqual(len(opening_with("**Blocking items**: [CH-1(feature/label)")), 1)
        self.assertEqual(len(opening_with("### [CH-1(feature/label)]")), 1)

        # The bare spellings must not come back, in any whitespace. `\s` rather than a
        # literal space: a tab after `[CH-1]` used to slip through.
        for bare in (r"\*\*Blocking items\*\*:\s*\[CH-1[,\]\s]", r"###\s*\[CH-1\]"):
            self.assertNotRegex(template, bare)

    def test_new_skills_have_only_the_approved_files(self) -> None:
        expected = {
            "evidence-first-review": {
                "SKILL.md",
                "agents/openai.yaml",
                "references/report-format.md",
            },
            "safe-checkpoint": {
                "SKILL.md",
                "agents/openai.yaml",
                "references/handoff-template.md",
            },
            "readable-ids": {
                "SKILL.md",
                "agents/openai.yaml",
                "references/registry-format.md",
            },
        }
        for skill_name, expected_files in expected.items():
            with self.subTest(skill_name=skill_name):
                skill_dir = ROOT / "skills" / skill_name
                actual_files = {
                    # as_posix(), not str(): on native Windows str() yields
                    # `agents\openai.yaml` and the comparison below fails.
                    path.relative_to(skill_dir).as_posix()
                    for path in skill_dir.rglob("*")
                    if path.is_file()
                }
                self.assertEqual(actual_files, expected_files)

    def test_new_skills_have_direct_default_prompts(self) -> None:
        for skill_name in ("evidence-first-review", "safe-checkpoint", "readable-ids"):
            with self.subTest(skill_name=skill_name):
                metadata = self.read(f"skills/{skill_name}/agents/openai.yaml")
                self.assertIn(f"${skill_name}", metadata)

    def test_new_skills_are_registered_symmetrically(self) -> None:
        catalog = json.loads(self.read("components.json"))
        install = self.read("install.sh")
        uninstall = self.read("uninstall.sh")

        for skill_name in ("evidence-first-review", "safe-checkpoint", "readable-ids"):
            with self.subTest(skill_name=skill_name):
                matches = [
                    component
                    for component in catalog["components"]
                    if component["kind"] == "skill"
                    and component["name"] == skill_name
                ]
                self.assertEqual(len(matches), 1)
                component = matches[0]
                self.assertEqual(
                    component["source"],
                    f"skills/{skill_name}",
                )
                for client in ("claude", "codex"):
                    self.assertEqual(
                        component["support"][client],
                        {"posix": True, "windows": True},
                    )

        for script in (install, uninstall):
            self.assertIn("catalog_names skill claude", script)
            self.assertIn("catalog_names skill codex", script)


class SkillReferenceIntegrityTest(SkillReadingMixin, unittest.TestCase):
    """read_skill_dir()'s three structural checks, applied to every shipped skill.

    The contract tests above only reach read_skill() for the two skills whose text they
    assert on, so ten of the twelve skills could acquire a broken pointer, an orphaned
    reference document or a path escaping the skill directory without anything failing.
    Discovery is by glob rather than a hardcoded list, so a new skill is covered the
    moment it ships a SKILL.md.
    """

    def skill_dirs(self) -> list[Path]:
        skill_dirs = sorted(path.parent for path in (ROOT / "skills").glob("*/SKILL.md"))
        # A typo in the glob, or a rename of skills/, would otherwise turn this whole
        # class into a silent no-op that reports as passing.
        self.assertGreaterEqual(len(skill_dirs), 12, "skills/ discovery found too few")
        return skill_dirs

    def test_every_skill_resolves_its_own_references(self) -> None:
        for skill_dir in self.skill_dirs():
            with self.subTest(skill=skill_dir.name):
                self.read_skill_dir(skill_dir)

    def test_the_html_report_template_is_a_checked_reference(self) -> None:
        # The concrete non-Markdown asset that motivated widening the existence check:
        # skills/report-output/SKILL.md calls it the skeleton every HTML report starts
        # from, but a `*.md`-only scan never noticed whether it was still there.
        links = reference_links(self.read("skills/report-output/SKILL.md"))
        self.assertIn("references/report-template.html", links)
        self.assertTrue(
            (ROOT / "skills/report-output/references/report-template.html").is_file()
        )


class SkillReferenceLinkTest(SkillReadingMixin, unittest.TestCase):
    """Boundary conditions of the reference-link extraction read_skill() depends on.

    These build a throwaway skill directory instead of reading skills/, so they pin the
    helper's own behaviour and stay stable while the real skills are edited.
    """

    def make_skill(self, body: str, *references: str) -> Path:
        """A temp skill directory holding `body` as SKILL.md plus empty `references`."""
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        skill_dir = Path(temp_dir.name) / "fake-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")
        for relative_path in references:
            reference = skill_dir / relative_path
            reference.parent.mkdir(parents=True, exist_ok=True)
            reference.write_text(f"content of {relative_path}\n", encoding="utf-8")
        return skill_dir

    def test_only_paths_ending_in_md_are_links(self) -> None:
        cases = {
            "[x](references/foo.mdx)": [],
            "[x](references/foo.md.bak)": [],
            "[x](references/foo.md.txt)": [],
            "[x](references/foo.md)": ["references/foo.md"],
            "`references/foo.bar.md`": ["references/foo.bar.md"],
            "[x](references/nested/deep.md)": ["references/nested/deep.md"],
            "[x](references/foo.md#step-2)": ["references/foo.md"],
            "Read references/foo.md. Then stop.": ["references/foo.md"],
        }
        for body, expected in cases.items():
            with self.subTest(body=body):
                self.assertEqual(reference_links(body), expected)

    def test_text_continuing_the_name_or_path_after_md_is_not_a_link(self) -> None:
        # `.md` followed by a name character was already rejected; these are the two
        # remaining continuations, a hyphenated suffix and a further path segment.
        cases = {
            "[x](references/foo.md-bak)": [],
            "[x](references/foo.md/extra)": [],
            "`references/foo.md-`": [],
            # Still links: the continuation itself ends at `.md`, or is punctuation that
            # cannot be part of a path.
            "[x](references/foo.md-bak.md)": ["references/foo.md-bak.md"],
            "[x](references/foo.md/extra.md)": ["references/foo.md/extra.md"],
            "See [x](references/foo.md), then stop.": ["references/foo.md"],
        }
        for body, expected in cases.items():
            with self.subTest(body=body):
                self.assertEqual(reference_links(body), expected)

    # A link destination is the whole path, so each of these names something other than
    # `references/foo.md` - yet the body-text rules truncate or shave every one of them to
    # exactly that.
    TRUNCATED_DESTINATIONS = (
        # A trailing period ends a sentence in prose; inside parentheses it is part of the
        # filename, and `foo.md.` is not `foo.md`.
        "references/foo.md.",
        "references/foo.md..",
        # `%2F` is an encoded separator: the target is a path *inside* foo.md.
        "references/foo.md%2Fextra",
        # Drive-relative on Windows: resolved against the current directory of drive C:,
        # which is not this skill directory.
        "C:references/foo.md",
        # A URI scheme, not a relative path.
        "file:references/foo.md",
        # The same trap reached through the extension boundary.
        "references/foo.mdx",
        "references/foo.md-bak",
        "references/foo.md/extra",
    )

    # Both label spellings, because the destination rules must stand on their own.
    #
    # `[foo](...)` was the only spelling these cases were written in, and that is why the
    # bypass survived a round of review: with the label left in the body text, a label
    # that is not a path yields nothing either way, so the test passed for the wrong
    # reason. Every link in this repository is spelled the second way - the path appears
    # in the label *as well* - and under that spelling a rejected destination used to be
    # handed straight back to the looser body rules and accepted.
    LABEL_SPELLINGS = ("foo", "references/foo.md")

    def broken_destination_bodies(self) -> list[str]:
        return [
            f"Read [{label}]({destination})\n"
            for destination in self.TRUNCATED_DESTINATIONS
            for label in self.LABEL_SPELLINGS
        ]

    def test_broken_link_destinations_are_not_truncated_into_valid_paths(self) -> None:
        for body in self.broken_destination_bodies():
            with self.subTest(body=body):
                self.assertEqual(reference_links(body), [])

    def test_a_broken_destination_cannot_borrow_a_neighbouring_file(self) -> None:
        # The practical danger, reproduced: with a real `references/foo.md` next door,
        # truncating the destination made the existence check pass *and* stopped foo.md
        # looking orphaned, so a broken pointer produced no failure whatsoever. Now the
        # destination counts for nothing and foo.md is correctly reported unreachable.
        for body in self.broken_destination_bodies():
            with self.subTest(body=body):
                skill_dir = self.make_skill(body, "references/foo.md")
                with self.assertRaises(AssertionError) as caught:
                    self.read_skill_dir(skill_dir)
                self.assertIn("never points at", str(caught.exception))
                self.assertIn("references/foo.md", str(caught.exception))

    def test_a_path_written_only_in_a_link_label_is_not_a_reference(self) -> None:
        # The rule the masking rests on, stated on its own: a label names the link for a
        # reader, a destination routes the model to a file. Here the destination is a URL,
        # so nothing local is pointed at however the link is captioned - and the local
        # foo.md is correctly reported unreachable rather than credited to the label.
        body = "Read [references/foo.md](https://example.com/guide).\n"
        self.assertEqual(reference_links(body), [])
        skill_dir = self.make_skill(body, "references/foo.md")
        with self.assertRaises(AssertionError) as caught:
            self.read_skill_dir(skill_dir)
        self.assertIn("never points at", str(caught.exception))
        self.assertIn("references/foo.md", str(caught.exception))

    def test_the_repositorys_own_link_spelling_still_resolves(self) -> None:
        # The other side of the masking: `[references/foo.md](references/foo.md)` is how
        # every link in skills/ is written, and it must keep resolving on the strength of
        # its destination alone.
        body = "See [references/foo.md](references/foo.md) for the details.\n"
        self.assertEqual(reference_links(body), ["references/foo.md"])
        skill_dir = self.make_skill(body, "references/foo.md")
        self.assertIn("content of references/foo.md", self.read_skill_dir(skill_dir))

    def test_a_sentence_ending_period_still_closes_a_body_path(self) -> None:
        # The tolerance the destination rules drop must survive in body text, which is
        # where it was introduced: prose and inline code end sentences with a period.
        cases = {
            "Read references/foo.md.": ["references/foo.md"],
            "Read `references/foo.md`.": ["references/foo.md"],
            "Read references/foo.md. Then stop.": ["references/foo.md"],
            "See references/foo.md, references/bar.md.": [
                "references/bar.md",
                "references/foo.md",
            ],
            # The label of a link is body text too, and this is the spelling most of this
            # repository's SKILL.md files use.
            "[references/foo.md](references/foo.md)": ["references/foo.md"],
        }
        for body, expected in cases.items():
            with self.subTest(body=body):
                self.assertEqual(reference_links(body), expected)

        # ... and it still resolves end to end, not just in the extractor.
        skill_dir = self.make_skill("Read references/foo.md.\n", "references/foo.md")
        self.assertIn("content of references/foo.md", self.read_skill_dir(skill_dir))

    def test_non_markdown_reference_assets_must_exist(self) -> None:
        skill_dir = self.make_skill("Start from `references/template.html`.\n")
        with self.assertRaises(AssertionError) as caught:
            self.read_skill_dir(skill_dir)
        self.assertIn("does not exist", str(caught.exception))
        self.assertIn("references/template.html", str(caught.exception))

    def test_a_linked_non_markdown_asset_is_read_and_not_an_orphan(self) -> None:
        for body in (
            "Start from `references/template.html`.\n",
            "Start from [t](references/template.html).\n",
        ):
            with self.subTest(body=body):
                skill_dir = self.make_skill(body, "references/template.html")
                self.assertIn(
                    "content of references/template.html",
                    self.read_skill_dir(skill_dir),
                )

    def test_an_unlinked_non_markdown_asset_is_an_orphan(self) -> None:
        skill_dir = self.make_skill("No pointers here.\n", "references/template.html")
        with self.assertRaises(AssertionError) as caught:
            self.read_skill_dir(skill_dir)
        self.assertIn("never points at", str(caught.exception))
        self.assertIn("references/template.html", str(caught.exception))

    def test_extensions_outside_the_allowlist_are_neither_links_nor_orphans(self) -> None:
        # The other side of the allowlist: an unlisted extension is not a pointer, so
        # prose mentioning one demands nothing, and a shipped file of that kind is not
        # required to be linked from SKILL.md - see read_skill()'s docstring.
        self.assertEqual(reference_links("Patterns live in `references/x.php`.\n"), [])
        skill_dir = self.make_skill("No pointers here.\n", "references/logo.png")
        self.assertEqual(self.read_skill_dir(skill_dir), "No pointers here.\n")

    def test_a_truncated_hyphen_suffix_link_no_longer_hides_an_orphan(self) -> None:
        # Same trap as the .mdx case below, reached through the other boundary: the
        # pointer is broken, but truncating it to `references/foo.md` used to satisfy the
        # existence check and make the real foo.md look linked.
        body = "Read [foo](references/foo.md-bak).\n"
        skill_dir = self.make_skill(body, "references/foo.md")
        self.assertEqual(reference_links(body), [])
        with self.assertRaises(AssertionError) as caught:
            self.read_skill_dir(skill_dir)
        self.assertIn("never points at", str(caught.exception))
        self.assertIn("references/foo.md", str(caught.exception))

    def test_a_broken_mdx_link_no_longer_resolves_to_the_neighbouring_md_file(
        self,
    ) -> None:
        # The regression that motivated the right-hand boundary: the pointer is broken,
        # but the truncated `references/foo.md` existed, so both structural checks used
        # to pass. Now nothing is linked, and foo.md is correctly reported unreachable.
        skill_dir = self.make_skill(
            "Read [foo](references/foo.mdx).\n", "references/foo.md"
        )
        self.assertEqual(reference_links("Read [foo](references/foo.mdx).\n"), [])
        with self.assertRaises(AssertionError) as caught:
            self.read_skill_dir(skill_dir)
        self.assertIn("never points at", str(caught.exception))
        self.assertIn("references/foo.md", str(caught.exception))

    def test_dot_slash_prefixed_links_are_followed(self) -> None:
        self.assertEqual(
            reference_links("Read [foo](./references/foo.md).\n"),
            ["./references/foo.md"],
        )
        skill_dir = self.make_skill(
            "Read [foo](./references/foo.md).\n", "references/foo.md"
        )
        self.assertIn("content of references/foo.md", self.read_skill_dir(skill_dir))

    def test_the_same_reference_spelled_two_ways_is_read_once(self) -> None:
        skill_dir = self.make_skill(
            "Read [foo](./references/foo.md) - that is `references/foo.md`.\n",
            "references/foo.md",
        )
        joined = self.read_skill_dir(skill_dir)
        self.assertEqual(joined.count("content of references/foo.md"), 1)

    def test_navigating_path_segments_are_not_links(self) -> None:
        # A segment that is exactly `.` or `..` navigates rather than names, and every
        # reference this repository ships sits under references/. Both notations, because
        # the destination rules and the body rules have to agree here.
        cases = {
            "[x](references/../outside.md)": [],
            "Read `references/../outside.md` first.": [],
            "Read references/../outside.md first.": [],
            "[x](references/../../other/a.md)": [],
            "[x](references/foo/../bar.md)": [],
            "[x](references/./foo.md)": [],
            "Read `references/./foo.md` first.": [],
            # ... while a period *inside* a name is an ordinary filename character, so
            # these stay links: the guard is about whole segments, not about dots.
            "[x](references/..md)": ["references/..md"],
            "[x](references/.hidden.md)": ["references/.hidden.md"],
            "`references/foo.bar.md`": ["references/foo.bar.md"],
        }
        for body, expected in cases.items():
            with self.subTest(body=body):
                self.assertEqual(reference_links(body), expected)

    def test_a_dot_dot_segment_cannot_borrow_a_file_outside_references(self) -> None:
        # Why the segment rule has to live in the regex, and why the containment
        # assertion could not have caught this: `references/../outside.md` resolves to
        # `<skill>/outside.md`, which is *inside* the skill directory, so containment
        # passed. The pointer climbed out of references/ and claimed a file SKILL.md never
        # routes to through references/ - existence passed, and outside.md stopped looking
        # orphaned. Now it is not a link at all and outside.md is reported unreachable.
        body = "Read [references/foo.md](references/../outside.md).\n"
        skill_dir = self.make_skill(body, "outside.md")
        self.assertTrue((skill_dir / "references/../outside.md").resolve().is_file())

        self.assertEqual(reference_links(body), [])
        with self.assertRaises(AssertionError) as caught:
            self.read_skill_dir(skill_dir)
        self.assertIn("never points at", str(caught.exception))
        self.assertIn("outside.md", str(caught.exception))

    def test_links_escaping_the_skill_directory_fail(self) -> None:
        # The containment assertion's remaining job now that `..` cannot be written: an
        # escape that no path can show, because it lives in the filesystem. references/ is
        # a symlink out of the skill, so the perfectly ordinary `references/a.md` resolves
        # somewhere the installer would never copy.
        skill_dir = self.make_skill("Read [a](references/a.md).\n")
        outside = skill_dir.parent / "other"
        outside.mkdir()
        (outside / "a.md").write_text("content of a.md\n", encoding="utf-8")
        try:
            (skill_dir / "references").symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError) as error:  # unprivileged Windows
            self.skipTest(f"symlinks unavailable: {error}")
        self.assertTrue((skill_dir / "references/a.md").resolve().is_file())

        with self.assertRaises(AssertionError) as caught:
            self.read_skill_dir(skill_dir)
        self.assertIn("leaves the skill directory", str(caught.exception))

    def test_other_skills_reference_paths_are_not_this_skills_links(self) -> None:
        for body in (
            "**Security patterns** (from `web-security-review/references/x.md`)",
            "See `../references/shared.md`",
            "See `my-references/x.md`",
        ):
            with self.subTest(body=body):
                self.assertEqual(reference_links(body), [])

    def test_prefixed_paths_are_not_links(self) -> None:
        # The left boundary used to stop at `/` and `\`, so a prefix ending in `:` was
        # simply shaved off and the remainder matched as the bare local path. Each of
        # these names something that is not this skill's `references/foo.md`: a file on
        # drive C:'s current directory, a URI, a document on a web server.
        for body in (
            "Read `C:references/foo.md` first.",
            "Read C:references/foo.md first.",
            "Read `file:references/foo.md` first.",
            "Read file:references/foo.md first.",
            "See https://example.com/references/foo.md",
            # `%2F` is an encoded separator, so the target is inside foo.md - the same
            # rejection the destination pass makes, now made in body text too.
            "Read `references/foo.md%2Fextra` first.",
        ):
            with self.subTest(body=body):
                self.assertEqual(reference_links(body), [])

    def test_a_prefixed_body_path_cannot_borrow_a_neighbouring_file(self) -> None:
        # The same danger as the broken destinations, reached through inline code rather
        # than a link: shaving `C:` off left `references/foo.md`, which exists here, so
        # a drive-relative pointer satisfied every check and cleared the orphan report.
        for body in (
            "Read `C:references/foo.md` first.\n",
            "Read `file:references/foo.md` first.\n",
        ):
            with self.subTest(body=body):
                skill_dir = self.make_skill(body, "references/foo.md")
                with self.assertRaises(AssertionError) as caught:
                    self.read_skill_dir(skill_dir)
                self.assertIn("never points at", str(caught.exception))
                self.assertIn("references/foo.md", str(caught.exception))

    def test_backslash_separated_paths_are_not_links(self) -> None:
        # A backslash is a path separator on Windows but not in Markdown, and no SKILL.md
        # here spells one. All three shapes must come back empty: the two mixed ones
        # because their leading segments must not be shaved off (see the two tests
        # below), the fully-backslashed one because that notation is not adopted at all.
        for body in (
            r"See `..\references\foo.md`",
            r"See `other-skill\references\foo.md`",
            r"See `references\foo.md`",
            # The mixed spellings are the ones that used to slip through.
            r"See `..\references/foo.md`",
            r"See `other-skill\references/foo.md`",
            r"See `..\..\references/foo.md`",
            r"[x](..\references/foo.md)",
            r"See `C:\skills\other\references/foo.md`",
            # `.md` continued by a Windows segment is a truncation trap of the same kind
            # as `references/foo.md/extra`.
            r"See `references/foo.md\extra`",
        ):
            with self.subTest(body=body):
                self.assertEqual(reference_links(body), [])

    def test_a_backslash_escape_path_cannot_pose_as_a_local_reference(self) -> None:
        # The practical danger, reproduced: the pointer leaves the skill, but shaving
        # `..\` off left the bare `references/foo.md`, which exists here. Containment and
        # existence both passed and foo.md stopped looking orphaned, so a pointer to a
        # file outside the skill was reported as a healthy local link.
        body = "Read [foo](..\\references/foo.md).\n"
        skill_dir = self.make_skill(body, "references/foo.md")
        # Make the real escape target exist too, so nothing here is merely missing.
        outside = skill_dir.parent / "references"
        outside.mkdir()
        (outside / "foo.md").write_text("content of escaped foo.md\n", encoding="utf-8")

        self.assertEqual(reference_links(body), [])
        with self.assertRaises(AssertionError) as caught:
            self.read_skill_dir(skill_dir)
        self.assertIn("never points at", str(caught.exception))
        self.assertIn("references/foo.md", str(caught.exception))

    def test_a_backslash_cross_skill_path_cannot_pose_as_a_local_reference(self) -> None:
        # Same disguise through the other shape: `other-skill\references/foo.md` names
        # another skill's document, but shaving the first segment made it satisfy this
        # skill's contract against the local file of the same name.
        body = "Read [foo](other-skill\\references/foo.md).\n"
        skill_dir = self.make_skill(body, "references/foo.md")
        self.assertEqual(reference_links(body), [])
        with self.assertRaises(AssertionError) as caught:
            self.read_skill_dir(skill_dir)
        self.assertIn("never points at", str(caught.exception))
        self.assertIn("references/foo.md", str(caught.exception))

    def test_a_backslash_spelled_local_reference_is_reported_as_an_orphan(self) -> None:
        # The deliberate consequence of not normalising `references\foo.md`: the file is
        # shipped but nothing points at it, so the author is told to respell the link
        # with `/` rather than having a second notation quietly accepted.
        skill_dir = self.make_skill(
            "Read [foo](references\\foo.md).\n", "references/foo.md"
        )
        with self.assertRaises(AssertionError) as caught:
            self.read_skill_dir(skill_dir)
        self.assertIn("never points at", str(caught.exception))
        self.assertIn("references/foo.md", str(caught.exception))

    def test_paths_inside_html_comments_are_not_links(self) -> None:
        self.assertEqual(reference_links("<!-- references/ghost.md -->\n"), [])
        self.assertEqual(
            reference_links("<!--\nold: references/ghost.md\n-->\n"), []
        )
        # A real pointer next to a commented-out one still counts.
        self.assertEqual(
            reference_links("<!-- references/ghost.md -->\nRead `references/real.md`\n"),
            ["references/real.md"],
        )

    def test_paths_inside_fenced_code_blocks_are_not_links(self) -> None:
        body = (
            "Read `references/real.md`.\n"
            "\n"
            "```bash\n"
            "cat references/example.md\n"
            "```\n"
            "\n"
            "    ~~~\n"
            "    cat references/tilde.md\n"
            "    ~~~\n"
        )
        self.assertEqual(reference_links(body), ["references/real.md"])

    def test_a_fence_line_carrying_text_does_not_close_the_block(self) -> None:
        # ```` ```not-a-close ```` used to end the block, so the example command below it
        # was read as an instruction. CommonMark allows nothing but whitespace after a
        # closing fence.
        body = (
            "Read `references/real.md`.\n"
            "\n"
            "```bash\n"
            "```not-a-close\n"
            "cat references/example.md\n"
            "```\n"
        )
        self.assertEqual(reference_links(body), ["references/real.md"])

    def test_only_a_matching_fence_of_sufficient_length_closes_the_block(self) -> None:
        cases = {
            # A shorter run of the same character does not close a longer opening fence.
            "````\n```\ncat references/short.md\n````\n": [],
            # Nor does the other fence character.
            "```\n~~~\ncat references/tilde.md\n```\n": [],
            # A longer run does close it, and trailing whitespace is allowed.
            "```\ncat references/inside.md\n`````   \nRead `references/after.md`\n": [
                "references/after.md"
            ],
        }
        for body, expected in cases.items():
            with self.subTest(body=body):
                self.assertEqual(reference_links(body), expected)

    def test_orphan_paths_are_reported_in_posix_notation(self) -> None:
        # Guards a Windows-only regression: str(Path) spells the nested path
        # `references\nested\deep.md` there, which neither matches this expectation nor
        # matches how SKILL.md writes the path. Passes either way on POSIX.
        skill_dir = self.make_skill("No pointers here.\n", "references/nested/deep.md")
        with self.assertRaises(AssertionError) as caught:
            self.read_skill_dir(skill_dir)
        message = str(caught.exception)
        self.assertIn("references/nested/deep.md", message)
        self.assertNotIn("\\", message)

    def test_a_missing_reference_fails_even_when_nothing_is_orphaned(self) -> None:
        skill_dir = self.make_skill("Read `references/gone.md`.\n")
        with self.assertRaises(AssertionError) as caught:
            self.read_skill_dir(skill_dir)
        self.assertIn("does not exist", str(caught.exception))


class InstructionSenseHelperTest(SkillReadingMixin, unittest.TestCase):
    """Tests for the checkers that decide whether a pinned instruction still instructs.

    These exist because the contracts above were, for one round, satisfied by documents
    saying the opposite of what they pin. A checker written to catch that is worth
    exactly as much as its own coverage, so its boundaries are tested here rather than
    assumed.
    """

    def test_a_hard_wrapped_sentence_is_not_split_at_the_line_break(self) -> None:
        # Every SKILL.md in this repository wraps prose. Treating `\n` as a boundary
        # would put the negation and the instruction in different "sentences" and let an
        # inverted document pass.
        text = "Do not\n  write `A1(feature/label)` here."
        self.assertEqual(
            sentences_containing(text, "write `A1(feature/label)`"),
            [
            "Do not write `A1(feature/label)` here."],
        )

    def test_a_blank_line_ends_the_sentence(self) -> None:
        text = "Never do this.\n\nWrite `A1(feature/label)` instead-of-nothing."
        self.assertEqual(
            sentences_containing(text, "Write `A1(feature/label)`"),
            [
            "Write `A1(feature/label)` instead-of-nothing."],
        )

    def test_a_preceding_sentence_negation_is_not_borrowed(self) -> None:
        # The neighbouring sentence is allowed to be negative - these documents pair an
        # instruction with its exception on purpose.
        text = "Do not create the registry. Write `A1(feature/label)` inline."
        self.assertEqual(
            sentences_containing(text, "Write `A1(feature/label)`"),
            [
            "Write `A1(feature/label)` inline."],
        )

    def test_every_occurrence_is_returned_not_just_the_first(self) -> None:
        """The hole Codex found: an explanatory first mention shielding a reversed one.

        `text.index()` stopped at the first match, so leaving one clean occurrence in
        place let a second be inverted with the contract still green.
        """
        text = "Write `A1(x/y)` in reports. Do not Write `A1(x/y)` in code."
        self.assertEqual(
            sentences_containing(text, "Write `A1(x/y)`"),
            ["Write `A1(x/y)` in reports.", "Do not Write `A1(x/y)` in code."],
        )
        with self.assertRaises(AssertionError):
            self.assertPositiveInstruction(text, "Write `A1(x/y)`")

    def test_a_contract_block_rejects_any_rewrite_of_itself(self) -> None:
        expected = "Write `A1(x/y)` in reports."
        self.assertContractBlock("Write `A1(x/y)` in reports.", "`A1(x/y)`", expected)
        for rewritten in (
            "It is forbidden to Write `A1(x/y)` in reports.",   # a synonym the net misses
            "In reports, Write `A1(x/y)`.",                     # harmless, still flagged
            "Write `A1(x/y)` in reports and nowhere else.",
            "Ignore what follows. Write `A1(x/y)` in reports.",  # the sentence-scope hole
        ):
            with self.subTest(rewritten=rewritten):
                with self.assertRaises(AssertionError):
                    self.assertContractBlock(rewritten, "`A1(x/y)`", expected)

    def test_the_negation_pattern_matches_what_an_inverting_edit_writes(self) -> None:
        for phrase in (
            "Do not write it",
            "does not write it",
            "Never write it",
            "must not write it",
            "shall not write it",
            "no longer write it",
            "render it instead of writing it",
            "don't write it",
        ):
            with self.subTest(phrase=phrase):
                self.assertIsNotNone(INVERTING_NEGATION.search(phrase))

    def test_the_negation_pattern_ignores_ordinary_prose(self) -> None:
        """Bare `not` and `no` are excluded, and that exclusion is the point.

        All four of these sit in the very sentences the contracts pin. A checker that
        fired on them would be switched off rather than fixed, so the narrow set is a
        deliberate trade: it catches the inversions an editor actually writes and stays
        quiet on the prose these documents are made of.
        """
        for phrase in (
            "`CH-1` alone is not enough",
            "carries no meaning for the reader",
            "someone who does not yet know",       # `does not` *is* caught - see below
            "render the labels inline and create no registry",
        ):
            with self.subTest(phrase=phrase):
                matched = INVERTING_NEGATION.search(phrase)
                expected = "does not" in phrase
                self.assertEqual(matched is not None, expected)

    def test_a_list_item_is_its_own_block(self) -> None:
        text = "- first item here\n- second `A1(x/y)` item\n- third item\n"
        self.assertEqual(block_containing(text, "`A1(x/y)`"), ["- second `A1(x/y)` item"])

    def test_a_paragraph_is_one_block_across_hard_wraps(self) -> None:
        text = "opening line\n  continues `A1(x/y)` here\n\nnext paragraph\n"
        self.assertEqual(
            block_containing(text, "`A1(x/y)`"), ["opening line continues `A1(x/y)` here"]
        )

    def test_fenced_blocks_returns_the_block_and_not_its_surroundings(self) -> None:
        markdown = (
            "prose before\n"
            "<!-- ### [CH-1(feature/label)] hidden in a comment -->\n"
            "```\n"
            "### [CH-1(feature/label)] Finding Title\n"
            "```\n"
            "prose after\n"
        )
        blocks = fenced_blocks(markdown)
        self.assertEqual(blocks, ["### [CH-1(feature/label)] Finding Title"])

    def test_a_fence_line_carrying_text_does_not_close_the_block(self) -> None:
        markdown = "```\nkept\n```not-a-close\nalso kept\n```\n"
        self.assertEqual(fenced_blocks(markdown), ["kept\n```not-a-close\nalso kept"])

    def test_hiding_ancestors_matches_what_html_actually_hides(self) -> None:
        """Both directions, because every earlier version was wrong in both.

        Codex found each of these by construction; they are pinned here so a later
        tightening of the checker cannot quietly reintroduce one.
        """
        hides = {
            "<template>": ["template"],
            "<script>": ["script"],
            "<details>": ["details"],
            '<div hidden>': ["div"],
            '<div hidden="false">': ["div"],        # boolean attribute: presence hides
            '<div aria-hidden="true">': ["div"],
            '<div title="a > b" hidden>': ["div"],  # quoted `>` does not end the tag
            "<details><summary>t</summary>": ["details"],
            "<details open hidden>": ["details"],   # `open` does not undo `hidden`
            '<details class="x open y">': ["details"],   # a value is not an attribute
            # A summary cancels *its own* details and nothing above it.
            "<div hidden><details><summary>": ["div"],
            "<template><details><summary>": ["template"],
        }
        shows = (
            "<details open>",                       # renders expanded
            "<details><summary>",                   # the summary is the click target
            '<div aria-hidden="false">',
            '<div data-hidden="false">',
            '<div class="not-hidden">',
            '<div style="display:none">',           # inline CSS is out of scope, stated
            "<div>visible</div>\n<div>",             # a closed div cancels nothing
            '<span aria-hidden="true">x</span>',    # closed: no longer an ancestor
            "<br>\n<img src=x>",                    # void elements open nothing
            '<span aria-hidden="true"/>',           # self-closing opens nothing
            "<details><div>a</div></details>",      # popped by name
        )
        for markup, expected in hides.items():
            with self.subTest(markup=markup):
                self.assertEqual(hiding_ancestors(markup), expected)
        for markup in shows:
            with self.subTest(markup=markup):
                self.assertEqual(hiding_ancestors(markup), [])

    def test_a_table_opens_only_on_a_header_and_a_matching_separator(self) -> None:
        """Each half was a fail-open alone; both are required together.

        A separator with nothing above it opened a body out of nowhere, and any pipe
        line above a separator was taken for a header - so a data row parked in the
        header position vanished from every check below.
        """
        registry = UniqidRegistryTest("test_every_row_uses_the_closed_status_vocabulary")
        header = UniqidRegistryTest.HEADER
        good = f"{header}\n|----|----|----|----|\n| A-1 | 표식 | 설명 | open |\n"
        self.assertEqual(registry.rows(good), [["A-1", "표식", "설명", "open"]])

        for name, bad in {
            "separator with no header": "\n|----|----|----|----|\n| A-1 | 표식 | 설명 | open |\n",
            "data row in the header position": (
                "| A-1 | 표식 | 설명 | open |\n|----|----|----|----|\n"
                "| A-2 | 다른표식 | 설명 | open |\n"
            ),
            "separator narrower than the header": (
                f"{header}\n|----|----|\n| A-1 | 표식 | 설명 | open |\n"
            ),
            "header with no separator": f"{header}\n\n프롤로그 문단.\n",
            "escaped pipe outside the body": (
                f"{good}\n표 밖에서 A-9 \\| 표식 \\| 설명 \\| open\n"
            ),
        }.items():
            with self.subTest(name=name):
                with self.assertRaises(AssertionError):
                    registry.rows(bad)

    def test_the_table_separator_is_not_a_thematic_break(self) -> None:
        separator = UniqidRegistryTest.SEPARATOR
        for line in ("|---|---|", "| --- | --- |", "---|---", "| :--- | ---: |"):
            with self.subTest(line=line):
                self.assertRegex(line, separator)
        # A bare run of dashes is a horizontal rule and a frontmatter fence. Reading one
        # as a table separator turned every following paragraph into a malformed row.
        for line in ("---", "----", "- - -", ": --- :", ""):
            with self.subTest(line=line):
                self.assertNotRegex(line, separator)

    def test_assert_positive_instruction_rejects_an_inverted_sentence(self) -> None:
        with self.assertRaises(AssertionError) as caught:
            self.assertPositiveInstruction(
                "Do not write `A1(feature/label)` anywhere.", "write `A1(feature/label)`"
            )
        self.assertIn("inverted", str(caught.exception))

    def test_the_known_limits_of_the_checker_are_the_ones_documented(self) -> None:
        """Pins both holes, so a later reader finds them measured rather than assumed.

        A test that records a limit is worth more than a docstring alone: if someone
        closes one of these, this test fails and forces the docstring to be corrected
        with it.
        """
        # assertPositiveInstruction is sentence-scoped, so a negation one sentence back
        # is out of its window. This is why the two blocks that *are* the contract use
        # assertContractBlock instead, which catches exactly this - see below.
        self.assertPositiveInstruction(
            "The following is prohibited. Write `A1(feature/label)` here.",
            "Write `A1(feature/label)`",
            sentence_initial=True,
        )
        with self.assertRaises(AssertionError):
            self.assertContractBlock(
                "The following is prohibited. Write `A1(x/y)` here.",
                "`A1(x/y)`",
                "Write `A1(x/y)` here.",
            )
        # An uninverted reword still fails the structural check.
        with self.assertRaises(AssertionError) as caught:
            self.assertPositiveInstruction(
                "In reports, Write `A1(feature/label)` here.",
                "Write `A1(feature/label)`",
                sentence_initial=True,
            )
        self.assertIn("no longer starts its sentence", str(caught.exception))

    def test_assert_positive_instruction_accepts_the_real_document(self) -> None:
        self.assertPositiveInstruction(
            self.readable_ids_body(), "Write `A1(feature/label)`"
        )

class UniqidRegistryTest(unittest.TestCase):
    """This repository's own `.uniqid/` files obey the rules skills/readable-ids states.

    Dogfooding, and the answer to a finding raised twice: the rules had no enforcement,
    so compliance was something a reviewer confirmed by hand and the next edit could
    silently break. Two violations were in fact introduced by hand while writing these
    very files - a status outside the closed vocabulary, and a file-naming rule that
    contradicted its own date rule - which is the argument for checking rather than
    trusting.

    Scoped to this repository's registries. The skill ships to projects that have their
    own, and nothing here reaches them; what it protects is the example this repository
    sets, which is what a reader copies.
    """

    STATUSES = {"open", "in-progress", "done", "withdrawn"}
    ROW = re.compile(r"^\|(?P<cells>.*)\|\s*$")
    HEADER = "| ID | 읽을 수 있는 표식 | 한 줄 설명 | 상태 |"
    # An unescaped pipe. `\|` is Markdown's literal pipe inside a table cell, so a naive
    # split() saw a legitimate description as an extra column - and, before the row
    # shape was enforced, silently dropped that row and any collision it carried.
    CELL_SPLIT = re.compile(r"(?<!\\)\|")
    FILE_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
    FEATURE = re.compile(r"(?m)^feature: (\S+)$")
    # Anything that *looks* like a feature declaration to a reader. Wider than FEATURE on
    # purpose: `feature:\tshadow` and `feature:<NBSP>shadow` were not counted as second
    # declarations by the strict pattern and so passed silently, while a person reading
    # the file sees two.
    FEATURE_LINE = re.compile(r"(?mi)^\s*feature\s*:")
    # The separator row that opens a Markdown table body. At least one pipe is required:
    # a bare `---` is a thematic break (and a frontmatter fence), and treating one as a
    # table separator made every following paragraph a malformed row.
    SEPARATOR = re.compile(r"^\|?(?:\s*:?-{2,}:?\s*\|)+\s*:?-{2,}:?\s*\|?$|^\|(?:\s*:?-{2,}:?\s*\|)+$")

    def registries(self) -> list[tuple[Path, str]]:
        """Every file under `.uniqid/`, at any depth, with its name checked.

        `glob("*.md")` searched only the top level and only that extension, so a
        registry in a subdirectory - or one saved as `.markdown` - was invisible to
        every check below. Discovery has to be wider than the rules it feeds, or the
        rules are optional to anyone who moves a file.
        """
        directory = ROOT / ".uniqid"
        entries = sorted(directory.rglob("*")) if directory.is_dir() else []
        files = []
        for path in entries:
            relative = path.relative_to(directory).as_posix()
            # is_file() follows a link, so a symlink passed every check below while its
            # target - and the target's rules - lived outside the directory entirely; a
            # broken one vanished from the scan without a word.
            self.assertFalse(path.is_symlink(), f"registry is a symlink: {relative}")
            if path.is_dir():
                self.fail(f"registry not at the top level: {relative}")
            self.assertEqual(relative, path.name, f"registry not at the top level: {relative}")
            self.assertRegex(path.name, self.FILE_NAME)
            files.append(path)
        self.assertTrue(files, "no .uniqid/ registry to check")
        return [(path, path.read_text(encoding="utf-8")) for path in files]

    def feature_of(self, text: str) -> str:
        """The file's one `feature` declaration.

        Exactly one: a second declaration used to be ignored, and since `feature` is
        what makes an identifier resolvable, a file with two of them has no answer to
        which one a rendered form refers to.
        """
        looks_declared = self.FEATURE_LINE.findall(text)
        self.assertEqual(
            len(looks_declared), 1, f"expected one feature declaration, saw {len(looks_declared)}"
        )
        declared = self.FEATURE.findall(text)
        self.assertEqual(len(declared), 1, f"malformed feature declaration: {declared}")
        return declared[0]

    def rows(self, text: str) -> list[list[str]]:
        """Data rows, with every table-shaped line either checked or rejected.

        Structural, not pipe-counting. Deciding "is this a row?" from how many unescaped
        pipes a line holds meant a legitimate `\\|` inside a description dropped the
        count below the threshold and the row vanished - taking its status, its label,
        and any collision it carried. Between the separator and the next blank line,
        every line *is* a row, whatever it looks like.

        A table opens only on a header immediately followed by a separator of the same
        width. Each half was a fail-open on its own: a separator with no header above it
        opened a body out of nowhere, and any pipe line above one was accepted as a
        header, so a data row parked there disappeared from every check.

        Outside a body, no line may carry a pipe at all once inline code is masked -
        escaped or not, ASCII or full-width. `\\|` was excused there, which is how a
        row-shaped line went on slipping past after the plain and full-width spellings
        were closed.
        """
        found = []
        in_body = False
        lines = [line.strip() for line in text.splitlines()]
        for position, stripped in enumerate(lines):
            if not stripped:
                in_body = False                          # a blank line ends the table
                continue

            if not in_body:
                previous = lines[position - 1].strip() if position else ""
                if self.SEPARATOR.match(stripped):
                    self.assertEqual(
                        previous, self.HEADER, f"a separator needs the header above it"
                    )
                    self.assertEqual(
                        stripped.strip("|").count("|") + 1,
                        self.HEADER.strip("|").count("|") + 1,
                        f"separator width does not match the header: {stripped}",
                    )
                    in_body = True
                    continue
                if stripped == self.HEADER:
                    self.assertTrue(
                        position + 1 < len(lines)
                        and self.SEPARATOR.match(lines[position + 1]),
                        "the header needs a separator under it",
                    )
                    continue
                self.assertNotRegex(
                    INLINE_CODE.sub("", stripped),
                    r"[|\uff5c]",
                    f"table row outside a table body: {stripped}",
                )
                continue

            self.assertTrue(
                stripped.startswith("|") and stripped.endswith("|"),
                f"a table row must open and close with an ASCII pipe: {stripped}",
            )
            match = self.ROW.match(stripped)
            self.assertIsNotNone(match, f"malformed table line: {stripped}")
            cells = [cell.strip() for cell in self.CELL_SPLIT.split(match.group("cells"))]
            self.assertEqual(len(cells), 4, f"expected four columns: {stripped}")
            self.assertTrue(cells[0], f"row with no identifier: {stripped}")
            found.append(cells)
        self.assertTrue(found, "registry has no data rows")
        return found

    def test_every_registry_declares_its_feature_and_source_document(self) -> None:
        for path, text in self.registries():
            with self.subTest(registry=path.name):
                self.assertRegex(text, r"(?m)^feature: \S+$")
                self.assertRegex(text, r"(?m)^문서: \S+$")

    def test_every_row_uses_the_closed_status_vocabulary(self) -> None:
        for path, text in self.registries():
            for identifier, _label, _description, status in self.rows(text):
                with self.subTest(registry=path.name, identifier=identifier):
                    self.assertIn(status, self.STATUSES)

    def assertRenderable(self, value: str, what: str) -> None:
        """`value` can be written into a sentence and read back out as one token.

        Three properties, each protecting the lookup the rendered form exists for.

        No `/`, because the slash is what separates `feature` from the label. No
        whitespace, because `A1(리뷰 신뢰 경계/x)` cannot be picked out of prose as one
        token.

        And no invisible character. A zero-width space, a soft hyphen, a bidi mark - all
        category `Cf`, none of which `str.split()` treats as whitespace - lets two labels
        render *identically* to a reader while comparing unequal, which is precisely the
        collision the uniqueness check below exists to prevent. NFC for the neighbouring
        reason: `e` plus a combining acute and a precomposed `é` look the same and are
        different strings, so one canonical spelling is required rather than assumed.
        """
        self.assertTrue(value, f"empty {what}")
        self.assertNotIn("/", value, f"{what} carries the separator: {value!r}")
        self.assertEqual(value.split(), [value], f"{what} carries whitespace: {value!r}")
        hidden = [c for c in value if unicodedata.category(c) in {"Cf", "Cc"}]
        self.assertEqual(hidden, [], f"{what} carries invisible characters: {value!r}")
        self.assertEqual(
            unicodedata.normalize("NFC", value),
            value,
            f"{what} is not NFC-normalised: {value!r}",
        )

    def test_labels_and_features_can_be_rendered_and_read_back(self) -> None:
        for path, text in self.registries():
            feature = self.feature_of(text)
            with self.subTest(registry=path.name, feature=feature):
                self.assertRenderable(feature, "feature")
            for identifier, label, _description, _status in self.rows(text):
                with self.subTest(registry=path.name, identifier=identifier):
                    self.assertRenderable(label, "label")
                    self.assertRenderable(identifier, "identifier")

    def test_no_identifier_or_label_collides_within_a_feature(self) -> None:
        """Across every registry, not within one file.

        The rendered form is `ID(feature/label)`, so `feature` is what makes a short
        identifier resolvable. Two files sharing a feature and an identifier put two
        meanings behind one rendered form, and the reader has no way to tell.
        """
        by_identifier: dict[tuple[str, str], str] = {}
        by_label: dict[tuple[str, str], str] = {}
        for path, text in self.registries():
            feature = self.feature_of(text)
            for identifier, label, _description, _status in self.rows(text):
                for index, seen in ((identifier, by_identifier), (label, by_label)):
                    key = (feature, index)
                    self.assertNotIn(
                        key,
                        seen,
                        f"{feature}/{index} is defined in both {seen.get(key)} "
                        f"and {path.name}",
                    )
                    seen[key] = path.name

if __name__ == "__main__":
    unittest.main()
