# Untrusted execution — does the tool run code the diff controls?

Read this before running any analysis tool on a diff you would not execute yourself
(`UNTRUSTED_DIFF=1`, or provenance you cannot vouch for). `SKILL.md` owns the gate decision and the
`READ_ONLY` / `UNTRUSTED_DIFF` export; this file owns the per-tool evidence behind it.

**A second, separate axis: does the tool *execute* the code under review?** Not writing files and
not running attacker-controlled code are different guarantees, and the read-only flags above
only buy the first. Measured in this repository:

**The test is not the config's file format, and it is not "does it name an extension" either.**
A declarative config executes code when it *names* code: `.eslintrc.json` is pure JSON, and
`{"plugins": ["probe"]}` in it loads and runs `eslint-plugin-probe` — reproduced here, as was
the same thing through `extends` in a `.stylelintrc.json`. But naming an extension is not
sufficient either: Biome's `plugins` takes GritQL pattern files, which are a matching DSL, not
host code.

**The question is whether the analysis ends up calling host code or an external executable that
the diff controls.** Answer it by resolving the whole chain before running:

0. **The repository replaces or wraps the tool itself** — this one sits above the others and
   applies no matter which tool you run. Both reproduced here:
   cargo config (`.cargo/config.toml` **or** the extensionless `.cargo/config`, both read) can
   set `build.rustc` / `rustc-wrapper` / `rustc-workspace-wrapper`, a `linker`, a
   `credential-provider`, **or an `[alias]` that shadows the subcommand itself** — `clippy` is
   an *external* subcommand, so `[alias] clippy = "run --bin x"` makes `cargo clippy` build and
   run a binary instead of linting, with no `build.rs` anywhere. (An alias cannot shadow a
   built-in like `check`; both directions verified.) And an `.npmrc` carrying
   `node-options=--require ./hook.js` injects that file into **every** npm-launched tool —
   ESLint, Stylelint, tsc alike — regardless of their own configs.
   The shape to look for is **anything that decides which executable actually runs**, not just
   what that executable then reads.
   Not every ecosystem has this: Go reads `GOFLAGS` only from the environment and the user's
   `GOENV`, never from a file in the repository, and a repository-level `sitecustomize.py` is
   not loaded by ruff or mypy (both verified). The question to ask is always **whether the diff
   can control it**, not whether the mechanism exists.
1. **The config is a program** — `eslint.config.js`, `.stylelintrc.js`, `stylelint.config.mjs`
   or `.ts`, a PHPStan `includes:` entry pointing at a `.php` file (reproduced: it runs).
2. **The config names host code** — `plugins`, `parser`, `processor`, `customSyntax`, an
   `extends` that resolves to a package, mypy's `plugins`, PHPStan's `rules` / `services`.
3. **The manifest loads code behind the tool's back** — cargo runs `build.rs` and proc macros;
   PHPStan loads the composer autoloader, which runs `autoload.files` **from the root package
   and from every dependency** (reproduced). A PHPStan extension shipped by a dependency can be
   activated by `phpstan/extension-installer` with nothing in the root config at all.
4. **Config chains hide all of the above** — `extends` and `includes` are recursive. A clean
   root config that includes a second file proves nothing until you have followed it.
5. **The invocation itself** — flags like PHPStan's `-a/--autoload-file` load code too. Those
   come from whoever runs the review, so they are yours to control; the point is that the
   closure is over *config + manifest + chain + invocation*, not config alone.

