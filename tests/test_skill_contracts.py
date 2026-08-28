import json
import re
import tempfile
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
INVERTING_NEGATION = re.compile(
    r"\b(?:do(?:es)?\s+not|don't|never|must\s+not|shall\s+not|no\s+longer|instead\s+of)\b",
    re.IGNORECASE,
)

# Where one sentence ends and the next begins, for the purpose above. Single newlines
# are not boundaries: every SKILL.md in this repository hard-wraps prose, so cutting on
# `\n` would split most sentences in half and hide a negation in the discarded piece.
SENTENCE_BOUNDARY = re.compile(r"(?:\n\s*\n|(?<=[.!?;])[ \n])")


def sentence_containing(text: str, needle: str) -> str:
    """The sentence `needle` sits in, whitespace normalised.

    Scoped to one sentence rather than one paragraph on purpose. A paragraph here
    routinely carries a positive instruction and its exception side by side - "render
    the labels inline and create no registry", "Do not write its registry here" - and a
    paragraph-wide negation check would reject the document for saying both, which is
    exactly what these documents are supposed to say.
    """
    index = text.index(needle)
    starts = [match.end() for match in SENTENCE_BOUNDARY.finditer(text) if match.end() <= index]
    start = starts[-1] if starts else 0
    end_match = SENTENCE_BOUNDARY.search(text, index + len(needle))
    end = end_match.start() if end_match else len(text)
    return " ".join(text[start:end].split())


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

    def assertPositiveInstruction(self, text: str, needle: str) -> None:
        """`needle` is present *and* its sentence has not been inverted.

        assertIn alone proves the words are there, not that they still instruct. Codex
        demonstrated the gap by injecting `Do not Write ...` and `Never invoke
        readable-ids and never render (feature/label).` into these documents: every
        substring assertion stayed green while the contract said the opposite.
        """
        self.assertIn(needle, text)
        sentence = sentence_containing(text, needle)
        negation = INVERTING_NEGATION.search(sentence)
        self.assertIsNone(
            negation,
            f"instruction inverted by {negation.group(0)!r}: {sentence}"
            if negation
            else "",
        )

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

        # Registry shape and the closed status vocabulary (SC-001).
        self.assertPositiveInstruction(skill, ".uniqid/{yyyy-mm-dd}-{slug}.md")
        for status in ("open", "in-progress", "done", "withdrawn"):
            self.assertIn(f"`{status}`", skill)

        # The rendering rule, and the constraint that keeps it readable (SC-002).
        self.assertPositiveInstruction(skill, "Write `A1(feature/label)`")
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
        # Writing the file and committing it are separate permissions; safe-checkpoint
        # grants authority per action and an ordinary task grants none.
        self.assertIn("Committing is a further authority", skill)

        # evidence-first-review may never write, in any mode.
        evidence = self.read("skills/evidence-first-review/SKILL.md")
        self.assertIn("Do not write its registry here", evidence)

        # branch-merge-review may write only outside its read-only rule. Newlines are
        # collapsed first: the sentence is hard-wrapped, so pinning it verbatim would
        # break on a rewrap that changed nothing about the rule.
        branch = " ".join(self.read("skills/branch-merge-review/SKILL.md").split())
        self.assertIn(
            "except under the read-only rule above, which forbids writing any file",
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

        assertPositiveInstruction, not assertIn, because a reversal is the mutation that
        actually happens here: `Never invoke readable-ids and never render
        (feature/label).` satisfies both substrings while instructing the opposite.
        """
        for relative_path in (
            "skills/plan-and-build/SKILL.md",
            "skills/branch-merge-review/SKILL.md",
            "skills/branch-merge-review/references/consolidated-report-template.md",
            "skills/evidence-first-review/SKILL.md",
            "skills/report-output/SKILL.md",
            "skills/safe-checkpoint/references/handoff-template.md",
        ):
            with self.subTest(relative_path=relative_path):
                document = instructional_text(self.read(relative_path))
                self.assertIn("readable-ids", document)
                self.assertPositiveInstruction(document, "(feature/label)")

    def test_the_report_template_carries_the_readable_form_where_a_person_decides(
        self,
    ) -> None:
        """Asserted against the template's fenced block, not the file.

        The block *is* the template - the shape a report actually takes. Against the
        whole file the same strings sitting in an HTML comment, or in the prose that
        explains the convention, would satisfy every assertion while the template itself
        had gone back to bare identifiers. Codex demonstrated exactly that.
        """
        blocks = fenced_blocks(
            self.read("skills/branch-merge-review/references/consolidated-report-template.md")
        )
        self.assertEqual(len(blocks), 1)
        template = blocks[0]

        # The blocking-items line *is* the decision request, and each finding heading is
        # the definition site a later recheck refers back to. Both are entry points a
        # reader reaches without reading forward, so both carry the full form.
        self.assertIn("**Blocking items**: [CH-1(feature/label)", template)
        self.assertIn("### [CH-1(feature/label)]", template)
        self.assertNotIn("**Blocking items**: [CH-1,", template)
        self.assertNotIn("### [CH-1] ", template)

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
            sentence_containing(text, "write `A1(feature/label)`"),
            "Do not write `A1(feature/label)` here.",
        )

    def test_a_blank_line_ends_the_sentence(self) -> None:
        text = "Never do this.\n\nWrite `A1(feature/label)` instead-of-nothing."
        self.assertEqual(
            sentence_containing(text, "Write `A1(feature/label)`"),
            "Write `A1(feature/label)` instead-of-nothing.",
        )

    def test_a_preceding_sentence_negation_is_not_borrowed(self) -> None:
        # The neighbouring sentence is allowed to be negative - these documents pair an
        # instruction with its exception on purpose.
        text = "Do not create the registry. Write `A1(feature/label)` inline."
        self.assertEqual(
            sentence_containing(text, "Write `A1(feature/label)`"),
            "Write `A1(feature/label)` inline.",
        )

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

    def test_assert_positive_instruction_rejects_an_inverted_sentence(self) -> None:
        with self.assertRaises(AssertionError) as caught:
            self.assertPositiveInstruction(
                "Do not write `A1(feature/label)` anywhere.", "write `A1(feature/label)`"
            )
        self.assertIn("inverted", str(caught.exception))

    def test_assert_positive_instruction_accepts_the_real_document(self) -> None:
        self.assertPositiveInstruction(
            self.readable_ids_body(), "Write `A1(feature/label)`"
        )

if __name__ == "__main__":
    unittest.main()
