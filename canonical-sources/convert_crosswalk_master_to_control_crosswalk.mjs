// convert_crosswalk_master_to_control_crosswalk.mjs

import fs from "fs";
import path from "path";

// CLI args:
//   node convert_crosswalk_master_to_control_crosswalk.mjs [inputJson] [outputJson]
const inputPath = process.argv[2] || "crosswalk_80053_master.json";
const outputPath = process.argv[3] || "control_crosswalk.json";

console.log(`Reading master crosswalk from: ${inputPath}`);

const masterRaw = fs.readFileSync(inputPath, "utf8");
const master = JSON.parse(masterRaw);

const frameworkKeyMap = {
  "SOC 2 TSC": "soc2_tsc",
  "ISO 27001:2022": "iso_27001_2022",
  "NIST CSF v2.0": "nist_csf_2_0",
  "PCI DSS v4.0": "pci_dss_4_0",
  "HIPAA (45 CFR)": "hipaa_security",
  "SCF": "scf_controls",
  "NIST 800-171r3": "nist_800_171r3"
};

const nist_800_53_rev5 = {};

for (const [controlId, frameworks] of Object.entries(master.map)) {
  const entry = {};
  for (const [fwLabel, ids] of Object.entries(frameworks)) {
    const key = frameworkKeyMap[fwLabel];
    if (!key) continue; // ignore unknown labels for now
    entry[key] = ids;
  }
  nist_800_53_rev5[controlId] = entry;
}

const controlCrosswalk = {
  mapping_version: `Generated from ${master.master}`,
  framework_catalog: {},          // optional; you can fill this later
  nist_800_53_rev5,
  framework_to_53: {},            // can be auto-built later
  nist_800_171r3_to_53: {},       // can be filled from your overlay
  mapping_sources: [
    `crosswalk_80053_master.json (${master.master})`
  ]
};

fs.writeFileSync(
  outputPath,
  JSON.stringify(controlCrosswalk, null, 2),
  "utf8"
);

console.log(`Wrote control crosswalk JSON to: ${outputPath}`);
