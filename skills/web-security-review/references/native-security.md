# Native Surface Security Reference

**Surface axis.** CLIs, daemons, build scripts, and libraries — anything that runs with the
user's own privileges instead of behind an HTTP boundary. Pair this file with the **language
axis** reference for the runtime (`node-security.md`, …).

The trust model differs from a server: there is no request, no session, and no origin. What
takes their place is the **invocation** — argv, environment, stdin, config files, and whatever
the process reads from disk or the network. A CLI that trusts its arguments completely is
usually fine; one that is invoked *by* something else (a CI job, a git hook, an editor plugin)
has an attacker-reachable boundary its author did not picture.

**Severity if violated** is stated per section.

## Table of Contents
1. [Trust Boundary of the Invocation](#1-trust-boundary-of-the-invocation)
2. [Filesystem](#2-filesystem)
3. [Temporary Files](#3-temporary-files)
4. [Child Processes & IPC](#4-child-processes--ipc)
5. [Privilege](#5-privilege)
6. [Output & Terminal](#6-output--terminal)

---

## 1. Trust Boundary of the Invocation

**Severity if violated**: High

### MUST
- MUST state, in code or comment, which inputs are trusted. A tool run only by a human on their
  own machine and a tool run by CI on a pull request have different boundaries, and the same
  code cannot be judged without knowing which it is.
- MUST treat any file whose path comes from the repository under analysis as untrusted content —
  config files, lockfiles, and manifests included.
- MUST NOT read configuration from the current working directory when the tool may run against
  an untrusted checkout, unless that config's effects are bounded.

A config file that can specify a plugin path, a hook, or a shell command is remote code
execution for anyone who can open a pull request. This is the defect class most often missed
because the config "belongs to the project".

## 2. Filesystem

**Severity if violated**: Critical

### MUST
- MUST resolve any path built from input and verify containment before opening it (see
  `node-security.md` §2 for the resolve-then-contain shape).
- MUST NOT follow symlinks out of the intended root when walking a directory — a repository can
  contain a symlink to `/etc` or to the user's SSH directory.
- MUST create files with explicit, restrictive permissions rather than relying on umask.

```bash
# Symlinks that escape the tree — a finding when the tool walks a checkout
find . -type l -exec sh -c 'case "$(readlink -f "$1")" in "$PWD"/*) ;; *) echo "escapes: $1";; esac' _ {} \;
```

## 3. Temporary Files

**Severity if violated**: High

### MUST
- MUST create temporary files with `mkstemp`-equivalent APIs (`fs.mkdtemp`, `tempfile`), never a
  predictable name in a shared directory — a predictable path in `/tmp` is a symlink-attack
  target.
- MUST NOT write intermediate output into the user's repository. A tool that leaves artefacts in
  the working tree turns a read-only operation into a commit candidate.
- MUST clean up on failure paths, not only on success.

## 4. Child Processes & IPC

**Severity if violated**: Critical

### MUST
- MUST apply the command-execution rules from the language axis reference; nothing about running
  as a CLI makes shell interpolation safe.
- MUST NOT pass secrets as command-line arguments — argv is visible to other processes.
- MUST validate messages received over a socket, pipe, or IPC channel as untrusted input, even
  when the peer is "our own" process.
- MUST bound what a child inherits: close descriptors and scrub the environment when the child
  is less trusted than the parent.

## 5. Privilege

**Severity if violated**: Critical

### MUST
- MUST NOT require elevated privileges for work that does not need them, and MUST drop them
  before touching user-supplied paths when it does.
- MUST NOT write to system-wide locations by default; per-user paths are the default and the
  system path is opt-in.
- MUST NOT re-exec itself through a shell to gain privileges (`sudo sh -c "$cmd"`).

## 6. Output & Terminal

**Severity if violated**: Medium

### MUST
- MUST sanitise untrusted text before printing it to a terminal — ANSI escape sequences can
  rewrite the display, hide text, or in some terminals trigger a response the shell then reads.
- MUST mask secrets in logs and error output, including inside raw command output the tool
  relays.
- MUST NOT echo the full environment on error.

Bidirectional-override characters (U+202E and relatives) in relayed output can make a line read
differently from what it does — the "Trojan Source" class. Replace them rather than printing
them.
