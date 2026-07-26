#!/usr/bin/env node
/**
 * synapse — npx wrapper for the Synapse CLI.
 *
 * Forwards all arguments to the Python synapse CLI:
 *   npx synapse-mcp synapse init C:/Projects/myapp
 *   npx synapse-mcp synapse status
 *   npx synapse-mcp synapse search "error handling"
 */

"use strict";

const { execSync, spawnSync } = require("child_process");

function findPython() {
  for (const cmd of ["python3", "python"]) {
    try {
      const r = execSync(`${cmd} --version 2>&1`, { encoding: "utf8" });
      if (/Python 3\.(1[0-9]|[2-9]\d)/.test(r)) return cmd;
    } catch (_) {}
  }
  return null;
}

const python = findPython();
if (!python) { console.error("Python 3.10+ required."); process.exit(1); }

const args = process.argv.slice(2);
const result = spawnSync(python, ["-m", "synapse.cli", ...args], {
  stdio: "inherit",
  shell: false,
});
process.exit(result.status ?? 1);
