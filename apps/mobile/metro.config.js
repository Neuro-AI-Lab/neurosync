// Learn more: https://docs.expo.dev/guides/monorepos/
const { getDefaultConfig } = require("expo/metro-config");
// metro-config 0.83's package.json "exports" only allows deep imports under
// "private/*"; the CJS build wraps the default export in an ESM interop
// object, so ".default" must be unwrapped explicitly.
const exclusionList = require("metro-config/private/defaults/exclusionList")
  .default;
const path = require("path");

const projectRoot = __dirname;
const workspaceRoot = path.resolve(projectRoot, "../..");

const config = getDefaultConfig(projectRoot);

// 1. Watch all files within the monorepo
config.watchFolders = [workspaceRoot];

// 2. Let Metro resolve packages from both the app and the workspace root
config.resolver.nodeModulesPaths = [
  path.resolve(projectRoot, "node_modules"),
  path.resolve(workspaceRoot, "node_modules"),
];

// 3. Exclude non-code monorepo directories from the crawl. `experiments/`
// hosts per-run artifacts including live postgres unix domain sockets
// (e.g. pgdata_master/.s.PGSQL.5432); Metro's crawler open()s every
// discovered path as a plain file, which throws ENXIO on a socket and
// crashes @expo/cli's uncaughtException handler (rethrows for non
// EMFILE/darwin cases). `backups/` is excluded for the same class of risk
// (arbitrary non-code snapshots). `.git/` is already excluded by
// metro-file-map's built-in VCS_DIRECTORIES pattern, kept here as an
// explicit safety net.
const escapeStringRegexp = (str) =>
  str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

config.resolver.blockList = exclusionList([
  new RegExp(`^${escapeStringRegexp(workspaceRoot)}/experiments/.*$`),
  new RegExp(`^${escapeStringRegexp(workspaceRoot)}/backups/.*$`),
  new RegExp(`^${escapeStringRegexp(workspaceRoot)}/\\.git/.*$`),
]);

module.exports = config;
