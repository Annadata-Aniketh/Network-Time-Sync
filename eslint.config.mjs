import js from "@eslint/js";
import globals from "globals";

export default [
  { ignores: ["node_modules/**", "tmp/**", "output/**"] },
  {
    ...js.configs.recommended,
    files: ["web/**/*.js"],
    languageOptions: { globals: globals.browser },
  },
  {
    files: ["web/clock-model.js"],
    languageOptions: { globals: { module: "readonly" } },
  },
  {
    ...js.configs.recommended,
    files: ["tests/**/*.cjs"],
    languageOptions: { globals: globals.node, sourceType: "commonjs" },
  },
];
