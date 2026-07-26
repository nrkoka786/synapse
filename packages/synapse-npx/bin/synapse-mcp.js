#!/usr/bin/env node
/**
 * synapse-mcp — npx wrapper for the Synapse MCP server.
 *
 * Lets non-Python developers use Synapse without touching pip:
 *   npx synapse-mcp
 *
 * What this does:
 *   1. Checks Python 3.10+ is installed
 *   2. Checks if synapse-mcp (Python) is installed
 *   3. Installs it via pip if not found
 *   4. Execs synapse-mcp with all CLI args forwarded
 */

"use strict";

const { execSync, spawnSync } = require("child_process");
const path = require("path");

const PYPI_PACKAGE = "synapse-mcp";
const MIN_PYTHON_MAJOR = 3;
const MIN_PYTHON_MINOR = 10;

// ── Helpers ───────────────────────────────────────────────────────────────────

function findPython() {
  for (const cmd of ["python3", "python"]) {
    try {
      const result = execSync(`${cmd} --version 2>&1`, { encoding: "utf8" }).trim();
      const match = result.match(/Python (\d+)\.(\d+)/);
      if (match) {
        const major = parseInt(match[1], 10);
        const minor = parseInt(match[2], 10);
        if (major > MIN_PYTHON_MAJOR || (major === MIN_PYTHON_MAJOR && minor >= MIN_PYTHON_MINOR)) {
          return cmd;
        }
      }
    } catch (_) {}
  }
  return null;
}

function isInstalled(python) {
  try {
    execSync(`${python} -m synapse --version 2>&1`, { encoding: "utf8" });
    return true;
  } catch (_) {
    try {
      execSync(`synapse-mcp --version 2>&1`, { encoding: "utf8" });
      return true;
    } catch (_) {
      return false;
    }
  }
}

function install(python) {
  console.log(`\n📦 Installing ${PYPI_PACKAGE} via pip...\n`);
  const result = spawnSync(python, ["-m", "pip", "install", PYPI_PACKAGE], {
    stdio: "inherit",
    shell: false,
  });
  if (result.status !== 0) {
    console.error(`\n❌ pip install failed. Try manually:\n\n  ${python} -m pip install ${PYPI_PACKAGE}\n`);
    process.exit(1);
  }
}

function runSynapseMcp(python) {
  // Try the installed synapse-mcp command first, then fall back to python -m
  const args = process.argv.slice(2);

  // Attempt 1: synapse-mcp command directly
  let result = spawnSync("synapse-mcp", args, { stdio: "inherit", shell: false });
  if (result.status === null && result.error) {
    // Attempt 2: python -m synapse.mcp.server
    result = spawnSync(python, ["-m", "synapse.mcp.server", ...args], {
      stdio: "inherit",
      shell: false,
    });
  }
  process.exit(result.status ?? 1);
}

// ── Main ──────────────────────────────────────────────────────────────────────

const python = findPython();

if (!python) {
  console.error(`
❌ Python ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+ is required but was not found.

Install Python from: https://www.python.org/downloads/

Then retry:
  npx synapse-mcp
`);
  process.exit(1);
}

if (!isInstalled(python)) {
  install(python);
}

runSynapseMcp(python);
