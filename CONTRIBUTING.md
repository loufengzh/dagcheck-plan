# Contributing

Use Python 3.10 or newer. There are no runtime dependencies.

1. Run `python -m unittest discover -s tests -v` from the repository root.
2. Add regression tests for behavior changes, including input permutations and
   zero-duration tasks when scheduling is affected.
3. Keep JSON schema validation strict; describe any compatibility change.
4. Update the English README and Chinese, Russian, and German translations.
5. Never imply the greedy worker schedule is globally optimal.

Use issues for reproducible bugs and focused proposals. Include a minimal JSON
input, Python version, command, expected output, and actual output. Remove secrets
and proprietary workflow names first. Contributions use the repository's MIT license.
