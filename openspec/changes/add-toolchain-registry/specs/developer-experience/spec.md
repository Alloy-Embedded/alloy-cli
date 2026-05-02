## ADDED Requirements

### Requirement: alloy-cli SHALL document the per-family toolchain manifest format for contributors

The repo SHALL include a `docs/TOOLCHAIN_REGISTRY.md` document
that describes:

- The purpose of `data/families/<id>.yml` and how it differs
  from the canonical device IR.
- The full schema vocabulary (every field in
  `schema/family_toolchain_v1.json`), with at least one example
  value per field.
- The `extends:` resolution rules, with a worked example showing
  how `stm32f4.yml` overlays `arm-cortex-m.yml`.
- The closed enum of `source` strings, what each one means, and
  a contributor-facing rule for when to pick `vendor`.
- A short walkthrough of how to add a new family manifest:
  copy the template, populate fields, run the validator, run
  the doctor smoke test, open a PR.

The doc SHALL link to the JSON Schema and to the cookbook anchor
for `family-toolchain-error`.

#### Scenario: the contributor doc covers every schema field

- **WHEN** the test suite parses `docs/TOOLCHAIN_REGISTRY.md`
  and extracts the documented field names
- **THEN** the documented set SHALL be a superset of the
  required fields in `schema/family_toolchain_v1.json`
- **AND** SHALL include `extends`, `bundles`, `udev_required`,
  and `install_docs`

#### Scenario: a new family manifest is acceptable when the doc walkthrough is followed

- **WHEN** a contributor follows the "add a new family"
  walkthrough end-to-end on a new family id (`samd51` in the
  test fixture)
- **AND** runs the documented validator command
- **THEN** validation SHALL succeed
- **AND** `alloy doctor --for samd51` SHALL render the new
  family's tool list without code changes
