#!/usr/bin/env node
// Compile a Kaitai Struct .ksy to a Python parser using the local JS compiler build.
//   node compile.js <spec.ksy> [outDir]
const fs = require("fs");
const path = require("path");
const yaml = require("js-yaml");
const compiler = require("kaitai-struct-compiler");

const [, , ksyPath, outDir] = process.argv;
if (!ksyPath) {
  console.error("usage: compile.js <spec.ksy> [outDir]");
  process.exit(2);
}
const spec = yaml.load(fs.readFileSync(ksyPath, "utf8"));
const dir = outDir || path.dirname(ksyPath);

compiler
  .compile("python", spec, null, false)
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