| Tool | Calls host code the diff controls? |
|---|---|
| `cargo clippy`, `cargo check` | **Yes**, by two independent routes: a `build.rs` or proc-macro dependency is compiled *and run* (a `build.rs` writing outside the workspace was reproduced on cargo 1.91.0), **and** `.cargo/config.toml` can set `build.rustc` / `build.rustc-wrapper` to any executable, which cargo then calls with no `build.rs` present (also reproduced) |
| ESLint | **Yes** with a flat config, and with any config naming a plugin, parser, processor, or shared-config package |
| Stylelint | **Yes** for a `.js`/`.mjs`/`.cjs`/`.ts` config, and for a JSON or `package.json` config naming `extends`, `plugins`, or `customSyntax` (both reproduced) |
| mypy | **Yes if `[tool.mypy] plugins` is set** |
| PHPStan | **Yes** for `bootstrapFiles`, project `rules`/`services`, a `.php` `includes:` entry, or composer `autoload.files` in the root **or any dependency** — see below |
| Biome | **A weaker yes** — `plugins` loads local GritQL files. That is a pattern DSL, not host code: it can distort what the analysis reports, but it does not execute arbitrary commands. Treat it as a reason to read the plugin, not as a reason to sandbox |
| `ruff` | No — a Rust binary with no plugin mechanism |
| `go vet`, `staticcheck`, `gofmt` | No. Go has no build-time hook, cgo is compiled without running, and `-toolexec` — which *does* call an external program — can only arrive through the environment, which the diff does not control (all verified) |
| `tsc` | No |

So the safe answer is never "the config looks declarative". It is: **the resolved chain — the
repository's tool-level settings, the config, its `extends`/`includes`, the manifest and
lockfile, the autoloader, and the invocation — names no host code and no external executable
that the diff controls.** Anything you have not resolved counts as unresolved, not as safe.

**PHPStan's condition is narrow and worth stating exactly**, because the common case is safe.
Measured on PHPStan 2.x with PHP 8.3, one file per case:

| Setup | Runs the file? |
|---|---|
| `paths:` — the files being analysed | No. Analysis is static parsing |
| `scanFiles:` | No |
| `bootstrapFiles:` in the config | **Yes** |
| project `rules:` / `services:` in the config | **Yes** — a project-defined rule or extension is a class PHPStan instantiates and calls during analysis |
| an `includes:` entry pointing at a `.php` file | **Yes** — PHPStan supports PHP files as dynamic config and executes them (reproduced) |
| `bootstrapFiles:` reached through `includes:` | **Yes** — the chain is recursive, so a clean root config proves nothing (reproduced) |
| `composer.json` → `autoload.files`, root **or any dependency** | **Yes**, with nothing declared in `phpstan.neon`. The composer autoloader runs every entry in `vendor/composer/autoload_files.php`, which includes dependencies' own `autoload.files` (reproduced) |

**On an untrusted diff, do not try to judge the config — a PHPStan config at all is a stop.**
Reading it as text cannot be made sound: NEON's inline forms, an `includes: [inner.neon]` whose
target a line-based collector never reaches, and `\uXXXX` escapes that reconstruct `.php` from
text containing no `.php` each defeat it. Proving a config harmless needs a real NEON parser
over the whole include graph, and the only one at hand is inside PHPStan — which starting
would already run the code in question. So the gate in `references/php-quality.md` §0 stops on
any config, and its text scan only records **why**; a project with no PHPStan config has no
config-driven execution path and still gets analysed.

**The read-only cache question is separate and is not judged at all — it is moved.** The gate
writes an override config outside the workspace that `includes:` the project's own config and
redirects `tmpDir` and `resultCachePath` into a temp directory. Every project setting still
applies, and no spelling of an in-repository cache path can put a file in the repository —
there is nothing to parse and nothing to get wrong.

On your own or your team's branch neither gate fires: without `UNTRUSTED_DIFF` the execution
gate is inert, and outside read-only mode PHPStan runs with the project's own config exactly
as before.

**When the diff is untrusted** — an external contributor's branch, an unfamiliar dependency, any
code you would not run — the executing tools need isolation before they run. A workspace mounted
read-only is **not** enough on its own: the `build.rs` reproduced above wrote to an absolute path
outside the workspace, which a workspace-only restriction does nothing about. The isolation has
to cover the host: every writable path the process can reach, the network, and the environment
(`HOME`, `CARGO_HOME`, `CARGO_TARGET_DIR`, `npm_config_cache`, `GOPATH`) pointed into the
sandbox. Without that, record the check as **`skipped-untrusted-execution`** and say what it
would have taken to run it.

Reviewing your own team's branch is the ordinary case and needs none of this. But "our repo" is
not a standing exemption for what the diff *adds*: a newly introduced build hook, plugin, or
dependency is code that was not there before, and it earns its own look regardless of who wrote
it. The rule exists so the exception is a decision, not an oversight.
