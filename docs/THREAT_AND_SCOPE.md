# Execution and evidence boundaries
Generated source is untrusted. The author tool forbids preprocessor/import/assembly constructs, limits source size and invokes a fixed compiler command. It produces freestanding WASM with no imported capabilities and a 2 MiB memory ceiling. Execution uses a separate Node process with a 10-second timeout; compilation has a 90-second timeout.

This is a development boundary, not a hardened multi-tenant compiler service. Do not expose the local compiler endpoint publicly. The hosted static site executes reviewed hash-bound modules shipped in the package. Custom inputs have integer bounds and a 500-row cap.

The provider can propose source and tests; it receives no independent evaluation outcomes. The Python oracle shares the authored specification, so common specification errors remain possible.

Missing dependency identities block reuse. Changed identities require revalidation. An omitted dependency is tested as a negative control. The public context experiment should be read as an authored-manifest experiment, not an arbitrary code-impact analyzer.

Browser exports are editable records, not signed audit evidence or authenticated approval. The local workflow ends awaiting human review. Nothing creates or merges an employer pull request.

No credentials, tenant data, employer source or private architecture are required.

