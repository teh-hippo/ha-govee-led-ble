#!/usr/bin/env node
// Compile a Kaitai Struct .ksy to a Python parser using the local JS compiler build.
//   node compile.js <spec.ksy> [outDir]
// Resolves meta.imports by loading "<name>.ksy" from the spec's directory, so
// specs can share provably-common types (see govee_common.ksy).
const fs = require("fs");
const path = require("path");
const yaml = require("js-yaml");
const compiler = require("kaitai-struct-compiler");

const [, , ksyPath, outDir] = process.argv;
if (!ksyPath) {
  console.error("usage: compile.js <spec.ksy> [outDir]");
  process.exit(2);
}
const dir = outDir || path.dirname(ksyPath);
const specDir = path.dirname(path.resolve(ksyPath));
const spec = yaml.load(fs.readFileSync(ksyPath, "utf8"));

const importer = {
  importYaml(name /* , mode */) {
    const p = path.join(specDir, name + ".ksy");
    return Promise.resolve(yaml.load(fs.readFileSync(p, "utf8")));
  },
};

compiler
  .compile("python", spec, importer, false)
  .then((files) => {
    for (const name of Object.keys(files)) {
      fs.writeFileSync(path.join(dir, name), files[name]);
      console.log("wrote", path.join(dir, name));
    }
  })
  .catch((e) => {
    console.error("compile error:", e);
    process.exit(1);
  });
